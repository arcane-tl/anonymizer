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
    from tkinter import filedialog, messagebox, simpledialog, ttk
except ImportError as _tk_err:  # pragma: no cover
    tk = None  # type: ignore[assignment]
    ttk = None  # type: ignore[assignment]
    simpledialog = None  # type: ignore[assignment]
    _TK_IMPORT_ERROR = _tk_err
else:
    _TK_IMPORT_ERROR = None

from anonymizer import __version__
from anonymizer.anonymize.config import load_config
from anonymizer.anonymize.templates import (
    Template,
    default_enabled_ids,
    deny_from_lines,
    discover_templates,
    fork_template,
    lines_from_text,
    load_template_file,
    persist_templates_enabled,
    save_template,
    slugify,
)
from anonymizer.lists_io import default_config_path

MODE_LABELS = [
    ("strict", "Strict - Remove all sensitive data (recommended)"),
    ("standard", "Standard - Remove sensitive personal data"),
    ("extract", "Extract - Keep all the data"),
]
STYLE_LABELS = [
    ("placeholder", "Replace redacted data with stable placeholders"),
    ("remove", "Delete redacted data"),
]
# Output format (CLI --format md|source|both).
FORMAT_LABELS = [
    ("md", "Markdown"),
    ("source", "Source filetype"),
    ("both", "Both (Markdown & source filetype)"),
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


def _templates_status(
    enabled_ids: list[str], all_packs: list[Template] | None = None
) -> str:
    packs = all_packs if all_packs is not None else discover_templates()
    by_id = {t.id: t for t in packs}
    n = len(enabled_ids)
    if n == 0:
        return "No templates selected for this run  —  edit with Templates…"
    names = [by_id[i].display_title() if i in by_id else i for i in enabled_ids[:3]]
    more = f" +{n - 3}" if n > 3 else ""
    return f"{n} template(s): {', '.join(names)}{more}  —  Templates…"


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


def _label_for(choices: list[tuple[str, str]], value: str) -> str:
    for val, label in choices:
        if val == value:
            return label
    return choices[0][1]


def _value_for(choices: list[tuple[str, str]], label: str) -> str:
    for val, lab in choices:
        if lab == label:
            return val
    return choices[0][0]


_DARK_COMBO_STYLE = "Anonymizer.Dark.TCombobox"
_dark_combo_style_ready = False


def _ensure_dark_combobox_style(master: "tk.Misc") -> None:
    """Configure a calm, dark readonly combobox once per process."""
    global _dark_combo_style_ready
    if _dark_combo_style_ready or ttk is None:
        return
    style = ttk.Style(master)
    # "clam" honors fieldbackground / border colors more reliably than vista/xpnative.
    try:
        if style.theme_use() in {"vista", "xpnative", "winnative", "default"}:
            style.theme_use("clam")
    except tk.TclError:
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

    style.configure(
        _DARK_COMBO_STYLE,
        fieldbackground=_BG_WELL,
        background=_BG_BTN,
        foreground=_TEXT,
        arrowcolor=_TEXT,
        bordercolor=_BORDER,
        lightcolor=_BORDER,
        darkcolor=_BORDER,
        insertcolor=_TEXT,
        selectbackground=_SELECT,
        selectforeground=_TEXT,
        padding=(10, 7),
        relief="flat",
        borderwidth=1,
    )
    style.map(
        _DARK_COMBO_STYLE,
        fieldbackground=[
            ("readonly", _BG_WELL),
            ("disabled", _BG_APP),
            ("focus", _BG_WELL),
        ],
        foreground=[
            ("readonly", _TEXT),
            ("disabled", _TEXT_MUTED),
            ("focus", _TEXT),
        ],
        selectbackground=[("readonly", _SELECT), ("focus", _SELECT)],
        selectforeground=[("readonly", _TEXT), ("focus", _TEXT)],
        background=[
            ("active", _BG_BTN_HOVER),
            ("pressed", _BG_BTN_HOVER),
            ("readonly", _BG_BTN),
        ],
        arrowcolor=[("disabled", _TEXT_MUTED), ("readonly", _TEXT)],
        bordercolor=[("focus", _ACCENT), ("readonly", _BORDER)],
        lightcolor=[("focus", _ACCENT), ("readonly", _BORDER)],
        darkcolor=[("focus", _ACCENT), ("readonly", _BORDER)],
    )

    # Dropdown listbox (not fully covered by ttk style maps).
    try:
        master.option_add("*TCombobox*Listbox.background", _BG_WELL)
        master.option_add("*TCombobox*Listbox.foreground", _TEXT)
        master.option_add("*TCombobox*Listbox.selectBackground", _SELECT)
        master.option_add("*TCombobox*Listbox.selectForeground", _TEXT)
        master.option_add("*TCombobox*Listbox.font", _FONT)
        master.option_add("*TCombobox*Listbox.relief", "flat")
        master.option_add("*TCombobox*Listbox.borderWidth", 0)
    except tk.TclError:
        pass
    _dark_combo_style_ready = True


def _dark_popup(
    parent: "tk.Misc",
    variable: "tk.StringVar",
    choices: list[tuple[str, str]],
    *,
    pady: tuple[int, int] = (0, 2),
) -> "ttk.Combobox | tk.OptionMenu":
    """Exclusive dropdown; *variable* holds the CLI value key (not the display label)."""
    labels = [lab for _, lab in choices]
    display = tk.StringVar(value=_label_for(choices, variable.get()))

    def _sync_from_display(*_args: object) -> None:
        variable.set(_value_for(choices, display.get()))

    if ttk is None:
        # Extremely old / broken Tk — fall back to OptionMenu.
        def _on_pick(lab: str) -> None:
            display.set(lab)
            variable.set(_value_for(choices, lab))

        om = tk.OptionMenu(parent, display, *labels, command=_on_pick)
        om.configure(
            bg=_BG_WELL,
            fg=_TEXT,
            activebackground=_BG_BTN_HOVER,
            activeforeground=_TEXT,
            highlightthickness=1,
            highlightbackground=_BORDER,
            font=_FONT,
            anchor=tk.W,
            cursor="hand2",
        )
        om.pack(fill=tk.X, pady=pady)
        return om

    _ensure_dark_combobox_style(parent)
    combo = ttk.Combobox(
        parent,
        textvariable=display,
        values=labels,
        state="readonly",
        style=_DARK_COMBO_STYLE,
        font=_FONT,
        cursor="hand2",
    )
    combo.pack(fill=tk.X, pady=pady)
    combo.bind("<<ComboboxSelected>>", _sync_from_display, add="+")
    # Prevent mouse-wheel from accidentally changing the selection while scrolling.
    combo.bind("<MouseWheel>", lambda _e: "break")
    combo.bind("<Button-4>", lambda _e: "break")
    combo.bind("<Button-5>", lambda _e: "break")
    return combo


def _dark_check(
    parent: "tk.Misc",
    text: str,
    *,
    variable: "tk.BooleanVar",
    pady: tuple[int, int] | int = 2,
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
    cb.pack(anchor=tk.W, pady=pady)
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


class TemplatesDialog(tk.Toplevel):
    """Master–detail: left templates (enable for run), right allow/deny editors."""

    def __init__(self, master: tk.Misc, enabled_ids: list[str]) -> None:
        super().__init__(master)
        self.title("Templates")
        self.resizable(True, True)
        self.geometry("820x520")
        self.minsize(700, 420)
        # Done → list of enabled template ids; Cancel → None
        self.result: list[str] | None = None
        self.transient(master)
        self.configure(bg=_BG_APP)
        self._icon_refs = _apply_window_icons(self)
        self.grab_set()

        self._packs: list[Template] = discover_templates()
        self._enabled: dict[str, tk.BooleanVar] = {}
        for t in self._packs:
            self._enabled[t.id] = tk.BooleanVar(value=(t.id in enabled_ids))
        self._selected_id: str | None = self._packs[0].id if self._packs else None
        self._dirty = False
        self._loading_editor = False
        self._row_frames: dict[str, tk.Frame] = {}

        outer = tk.Frame(self, bg=_BG_APP, padx=16, pady=14)
        outer.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            outer,
            text=(
                "Check packs to use on this run. Select a pack to view or edit "
                "allow (never redact) and deny (always redact). Builtin packs "
                "are read-only — fork to customize."
            ),
            bg=_BG_APP,
            fg=_TEXT_MUTED,
            font=_FONT_SMALL,
            wraplength=780,
            justify=tk.LEFT,
            anchor=tk.W,
        ).pack(anchor=tk.W, pady=(0, 10))

        body = tk.Frame(outer, bg=_BG_APP)
        body.pack(fill=tk.BOTH, expand=True)

        # ── Left: template list ───────────────────────────────────
        left = tk.Frame(body, bg=_BG_APP, width=240)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 12))
        left.pack_propagate(False)
        tk.Label(
            left, text="Templates", bg=_BG_APP, fg=_TEXT, font=_FONT_BOLD, anchor=tk.W
        ).pack(anchor=tk.W, pady=(0, 4))

        list_wrap = tk.Frame(
            left, bg=_BG_WELL, highlightthickness=1, highlightbackground=_BORDER
        )
        list_wrap.pack(fill=tk.BOTH, expand=True)
        self._list_canvas = tk.Canvas(
            list_wrap, bg=_BG_WELL, highlightthickness=0, bd=0
        )
        sb = tk.Scrollbar(list_wrap, orient=tk.VERTICAL, command=self._list_canvas.yview)
        self._list_inner = tk.Frame(self._list_canvas, bg=_BG_WELL)
        self._list_inner.bind(
            "<Configure>",
            lambda _e: self._list_canvas.configure(
                scrollregion=self._list_canvas.bbox("all")
            ),
        )
        self._list_win = self._list_canvas.create_window(
            (0, 0), window=self._list_inner, anchor=tk.NW
        )
        self._list_canvas.configure(yscrollcommand=sb.set)
        self._list_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._list_canvas.bind(
            "<Configure>",
            lambda e: self._list_canvas.itemconfigure(self._list_win, width=e.width),
        )

        left_btns = tk.Frame(left, bg=_BG_APP)
        left_btns.pack(fill=tk.X, pady=(8, 0))
        _chip_button(left_btns, "+ New", self._new_template, width=8).pack(
            side=tk.LEFT, padx=(0, 6)
        )
        _chip_button(left_btns, "Delete", self._delete_template, width=8).pack(
            side=tk.LEFT
        )

        # ── Right: allow / deny ───────────────────────────────────
        right = tk.Frame(body, bg=_BG_APP)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        head = tk.Frame(right, bg=_BG_APP)
        head.pack(fill=tk.X, pady=(0, 6))
        self._title_lbl = tk.Label(
            head, text="", bg=_BG_APP, fg=_TEXT, font=_FONT_BOLD, anchor=tk.W
        )
        self._title_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._badge_lbl = tk.Label(
            head, text="", bg=_BG_APP, fg=_TEXT_MUTED, font=_FONT_SMALL, anchor=tk.E
        )
        self._badge_lbl.pack(side=tk.RIGHT)

        self._desc_lbl = tk.Label(
            right,
            text="",
            bg=_BG_APP,
            fg=_TEXT_MUTED,
            font=_FONT_SMALL,
            wraplength=500,
            justify=tk.LEFT,
            anchor=tk.W,
        )
        self._desc_lbl.pack(anchor=tk.W, pady=(0, 8))

        tk.Label(
            right,
            text="Never redact (allow)",
            bg=_BG_APP,
            fg=_TEXT,
            font=_FONT_BOLD,
            anchor=tk.W,
        ).pack(anchor=tk.W)
        self.allow_txt = tk.Text(
            right,
            height=9,
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
            wrap=tk.WORD,
        )
        self.allow_txt.pack(fill=tk.BOTH, expand=True, pady=(4, 10))
        self.allow_txt.bind("<<Modified>>", self._on_editor_modified)

        tk.Label(
            right,
            text="Always redact (deny)",
            bg=_BG_APP,
            fg=_TEXT,
            font=_FONT_BOLD,
            anchor=tk.W,
        ).pack(anchor=tk.W)
        self.deny_txt = tk.Text(
            right,
            height=7,
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
            wrap=tk.WORD,
        )
        self.deny_txt.pack(fill=tk.BOTH, expand=True, pady=(4, 10))
        self.deny_txt.bind("<<Modified>>", self._on_editor_modified)

        edit_btns = tk.Frame(right, bg=_BG_APP)
        edit_btns.pack(fill=tk.X, pady=(0, 8))
        self._fork_btn = _chip_button(
            edit_btns, "Fork & edit…", self._fork_selected, width=12
        )
        self._fork_btn.pack(side=tk.LEFT, padx=(0, 8))
        self._revert_btn = _chip_button(edit_btns, "Revert", self._revert_editor, width=8)
        self._revert_btn.pack(side=tk.LEFT, padx=(0, 8))
        self._save_btn = _chip_button(
            edit_btns, "Save pack", self._save_pack, primary=True, width=10
        )
        self._save_btn.pack(side=tk.RIGHT)

        foot = tk.Frame(outer, bg=_BG_APP)
        foot.pack(fill=tk.X, pady=(12, 0))
        _chip_button(foot, "Cancel", self._cancel).pack(side=tk.LEFT)
        _chip_button(foot, "Done", self._done, primary=True).pack(side=tk.RIGHT)

        self._rebuild_list()
        if self._selected_id:
            self._load_editor(self._selected_id)

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.wait_window(self)

    def _pack_by_id(self, tid: str) -> Template | None:
        for t in self._packs:
            if t.id == tid:
                return t
        return None

    def _rebuild_list(self) -> None:
        for w in self._list_inner.winfo_children():
            w.destroy()
        self._row_frames.clear()
        for t in self._packs:
            if t.id not in self._enabled:
                self._enabled[t.id] = tk.BooleanVar(value=False)
            row = tk.Frame(self._list_inner, bg=_BG_WELL, cursor="hand2")
            row.pack(fill=tk.X, padx=4, pady=2)
            self._row_frames[t.id] = row
            cb = tk.Checkbutton(
                row,
                variable=self._enabled[t.id],
                bg=_BG_WELL,
                fg=_TEXT,
                activebackground=_BG_WELL,
                activeforeground=_TEXT,
                selectcolor=_BG_APP,
                highlightthickness=0,
                bd=0,
            )
            cb.pack(side=tk.LEFT, padx=(4, 2))
            kind = "builtin" if t.builtin else "user"
            lbl = tk.Label(
                row,
                text=f"{t.display_title()}\n{t.id} · {kind}",
                bg=_BG_WELL,
                fg=_TEXT,
                font=_FONT_SMALL,
                justify=tk.LEFT,
                anchor=tk.W,
            )
            lbl.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4, pady=4)
            for widget in (row, lbl):
                widget.bind("<Button-1>", lambda _e, i=t.id: self._select(i))
            self._paint_row(t.id)
        self._list_inner.update_idletasks()
        self._list_canvas.configure(scrollregion=self._list_canvas.bbox("all"))

    def _paint_row(self, tid: str) -> None:
        fr = self._row_frames.get(tid)
        if not fr:
            return
        bg = _SELECT if tid == self._selected_id else _BG_WELL
        fr.configure(bg=bg)
        for child in fr.winfo_children():
            try:
                child.configure(bg=bg, activebackground=bg)
            except tk.TclError:
                pass

    def _select(self, tid: str) -> None:
        if tid == self._selected_id:
            return
        if self._dirty and not self._confirm_discard():
            return
        prev = self._selected_id
        self._selected_id = tid
        if prev:
            self._paint_row(prev)
        self._paint_row(tid)
        self._load_editor(tid)

    def _confirm_discard(self) -> bool:
        return messagebox.askyesno(
            "Unsaved changes",
            "Discard unsaved edits to this pack?",
            parent=self,
        )

    def _on_editor_modified(self, _event=None) -> None:
        if self._loading_editor:
            for w in (self.allow_txt, self.deny_txt):
                w.edit_modified(False)
            return
        if self.allow_txt.edit_modified() or self.deny_txt.edit_modified():
            self._dirty = True
            for w in (self.allow_txt, self.deny_txt):
                w.edit_modified(False)

    def _load_editor(self, tid: str) -> None:
        t = self._pack_by_id(tid)
        if t is None:
            return
        self._loading_editor = True
        self._title_lbl.configure(text=t.display_title())
        self._badge_lbl.configure(text="builtin" if t.builtin else "user")
        self._desc_lbl.configure(text=(t.description or "").strip())
        self.allow_txt.configure(state=tk.NORMAL)
        self.deny_txt.configure(state=tk.NORMAL)
        self.allow_txt.delete("1.0", tk.END)
        self.deny_txt.delete("1.0", tk.END)
        self.allow_txt.insert("1.0", "\n".join(t.allow))
        self.deny_txt.insert("1.0", "\n".join(d.text for d in t.deny))
        for w in (self.allow_txt, self.deny_txt):
            w.edit_modified(False)
        if t.builtin:
            self.allow_txt.configure(state=tk.DISABLED)
            self.deny_txt.configure(state=tk.DISABLED)
            self._save_btn.configure(state=tk.DISABLED)
            self._revert_btn.configure(state=tk.DISABLED)
            try:
                self._fork_btn.configure(state=tk.NORMAL)
            except tk.TclError:
                pass
        else:
            self.allow_txt.configure(state=tk.NORMAL)
            self.deny_txt.configure(state=tk.NORMAL)
            self._save_btn.configure(state=tk.NORMAL)
            self._revert_btn.configure(state=tk.NORMAL)
            try:
                self._fork_btn.configure(state=tk.DISABLED)
            except tk.TclError:
                pass
        self._dirty = False
        self._loading_editor = False

    def _current_editor_template(self) -> Template | None:
        tid = self._selected_id
        if not tid:
            return None
        base = self._pack_by_id(tid)
        if base is None or base.builtin:
            return base
        allow = lines_from_text(self.allow_txt.get("1.0", "end-1c"))
        deny = deny_from_lines(lines_from_text(self.deny_txt.get("1.0", "end-1c")))
        return Template(
            id=base.id,
            title=base.title,
            description=base.description,
            allow=allow,
            deny=deny,
            builtin=False,
            default=base.default,
            path=base.path,
            languages=list(base.languages),
        )

    def _save_pack(self) -> None:
        t = self._current_editor_template()
        if t is None or t.builtin:
            return
        try:
            path = save_template(t)
            # Reload from disk
            loaded = load_template_file(path, builtin=False)
            self._packs = [loaded if p.id == loaded.id else p for p in self._packs]
            if not any(p.id == loaded.id for p in self._packs):
                self._packs.append(loaded)
            self._packs.sort(key=lambda x: (not x.builtin, x.id))
            self._dirty = False
            self._rebuild_list()
            self._selected_id = loaded.id
            self._load_editor(loaded.id)
            messagebox.showinfo("Anonymizer", f"Saved {path.name}", parent=self)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(
                "Anonymizer", f"Could not save template:\n{exc}", parent=self
            )

    def _revert_editor(self) -> None:
        if self._selected_id:
            self._load_editor(self._selected_id)

    def _fork_selected(self) -> None:
        t = self._pack_by_id(self._selected_id or "")
        if t is None or not t.builtin:
            return
        if self._dirty and not self._confirm_discard():
            return
        forked = fork_template(t)
        try:
            path = save_template(forked)
            loaded = load_template_file(path, builtin=False)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(
                "Anonymizer", f"Could not fork template:\n{exc}", parent=self
            )
            return
        self._packs.append(loaded)
        self._packs.sort(key=lambda x: (not x.builtin, x.id))
        self._enabled[loaded.id] = tk.BooleanVar(value=True)
        self._selected_id = loaded.id
        self._rebuild_list()
        self._load_editor(loaded.id)

    def _new_template(self) -> None:
        if simpledialog is None:
            return
        if self._dirty and not self._confirm_discard():
            return
        name = simpledialog.askstring(
            "New template",
            "Name for the new pack:",
            parent=self,
        )
        if not name or not name.strip():
            return
        tid = slugify(name)
        if any(p.id == tid for p in self._packs):
            messagebox.showerror(
                "Anonymizer", f"A template named “{tid}” already exists.", parent=self
            )
            return
        t = Template(
            id=tid,
            title=name.strip(),
            description="User template",
            builtin=False,
            default=False,
        )
        try:
            path = save_template(t)
            loaded = load_template_file(path, builtin=False)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(
                "Anonymizer", f"Could not create template:\n{exc}", parent=self
            )
            return
        self._packs.append(loaded)
        self._packs.sort(key=lambda x: (not x.builtin, x.id))
        self._enabled[loaded.id] = tk.BooleanVar(value=True)
        self._selected_id = loaded.id
        self._rebuild_list()
        self._load_editor(loaded.id)

    def _delete_template(self) -> None:
        t = self._pack_by_id(self._selected_id or "")
        if t is None:
            return
        if t.builtin:
            messagebox.showinfo(
                "Anonymizer",
                "Builtin packs cannot be deleted. Fork one to customize.",
                parent=self,
            )
            return
        if not messagebox.askyesno(
            "Delete template",
            f"Delete user pack “{t.display_title()}”?\nThis cannot be undone.",
            parent=self,
        ):
            return
        if t.path and t.path.is_file():
            try:
                t.path.unlink()
            except OSError as exc:
                messagebox.showerror(
                    "Anonymizer", f"Could not delete file:\n{exc}", parent=self
                )
                return
        self._packs = [p for p in self._packs if p.id != t.id]
        self._enabled.pop(t.id, None)
        self._selected_id = self._packs[0].id if self._packs else None
        self._dirty = False
        self._rebuild_list()
        if self._selected_id:
            self._load_editor(self._selected_id)

    def _enabled_ids(self) -> list[str]:
        return [t.id for t in self._packs if self._enabled.get(t.id, tk.BooleanVar()).get()]

    def _done(self) -> None:
        if self._dirty:
            if messagebox.askyesno(
                "Unsaved changes",
                "Save edits to the current pack before Done?",
                parent=self,
            ):
                self._save_pack()
            elif not self._confirm_discard():
                return
            else:
                self._dirty = False
        ids = self._enabled_ids()
        try:
            persist_templates_enabled(ids)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(
                "Anonymizer",
                f"Could not save template selection to config:\n{exc}",
                parent=self,
            )
            return
        self.result = ids
        self.destroy()

    def _cancel(self) -> None:
        if self._dirty and not self._confirm_discard():
            return
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

        # Templates enabled for this run (builtin defaults or config)
        packs = discover_templates()
        cfg_enabled: list[str] | None = None
        try:
            cfg_path = default_config_path()
            if cfg_path.is_file():
                cfg_enabled = load_config(cfg_path).templates_enabled
        except Exception:  # noqa: BLE001
            cfg_enabled = None
        if cfg_enabled is not None:
            known = {t.id for t in packs}
            self.enabled_template_ids = [i for i in cfg_enabled if i in known]
        else:
            self.enabled_template_ids = default_enabled_ids(packs)

        self.mode_var = tk.StringVar(value="strict")
        self.style_var = tk.StringVar(value="placeholder")
        self.format_var = tk.StringVar(value="md")
        self.review_var = tk.BooleanVar(value=True)
        self.open_var = tk.BooleanVar(value=True)

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
        _dark_popup(root, self.mode_var, MODE_LABELS)

        tk.Label(
            root,
            text="Output style",
            bg=_BG_APP,
            fg=_TEXT,
            font=_FONT_BOLD,
            anchor=tk.W,
        ).pack(anchor=tk.W, pady=(16, 4))
        _dark_popup(root, self.style_var, STYLE_LABELS)

        tk.Label(
            root,
            text="Output format",
            bg=_BG_APP,
            fg=_TEXT,
            font=_FONT_BOLD,
            anchor=tk.W,
        ).pack(anchor=tk.W, pady=(16, 4))
        _dark_popup(root, self.format_var, FORMAT_LABELS)

        tk.Label(
            root,
            text="Templates",
            bg=_BG_APP,
            fg=_TEXT,
            font=_FONT_BOLD,
            anchor=tk.W,
        ).pack(anchor=tk.W, pady=(16, 4))
        self.templates_lbl = tk.Label(
            root,
            text=_templates_status(self.enabled_template_ids, packs),
            bg=_BG_APP,
            fg=_TEXT_MUTED,
            font=_FONT_SMALL,
            anchor=tk.W,
            wraplength=420,
            justify=tk.LEFT,
        )
        self.templates_lbl.pack(anchor=tk.W, pady=(0, 4))

        # Extra vertical separation: format field vs toggle group
        _dark_check(
            root,
            "Review findings before saving",
            variable=self.review_var,
            pady=(18, 4),
        )
        _dark_check(
            root,
            "Open result when finished",
            variable=self.open_var,
            pady=(2, 2),
        )

        # Action bar: Cancel left · Templates… + Start right
        bar = tk.Frame(root, bg=_BG_APP)
        bar.pack(fill=tk.X, pady=(28, 0))
        _chip_button(bar, "Cancel", self._on_cancel).pack(side=tk.LEFT)
        right = tk.Frame(bar, bg=_BG_APP)
        right.pack(side=tk.RIGHT)
        _chip_button(right, "Templates…", self._templates).pack(
            side=tk.LEFT, padx=(0, 10)
        )
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

    def _templates(self) -> None:
        dlg = TemplatesDialog(self, list(self.enabled_template_ids))
        if dlg.result is not None:
            self.enabled_template_ids = list(dlg.result)
            try:
                self.templates_lbl.configure(
                    text=_templates_status(self.enabled_template_ids)
                )
            except tk.TclError:
                pass

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
        # Extract has no native redaction; force Markdown-only.
        out_fmt = "md" if mode == "extract" else self.format_var.get()
        if out_fmt not in {"md", "source", "both"}:
            out_fmt = "md"
        want_review = self.review_var.get() and mode != "extract"
        want_open = self.open_var.get()

        cfg_path = self._write_temp_config(style, self.enabled_template_ids)
        common_flags = [
            "--config",
            str(cfg_path),
            "--redact-style",
            style,
            "--format",
            out_fmt,
            "--template",
            ",".join(self.enabled_template_ids),
        ]

        if want_review:
            cmds = [
                [*cli, mode, str(p), *common_flags, "--review-window"]
                for p in self.files
            ]
            try:
                self._run_review_batch(cmds, want_open)
            finally:
                try:
                    Path(cfg_path).unlink(missing_ok=True)
                except OSError:
                    pass
            _log("OptionsApp review batch finished → destroy")
            try:
                if self.winfo_exists():
                    self.destroy()
            except tk.TclError:
                pass
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
                    outs = _guess_outputs([fpath], mode, out_fmt)
                outputs.extend(outs)
        finally:
            try:
                Path(cfg_path).unlink(missing_ok=True)
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
                "Finished. Check next to your original files for Markdown "
                "and/or redacted source output."
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

    def _write_temp_config(self, style: str, template_ids: list[str]) -> Path:
        import yaml

        fd, cfg_name = tempfile.mkstemp(suffix=".yaml", prefix="anonymizer-gui-")
        import os as _os

        _os.close(fd)
        cfg_path = Path(cfg_name)
        data = {
            "redact_style": style,
            "templates_enabled": list(template_ids),
        }
        cfg_path.write_text(
            yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        return cfg_path

    def _run_review_batch(self, cmds: list[list[str]], want_open: bool) -> None:
        """Run CLI with --review-window; wait for each job and surface errors.

        Windows: do **not** fire-and-forget a Terminal ``cmd /k … & echo Finished``
        chain (that prints Finished even when review never stayed open). Wait on
        the CLI process so the Tk review window can take focus; optional progress
        console via CREATE_NEW_CONSOLE.
        """
        env = os.environ.copy()
        if want_open:
            env["ANONYMIZER_OPEN"] = "1"

        if sys.platform == "darwin":
            chain = " ; ".join(" ".join(shlex_quote(c) for c in cmd) for cmd in cmds)
            chain += '; echo; echo "--- Finished. You can close this window. ---"'
            chain_esc = chain.replace("\\", "\\\\").replace('"', '\\"')
            osa = f'tell application "Terminal" to do script "{chain_esc}"'
            subprocess.Popen(["osascript", "-e", osa], env=env)
            return

        # Windows / Linux: wait for CLI (review window is interactive).
        errors: list[str] = []
        cancelled = 0
        try:
            self.withdraw()
        except tk.TclError:
            pass

        for cmd in cmds:
            _log(f"REVIEW RUN: {cmd[0] if cmd else '?'} …")
            try:
                if sys.platform == "win32":
                    # New console for progress; process is waited so review can block.
                    creationflags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
                    proc = subprocess.run(
                        cmd,
                        env=env,
                        creationflags=creationflags,
                    )
                else:
                    proc = subprocess.run(cmd, env=env)
            except OSError as exc:
                errors.append(str(exc))
                _log(f"REVIEW FAIL spawn: {exc}")
                continue

            code = int(proc.returncode or 0)
            if code == 0:
                _log("REVIEW ok")
                continue
            if code == 130:
                cancelled += 1
                _log("REVIEW cancelled (130)")
                continue
            errors.append(f"exit {code}")
            _log(f"REVIEW FAIL exit={code}")

        try:
            if self.winfo_exists():
                self.deiconify()
                self.lift()
        except tk.TclError:
            pass

        if errors and not cancelled:
            messagebox.showerror(
                "Anonymizer",
                "Review / anonymize failed:\n\n"
                + "\n".join(errors[:5])
                + f"\n\nLog: {_log_path()}",
                parent=self if self.winfo_exists() else None,
            )
        elif cancelled and not errors:
            messagebox.showinfo(
                "Anonymizer",
                "Review cancelled — no output written for cancelled file(s).",
                parent=self if self.winfo_exists() else None,
            )
        elif not errors:
            messagebox.showinfo(
                "Anonymizer",
                "Done. Outputs are next to your original files "
                "(Markdown and/or source, per your format choice).",
                parent=self if self.winfo_exists() else None,
            )


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


def _guess_outputs(
    files: list[Path],
    mode: str,
    output_format: str = "md",
) -> list[str]:
    """Best-effort paths when CLI OUTPUT: lines are missing."""
    fmt = "md" if mode == "extract" else (output_format or "md")
    write_md = fmt in ("md", "both")
    write_native = fmt in ("source", "both") and mode != "extract"
    paths: list[str] = []
    for f in files:
        if write_md:
            if mode == "extract":
                cand = f.with_name(f"{f.stem}.md")
                if cand.resolve() == f.resolve():
                    cand = f.with_name(f"{f.stem}.extracted.md")
            else:
                cand = f.with_name(f"{f.stem}.anonymized.md")
            if cand.is_file():
                paths.append(str(cand))
        if write_native and f.suffix.lower() in {".pdf", ".docx"}:
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
