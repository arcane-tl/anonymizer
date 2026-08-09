"""Anonymizer options window — layout/copy parity with Mac droplet.

Thin wrapper: collects options, invokes anonymize CLI. Target: Windows.
Dark charcoal chrome + app icon matches the Mac ASObjC options panel.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox
except ImportError as _tk_err:  # pragma: no cover
    tk = None  # type: ignore[assignment]
    _TK_IMPORT_ERROR = _tk_err
else:
    _TK_IMPORT_ERROR = None

from anonymizer import __version__
from anonymizer.lists_io import load_lists, save_lists

MODE_LABELS = [
    ("strict", "Remove personal details (recommended)"),
    ("standard", "Remove identity only (keep company names)"),
    ("extract", "Convert to text only (no privacy scrub)"),
]
STYLE_LABELS = [
    ("placeholder", "Replace with tags  [PERSON_1]"),
    ("remove", "Delete text entirely (no tags)"),
]

SUPPORTED = {".pdf", ".docx", ".txt", ".md", ".text", ".markdown"}

# Windows Tk is picky: one pattern per entry (not "a.pdf b.docx" in one string).
_FILETYPES = [
    ("PDF", "*.pdf"),
    ("Word documents", "*.docx"),
    ("Text / Markdown", "*.txt *.md"),
    ("All files", "*.*"),
]

# ── Dark theme (Mac options panel parity) ─────────────────────────
_BG_APP = "#2C2C2E"  # charcoal panel
_BG_WELL = "#1C1C1E"  # files / text wells
_BG_BTN = "#3A3A3C"  # secondary buttons
_BG_BTN_HOVER = "#48484A"
_BORDER = "#3A3A3C"
_TEXT = "#F5F5F7"
_TEXT_MUTED = "#98989D"
_ACCENT = "#0A84FF"  # macOS system blue
_ACCENT_HOVER = "#409CFF"
_TEXT_ON_ACCENT = "#FFFFFF"
_SELECT = "#1E3A5F"

_FONT = ("Segoe UI", 11)
_FONT_BOLD = ("Segoe UI", 12, "bold")
_FONT_TITLE = ("Segoe UI", 16, "bold")
_FONT_SMALL = ("Segoe UI", 10)
_ICON_TITLE_PX = 44


def _log_path() -> Path:
    base = os.environ.get("TEMP") or os.environ.get("TMP") or str(Path.home())
    return Path(base) / "anonymizer-gui.log"


def _log(msg: str) -> None:
    try:
        p = _log_path()
        with p.open("a", encoding="utf-8") as f:
            f.write(msg.rstrip() + "\n")
    except OSError:
        pass


def _message_box(title: str, text: str) -> None:
    """Show an error even when tkinter is broken (Windows MessageBox)."""
    try:
        if tk is not None:
            # Need a root for messagebox sometimes
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(title, text)
            root.destroy()
            return
    except Exception:
        pass
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(0, text, title, 0x10)
            return
        except Exception:
            pass
    print(f"{title}: {text}", file=sys.stderr)


def _app_dir() -> Path:
    """Directory of frozen Anonymizer.exe or this source tree."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _cli_prefix_for_path(path: str | Path) -> list[str]:
    """Build argv prefix for a discovered CLI path.

    Prefer ``python -m anonymizer.cli`` for embeddable runtime (relocatable).
    Wrap ``.cmd`` launchers with ``cmd /c`` so CreateProcess can run them.
    """
    p = Path(path)
    name = p.name.lower()
    if name in {"python.exe", "python", "pythonw.exe"}:
        return [str(p), "-m", "anonymizer.cli"]
    if name.endswith(".cmd") or name.endswith(".bat"):
        return ["cmd", "/c", str(p)]
    return [str(p)]


def _probe_cli_base(base: Path) -> list[str] | None:
    """Look for CLI under an install/stage prefix."""
    if not base:
        return None
    # Embeddable / frozen stage: runtime\python.exe -m anonymizer.cli
    for rel in (
        "runtime/python.exe",
        "runtime/Scripts/python.exe",
        ".venv/Scripts/python.exe",
        ".venv/bin/python",
    ):
        cand = base / rel
        if cand.is_file():
            return _cli_prefix_for_path(cand)
    for rel in (
        "bin/anonymize.cmd",
        "bin/anonymize.exe",
        "runtime/Scripts/anonymize.exe",
        "runtime/Scripts/anonymize",
        ".venv/Scripts/anonymize.exe",
        ".venv/Scripts/anonymize",
        ".venv/bin/anonymize",
    ):
        cand = base / rel
        if cand.is_file():
            return _cli_prefix_for_path(cand)
    return None


