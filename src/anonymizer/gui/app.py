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
    from tkinter import filedialog, messagebox, ttk
except ImportError as _tk_err:  # pragma: no cover
    tk = None  # type: ignore[assignment]
    ttk = None  # type: ignore[assignment]
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
    ("Text", "*.txt"),
    ("Markdown", "*.md"),
    ("All files", "*.*"),
]

# ── Dark theme ────────────────────────────────────────────────────
# macOS: match native NSPanel (windowBackgroundColor / controlAccent).
# Windows: slightly elevated charcoal (OptionsApp chrome).
if sys.platform == "darwin":
    _BG_APP = "#1E1E1E"  # AppKit windowBackgroundColor (Dark)
    _BG_WELL = "#282828"  # underPage / elevated field
    _BG_BTN = "#3A3A3C"
    _BG_BTN_HOVER = "#48484A"
    _BORDER = "#3A3A3C"
    _TEXT = "#FFFFFF"
    _TEXT_MUTED = "#98989D"
    _ACCENT = "#007AFF"  # controlAccent
    _ACCENT_HOVER = "#409CFF"
    _TEXT_ON_ACCENT = "#FFFFFF"
    _SELECT = "#0059D1"  # selectedContentBackground approx
else:
    _BG_APP = "#2C2C2E"
    _BG_WELL = "#1C1C1E"
    _BG_BTN = "#3A3A3C"
    _BG_BTN_HOVER = "#48484A"
    _BORDER = "#3A3A3C"
    _TEXT = "#F5F5F7"
    _TEXT_MUTED = "#98989D"
    _ACCENT = "#0A84FF"
    _ACCENT_HOVER = "#409CFF"
    _TEXT_ON_ACCENT = "#FFFFFF"
    _SELECT = "#1E3A5F"

# Platform fonts: Segoe on Windows; system UI on macOS (matches NSPanel).
if sys.platform == "darwin":
    _FONT = (".AppleSystemUIFont", 13)
    _FONT_BOLD = (".AppleSystemUIFont", 13, "bold")
    _FONT_TITLE = (".AppleSystemUIFont", 17, "bold")
    _FONT_SMALL = (".AppleSystemUIFont", 12)
else:
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
            f.flush()
    except OSError:
        pass
    # Mirror to console when present (dev / run-gui-dev.ps1)
    try:
        print(f"[anonymizer-gui] {msg}", file=sys.stderr, flush=True)
    except Exception:  # noqa: BLE001
        pass


def _gui_debug_enabled() -> bool:
    v = (os.environ.get("ANONYMIZER_GUI_DEBUG") or "").strip().lower()
    return v in {"1", "true", "yes", "on"}


def _debug_box(text: str) -> None:
    """Optional step MessageBox when ANONYMIZER_GUI_DEBUG=1."""
    if not _gui_debug_enabled():
        return
    _log(f"DEBUG BOX: {text}")
    try:
        if tk is not None:
            messagebox.showinfo("Anonymizer debug", text)
            return
    except Exception:  # noqa: BLE001
        pass
    _message_box("Anonymizer debug", text)


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
    """Return argv prefix for the anonymize CLI, or None if not found.

    Non-frozen (dev): prefer ``sys.executable -m anonymizer.cli`` so Start uses
    the same package tree as the GUI (via PYTHONPATH). Preferring the Setup
    install first caused exit 2 when an older install lacked ``--template``.
    """
    env = os.environ.get("ANONYMIZER_BIN")
    if env and Path(env).is_file():
        return _cli_prefix_for_path(env)

    # Frozen Setup/portable layout: always prefer runtime next to Anonymizer.exe
    # over PATH (PATH may point at a broken/partial install.ps1 bin).
    if getattr(sys, "frozen", False):
        found = _probe_cli_base(_app_dir()) or _probe_cli_base(_app_dir().parent)
        if found:
            return found
        return None

    # Dev / python -m anonymizer.gui: same interpreter + code as this process.
    exe = Path(sys.executable)
    if exe.is_file():
        try:
            import anonymizer.cli  # noqa: F401

            prefix = [str(exe), "-m", "anonymizer.cli"]
            _log(f"_find_anonymize: using GUI interpreter {prefix!r}")
            return prefix
        except Exception as exc:  # noqa: BLE001
            _log(f"_find_anonymize: sys.executable cannot import anonymizer.cli: {exc}")

    # Worktree / repo layout near this source file
    here = Path(__file__).resolve()
    for root in (here.parents[3], here.parents[2], Path.cwd()):
        found = _probe_cli_base(root)
        if found:
            _log(f"_find_anonymize: repo probe {found!r}")
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

    which = shutil.which("anonymize")
    if which:
        _log(f"_find_anonymize: PATH anonymize {which!r}")
        return _cli_prefix_for_path(which)

    # Last resort: installed Setup (may lag feature flags vs this GUI)
    local_app = Path(os.environ.get("LOCALAPPDATA", ""))
    for base in (local_app / "Anonymizer", local_app / "anonymizer"):
        found = _probe_cli_base(base)
        if found:
            _log(f"_find_anonymize: fallback install {found!r}")
            return found
    return None


def _templates_status(
    enabled_ids: list[str], all_packs: list[Template] | None = None
) -> str:
    """Active-templates status line (Mac templatesStatusLine spirit).

    Empty → "No templates selected". Otherwise comma-separated display titles
    (ids as fallback). No count prefix or "— Templates…" suffix.
    """
    packs = all_packs if all_packs is not None else discover_templates()
    by_id = {t.id: t for t in packs}
    if not enabled_ids:
        return "No templates selected"
    names = [by_id[i].display_title() if i in by_id else i for i in enabled_ids]
    return ", ".join(names)


def _files_list_column_count(n_files: int) -> int:
    """1 column for a single file; 2 columns when multiple (Mac parity)."""
    return 2 if n_files > 1 else 1


def _files_list_row_count(n_files: int) -> int:
    if n_files <= 0:
        return 1
    cols = _files_list_column_count(n_files)
    return (n_files + cols - 1) // cols


def _files_list_height_px(n_files: int, *, row_h: int = 22, pad: int = 12) -> int:
    """Dynamic files-well height from content; capped like Mac (~max rows)."""
    rows = _files_list_row_count(n_files)
    rows = max(1, min(rows, 8))
    return rows * row_h + pad