def _find_anonymize() -> list[str] | None:
    """Return argv prefix for the anonymize CLI, or None if not found."""
    env = os.environ.get("ANONYMIZER_BIN")
    if env and Path(env).is_file():
        return _cli_prefix_for_path(env)

    # Frozen Setup/portable layout: always prefer runtime next to Anonymizer.exe
    # over PATH (PATH may point at a broken/partial install.ps1 bin).
    if getattr(sys, "frozen", False):
        found = _probe_cli_base(_app_dir()) or _probe_cli_base(_app_dir().parent)
        if found:
            return found

    # Install prefixes (Setup.exe → %LOCALAPPDATA%\Anonymizer, install.ps1 → anonymizer)
    local_app = Path(os.environ.get("LOCALAPPDATA", ""))
    for base in (
        local_app / "Anonymizer",
        local_app / "anonymizer",
        _app_dir(),
        _app_dir().parent,
    ):
        found = _probe_cli_base(base)
        if found:
            return found

    which = shutil.which("anonymize")
    if which:
        return _cli_prefix_for_path(which)

    here = Path(__file__).resolve()
    for root in (here.parents[3], here.parents[2], Path.cwd()):
        found = _probe_cli_base(root)
        if found:
            return found
        for rel in (
            ".venv/Scripts/python.exe",
            ".venv/bin/python",
            ".venv/bin/anonymize",
            ".venv/Scripts/anonymize.exe",
            ".venv/Scripts/anonymize",
            ".venv/Scripts/anonymize.cmd",
        ):
            cand = root / rel
            if cand.is_file():
                return _cli_prefix_for_path(cand)
    return None


def _lists_status(allow: str, deny: str) -> str:
    def count(text: str) -> int:
        n = 0
        for line in text.splitlines():
            s = line.strip()
            if s and not s.startswith("#"):
                n += 1
        return n

    return (
        f"Allowlist {count(allow)}  ·  Denylist {count(deny)}  —  edit with Lists…"
    )


def _filter_paths(paths: list[str] | tuple[str, ...]) -> list[Path]:
    files: list[Path] = []
    for a in paths:
        p = Path(a).expanduser()
        try:
            p = p.resolve()
        except OSError:
            continue
        if p.is_file() and p.suffix.lower() in SUPPORTED:
            files.append(p)
    return files


def resolve_dialog_icon_path() -> Path | None:
    """Locate the dialog/app icon PNG (packaged asset, frozen, or Mac packaging)."""
    candidates: list[Path] = [
        Path(__file__).resolve().parent / "assets" / "Anonymizer-dialog.png",
    ]
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            base = Path(meipass)
            candidates.extend(
                [
                    base / "anonymizer" / "gui" / "assets" / "Anonymizer-dialog.png",
                    base / "assets" / "Anonymizer-dialog.png",
                ]
            )
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir / "assets" / "Anonymizer-dialog.png")
        candidates.append(exe_dir / "Anonymizer-dialog.png")
    # Dev tree: packaging/macos/icons next to repo root
    for parent in Path(__file__).resolve().parents:
        icons = parent / "packaging" / "macos" / "icons"
        candidates.append(icons / "Anonymizer-readme.png")
        candidates.append(icons / "Anonymizer-256.png")
    seen: set[str] = set()
    for cand in candidates:
        try:
            key = str(cand.resolve())
        except OSError:
            key = str(cand)
        if key in seen:
            continue
        seen.add(key)
        if cand.is_file():
            return cand
    return None


def _photo_scaled(
    path: Path, size_px: int, *, master: "tk.Misc | None" = None
) -> "tk.PhotoImage | None":
    """Load PNG and nearest-neighbour scale to ~size_px (Tk PhotoImage)."""
    if tk is None:
        return None
    try:
        kw: dict = {"file": str(path)}
        if master is not None:
            kw["master"] = master
        img = tk.PhotoImage(**kw)
    except (tk.TclError, RuntimeError):
        return None
    w, h = int(img.width()), int(img.height())
    if w <= 0 or h <= 0:
        return img
    # subsample then zoom to get close to size_px
    if w > size_px:
        factor = max(1, round(w / size_px))
        if factor > 1:
            img = img.subsample(factor, factor)
            w, h = int(img.width()), int(img.height())
    if w < size_px and w > 0:
        factor = max(1, size_px // w)
        if factor > 1:
            img = img.zoom(factor, factor)
    return img


def _apply_window_icons(window: "tk.Misc") -> list["tk.PhotoImage"]:
    """Set title-bar/taskbar icon; return PhotoImage refs that must be kept alive."""
    kept: list[tk.PhotoImage] = []
    path = resolve_dialog_icon_path()
    if path is None or tk is None:
        return kept
    # Larger image for taskbar; title-bar uses same when possible
    for px in (64, 32, _ICON_TITLE_PX):
        photo = _photo_scaled(path, px, master=window)
        if photo is not None:
            kept.append(photo)
    if not kept:
        return kept
    try:
        # First image is default; pass all sizes when available
        window.iconphoto(True, *kept)  # type: ignore[attr-defined]
    except tk.TclError:
        try:
            window.iconphoto(True, kept[0])  # type: ignore[attr-defined]
        except tk.TclError:
            pass
    return kept


def _title_icon_image(master: "tk.Misc") -> "tk.PhotoImage | None":
    path = resolve_dialog_icon_path()
    if path is None:
        return None
    return _photo_scaled(path, _ICON_TITLE_PX, master=master)


def _privacy_caption() -> str:
    if sys.platform == "darwin":
        return "Private on this Mac"
    return "Private on this PC"


def _dark_label(
    parent: "tk.Misc",
    text: str,
    *,
    font=_FONT,
    fg: str = _TEXT,
    **pack_kw,
) -> "tk.Label":
    lbl = tk.Label(parent, text=text, bg=_BG_APP, fg=fg, font=font, anchor=tk.W)
    if pack_kw:
        lbl.pack(**pack_kw)
    return lbl


def _section_label(parent: "tk.Misc", text: str) -> "tk.Label":
    return _dark_label(parent, text, font=_FONT_BOLD, pady=(14, 4))


def _dark_radio(
    parent: "tk.Misc",
    text: str,
    *,
    variable: "tk.Variable",
    value: str,
) -> "tk.Radiobutton":
    rb = tk.Radiobutton(
        parent,
        text=text,
        value=value,
        variable=variable,
        bg=_BG_APP,
        fg=_TEXT,
        activebackground=_BG_APP,
        activeforeground=_TEXT,
        selectcolor=_BG_WELL,
        font=_FONT,
        highlightthickness=0,
        bd=0,
        anchor=tk.W,
        cursor="hand2",
    )
    rb.pack(anchor=tk.W, pady=2)
    return rb


def _dark_check(
    parent: "tk.Misc",
    text: str,
    *,
    variable: "tk.BooleanVar",
) -> "tk.Checkbutton":
    cb = tk.Checkbutton(
        parent,
        text=text,
        variable=variable,
        bg=_BG_APP,
        fg=_TEXT,
        activebackground=_BG_APP,
        activeforeground=_TEXT,
        selectcolor=_BG_WELL,
        font=_FONT,
        highlightthickness=0,
        bd=0,
        anchor=tk.W,
        cursor="hand2",
    )
    cb.pack(anchor=tk.W, pady=2)
    return cb


def _chip_button(
    parent: "tk.Misc",
    text: str,
    command,
    *,
    primary: bool = False,
    width: int | None = 11,
) -> "tk.Button":
    """Compact action chip (~Mac 96×32 dialog buttons when width=11)."""
    if primary:
        bg, fg, active = _ACCENT, _TEXT_ON_ACCENT, _ACCENT_HOVER
    else:
        bg, fg, active = _BG_BTN, _TEXT, _BG_BTN_HOVER
    kw: dict = dict(
        text=text,
        command=command,
        bg=bg,
        fg=fg,
        activebackground=active,
        activeforeground=fg,
        disabledforeground=_TEXT_MUTED,
        font=_FONT,  # same size for Cancel / Lists… / Start (Mac HIG-ish)
        relief=tk.FLAT,
        bd=0,
        padx=10,
        pady=4,
        cursor="hand2",
        highlightthickness=0,
    )
    if width is not None:
        kw["width"] = width
    return tk.Button(parent, **kw)


def _pack_title_row(parent: "tk.Misc", title: str, icon_holder: list) -> "tk.Frame":
    """Icon (44px) + title text — Mac addTitleRow parity."""
    row = tk.Frame(parent, bg=_BG_APP)
    row.pack(fill=tk.X, pady=(0, 6))
    # Prefer the toplevel that owns the window for PhotoImage master
    root = parent.winfo_toplevel() if hasattr(parent, "winfo_toplevel") else parent
    photo = _title_icon_image(root)
    if photo is not None:
        icon_holder.append(photo)
        tk.Label(row, image=photo, bg=_BG_APP, bd=0).pack(
            side=tk.LEFT, padx=(0, 12)
        )
    tk.Label(
        row,
        text=title,
        bg=_BG_APP,
        fg=_TEXT,
        font=_FONT_TITLE,
        anchor=tk.W,
    ).pack(side=tk.LEFT, fill=tk.X, expand=True)
    return row


class ListsDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc, allow: str, deny: str) -> None:
        super().__init__(master)
        self.title("Custom lists")
        self.resizable(True, True)
        self.result: tuple[str, str] | None = None
        self.transient(master)
        self.configure(bg=_BG_APP)
        self._icon_refs = _apply_window_icons(self)
        self.grab_set()

        frm = tk.Frame(self, bg=_BG_APP, padx=20, pady=18)
        frm.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            frm,
            text=(
                "One phrase per line. Allowlist is never redacted; "
                "denylist is always redacted. Done saves to "
                "~/.config/anonymizer/config.yaml."
            ),
            bg=_BG_APP,
            fg=_TEXT_MUTED,
            font=_FONT_SMALL,
            wraplength=420,
            justify=tk.LEFT,
            anchor=tk.W,
        ).pack(anchor=tk.W, pady=(0, 12))

        tk.Label(
            frm,
            text="Allowlist — never redact",
            bg=_BG_APP,
            fg=_TEXT,
            font=_FONT_BOLD,
            anchor=tk.W,
        ).pack(anchor=tk.W)
        self.allow_txt = tk.Text(
            frm,
            height=8,
            width=52,
            font=_FONT_SMALL,
            bg=_BG_WELL,
            fg=_TEXT,
            insertbackground=_TEXT,
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground=_BORDER,
            highlightcolor=_ACCENT,
            bd=0,
            padx=8,
            pady=8,
        )
        self.allow_txt.pack(fill=tk.BOTH, expand=True, pady=(4, 12))
        self.allow_txt.insert("1.0", allow)

        tk.Label(
            frm,
            text="Denylist — always redact",
            bg=_BG_APP,
            fg=_TEXT,
            font=_FONT_BOLD,
            anchor=tk.W,
        ).pack(anchor=tk.W)
        self.deny_txt = tk.Text(
            frm,
            height=8,
            width=52,
            font=_FONT_SMALL,
            bg=_BG_WELL,
            fg=_TEXT,
            insertbackground=_TEXT,
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground=_BORDER,
            highlightcolor=_ACCENT,
            bd=0,
            padx=8,
            pady=8,
        )
        self.deny_txt.pack(fill=tk.BOTH, expand=True, pady=(4, 12))
        self.deny_txt.insert("1.0", deny)

        btns = tk.Frame(frm, bg=_BG_APP)
        btns.pack(fill=tk.X)
        _chip_button(btns, "Cancel", self._cancel).pack(side=tk.LEFT)
        _chip_button(btns, "Done", self._done, primary=True).pack(side=tk.RIGHT)

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.wait_window(self)

    def _done(self) -> None:
        self.result = (
            self.allow_txt.get("1.0", "end-1c"),
            self.deny_txt.get("1.0", "end-1c"),
        )
        try:
            save_lists(self.result[0], self.result[1])
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(
                "Anonymizer", f"Could not save lists:\n{exc}", parent=self
            )
            return
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()