def _pack_files_list(parent: "tk.Misc", files: list[Path], *, width_px: int = 420) -> "tk.Frame":
    """File names as bullets; 2 columns when multiple (Mac makeFilesListWell).

    Window-colored, no border — not a sunk text well.
    """
    n = len(files)
    cols = _files_list_column_count(n)
    h = _files_list_height_px(n, pad=8)
    wrap = tk.Frame(
        parent,
        bg=_BG_APP,
        highlightthickness=0,
        height=h,
    )
    wrap.pack(fill=tk.X, pady=(4, 4))
    wrap.pack_propagate(False)
    inner = tk.Frame(wrap, bg=_BG_APP)
    inner.pack(fill=tk.BOTH, expand=True, padx=0, pady=2)
    for c in range(cols):
        inner.columnconfigure(c, weight=1, uniform="files")
    col_w = max(80, (width_px - 12) // cols)
    names = [p.name for p in files]
    max_name = 34 if cols == 1 else 28
    for i, name in enumerate(names):
        if cols == 1:
            r, c = i, 0
        else:
            r, c = i // cols, i % cols
        # Truncate long basenames for display
        display = name
        if len(display) > max_name:
            stem, _, ext = display.rpartition(".")
            if stem and ext and len(ext) <= 5:
                keep = max_name - 2 - len(ext)
                display = (
                    (stem[: max(8, keep)] + "…" + "." + ext)
                    if keep > 0
                    else display[: max_name - 1] + "…"
                )
            else:
                display = display[: max_name - 1] + "…"
        tk.Label(
            inner,
            text=f"• {display}",
            bg=_BG_APP,
            fg=_TEXT,
            font=_FONT_SMALL,
            anchor=tk.W,
            justify=tk.LEFT,
            width=max(12, col_w // 7),
        ).grid(row=r, column=c, sticky="ew", padx=(0, 12), pady=1)
    return wrap


def _coerce_path_args(paths: object) -> list[str]:
    """Normalize filedialog / argv results to a list of path strings.

    Windows ``askopenfilenames`` usually returns a tuple, but a single selection
    can occasionally arrive as a bare string. Iterating a string yields
    characters and silently drops every file — treat str/Path as one path.
    """
    if paths is None:
        return []
    if isinstance(paths, (str, Path)):
        s = str(paths).strip()
        return [s] if s else []
    try:
        seq = list(paths)  # type: ignore[arg-type]
    except TypeError:
        s = str(paths).strip()
        return [s] if s else []
    out: list[str] = []
    for item in seq:
        if item is None:
            continue
        s = str(item).strip()
        if s:
            out.append(s)
    return out


def _filter_paths(paths: object) -> list[Path]:
    files: list[Path] = []
    for a in _coerce_path_args(paths):
        p = Path(a).expanduser()
        try:
            p = p.resolve()
        except OSError:
            continue
        if p.is_file() and p.suffix.lower() in SUPPORTED:
            files.append(p)
    return files


def _merge_paths(existing: list[Path], added: list[Path]) -> list[Path]:
    """Append *added* paths, skipping duplicates (by resolve())."""
    seen = {p.resolve() for p in existing}
    out = list(existing)
    for p in added:
        try:
            key = p.resolve()
        except OSError:
            key = p
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def _truncate_path_display(path: Path | str, max_len: int = 48) -> str:
    s = str(path)
    if len(s) <= max_len:
        return s
    return "…" + s[-(max_len - 1) :]


def _icon_chip(
    parent: "tk.Misc",
    glyph: str,
    command,
    *,
    tooltip: str = "",
    chrome: str | None = None,
) -> "tk.Frame":
    """Small square + / − control for the Files toolbar."""
    chrome_bg = chrome if chrome is not None else _BG_APP
    size = 28
    wrap = tk.Frame(parent, bg=chrome_bg, width=size, height=size, cursor="hand2")
    wrap.pack_propagate(False)
    cv = tk.Canvas(
        wrap,
        width=size,
        height=size,
        bg=chrome_bg,
        highlightthickness=0,
        bd=0,
        cursor="hand2",
    )
    cv.pack(fill=tk.BOTH, expand=True)

    def _paint(*, hover: bool = False) -> None:
        fill = _BG_BTN_HOVER if hover else _BG_BTN
        cv.delete("all")
        _round_rect(cv, 1, 1, size - 2, size - 2, 7, fill=fill, outline=_BORDER, width=1)
        cv.create_text(
            size // 2,
            size // 2,
            text=glyph,
            fill=_TEXT,
            font=_FONT_BOLD,
        )

    def _run(_e=None) -> None:
        if command is not None:
            command()

    _paint()
    cv.bind("<Button-1>", _run)
    wrap.bind("<Button-1>", _run)
    cv.bind("<Enter>", lambda _e: _paint(hover=True))
    cv.bind("<Leave>", lambda _e: _paint(hover=False))
    if tooltip:
        _attach_simple_tooltip(wrap, tooltip)
        _attach_simple_tooltip(cv, tooltip)
    return wrap


def _attach_simple_tooltip(widget: "tk.Misc", text: str) -> None:
    """Solid rectangular tip (reliable on Windows and macOS Tk)."""
    state: dict[str, object] = {"after": None, "tip": None}

    def _hide(_event=None) -> None:
        job = state.get("after")
        if job is not None:
            try:
                widget.after_cancel(job)  # type: ignore[arg-type]
            except tk.TclError:
                pass
            state["after"] = None
        tip = state.get("tip")
        if tip is not None:
            try:
                tip.destroy()  # type: ignore[union-attr]
            except tk.TclError:
                pass
            state["tip"] = None

    def _show() -> None:
        state["after"] = None
        if not text.strip():
            return
        try:
            if not widget.winfo_exists():
                return
        except tk.TclError:
            return
        _hide()
        tip = tk.Toplevel(widget)
        tip.wm_overrideredirect(True)
        try:
            tip.wm_attributes("-topmost", True)
        except tk.TclError:
            pass
        tip.configure(bg=_BORDER)
        lbl = tk.Label(
            tip,
            text=text,
            bg=_BG_WELL,
            fg=_TEXT,
            font=_FONT_SMALL,
            padx=10,
            pady=5,
            justify=tk.LEFT,
        )
        lbl.pack(padx=1, pady=1)
        tip.update_idletasks()
        x = widget.winfo_rootx() + 8
        y = widget.winfo_rooty() + widget.winfo_height() + 4
        tip.geometry(f"+{x}+{y}")
        state["tip"] = tip

    def _schedule(_event=None) -> None:
        _hide()
        try:
            state["after"] = widget.after(350, _show)
        except tk.TclError:
            pass

    widget.bind("<Enter>", _schedule, add="+")
    widget.bind("<Leave>", _hide, add="+")
    widget.bind("<ButtonPress>", _hide, add="+")


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


def _round_rect(canvas: "tk.Canvas", x1: int, y1: int, x2: int, y2: int, r: int, **kwargs):
    """Draw a rounded rectangle on a canvas (macOS-safe solid fills)."""
    r = max(0, min(r, (x2 - x1) // 2, (y2 - y1) // 2))
    points = [
        x1 + r, y1,
        x2 - r, y1,
        x2, y1,
        x2, y1 + r,
        x2, y2 - r,
        x2, y2,
        x2 - r, y2,
        x1 + r, y2,
        x1, y2,
        x1, y2 - r,
        x1, y1 + r,
        x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


def _chip_button(
    parent: "tk.Misc",
    text: str,
    command,
    *,
    primary: bool = False,
    width: int | None = 11,
    chrome: str | None = None,
    fill_x: bool = False,
) -> "tk.Frame":
    """Rounded pill button drawn on canvas.

    Aqua ignores ``tk.Button`` bg/fg; canvas fills match OptionsApp chrome on
    both macOS and Windows. Supports ``.configure(state=...)`` for enable/disable.

    *fill_x*: stretch the pill to the full width of the parent (launcher buttons).
    """
    chrome_bg = chrome if chrome is not None else _BG_APP
    fill_idle = _ACCENT if primary else _BG_BTN
    fill_hover = _ACCENT_HOVER if primary else _BG_BTN_HOVER
    fill_disabled = _BG_WELL if primary else _BG_WELL
    fg_idle = _TEXT_ON_ACCENT if primary else _TEXT
    fg_disabled = _TEXT_MUTED
    outline = _ACCENT if primary else _BORDER
    font = _FONT_BOLD if primary else _FONT
    pad_x, pad_y, radius = 14, 7, 8

    probe = tk.Label(parent, text=text, font=font)
    try:
        probe.update_idletasks()
        tw, th = probe.winfo_reqwidth(), probe.winfo_reqheight()
    finally:
        probe.destroy()
    # Optional min width in "character cells" (parity with old tk.Button width=)
    min_w = 0
    if width is not None and not fill_x:
        probe2 = tk.Label(parent, text="0" * max(1, width), font=font)
        try:
            probe2.update_idletasks()
            min_w = probe2.winfo_reqwidth() + pad_x
        finally:
            probe2.destroy()
    size = {
        "bw": max(tw + pad_x * 2, min_w, 72),
        "bh": max(th + pad_y * 2, 32),
    }

    wrap = tk.Frame(
        parent, bg=chrome_bg, width=size["bw"], height=size["bh"], cursor="hand2"
    )
    wrap.pack_propagate(False)
    canvas = tk.Canvas(
        wrap,
        width=size["bw"],
        height=size["bh"],
        bg=chrome_bg,
        highlightthickness=0,
        bd=0,
        cursor="hand2",
    )
    canvas.pack(fill=tk.BOTH, expand=True)

    state: dict = {"enabled": True, "hover": False}

    def _paint() -> None:
        enabled = state["enabled"]
        hover = state["hover"] and enabled
        bw, bh = size["bw"], size["bh"]
        if not enabled:
            fill, fg = fill_disabled, fg_disabled
            ol = _BORDER
        elif hover:
            fill, fg, ol = fill_hover, fg_idle, outline
        else:
            fill, fg, ol = fill_idle, fg_idle, outline
        canvas.delete("all")
        _round_rect(
            canvas, 1, 1, max(bw - 2, 2), max(bh - 2, 2), radius,
            fill=fill, outline=ol, width=1,
        )
        canvas.create_text(bw // 2, bh // 2, text=text, fill=fg, font=font)

    def _run(_e=None) -> None:
        if state["enabled"] and command is not None:
            command()

    def _configure(cnf=None, **kw):  # type: ignore[no-untyped-def]
        if isinstance(cnf, dict):
            kw = {**cnf, **kw}
        elif cnf is not None and not kw:
            # cnf as single option name → Frame.configure
            return tk.Frame.configure(wrap, cnf)
        if "state" in kw:
            st = kw.pop("state")
            state["enabled"] = st not in (tk.DISABLED, "disabled", 0, "0")
            wrap.configure(cursor="hand2" if state["enabled"] else "arrow")
            canvas.configure(cursor="hand2" if state["enabled"] else "arrow")
            _paint()
        if kw:
            return tk.Frame.configure(wrap, **kw)
        return None

    wrap.configure = _configure  # type: ignore[method-assign]
    wrap.config = _configure  # type: ignore[method-assign]

    if fill_x:
        def _on_configure(event) -> None:  # type: ignore[no-untyped-def]
            # Use allocated width from pack(fill=X); ignore height noise
            nw = int(event.width)
            if nw < 40 or nw == size["bw"]:
                return
            size["bw"] = nw
            wrap.configure(width=nw, height=size["bh"])
            canvas.configure(width=nw, height=size["bh"])
            _paint()

        wrap.bind("<Configure>", _on_configure)

    _paint()
    canvas.bind("<Button-1>", _run)
    canvas.bind("<Enter>", lambda _e: state.update(hover=True) or _paint())
    canvas.bind("<Leave>", lambda _e: state.update(hover=False) or _paint())
    wrap.bind("<Button-1>", _run)
    return wrap


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


def _raise_toplevel(win: "tk.Misc") -> None:
    """Bring a Tk window to the front (sticky topmost; activate on macOS)."""
    try:
        win.update_idletasks()
        win.deiconify()
        win.lift()
        win.focus_force()
        win.attributes("-topmost", True)
    except tk.TclError:
        pass
    if sys.platform == "darwin":
        # Separate process (templates-ui via do shell script) must steal focus
        # from the Anonymizer NSPanel app or it stays buried.
        try:
            pid = os.getpid()
            subprocess.run(
                [
                    "osascript",
                    "-e",
                    f'tell application "System Events" to set frontmost of '
                    f"first process whose unix id is {pid} to true",
                ],
                check=False,
                capture_output=True,
                timeout=3,
            )
        except Exception:  # noqa: BLE001
            pass


class TemplatesDialog(tk.Toplevel):
    """Two-step Templates UI matching Mac AppKit flow.

    A) Enable list: checkbox + row actions (edit / duplicate / trash),
       footer ``+ New`` left · ``Cancel`` + ``Done`` right.
    B) Edit pack: click title/description in place; allow/deny lists;
       Save/Cancel (user) or Close (builtin); returns to enable list.

    Done persists ``templates_enabled``; Cancel discards enablement changes.
    """

    def __init__(
        self,
        master: tk.Misc,
        enabled_ids: list[str],
        *,
        standalone: bool = False,
    ) -> None:
        super().__init__(master)
        self.title(f"Anonymizer {__version__} — Templates")
        self.resizable(True, True)
        # Tall enough for edit view (title + two lists + footer) without clipping.
        self.geometry("560x640")
        self.minsize(520, 560)
        # Done → list of enabled template ids; Cancel → None
        self.result: list[str] | None = None
        self._standalone = standalone
        self.configure(bg=_BG_APP)
        try:
            if sys.platform == "darwin":
                self.tk.call(
                    "::tk::unsupported::MacWindowStyle",
                    "style",
                    self._w,
                    "document",
                    "closeBox collapseBox resizable",
                )
        except tk.TclError:
            pass
        if not standalone:
            try:
                if bool(master.winfo_viewable()):
                    self.transient(master)
            except tk.TclError:
                pass
        self._icon_refs: list = []
        self._icon_refs.extend(_apply_window_icons(self))
        try:
            self.grab_set()
        except tk.TclError:
            pass

        self._packs: list[Template] = discover_templates()
        self._enabled: dict[str, tk.BooleanVar] = {}
        for t in self._packs:
            self._enabled[t.id] = tk.BooleanVar(value=(t.id in enabled_ids))
        self._view = "list"  # "list" | "edit"
        self._edit_pack_id: str | None = None
        self._edit_builtin = False
        self._title_editing = False
        self._desc_editing = False

        self._pad = 24
        self._outer = tk.Frame(self, bg=_BG_APP, padx=self._pad, pady=self._pad)
        self._outer.pack(fill=tk.BOTH, expand=True)

        self._build_list_view()
        self.protocol("WM_DELETE_WINDOW", self._on_window_close)
        self.bind("<Escape>", self._on_escape)
        self.bind("<Return>", self._on_return)
        self.bind("<KP_Enter>", self._on_return)
        try:
            _raise_toplevel(self)
            self.after(50, lambda: _raise_toplevel(self))
            self.after(300, lambda: _raise_toplevel(self))
        except tk.TclError:
            pass
        self.wait_window(self)

    # ── shared helpers ────────────────────────────────────────────

    def _clear_outer(self) -> None:
        for w in self._outer.winfo_children():
            w.destroy()

    def _pack_by_id(self, tid: str) -> Template | None:
        for t in self._packs:
            if t.id == tid:
                return t
        return None

    def _reload_packs(self) -> None:
        prev = {tid: var.get() for tid, var in self._enabled.items()}
        self._packs = discover_templates()
        self._enabled = {}
        for t in self._packs:
            self._enabled[t.id] = tk.BooleanVar(
                value=prev.get(t.id, False)
            )

    def _enabled_ids(self) -> list[str]:
        return [
            t.id
            for t in self._packs
            if self._enabled.get(t.id, tk.BooleanVar()).get()
        ]

    def _icon_btn(
        self,
        parent: tk.Misc,
        kind: str,
        command,
        *,
        tooltip: str = "",
        chrome: str | None = None,
    ) -> tk.Frame:
        """Row action: Windows Segoe MDL2 icons (Edit/Copy/Delete), else short labels."""
        bg = chrome if chrome is not None else _BG_WELL
        # MDL2 private-use glyphs (same as Windows Settings / Explorer)
        mdl2 = {
            "edit": "\uE70F",       # Edit
            "duplicate": "\uE8C8",  # Copy
            "delete": "\uE74D",     # Delete
        }
        labels = {"edit": "Edit", "duplicate": "Copy", "delete": "Del"}
        glyph = mdl2.get(kind, "")
        label = labels.get(kind, kind)

        icon_family: str | None = None
        if sys.platform == "win32":
            try:
                import tkinter.font as tkfont

                families = set(tkfont.families(self))
                for cand in ("Segoe MDL2 Assets", "Segoe Fluent Icons"):
                    if cand in families:
                        icon_family = cand
                        break
            except tk.TclError:
                icon_family = None

        use_icon = bool(icon_family and glyph)
        size = 32 if use_icon else 40
        wrap = tk.Frame(parent, bg=bg, width=size, height=size, cursor="hand2")
        wrap.pack_propagate(False)
        cv = tk.Canvas(
            wrap,
            width=size,
            height=size,
            bg=bg,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        cv.pack(fill=tk.BOTH, expand=True)
        state = {"hover": False}

        def _paint() -> None:
            cv.delete("all")
            fill = _BG_BTN_HOVER if state["hover"] else bg
            cv.configure(bg=fill)
            color = _TEXT if state["hover"] else _TEXT_MUTED
            if use_icon:
                cv.create_text(
                    size // 2,
                    size // 2,
                    text=glyph,
                    fill=color,
                    font=(icon_family, 15),
                )
            else:
                cv.create_text(
                    size // 2,
                    size // 2,
                    text=label,
                    fill=color,
                    font=_FONT_SMALL,
                )

        def _run(_e=None) -> None:
            if command is not None:
                command()

        _paint()
        cv.bind("<Button-1>", _run)
        wrap.bind("<Button-1>", _run)
        cv.bind("<Enter>", lambda _e: state.update(hover=True) or _paint())
        cv.bind("<Leave>", lambda _e: state.update(hover=False) or _paint())
        if tooltip:
            try:
                wrap.configure(takefocus=0)
            except tk.TclError:
                pass
            wrap._tooltip = tooltip  # type: ignore[attr-defined]
        return wrap

    # ── View A: enable list ───────────────────────────────────────

    def _build_list_view(self) -> None:
        self._view = "list"
        self._edit_pack_id = None
        self._clear_outer()
        outer = self._outer

        # Footer first (side=BOTTOM) so Done/Cancel never clip off-screen
        foot = tk.Frame(outer, bg=_BG_APP)
        foot.pack(side=tk.BOTTOM, fill=tk.X, pady=(16, 0))
        _chip_button(foot, "+ New", self._new_template, width=9).pack(side=tk.LEFT)
        right = tk.Frame(foot, bg=_BG_APP)
        right.pack(side=tk.RIGHT)
        _chip_button(right, "Cancel", self._cancel, width=11).pack(
            side=tk.LEFT, padx=(0, 10)
        )
        _chip_button(right, "Done", self._done, primary=True, width=11).pack(
            side=tk.LEFT
        )

        _pack_title_row(outer, "Templates", self._icon_refs)
        tk.Label(
            outer,
            text=(
                "Turn templates on for this run. Pencil edits lists; "
                "copy duplicates; trash deletes user templates."
            ),
            bg=_BG_APP,
            fg=_TEXT_MUTED,
            font=_FONT_SMALL,
            wraplength=500,
            justify=tk.LEFT,
            anchor=tk.W,
        ).pack(anchor=tk.W, pady=(0, 16))

        list_wrap = tk.Frame(
            outer,
            bg=_BG_WELL,
            highlightthickness=1,
            highlightbackground=_BORDER,
            highlightcolor=_BORDER,
        )
        list_wrap.pack(fill=tk.BOTH, expand=True)

        self._list_canvas = tk.Canvas(
            list_wrap, bg=_BG_WELL, highlightthickness=0, bd=0
        )
        sb = tk.Scrollbar(
            list_wrap,
            orient=tk.VERTICAL,
            command=self._list_canvas.yview,
            bg=_BG_BTN,
            troughcolor=_BG_WELL,
            activebackground=_BG_BTN_HOVER,
            highlightthickness=0,
            bd=0,
            width=12,
        )
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
            lambda e: self._list_canvas.itemconfigure(
                self._list_win, width=e.width
            ),
        )

        self._rebuild_list_rows()

    def _rebuild_list_rows(self) -> None:
        for w in self._list_inner.winfo_children():
            w.destroy()
        for t in self._packs:
            if t.id not in self._enabled:
                self._enabled[t.id] = tk.BooleanVar(value=False)
            row = tk.Frame(self._list_inner, bg=_BG_WELL)
            row.pack(fill=tk.X, padx=6, pady=3)

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
                cursor="hand2",
            )
            cb.pack(side=tk.LEFT, padx=(4, 4))

            kind = "builtin" if t.builtin else "user"
            lbl = tk.Label(
                row,
                text=f"{t.display_title()}  ·  {kind}",
                bg=_BG_WELL,
                fg=_TEXT,
                font=_FONT_SMALL,
                justify=tk.LEFT,
                anchor=tk.W,
            )
            lbl.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(2, 6), pady=4)

            actions = tk.Frame(row, bg=_BG_WELL)
            actions.pack(side=tk.RIGHT, padx=(0, 2))
            tid = t.id
            self._icon_btn(
                actions,
                "edit",
                lambda i=tid: self._open_edit(i),
                tooltip="Edit template",
            ).pack(side=tk.LEFT, padx=1)
            self._icon_btn(
                actions,
                "duplicate",
                lambda i=tid: self._duplicate(i),
                tooltip="Duplicate template",
            ).pack(side=tk.LEFT, padx=1)
            if not t.builtin:
                self._icon_btn(
                    actions,
                    "delete",
                    lambda i=tid: self._delete(i),
                    tooltip="Delete template",
                ).pack(side=tk.LEFT, padx=1)

        self._list_inner.update_idletasks()
        self._list_canvas.configure(scrollregion=self._list_canvas.bbox("all"))

    # ── View B: edit pack ─────────────────────────────────────────

    def _open_edit(self, tid: str) -> None:
        t = self._pack_by_id(tid)
        if t is None:
            # May be newly created; reload
            self._reload_packs()
            t = self._pack_by_id(tid)
        if t is None:
            messagebox.showerror(
                "Anonymizer", f"Could not load template “{tid}”.", parent=self
            )
            return
        self._build_edit_view(t)

    def _build_edit_view(self, t: Template) -> None:
        self._view = "edit"
        self._edit_pack_id = t.id
        self._edit_builtin = bool(t.builtin)
        self._title_editing = False
        self._desc_editing = False
        self._clear_outer()
        outer = self._outer

        # Ensure window is tall enough for footer + two list panes
        try:
            self.update_idletasks()
            cur = self.geometry()  # WxH+X+Y
            parts = cur.split("+")[0].split("x")
            if len(parts) == 2:
                cw, ch = int(parts[0]), int(parts[1])
                nw, nh = max(cw, 560), max(ch, 640)
                if nw != cw or nh != ch:
                    # Keep current position if present
                    pos = cur[len(parts[0]) + 1 + len(parts[1]) :]
                    self.geometry(f"{nw}x{nh}{pos}")
        except (tk.TclError, ValueError):
            try:
                self.geometry("560x640")
            except tk.TclError:
                pass

        # Footer first so Cancel/Save/Close stay visible
        foot = tk.Frame(outer, bg=_BG_APP)
        foot.pack(side=tk.BOTTOM, fill=tk.X, pady=(16, 0))
        if t.builtin:
            _chip_button(foot, "Close", self._close_edit, width=11).pack(side=tk.RIGHT)
        else:
            right = tk.Frame(foot, bg=_BG_APP)
            right.pack(side=tk.RIGHT)
            _chip_button(right, "Cancel", self._close_edit, width=11).pack(
                side=tk.LEFT, padx=(0, 10)
            )
            _chip_button(
                right, "Save", self._save_edit, primary=True, width=11
            ).pack(side=tk.LEFT)

        _pack_title_row(outer, "Templates", self._icon_refs)

        # Click-to-edit title
        title_row = tk.Frame(outer, bg=_BG_APP)
        title_row.pack(fill=tk.X, pady=(8, 4))
        self._title_label = tk.Label(
            title_row,
            text=t.display_title(),
            bg=_BG_APP,
            fg=_TEXT,
            font=_FONT_TITLE,
            anchor=tk.W,
            cursor="hand2" if not t.builtin else "arrow",
        )
        self._title_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._title_entry = tk.Entry(
            title_row,
            font=_FONT_TITLE,
            bg=_BG_WELL,
            fg=_TEXT,
            insertbackground=_TEXT,
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground=_BORDER,
            highlightcolor=_ACCENT,
        )
        # Hidden until click
        if not t.builtin:
            self._title_label.bind("<Button-1>", lambda _e: self._begin_title_edit())
            self._title_entry.bind("<FocusOut>", lambda _e: self._end_title_edit())
            self._title_entry.bind("<Return>", lambda _e: self._end_title_edit())

        badge = "builtin · read-only" if t.builtin else "user"
        tk.Label(
            outer,
            text=badge,
            bg=_BG_APP,
            fg=_TEXT_MUTED,
            font=_FONT_SMALL,
            anchor=tk.W,
        ).pack(anchor=tk.W, pady=(0, 8))

        # Click-to-edit description (container keeps pack order above editors)
        self._desc_frame = tk.Frame(outer, bg=_BG_APP)
        self._desc_frame.pack(anchor=tk.W, fill=tk.X, pady=(0, 12))
        desc_text = (t.description or "").strip() or (
            "Click to add a description" if not t.builtin else ""
        )
        self._desc_label = tk.Label(
            self._desc_frame,
            text=desc_text,
            bg=_BG_APP,
            fg=_TEXT_MUTED,
            font=_FONT_SMALL,
            wraplength=500,
            justify=tk.LEFT,
            anchor=tk.W,
            cursor="hand2" if not t.builtin else "arrow",
        )
        self._desc_label.pack(anchor=tk.W, fill=tk.X)
        self._desc_text = tk.Text(
            self._desc_frame,
            height=2,
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
            pady=6,
            wrap=tk.WORD,
        )
        if not t.builtin:
            self._desc_label.bind("<Button-1>", lambda _e: self._begin_desc_edit())
            self._desc_text.bind("<FocusOut>", lambda _e: self._end_desc_edit())

        # Allow / deny
        editors = tk.Frame(outer, bg=_BG_APP)
        editors.pack(fill=tk.BOTH, expand=True)
        editors.columnconfigure(0, weight=1)
        editors.rowconfigure(2, weight=1, uniform="ed")
        editors.rowconfigure(5, weight=1, uniform="ed")

        tk.Label(
            editors,
            text="Never redact (allow)",
            bg=_BG_APP,
            fg=_TEXT,
            font=_FONT_BOLD,
            anchor=tk.W,
        ).grid(row=0, column=0, sticky="ew")
        tk.Label(
            editors,
            text="One word or phrase per line.",
            bg=_BG_APP,
            fg=_TEXT_MUTED,
            font=_FONT_SMALL,
            anchor=tk.W,
        ).grid(row=1, column=0, sticky="ew", pady=(2, 4))
        self.allow_txt = tk.Text(
            editors,
            height=4,
            font=_FONT_SMALL,
            bg=_BG_WELL,
            fg=_TEXT,
            insertbackground=_TEXT,
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground=_BORDER,
            highlightcolor=_ACCENT,
            bd=0,
            padx=10,
            pady=8,
            wrap=tk.WORD,
            selectbackground=_SELECT,
            selectforeground=_TEXT,
        )
        self.allow_txt.grid(row=2, column=0, sticky="nsew", pady=(0, 12))
        self.allow_txt.insert("1.0", "\n".join(t.allow))

        tk.Label(
            editors,
            text="Always redact (deny)",
            bg=_BG_APP,
            fg=_TEXT,
            font=_FONT_BOLD,
            anchor=tk.W,
        ).grid(row=3, column=0, sticky="ew")
        tk.Label(
            editors,
            text="One word or phrase per line.",
            bg=_BG_APP,
            fg=_TEXT_MUTED,
            font=_FONT_SMALL,
            anchor=tk.W,
        ).grid(row=4, column=0, sticky="ew", pady=(2, 4))
        self.deny_txt = tk.Text(
            editors,
            height=4,
            font=_FONT_SMALL,
            bg=_BG_WELL,
            fg=_TEXT,
            insertbackground=_TEXT,
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground=_BORDER,
            highlightcolor=_ACCENT,
            bd=0,
            padx=10,
            pady=8,
            wrap=tk.WORD,
            selectbackground=_SELECT,
            selectforeground=_TEXT,
        )
        self.deny_txt.grid(row=5, column=0, sticky="nsew", pady=(0, 0))
        self.deny_txt.insert("1.0", "\n".join(d.text for d in t.deny))

        if t.builtin:
            self.allow_txt.configure(state=tk.DISABLED)
            self.deny_txt.configure(state=tk.DISABLED)

    def _begin_title_edit(self) -> None:
        if self._edit_builtin or self._title_editing:
            return
        self._end_desc_edit()
        cur = self._title_label.cget("text")
        self._title_entry.delete(0, tk.END)
        self._title_entry.insert(0, cur)
        self._title_label.pack_forget()
        self._title_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._title_entry.focus_set()
        self._title_entry.selection_range(0, tk.END)
        self._title_editing = True

    def _end_title_edit(self) -> None:
        if not self._title_editing:
            return
        t = self._title_entry.get().strip()
        if not t:
            t = self._title_label.cget("text")
        self._title_label.configure(text=t)
        self._title_entry.pack_forget()
        self._title_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._title_editing = False

    def _begin_desc_edit(self) -> None:
        if self._edit_builtin or self._desc_editing:
            return
        self._end_title_edit()
        cur = self._desc_label.cget("text")
        if cur == "Click to add a description":
            cur = ""
        self._desc_text.delete("1.0", tk.END)
        self._desc_text.insert("1.0", cur)
        self._desc_label.pack_forget()
        self._desc_text.pack(anchor=tk.W, fill=tk.X)
        self._desc_text.focus_set()
        self._desc_editing = True

    def _end_desc_edit(self) -> None:
        if not self._desc_editing:
            return
        t = self._desc_text.get("1.0", "end-1c").strip()
        display = t if t else "Click to add a description"
        self._desc_label.configure(text=display)
        self._desc_text.pack_forget()
        self._desc_label.pack(anchor=tk.W, fill=tk.X)
        self._desc_editing = False

    def _current_edit_title(self) -> str:
        if self._title_editing:
            return self._title_entry.get().strip()
        return str(self._title_label.cget("text")).strip()

    def _current_edit_description(self) -> str:
        if self._desc_editing:
            return self._desc_text.get("1.0", "end-1c").strip()
        t = str(self._desc_label.cget("text")).strip()
        if t == "Click to add a description":
            return ""
        return t

    def _save_edit(self) -> None:
        tid = self._edit_pack_id
        if not tid:
            return
        base = self._pack_by_id(tid)
        if base is None:
            return
        if base.builtin:
            messagebox.showinfo(
                "Anonymizer",
                "Builtin templates are read-only. Use the copy icon in the "
                "list to duplicate one.",
                parent=self,
            )
            return
        self._end_title_edit()
        self._end_desc_edit()
        title = self._current_edit_title()
        if not title:
            messagebox.showwarning(
                "Anonymizer", "Name is required.", parent=self
            )
            return
        desc = self._current_edit_description()
        allow = lines_from_text(self.allow_txt.get("1.0", "end-1c"))
        deny = deny_from_lines(lines_from_text(self.deny_txt.get("1.0", "end-1c")))
        updated = Template(
            id=base.id,
            title=title,
            description=desc,
            allow=allow,
            deny=deny,
            builtin=False,
            default=base.default,
            path=base.path,
            languages=list(base.languages),
        )
        try:
            path = save_template(updated)
            loaded = load_template_file(path, builtin=False)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(
                "Anonymizer", f"Could not save template:\n{exc}", parent=self
            )
            return
        # Keep enablement for this id
        was_on = self._enabled.get(loaded.id, tk.BooleanVar(value=True)).get()
        self._reload_packs()
        if loaded.id not in {p.id for p in self._packs}:
            self._packs.append(loaded)
            self._packs.sort(key=lambda x: (not x.builtin, x.id))
        self._enabled[loaded.id] = tk.BooleanVar(value=was_on)
        self._build_list_view()

    def _close_edit(self) -> None:
        # Discard editor; keep enablement toggles; return to list
        self._reload_packs()
        self._build_list_view()

    # ── pack operations ───────────────────────────────────────────

    def _unique_fork(self, t: Template) -> Template:
        forked = fork_template(t)
        base = forked.id
        n = 2
        known = {p.id for p in self._packs}
        while forked.id in known:
            forked = Template(
                id=slugify(f"{base}-{n}"),
                title=forked.title,
                description=forked.description,
                allow=list(forked.allow),
                deny=list(forked.deny),
                builtin=False,
                default=False,
                languages=list(forked.languages),
            )
            n += 1
        return forked

    def _duplicate(self, tid: str) -> None:
        t = self._pack_by_id(tid)
        if t is None:
            return
        forked = self._unique_fork(t)
        try:
            path = save_template(forked)
            loaded = load_template_file(path, builtin=False)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(
                "Anonymizer", f"Could not duplicate template:\n{exc}", parent=self
            )
            return
        self._packs.append(loaded)
        self._packs.sort(key=lambda x: (not x.builtin, x.id))
        self._enabled[loaded.id] = tk.BooleanVar(value=True)
        self._rebuild_list_rows()

    def _new_template(self) -> None:
        """Create empty user pack (default “New template”) and open edit — no name dialog."""
        title = "New template"
        known = {p.id for p in self._packs}
        tid = slugify(title) or "new-template"
        base = tid
        n = 2
        while tid in known:
            tid = slugify(f"{base}-{n}")
            n += 1
        display = title
        if any(p.display_title() == display for p in self._packs):
            k = 2
            while any(p.display_title() == f"{title} {k}" for p in self._packs):
                k += 1
            display = f"{title} {k}"
        t = Template(
            id=tid,
            title=display,
            description="",
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
        self._build_edit_view(loaded)

    def _delete(self, tid: str) -> None:
        t = self._pack_by_id(tid)
        if t is None:
            return
        if t.builtin:
            messagebox.showinfo(
                "Anonymizer",
                "Builtin templates cannot be deleted.",
                parent=self,
            )
            return
        if not messagebox.askyesno(
            "Anonymizer",
            f"Delete template “{t.display_title()}”?\nThis cannot be undone.",
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
        self._rebuild_list_rows()

    # ── list Done / Cancel ────────────────────────────────────────

    def _done(self) -> None:
        if self._view != "list":
            return
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
        if self._view == "edit":
            self._close_edit()
            return
        self.result = None
        self.destroy()

    def _on_window_close(self) -> None:
        if self._view == "edit":
            self._close_edit()
            return
        self.result = None
        self.destroy()

    def _on_escape(self, _event=None) -> str:
        if self._view == "edit":
            self._close_edit()
        else:
            self._cancel()
        return "break"

    def _on_return(self, _event=None) -> str | None:
        # Avoid firing while typing in entry/text widgets
        try:
            focus = self.focus_get()
            if focus is not None:
                cls = focus.winfo_class()
                if cls in {"Entry", "Text", "TEntry"}:
                    return None
        except tk.TclError:
            pass
        if self._view == "edit":
            if not self._edit_builtin:
                self._save_edit()
            else:
                self._close_edit()
        else:
            self._done()
        return "break"


class OptionsApp(tk.Tk):
    def __init__(self, files: list[Path] | None = None) -> None:
        n_in = len(files or [])
        _log(f"OptionsApp __init__ begin n={n_in}")
        super().__init__()
        # Full paths; empty list is valid (user adds via +).
        self.files: list[Path] = []
        for p in files or []:
            try:
                self.files.append(p.resolve())
            except OSError:
                self.files.append(p)
        self.out_dir: Path | None = None  # None = next to original files
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
        _log("OptionsApp discover_templates…")
        packs = discover_templates()
        _log(f"OptionsApp packs={len(packs)}")
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
        self._root_frm = root

        _pack_title_row(
            root,
            f"Anonymizer (version {__version__})",
            self._icon_refs,
        )

        self.sub_lbl = tk.Label(
            root,
            text="",
            bg=_BG_APP,
            fg=_TEXT_MUTED,
            font=_FONT_SMALL,
            anchor=tk.W,
        )
        self.sub_lbl.pack(anchor=tk.W, pady=(0, 16))

        # Files header: label + Add / Remove
        files_head = tk.Frame(root, bg=_BG_APP)
        files_head.pack(fill=tk.X)
        tk.Label(
            files_head, text="Files", bg=_BG_APP, fg=_TEXT, font=_FONT_BOLD, anchor=tk.W
        ).pack(side=tk.LEFT)
        files_tools = tk.Frame(files_head, bg=_BG_APP)
        files_tools.pack(side=tk.RIGHT)
        _icon_chip(files_tools, "−", self._remove_file, tooltip="Remove file").pack(
            side=tk.RIGHT, padx=(6, 0)
        )
        _icon_chip(files_tools, "+", self._add_files, tooltip="Add file").pack(
            side=tk.RIGHT
        )

        # Placeholder host for file bullets (rebuilt by _refresh_files_ui)
        self.files_host = tk.Frame(root, bg=_BG_APP)
        self.files_host.pack(fill=tk.X, pady=(4, 4))

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

        # Output folder (after format, before templates) — Mac parity
        tk.Label(
            root,
            text="Output folder",
            bg=_BG_APP,
            fg=_TEXT,
            font=_FONT_BOLD,
            anchor=tk.W,
        ).pack(anchor=tk.W, pady=(16, 4))
        out_row = tk.Frame(root, bg=_BG_APP)
        out_row.pack(fill=tk.X)
        # Buttons first so row height follows chips; label fills and centers vertically
        out_btns = tk.Frame(out_row, bg=_BG_APP)
        out_btns.pack(side=tk.RIGHT)
        self._out_clear_btn = _chip_button(
            out_btns, "Clear", self._clear_out_dir, width=7
        )
        self._out_clear_btn.pack(side=tk.RIGHT, padx=(8, 0))
        _chip_button(out_btns, "Choose…", self._choose_out_dir, width=9).pack(
            side=tk.RIGHT
        )
        self.out_dir_lbl = tk.Label(
            out_row,
            text="same folder as source file (default)",
            bg=_BG_APP,
            fg=_TEXT_MUTED,
            font=_FONT_SMALL,
            anchor=tk.W,
            justify=tk.LEFT,
        )
        self.out_dir_lbl.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        tk.Label(
            root,
            text="Active templates",
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

        # Action bar: Templates… left · Cancel + Start right (Mac parity)
        bar = tk.Frame(root, bg=_BG_APP)
        bar.pack(fill=tk.X, pady=(28, 0))
        _chip_button(bar, "Templates…", self._templates).pack(side=tk.LEFT)
        right = tk.Frame(bar, bg=_BG_APP)
        right.pack(side=tk.RIGHT)
        _chip_button(right, "Cancel", self._on_cancel).pack(side=tk.LEFT, padx=(0, 10))
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

        self._refresh_files_ui()
        self._refresh_out_dir_ui()

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
        self.deiconify()
        self.lift()
        try:
            self.attributes("-topmost", True)
            self.after(600, self._clear_topmost_soon)
        except tk.TclError:
            pass
        # Enable Return → Start only after focus has settled
        self.after(500, self._enable_return_shortcut)
        _log(
            f"OptionsApp ready files={len(self.files)} "
            f"geom={self.geometry()!r} viewable={self.winfo_viewable()}"
        )
        _debug_box(
            f"Options window ready\n{len(self.files)} file(s)\n{self.geometry()}\n"
            f"Log: {_log_path()}"
        )

    def _clear_topmost_soon(self) -> None:
        self._safe_topmost(False)

    def _save_caption(self) -> str:
        if self.out_dir is not None:
            return "Saves to chosen folder"
        return "Saves next to original"

    def _refresh_files_ui(self) -> None:
        n = len(self.files)
        if n == 0:
            head = "No documents yet"
        else:
            head = f"{n} document{'s' if n != 1 else ''} ready"
        sub = f"{head}  ·  {self._save_caption()}  ·  {_privacy_caption()}"
        try:
            self.sub_lbl.configure(text=sub)
            for w in self.files_host.winfo_children():
                w.destroy()
            if n == 0:
                tk.Label(
                    self.files_host,
                    text="No files yet — use + to add",
                    bg=_BG_APP,
                    fg=_TEXT_MUTED,
                    font=_FONT_SMALL,
                    anchor=tk.W,
                ).pack(anchor=tk.W)
            else:
                # Window-colored 1–2 column bullets (Mac parity)
                _pack_files_list(self.files_host, self.files, width_px=420)
        except tk.TclError:
            pass

    def _refresh_out_dir_ui(self) -> None:
        try:
            if self.out_dir is None:
                self.out_dir_lbl.configure(text="same folder as source file (default)")
                self._out_clear_btn.configure(state=tk.DISABLED)
            else:
                self.out_dir_lbl.configure(
                    text=_truncate_path_display(self.out_dir, 52)
                )
                self._out_clear_btn.configure(state=tk.NORMAL)
            self.sub_lbl.configure(
                text=(
                    f"{'No documents yet' if not self.files else (str(len(self.files)) + ' document' + ('s' if len(self.files) != 1 else '') + ' ready')}"
                    f"  ·  {self._save_caption()}  ·  {_privacy_caption()}"
                )
            )
        except tk.TclError:
            pass

    def _add_files(self) -> None:
        paths = filedialog.askopenfilenames(
            parent=self,
            title="Add documents",
            filetypes=_FILETYPES,
        )
        if not paths:
            return
        added = _filter_paths(_coerce_path_args(paths))
        if not added:
            messagebox.showwarning(
                "Anonymizer",
                "No supported files selected.\n\n"
                "Supported: PDF, DOCX, TXT, Markdown.",
                parent=self,
            )
            return
        before = len(self.files)
        self.files = _merge_paths(self.files, added)
        self._refresh_files_ui()
        _log(f"OptionsApp add files +{len(self.files) - before} total={len(self.files)}")

    def _remove_file(self) -> None:
        if not self.files:
            return
        if len(self.files) == 1:
            self.files.clear()
            self._refresh_files_ui()
            return
        # Popover menu of basenames
        menu = tk.Menu(
            self,
            tearoff=0,
            bg=_BG_WELL,
            fg=_TEXT,
            activebackground=_SELECT,
            activeforeground=_TEXT,
            bd=0,
            font=_FONT_SMALL,
        )
        for i, p in enumerate(self.files):
            menu.add_command(
                label=p.name,
                command=lambda idx=i: self._remove_at(idx),
            )
        try:
            menu.tk_popup(self.winfo_pointerx(), self.winfo_pointery())
        finally:
            try:
                menu.grab_release()
            except tk.TclError:
                pass

    def _remove_at(self, index: int) -> None:
        if 0 <= index < len(self.files):
            del self.files[index]
            self._refresh_files_ui()
            _log(f"OptionsApp remove index={index} total={len(self.files)}")

    def _choose_out_dir(self) -> None:
        initial = str(self.out_dir) if self.out_dir else str(Path.home())
        path = filedialog.askdirectory(
            parent=self,
            title="Choose output folder",
            initialdir=initial,
            mustexist=True,
        )
        if not path:
            return
        try:
            self.out_dir = Path(path).expanduser().resolve()
        except OSError:
            self.out_dir = Path(path).expanduser()
        self._refresh_out_dir_ui()
        _log(f"OptionsApp out_dir={self.out_dir}")

    def _clear_out_dir(self) -> None:
        self.out_dir = None
        self._refresh_out_dir_ui()
        _log("OptionsApp out_dir cleared")

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
        # Keep Options visible underneath; Templates is transient + topmost.
        try:
            self.attributes("-topmost", False)
        except tk.TclError:
            pass
        dlg = TemplatesDialog(
            self, list(self.enabled_template_ids), standalone=False
        )
        if dlg.result is not None:
            self.enabled_template_ids = list(dlg.result)
            try:
                self.templates_lbl.configure(
                    text=_templates_status(self.enabled_template_ids)
                )
            except tk.TclError:
                pass
        try:
            if self.winfo_exists():
                self.lift()
                self.focus_force()
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
        if not self.files:
            messagebox.showinfo(
                "Anonymizer",
                "Add at least one document.\n\nUse + under Files to choose PDF, DOCX, or text.",
                parent=self,
            )
            return

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
        out_dir = self.out_dir

        cfg_path = self._write_temp_config(style, self.enabled_template_ids)
        common_flags = [
            "--config",
            str(cfg_path),
            "--redact-style",
            style,
            "--format",
            out_fmt,
        ]
        # Only pass --template when something is selected (empty string confuses old CLIs).
        if self.enabled_template_ids:
            common_flags.extend(
                ["--template", ",".join(self.enabled_template_ids)]
            )
        if out_dir is not None:
            common_flags.extend(["--out-dir", str(out_dir)])
        _log(
            f"_run_start mode={mode} style={style} fmt={out_fmt} "
            f"review={want_review} out_dir={out_dir!r} "
            f"templates={self.enabled_template_ids!r} cli={cli!r}"
        )

        if want_review:
            cmds = [
                [*cli, mode, str(p), *common_flags, "--review-window"]
                for p in self.files
            ]
            try:
                self._run_review_batch(
                    cmds,
                    want_open,
                    files=list(self.files),
                    mode=mode,
                    out_fmt=out_fmt,
                    out_dir=out_dir,
                )
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
                    outs = _guess_outputs([fpath], mode, out_fmt, out_dir=out_dir)
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
            _open_result_paths(outputs)
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
            folder = str(out_dir) if out_dir is not None else str(Path(outputs[0]).parent)
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

    def _run_review_batch(
        self,
        cmds: list[list[str]],
        want_open: bool,
        *,
        files: list[Path] | None = None,
        mode: str = "strict",
        out_fmt: str = "md",
        out_dir: Path | None = None,
    ) -> None:
        """Run CLI with --review-window; wait for each job and surface errors.

        On success: optionally open outputs (Open checkbox); **no** Done dialog.
        ANONYMIZER_OPEN is not honored by the Python CLI — GUI opens after exit.
        """
        src_files = list(files or self.files)
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
        outputs: list[str] = []
        try:
            self.withdraw()
        except tk.TclError:
            pass

        for i, cmd in enumerate(cmds):
            fpath = src_files[i] if i < len(src_files) else None
            _log(f"REVIEW RUN: {' '.join(cmd[:6])}…")
            try:
                # Capture stderr so CLI errors are visible in the dialog.
                # Review window is still a separate Tk UI from the CLI process.
                proc = subprocess.run(
                    cmd,
                    env=env,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
            except OSError as exc:
                errors.append(str(exc))
                _log(f"REVIEW FAIL spawn: {exc}")
                continue

            code = int(proc.returncode or 0)
            if code == 0:
                outs = _parse_outputs(proc.stdout or "", proc.stderr or "")
                if not outs and fpath is not None:
                    outs = _guess_outputs(
                        [fpath], mode, out_fmt, out_dir=out_dir
                    )
                outputs.extend(outs)
                _log(f"REVIEW ok outs={len(outs)}")
                continue
            if code == 130:
                cancelled += 1
                _log("REVIEW cancelled (130)")
                continue
            detail = (proc.stderr or proc.stdout or "").strip()
            if detail:
                _log(f"REVIEW FAIL exit={code} stderr:\n{detail[:2000]}")
                short = "\n".join(detail.splitlines()[:8])
                if len(short) > 400:
                    short = short[:400] + "…"
                errors.append(f"exit {code}\n{short}")
            else:
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
            # Success: open outputs if requested; never show a Done alert.
            if want_open and outputs:
                _open_result_paths(outputs)
                _log(f"REVIEW done open=1 n_out={len(outputs)}")
            else:
                _log(
                    f"REVIEW done open=0 n_out={len(outputs)} "
                    f"(no success dialog)"
                )


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


def _open_result_paths(paths: list[str]) -> None:
    """Open output files in the OS default app (Open-result checkbox)."""
    for out in paths:
        try:
            if sys.platform == "darwin":
                subprocess.run(["open", out], check=False)
            elif sys.platform == "win32":
                os.startfile(out)  # type: ignore[attr-defined]
            else:
                subprocess.run(["xdg-open", out], check=False)
            _log(f"opened result: {out}")
        except OSError as exc:
            _log(f"open result failed {out}: {exc}")


def _guess_outputs(
    files: list[Path],
    mode: str,
    output_format: str = "md",
    *,
    out_dir: Path | None = None,
) -> list[str]:
    """Best-effort paths when CLI OUTPUT: lines are missing."""
    fmt = "md" if mode == "extract" else (output_format or "md")
    write_md = fmt in ("md", "both")
    write_native = fmt in ("source", "both") and mode != "extract"
    paths: list[str] = []
    for f in files:
        base = out_dir if out_dir is not None else f.parent
        if write_md:
            if mode == "extract":
                cand = base / f"{f.stem}.md"
                if out_dir is None and cand.resolve() == f.resolve():
                    cand = base / f"{f.stem}.extracted.md"
            else:
                cand = base / f"{f.stem}.anonymized.md"
            if cand.is_file():
                paths.append(str(cand))
        if write_native and f.suffix.lower() in {".pdf", ".docx"}:
            n = base / f"{f.stem}.anonymized{f.suffix.lower()}"
            if n.is_file():
                paths.append(str(n))
    return paths


def run_templates_ui(
    enabled_csv: str = "",
    *,
    out_path: str | Path | None = None,
) -> int:
    """Open TemplatesDialog; print ENABLED:id1,id2 or CANCEL. Exit 0/2/1.

    Used by Mac droplet (and optional desktop tooling) so Mac and Windows
    share one Templates UI implementation.

    *standalone* windowing avoids a withdrawn Tk root as transient parent
    (which hides the dialog on macOS when launched via ``do shell script``).
    """
    if tk is None:
        print("error: tkinter is not available", file=sys.stderr)
        return 1
    enabled = [x.strip() for x in (enabled_csv or "").split(",") if x.strip()]
    if not enabled:
        enabled = default_enabled_ids()

    def _emit(line: str) -> None:
        print(line, flush=True)
        if out_path:
            try:
                Path(out_path).write_text(line + "\n", encoding="utf-8")
            except OSError as exc:
                print(f"error: could not write {out_path}: {exc}", file=sys.stderr)

    root = tk.Tk()
    root.withdraw()
    try:
        dlg = TemplatesDialog(root, enabled, standalone=True)
    except Exception as exc:  # noqa: BLE001
        print(f"error: templates UI failed: {exc}", file=sys.stderr)
        try:
            root.destroy()
        except tk.TclError:
            pass
        return 1
    try:
        root.destroy()
    except tk.TclError:
        pass
    if dlg.result is None:
        _emit("CANCEL")
        return 2
    _emit("ENABLED:" + ",".join(dlg.result))
    return 0


def main(argv: list[str] | None = None) -> int:
    _log(
        f"--- anonymize-gui start platform={sys.platform} "
        f"argv={argv or sys.argv} log={_log_path()} "
        f"debug={_gui_debug_enabled()}"
    )
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
        # Always open options: empty list unless argv / drag-drop paths.
        _log(f"main: raw args n={len(args)}")
        files = _filter_paths(args)
        _log(f"main: opening OptionsApp n={len(files)} (empty ok — add with +)")
        _debug_box(f"Opening options for {len(files)} file(s)…")
        app = OptionsApp(files)
        try:
            app.deiconify()
            app.lift()
            app.focus_force()
            if sys.platform == "win32":
                app.attributes("-topmost", True)
                app.after(600, app._clear_topmost_soon)
        except tk.TclError:
            pass
        _log("main: entering OptionsApp mainloop")
        app.mainloop()
        _log("main: OptionsApp mainloop ended")
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