class OptionsApp(tk.Tk):
    def __init__(self, files: list[Path]) -> None:
        super().__init__()
        self.files = [p.resolve() for p in files]
        self.title(f"Anonymizer {__version__}")
        self.resizable(False, False)
        self.configure(bg=_BG_APP)
        self._icon_refs: list[tk.PhotoImage] = []
        self._icon_refs.extend(_apply_window_icons(self))
        try:
            self.tk.call("tk", "scaling", 1.25)
        except tk.TclError:
            pass

        allow_lines, deny_lines = load_lists()
        self.allow_text = "\n".join(allow_lines)
        self.deny_text = "\n".join(deny_lines)

        self.mode_var = tk.StringVar(value="strict")
        self.style_var = tk.StringVar(value="placeholder")
        self.review_var = tk.BooleanVar(value=False)
        self.open_var = tk.BooleanVar(value=True)
        self.native_var = tk.BooleanVar(value=False)

        pad = 24
        root = tk.Frame(self, bg=_BG_APP, padx=pad, pady=pad)
        root.pack(fill=tk.BOTH, expand=True)

        _pack_title_row(
            root,
            f"Anonymizer (version {__version__})",
            self._icon_refs,
        )

        n = len(self.files)
        sub = (
            f"{n} document{'s' if n != 1 else ''} ready  ·  "
            f"Saves next to original  ·  {_privacy_caption()}"
        )
        tk.Label(
            root,
            text=sub,
            bg=_BG_APP,
            fg=_TEXT_MUTED,
            font=_FONT_SMALL,
            anchor=tk.W,
        ).pack(anchor=tk.W, pady=(0, 16))

        tk.Label(
            root, text="Files", bg=_BG_APP, fg=_TEXT, font=_FONT_BOLD, anchor=tk.W
        ).pack(anchor=tk.W)
        files_box = tk.Text(
            root,
            height=5,
            width=56,
            font=_FONT_SMALL,
            wrap=tk.WORD,
            bg=_BG_WELL,
            fg=_TEXT,
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground=_BORDER,
            highlightcolor=_BORDER,
            bd=0,
            padx=10,
            pady=8,
        )
        files_box.pack(fill=tk.X, pady=(4, 4))
        files_box.insert("1.0", "\n".join(f"• {p.name}" for p in self.files))
        # Text keeps bg/fg when disabled (no disabledbackground option)
        files_box.configure(state=tk.DISABLED)

        tk.Label(
            root, text="Mode", bg=_BG_APP, fg=_TEXT, font=_FONT_BOLD, anchor=tk.W
        ).pack(anchor=tk.W, pady=(16, 4))
        for val, label in MODE_LABELS:
            _dark_radio(root, label, variable=self.mode_var, value=val)

        tk.Label(
            root,
            text="Output style",
            bg=_BG_APP,
            fg=_TEXT,
            font=_FONT_BOLD,
            anchor=tk.W,
        ).pack(anchor=tk.W, pady=(16, 4))
        for val, label in STYLE_LABELS:
            _dark_radio(root, label, variable=self.style_var, value=val)

        tk.Label(
            root,
            text="Custom lists",
            bg=_BG_APP,
            fg=_TEXT,
            font=_FONT_BOLD,
            anchor=tk.W,
        ).pack(anchor=tk.W, pady=(16, 4))
        self.lists_lbl = tk.Label(
            root,
            text=_lists_status(self.allow_text, self.deny_text),
            bg=_BG_APP,
            fg=_TEXT_MUTED,
            font=_FONT_SMALL,
            anchor=tk.W,
        )
        self.lists_lbl.pack(anchor=tk.W, pady=(0, 10))

        _dark_check(
            root,
            "Review findings before saving (document window)",
            variable=self.review_var,
        )
        _dark_check(root, "Open result when finished", variable=self.open_var)
        _dark_check(
            root,
            "Also save redacted original (PDF/DOCX)",
            variable=self.native_var,
        )

        # Action bar (Mac HIG): Cancel left · Lists… + Start right, compact chips
        bar = tk.Frame(root, bg=_BG_APP)
        bar.pack(fill=tk.X, pady=(28, 0))
        _chip_button(bar, "Cancel", self._on_cancel).pack(side=tk.LEFT)
        right = tk.Frame(bar, bg=_BG_APP)
        right.pack(side=tk.RIGHT)
        _chip_button(right, "Lists…", self._lists).pack(side=tk.LEFT, padx=(0, 10))
        _chip_button(right, "Start", self._start, primary=True).pack(side=tk.LEFT)

        self._busy = False
        # Accept Return only after a short grace period. focus_force + topmost can
        # steal a keypress (e.g. Enter from another app) and looked like the window
        # "closed by itself" because _start() withdraws immediately.
        self._accept_return = False
        self.bind("<Escape>", self._on_escape)
        self.bind("<Return>", self._on_return)
        self.bind("<KP_Enter>", self._on_return)
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

        # Ensure window is on screen (Windows often starts behind). Soft focus:
        # lift/topmost without focus_force so we do not yank keystrokes mid-type.
        self.update_idletasks()
        try:
            w = max(self.winfo_reqwidth(), 480)
            h = max(self.winfo_reqheight(), 400)
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
            x = max(40, (sw - w) // 2)
            y = max(40, (sh - h) // 2)
            self.geometry(f"+{x}+{y}")
        except tk.TclError:
            pass
        self.lift()
        try:
            self.attributes("-topmost", True)
            self.after(400, lambda: self._safe_topmost(False))
        except tk.TclError:
            pass
        # Enable Return → Start only after focus has settled
        self.after(500, self._enable_return_shortcut)
        _log(f"OptionsApp ready files={len(self.files)}")

    def _safe_topmost(self, value: bool) -> None:
        try:
            if self.winfo_exists():
                self.attributes("-topmost", value)
        except tk.TclError:
            pass

    def _enable_return_shortcut(self) -> None:
        self._accept_return = True

    def _on_escape(self, _event=None) -> str:
        _log("OptionsApp Escape → cancel")
        self._on_cancel()
        return "break"

    def _on_return(self, _event=None) -> str | None:
        if not self._accept_return or self._busy:
            _log("OptionsApp Return ignored (grace/busy)")
            return "break"
        _log("OptionsApp Return → start")
        self._start()
        return "break"

    def _on_cancel(self) -> None:
        _log("OptionsApp cancel/close")
        try:
            self.destroy()
        except tk.TclError:
            pass

    def _lists(self) -> None:
        dlg = ListsDialog(self, self.allow_text, self.deny_text)
        if dlg.result is not None:
            self.allow_text, self.deny_text = dlg.result
            self.lists_lbl.configure(
                text=_lists_status(self.allow_text, self.deny_text)
            )

    def _start(self) -> None:
        if self._busy:
            _log("OptionsApp _start ignored (already busy)")
            return
        self._busy = True
        _log("OptionsApp _start begin")
        try:
            self._run_start()
        finally:
            # If window still alive (error paths), allow another try
            try:
                if self.winfo_exists():
                    self._busy = False
            except tk.TclError:
                pass

    def _run_start(self) -> None:
        cli = _find_anonymize()
        if not cli:
            messagebox.showerror(
                "Anonymizer",
                "Could not find the anonymize CLI.\n\n"
                "Install with Anonymizer-Setup.exe or scripts\\install.ps1, "
                "open a new terminal, and try again.\n\n"
                f"Log: {_log_path()}",
                parent=self,
            )
            return

        mode = self.mode_var.get()
        style = self.style_var.get()
        want_review = self.review_var.get() and mode != "extract"
        want_open = self.open_var.get()
        want_native = self.native_var.get() and mode != "extract"

        allow_f = tempfile.NamedTemporaryFile(
            "w", suffix=".txt", delete=False, encoding="utf-8"
        )
        deny_f = tempfile.NamedTemporaryFile(
            "w", suffix=".txt", delete=False, encoding="utf-8"
        )
        try:
            allow_f.write(self.allow_text)
            deny_f.write(self.deny_text)
        finally:
            allow_f.close()
            deny_f.close()

        cfg_path = self._write_temp_config(style, allow_f.name, deny_f.name)
        common_flags = ["--config", str(cfg_path), "--redact-style", style]
        if want_native:
            common_flags.extend(["--format", "both"])

        if want_review:
            cmds = [
                [*cli, mode, str(p), *common_flags, "--review-window"]
                for p in self.files
            ]
            self._run_review_batch(cmds, want_open)
            _log("OptionsApp review batch spawned → destroy")
            self.destroy()
            return

        # Keep the window visible with a working status instead of vanishing
        # (withdraw looked like a crash / auto-close).
        self._set_working(True)
        self.update_idletasks()
        outputs: list[str] = []
        errors: list[str] = []
        try:
            for fpath in self.files:
                cmd = [*cli, mode, str(fpath), *common_flags]
                _log(f"RUN: {cli[0] if cli else '?'} {mode} <file>")
                proc = subprocess.run(cmd, capture_output=True, text=True)
                if proc.returncode != 0:
                    err = (proc.stderr or proc.stdout or "error").strip()
                    errors.append(f"{fpath.name}: {err}")
                    _log(f"FAIL {fpath.name}: exit {proc.returncode}")
                    continue
                outs = _parse_outputs(proc.stdout or "", proc.stderr or "")
                if not outs:
                    outs = _guess_outputs([fpath], mode, want_native)
                outputs.extend(outs)
        finally:
            for p in (allow_f.name, deny_f.name, str(cfg_path)):
                try:
                    Path(p).unlink(missing_ok=True)
                except OSError:
                    pass
            self._set_working(False)

        if errors and not outputs:
            messagebox.showerror(
                "Anonymizer",
                "Something went wrong:\n\n" + "\n\n".join(errors[:3]),
                parent=self,
            )
            return

        if want_open and outputs:
            for out in outputs:
                try:
                    if sys.platform == "darwin":
                        subprocess.run(["open", out], check=False)
                    elif sys.platform == "win32":
                        os.startfile(out)  # type: ignore[attr-defined]
                    else:
                        subprocess.run(["xdg-open", out], check=False)
                except OSError:
                    pass
            _log("OptionsApp done (open results) → destroy")
            self.destroy()
            return

        msg = "Done.\n\n"
        if outputs:
            msg += "Created:\n" + "\n".join(f"• {Path(o).name}" for o in outputs)
        else:
            msg += (
                "Finished. Check next to your original files for .md / native output."
            )
        if errors:
            msg += "\n\nSome files failed:\n" + "\n".join(errors[:5])
        if outputs and messagebox.askyesno(
            "Anonymizer", msg + "\n\nShow in folder?", parent=self
        ):
            folder = str(Path(outputs[0]).parent)
            if sys.platform == "darwin":
                subprocess.run(["open", folder], check=False)
            elif sys.platform == "win32":
                subprocess.run(["explorer", folder], check=False)
            else:
                subprocess.run(["xdg-open", folder], check=False)
        else:
            messagebox.showinfo("Anonymizer", msg, parent=self)
        _log("OptionsApp done → destroy")
        self.destroy()

    def _set_working(self, working: bool) -> None:
        """Show a simple busy state without hiding the whole window."""
        try:
            if not self.winfo_exists():
                return
            if working:
                self.title(f"Anonymizer {__version__} — working…")
                self.configure(cursor="watch")
            else:
                self.title(f"Anonymizer {__version__}")
                self.configure(cursor="")
        except tk.TclError:
            pass

    def _write_temp_config(self, style: str, allow_path: str, deny_path: str) -> Path:
        import yaml

        fd, cfg_name = tempfile.mkstemp(suffix=".yaml", prefix="anonymizer-gui-")
        import os as _os

        _os.close(fd)
        cfg_path = Path(cfg_name)
        allow_lines = [
            ln.strip()
            for ln in Path(allow_path).read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
        deny_lines = [
            ln.strip()
            for ln in Path(deny_path).read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
        data = {
            "redact_style": style,
            "allowlist": allow_lines,
            "denylist": [{"text": t, "entity_type": "ORG"} for t in deny_lines],
        }
        cfg_path.write_text(
            yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        return cfg_path

    def _run_review_batch(self, cmds: list[list[str]], want_open: bool) -> None:
        # No pre-flight dialog (Mac opens review/Terminal directly after Start).
        env = os.environ.copy()
        if want_open:
            env["ANONYMIZER_OPEN"] = "1"
        if sys.platform == "win32":
            parts = [subprocess.list2cmdline(cmd) for cmd in cmds]
            parts.append("echo.")
            parts.append("echo --- Finished. You can close this window. ---")
            script = " & ".join(parts)
            if shutil.which("wt"):
                subprocess.Popen(["wt", "cmd", "/k", script], env=env)
            else:
                subprocess.Popen(
                    ["cmd", "/c", "start", "cmd", "/k", script], env=env
                )
        elif sys.platform == "darwin":
            chain = " ; ".join(" ".join(shlex_quote(c) for c in cmd) for cmd in cmds)
            chain += '; echo; echo "--- Finished. You can close this window. ---"'
            chain_esc = chain.replace("\\", "\\\\").replace('"', '\\"')
            osa = f'tell application "Terminal" to do script "{chain_esc}"'
            subprocess.Popen(["osascript", "-e", osa], env=env)
        else:
            for cmd in cmds:
                subprocess.run(cmd, env=env)


class LauncherApp(tk.Tk):
    """Always-visible first window: pick files or quit (never silent)."""

    def __init__(self) -> None:
        super().__init__()
        self.title(f"Anonymizer {__version__}")
        self.resizable(False, False)
        self.configure(bg=_BG_APP)
        self.chosen: list[Path] = []
        self._icon_refs: list[tk.PhotoImage] = []
        self._icon_refs.extend(_apply_window_icons(self))

        frm = tk.Frame(self, bg=_BG_APP, padx=28, pady=28)
        frm.pack(fill=tk.BOTH, expand=True)

        _pack_title_row(
            frm,
            f"Anonymizer (version {__version__})",
            self._icon_refs,
        )
        tk.Label(
            frm,
            text=(
                "Choose PDF, DOCX, or text documents to anonymize.\n"
                f"Saves next to the original · {_privacy_caption()}"
            ),
            bg=_BG_APP,
            fg=_TEXT_MUTED,
            font=_FONT,
            justify=tk.LEFT,
            anchor=tk.W,
        ).pack(anchor=tk.W, pady=(8, 20))

        _chip_button(frm, "Choose documents…", self._pick, primary=True, width=22).pack(
            fill=tk.X, pady=4
        )
        _chip_button(frm, "Quit", self.destroy, width=22).pack(fill=tk.X, pady=4)

        self.bind("<Escape>", lambda _e: self.destroy())
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.update_idletasks()
        self.lift()
        try:
            self.attributes("-topmost", True)
            self.after(400, lambda: self.attributes("-topmost", False))
        except tk.TclError:
            pass

    def _pick(self) -> None:
        paths = filedialog.askopenfilenames(
            parent=self,
            title="Choose documents to anonymize",
            filetypes=_FILETYPES,
        )
        files = _filter_paths(list(paths) if paths else [])
        if not files:
            if paths:
                messagebox.showwarning(
                    "Anonymizer",
                    "No supported files selected.\n\n"
                    "Supported: PDF, DOCX, TXT, Markdown.",
                    parent=self,
                )
            return
        self.chosen = files
        self.destroy()


def shlex_quote(s: str) -> str:
    if sys.platform == "win32":
        return '"' + s.replace('"', '\\"') + '"'
    import shlex

    return shlex.quote(s)


def _parse_outputs(stdout: str, stderr: str) -> list[str]:
    out: list[str] = []
    for block in (stdout, stderr):
        for line in block.splitlines():
            if line.startswith("OUTPUT:"):
                p = line[7:].strip()
                if p:
                    out.append(p)
    return out


def _guess_outputs(files: list[Path], mode: str, native: bool) -> list[str]:
    paths: list[str] = []
    for f in files:
        if mode == "extract":
            cand = f.with_name(f"{f.stem}.md")
            if cand.resolve() == f.resolve():
                cand = f.with_name(f"{f.stem}.extracted.md")
        else:
            cand = f.with_name(f"{f.stem}.anonymized.md")
        if cand.is_file():
            paths.append(str(cand))
        if native and f.suffix.lower() in {".pdf", ".docx"}:
            n = f.with_name(f"{f.stem}.anonymized{f.suffix.lower()}")
            if n.is_file():
                paths.append(str(n))
    return paths


def main(argv: list[str] | None = None) -> int:
    _log(f"--- anonymize-gui start platform={sys.platform} argv={argv or sys.argv}")
    if tk is None:
        msg = (
            "tkinter is not available in this Python build.\n\n"
            "On Windows, install Python from https://www.python.org/downloads/\n"
            "(include Tcl/Tk), then re-run install.ps1.\n\n"
            f"Import error: {_TK_IMPORT_ERROR}\n"
            f"Log: {_log_path()}"
        )
        _log(msg)
        _message_box("Anonymizer", msg)
        return 2

    try:
        args = list(sys.argv[1:] if argv is None else argv)
        # Strip Windows empty args
        args = [a for a in args if a and a.strip()]
        files = _filter_paths(args)

        if not files:
            launcher = LauncherApp()
            launcher.mainloop()
            files = launcher.chosen
            if not files:
                _log("no files chosen; exit")
                return 0

        app = OptionsApp(files)
        app.mainloop()
        return 0
    except Exception as exc:  # noqa: BLE001
        tb = traceback.format_exc()
        _log(tb)
        _message_box(
            "Anonymizer",
            f"The GUI crashed:\n\n{exc}\n\nDetails written to:\n{_log_path()}",
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
