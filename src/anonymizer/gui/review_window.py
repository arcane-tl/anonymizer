"""Interactive document review window (Tk): accept, reject, add redactions.

Dark theme, high contrast, rounded cards, screen-fitting window size.
Explicit tk colours (no global ttk style hacks). Offline; no network.
"""

from __future__ import annotations

import sys
from typing import Callable

from anonymizer.anonymize.review import (
    REVIEW_ADD_TYPES,
    ReviewFinding,
    ReviewSession,
    count_surface_occurrences,
    resolve_surface_in_blocks,
)

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except ImportError:  # pragma: no cover
    tk = None  # type: ignore[assignment]


# ── Dark theme tokens (plain names in comments) ───────────────────
_BG_APP = "#0F1115"  # near-black charcoal — window
_BG_PANEL = "#1A1D24"  # dark slate — cards
_BG_ELEVATED = "#242830"  # raised charcoal — toolbars / footer
_BG_SELECTED = "#1E3A5F"  # deep navy — selected list row
_BORDER = "#3A3F4B"  # soft grey border

_TEXT = "#F3F4F6"  # off-white primary
_TEXT_MUTED = "#9CA3AF"  # muted silver
_TEXT_ON_AMBER = "#FFFBEB"  # cream on amber
_TEXT_ON_BLUE = "#EFF6FF"  # ice white on strong blue

_ACCENT = "#60A5FA"  # sky blue accent
_HL_REDACT_BG = "#CA8A04"  # warm amber
_HL_SELECTED_BG = "#1D4ED8"  # strong blue

_PAD = 16
_GAP = 12
_RADIUS = 14
_LIST_SNIPPET_MAX = 48
_SEARCH_PLACEHOLDER = "Search findings…"

_FONT = ("Helvetica", 13) if sys.platform == "darwin" else ("Segoe UI", 11)
_FONT_BOLD = ("Helvetica", 14, "bold") if sys.platform == "darwin" else ("Segoe UI", 12, "bold")
_FONT_SMALL = ("Helvetica", 12) if sys.platform == "darwin" else ("Segoe UI", 10)
_FONT_MONO = ("Menlo", 12) if sys.platform == "darwin" else ("Consolas", 11)
_FONT_DOC = ("Menlo", 13) if sys.platform == "darwin" else ("Consolas", 12)


def display_available() -> bool:
    if tk is None:
        return False
    if sys.platform in {"darwin", "win32"}:
        return True
    import os

    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _human_type_label(f: ReviewFinding) -> str:
    """Map engine type / placeholder label to short UI name."""
    from anonymizer.anonymize.mapping import placeholder_label

    for ent, lab in REVIEW_ADD_TYPES:
        if ent == f.entity_type:
            return lab
    for ent, lab in REVIEW_ADD_TYPES:
        if placeholder_label(ent) == f.type_label:
            return lab
    return f.type_label.replace("_", " ").title()


def format_finding_primary(f: ReviewFinding, *, max_original: int = _LIST_SNIPPET_MAX) -> str:
    """Line 1: original surface text (main scannable content)."""
    snippet = f.original.replace("\n", " ").replace("\r", "")
    if len(snippet) > max_original:
        snippet = snippet[: max_original - 1] + "…"
    return snippet


def format_finding_secondary(f: ReviewFinding) -> str:
    """Line 2: type · tag · user-added marker."""
    parts = [_human_type_label(f), f.placeholder]
    if f.source == "user":
        parts.append("added")
    return " · ".join(parts)


def format_finding_label(f: ReviewFinding, *, max_original: int = _LIST_SNIPPET_MAX) -> str:
    """Single-line summary (tests / legacy)."""
    n = f" ×{f.occurrence_count}" if f.occurrence_count > 1 else ""
    return f"{format_finding_primary(f, max_original=max_original)}{n}  ({format_finding_secondary(f)})"


def format_finding_row(f: ReviewFinding, *, max_original: int = _LIST_SNIPPET_MAX) -> str:
    mark = "[x]" if f.enabled else "[ ]"
    return f"{mark} {format_finding_label(f, max_original=max_original)}"


def _shortcut_help_text() -> str:
    save = "⌘↩ save" if sys.platform == "darwin" else "Ctrl+Enter save"
    return (
        "↑/↓ or j/k move  ·  space or double-click toggle  ·  "
        f"select text then a or right-click to redact  ·  {save}  ·  esc cancel"
    )


def _round_rect(canvas: tk.Canvas, x1: int, y1: int, x2: int, y2: int, r: int, **kwargs):
    """Draw a rounded rectangle on a canvas."""
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


class RoundedCard(tk.Frame):
    """Dark card with rounded corners via background canvas."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        bg: str = _BG_PANEL,
        chrome: str = _BG_APP,
        radius: int = _RADIUS,
        pad: int = 12,
        **kwargs,
    ) -> None:
        # Outer frame matches app chrome so rounded corners “float”
        super().__init__(parent, bg=chrome, **kwargs)
        self._fill = bg
        self._radius = radius
        self._canvas = tk.Canvas(self, bg=chrome, highlightthickness=0, bd=0)
        self._canvas.pack(fill=tk.BOTH, expand=True)
        self.inner = tk.Frame(self._canvas, bg=bg)
        self._win = self._canvas.create_window(pad, pad, window=self.inner, anchor=tk.NW)
        self._shape = None
        self._pad = pad
        self._canvas.bind("<Configure>", self._redraw)

    def _redraw(self, event=None) -> None:
        w = self._canvas.winfo_width()
        h = self._canvas.winfo_height()
        if w < 4 or h < 4:
            return
        self._canvas.delete("shape")
        _round_rect(
            self._canvas,
            1,
            1,
            w - 2,
            h - 2,
            self._radius,
            fill=self._fill,
            outline=_BORDER,
            width=1,
            tags="shape",
        )
        self._canvas.tag_lower("shape")
        iw = max(10, w - 2 * self._pad)
        ih = max(10, h - 2 * self._pad)
        self._canvas.itemconfigure(self._win, width=iw, height=ih)
        self._canvas.coords(self._win, self._pad, self._pad)


def run_review_window(
    session: ReviewSession,
    *,
    file_label: str | None = None,
    on_allowlist: Callable[[str], None] | None = None,
    on_denylist: Callable[[str, str], None] | None = None,
) -> ReviewSession | None:
    """Open the review UI. Returns session on Save, ``None`` on Cancel."""
    if tk is None:
        raise RuntimeError("tkinter is not available")

    result: dict[str, ReviewSession | None] = {"session": None}

    root = tk.Tk()
    title = "Anonymizer review"
    if file_label:
        title = f"Anonymizer review — {file_label}"
    root.title(title)
    root.configure(bg=_BG_APP)

    # Fit on screen with room for Dock / menu bar
    root.update_idletasks()
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    w = max(1100, min(1400, int(sw * 0.88)))
    h = max(740, min(920, int(sh * 0.82)))
    x = max(0, (sw - w) // 2)
    y = max(28, (sh - h) // 2 - 24)
    root.geometry(f"{w}x{h}+{x}+{y}")
    root.minsize(1040, 720)

    selected_ph: list[str | None] = [None]
    filter_type = tk.StringVar(value="All")
    preview_redacted = tk.BooleanVar(value=False)
    status_var = tk.StringVar(value="")
    search_is_placeholder = [True]
    last_add_type: list[str] = ["PERSON"]  # sticky last-used entity type

    outer = tk.Frame(root, bg=_BG_APP, padx=_PAD, pady=_PAD)
    outer.pack(fill=tk.BOTH, expand=True)

    # Pack order: footer BOTTOM first, then header TOP, then paned fills middle
    # (so Cancel/Save/status never get swallowed by the split pane)

    # ── Footer (fixed bottom — always visible) ────────────────────
    foot_bar = tk.Frame(outer, bg=_BG_ELEVATED, highlightbackground=_BORDER, highlightthickness=1)
    foot_bar.pack(side=tk.BOTTOM, fill=tk.X, pady=(_GAP, 0))
    foot_inner = tk.Frame(foot_bar, bg=_BG_ELEVATED, padx=14, pady=10)
    foot_inner.pack(fill=tk.X)

    tk.Label(
        foot_inner,
        textvariable=status_var,
        bg=_BG_ELEVATED,
        fg=_TEXT,
        font=_FONT_BOLD,
        anchor=tk.W,
    ).pack(side=tk.LEFT, fill=tk.X, expand=True)

    act = tk.Frame(foot_inner, bg=_BG_ELEVATED)
    act.pack(side=tk.RIGHT)

    def _chip_button(
        parent: tk.Frame,
        text: str,
        command,
        *,
        primary: bool = False,
    ) -> tk.Frame:
        """Rounded pill button drawn on canvas (macOS-safe colours)."""
        bg = _HL_SELECTED_BG if primary else _BG_PANEL
        fg = _TEXT_ON_BLUE if primary else _TEXT
        outline = _ACCENT if primary else _BORDER
        font = _FONT_BOLD if primary else _FONT
        pad_x, pad_y, radius = 18, 8, 10

        # Measure text for canvas size
        probe = tk.Label(parent, text=text, font=font)
        probe.update_idletasks()
        tw, th = probe.winfo_reqwidth(), probe.winfo_reqheight()
        probe.destroy()
        bw = tw + pad_x * 2
        bh = max(th + pad_y * 2, 34)

        wrap = tk.Frame(parent, bg=_BG_ELEVATED, width=bw, height=bh, cursor="hand2")
        wrap.pack_propagate(False)
        canvas = tk.Canvas(
            wrap,
            width=bw,
            height=bh,
            bg=_BG_ELEVATED,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        canvas.pack(fill=tk.BOTH, expand=True)

        def _paint(*, hover: bool = False) -> None:
            fill = _ACCENT if (primary and hover) else bg
            if not primary and hover:
                fill = _BORDER
            canvas.delete("all")
            _round_rect(
                canvas,
                1,
                1,
                bw - 2,
                bh - 2,
                radius,
                fill=fill,
                outline=outline,
                width=1,
            )
            canvas.create_text(
                bw // 2,
                bh // 2,
                text=text,
                fill=fg,
                font=font,
            )

        def _run(_e=None):
            command()

        _paint()
        canvas.bind("<Button-1>", _run)
        canvas.bind("<Enter>", lambda _e: _paint(hover=True))
        canvas.bind("<Leave>", lambda _e: _paint(hover=False))
        wrap.bind("<Button-1>", _run)
        return wrap

    _chip_button(act, "Cancel", lambda: _on_close()).pack(side=tk.LEFT, padx=(0, 8))
    _chip_button(act, "Save output", lambda: _on_save(), primary=True).pack(
        side=tk.LEFT
    )

    shortcuts = tk.Label(
        outer,
        text=_shortcut_help_text(),
        bg=_BG_APP,
        fg=_TEXT_MUTED,
        font=_FONT_SMALL,
        anchor=tk.W,
        justify=tk.LEFT,
        wraplength=max(900, w - 40),
    )
    shortcuts.pack(side=tk.BOTTOM, fill=tk.X, pady=(6, 0))

    # Header
    header = tk.Frame(outer, bg=_BG_APP)
    header.pack(side=tk.TOP, fill=tk.X, pady=(0, _GAP))
    tk.Label(
        header, text=title, bg=_BG_APP, fg=_TEXT, font=_FONT_BOLD, anchor=tk.W
    ).pack(side=tk.LEFT)
    tk.Checkbutton(
        header,
        text="Preview redacted",
        variable=preview_redacted,
        command=lambda: _refresh_doc(),
        bg=_BG_APP,
        fg=_TEXT,
        activebackground=_BG_APP,
        activeforeground=_TEXT,
        selectcolor=_BG_ELEVATED,
        font=_FONT,
        highlightthickness=0,
    ).pack(side=tk.RIGHT)

    # Main split: drag sash to resize Findings | Document
    paned = tk.PanedWindow(
        outer,
        orient=tk.HORIZONTAL,
        bg=_BG_APP,
        sashwidth=8,
        sashrelief=tk.FLAT,
        sashpad=2,
        opaqueresize=True,
        bd=0,
    )
    paned.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

    # ── Findings card (narrower default — two-line rows) ───────────
    findings_card = RoundedCard(paned, bg=_BG_PANEL, radius=_RADIUS, pad=14)
    _findings_w = max(280, min(360, w // 3))
    paned.add(findings_card, width=_findings_w, minsize=240, stretch="always")
    side = findings_card.inner

    tk.Label(
        side, text="Findings", bg=_BG_PANEL, fg=_TEXT, font=_FONT_BOLD, anchor=tk.W
    ).pack(fill=tk.X, pady=(0, 10))

    # Toolbar: search + funnel + filter — one shared outer height
    _CTRL_H = 36
    _CTRL_R = 9
    _ICON = 22  # funnel size matched to control height

    tools = tk.Frame(side, bg=_BG_PANEL, height=_CTRL_H)
    tools.pack(fill=tk.X, pady=(0, 10))
    tools.pack_propagate(False)

    def _rounded_shell(
        parent: tk.Frame, *, expand: bool = False
    ) -> tuple[tk.Frame, tk.Canvas]:
        """Fixed-height elevated shell with rounded border (search & filter)."""
        shell = tk.Frame(parent, bg=_BG_PANEL, height=_CTRL_H)
        if expand:
            shell.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))
        else:
            shell.pack(side=tk.LEFT, fill=tk.Y)
        shell.pack_propagate(False)
        canvas = tk.Canvas(
            shell, bg=_BG_PANEL, highlightthickness=0, bd=0, height=_CTRL_H
        )
        canvas.pack(fill=tk.BOTH, expand=True)

        def _redraw(_event=None) -> None:
            cw = max(canvas.winfo_width(), 40)
            ch = _CTRL_H
            canvas.configure(height=ch)
            canvas.delete("shell")
            _round_rect(
                canvas,
                1,
                1,
                cw - 2,
                ch - 2,
                _CTRL_R,
                fill=_BG_ELEVATED,
                outline=_BORDER,
                width=1,
                tags="shell",
            )
            canvas.tag_lower("shell")

        canvas.bind("<Configure>", _redraw)
        return shell, canvas

    # --- Search (rounded elevated field) ---
    search_shell, search_canvas = _rounded_shell(tools, expand=True)
    search_entry = tk.Entry(
        search_canvas,
        font=_FONT,
        bg=_BG_ELEVATED,
        fg=_TEXT_MUTED,
        insertbackground=_TEXT,
        relief=tk.FLAT,
        highlightthickness=0,
        bd=0,
    )
    search_win = search_canvas.create_window(
        12, _CTRL_H // 2, window=search_entry, anchor=tk.W
    )

    def _redraw_search_shell(_event=None) -> None:
        cw = max(search_canvas.winfo_width(), 40)
        ch = _CTRL_H
        search_canvas.configure(height=ch)
        search_canvas.delete("shell")
        _round_rect(
            search_canvas,
            1,
            1,
            cw - 2,
            ch - 2,
            _CTRL_R,
            fill=_BG_ELEVATED,
            outline=_BORDER,
            width=1,
            tags="shell",
        )
        search_canvas.tag_lower("shell")
        search_canvas.itemconfigure(search_win, width=max(20, cw - 24))
        search_canvas.coords(search_win, 12, ch // 2)

    search_canvas.bind("<Configure>", _redraw_search_shell)

    # --- Filter: funnel icon only → opens pick list (no separate dropdown field) ---
    type_values = ["All"] + sorted(
        {f.type_label for f in session.findings} | {"PERSON", "ORG", "CUSTOM"}
    )
    # Hit target matches control height; icon sized to _ICON and centered
    icon_box = tk.Frame(
        tools, bg=_BG_PANEL, width=_CTRL_H, height=_CTRL_H, cursor="hand2"
    )
    icon_box.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 2))
    icon_box.pack_propagate(False)
    funnel = tk.Canvas(
        icon_box,
        width=_ICON,
        height=_ICON,
        bg=_BG_PANEL,
        highlightthickness=0,
        bd=0,
        cursor="hand2",
    )
    funnel.place(relx=0.5, rely=0.5, anchor=tk.CENTER)

    def _draw_funnel(*, active: bool = False) -> None:
        funnel.delete("all")
        color = _ACCENT if active else _TEXT_MUTED
        s = _ICON / 18.0

        def _f(x: float, y: float) -> tuple[float, float]:
            return x * s, y * s

        wline = max(1.5, s)
        funnel.create_line(*_f(2, 4), *_f(16, 4), fill=color, width=wline)
        funnel.create_line(*_f(2, 4), *_f(8, 11), fill=color, width=wline)
        funnel.create_line(*_f(16, 4), *_f(10, 11), fill=color, width=wline)
        funnel.create_line(*_f(8, 11), *_f(10, 11), fill=color, width=wline)
        funnel.create_line(*_f(9, 11), *_f(9, 16), fill=color, width=wline)

    def _set_filter(value: str) -> None:
        filter_type.set(value)
        _draw_funnel(active=value != "All")
        _refresh_list()

    def _open_filter_menu(_event=None) -> None:
        menu = tk.Menu(
            root,
            tearoff=0,
            bg=_BG_ELEVATED,
            fg=_TEXT,
            activebackground=_BG_SELECTED,
            activeforeground=_TEXT,
            bd=0,
            font=_FONT,
        )
        current = filter_type.get()
        for val in type_values:
            # Checkmark on current choice (pick list, single select)
            label = f"✓  {val}" if val == current else f"    {val}"
            menu.add_command(label=label, command=lambda v=val: _set_filter(v))
        try:
            x = icon_box.winfo_rootx()
            y = icon_box.winfo_rooty() + icon_box.winfo_height()
            menu.tk_popup(x, y)
        finally:
            try:
                menu.grab_release()
            except tk.TclError:
                pass

    _draw_funnel(active=False)
    for w in (icon_box, funnel):
        w.bind("<Button-1>", _open_filter_menu)

    def _layout_toolbar() -> None:
        _redraw_search_shell()

    root.after_idle(_layout_toolbar)
    root.after(50, _layout_toolbar)

    def _show_search_placeholder() -> None:
        search_is_placeholder[0] = True
        search_entry.delete(0, tk.END)
        search_entry.insert(0, _SEARCH_PLACEHOLDER)
        search_entry.configure(fg=_TEXT_MUTED, bg=_BG_ELEVATED)

    def _begin_search_edit(_evt=None) -> None:
        if search_is_placeholder[0]:
            search_is_placeholder[0] = False
            search_entry.delete(0, tk.END)
            search_entry.configure(fg=_TEXT, bg=_BG_ELEVATED)

    def _on_search_focus_out(_evt=None) -> None:
        if not search_entry.get().strip() or search_is_placeholder[0]:
            _show_search_placeholder()

    def _search_query() -> str:
        if search_is_placeholder[0]:
            return ""
        return search_entry.get().strip()

    def _on_search_key(_evt=None) -> None:
        if search_is_placeholder[0]:
            return
        _refresh_list()

    search_entry.bind("<FocusIn>", _begin_search_edit)
    search_entry.bind("<FocusOut>", _on_search_focus_out)
    search_entry.bind("<KeyRelease>", _on_search_key)
    # Click on rounded shell focuses entry
    search_canvas.bind("<Button-1>", lambda _e: search_entry.focus_set())
    _show_search_placeholder()

    # List viewport
    list_frame = tk.Frame(side, bg=_BG_PANEL)
    list_frame.pack(fill=tk.BOTH, expand=True)
    list_canvas = tk.Canvas(
        list_frame,
        highlightthickness=0,
        borderwidth=0,
        bg=_BG_PANEL,
        takefocus=True,
    )
    list_scroll = ttk.Scrollbar(
        list_frame, orient=tk.VERTICAL, command=list_canvas.yview
    )
    list_inner = tk.Frame(list_canvas, bg=_BG_PANEL)
    list_inner.bind(
        "<Configure>",
        lambda _e: list_canvas.configure(scrollregion=list_canvas.bbox("all")),
    )
    list_window = list_canvas.create_window((0, 0), window=list_inner, anchor=tk.NW)

    def _on_canvas_configure(event) -> None:
        list_canvas.itemconfigure(list_window, width=event.width)

    list_canvas.bind("<Configure>", _on_canvas_configure)
    list_canvas.configure(yscrollcommand=list_scroll.set)
    list_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    list_scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def _on_mousewheel(event) -> None:
        if sys.platform == "darwin":
            list_canvas.yview_scroll(int(-1 * event.delta), "units")
        else:
            list_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _bind_wheel(_e=None) -> None:
        list_canvas.bind_all("<MouseWheel>", _on_mousewheel)

    def _unbind_wheel(_e=None) -> None:
        list_canvas.unbind_all("<MouseWheel>")

    list_canvas.bind("<Enter>", _bind_wheel)
    list_canvas.bind("<Leave>", _unbind_wheel)
    list_canvas.bind("<Button-1>", lambda _e: _focus_list())

    visible_ph: list[str] = []
    row_widgets: dict[str, dict] = {}

    # ── Document card ─────────────────────────────────────────────
    doc_card = RoundedCard(paned, bg=_BG_PANEL, radius=_RADIUS, pad=14)
    paned.add(doc_card, minsize=360, stretch="always")
    doc_pad = doc_card.inner

    doc_header = tk.Frame(doc_pad, bg=_BG_PANEL)
    doc_header.pack(fill=tk.X, pady=(0, 8))
    tk.Label(
        doc_header, text="Document", bg=_BG_PANEL, fg=_TEXT, font=_FONT_BOLD
    ).pack(side=tk.LEFT)
    tk.Label(
        doc_header,
        text="Amber = redact  ·  blue = focused  ·  a / right-click adds",
        bg=_BG_PANEL,
        fg=_TEXT_MUTED,
        font=_FONT_SMALL,
    ).pack(side=tk.RIGHT)

    text_wrap = tk.Frame(doc_pad, bg=_BG_PANEL)
    text_wrap.pack(fill=tk.BOTH, expand=True)
    doc = tk.Text(
        text_wrap,
        wrap=tk.WORD,
        font=_FONT_DOC,
        undo=False,
        padx=12,
        pady=12,
        bg=_BG_ELEVATED,
        fg=_TEXT,
        insertbackground=_TEXT,
        relief=tk.FLAT,
        highlightthickness=1,
        highlightbackground=_BORDER,
        highlightcolor=_ACCENT,
        selectbackground=_HL_SELECTED_BG,
        selectforeground=_TEXT_ON_BLUE,
        borderwidth=0,
        cursor="xterm",  # select to redact, not free typing
    )
    doc_scroll = ttk.Scrollbar(text_wrap, orient=tk.VERTICAL, command=doc.yview)
    doc.configure(yscrollcommand=doc_scroll.set)
    doc.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    doc_scroll.pack(side=tk.RIGHT, fill=tk.Y)

    # Review canvas only: allow select/navigate/copy; block typing & paste/cut
    _NAV_KEYS = {
        "Left",
        "Right",
        "Up",
        "Down",
        "Home",
        "End",
        "Prior",
        "Next",
        "Tab",
        "ISO_Left_Tab",
        "Shift_L",
        "Shift_R",
        "Control_L",
        "Control_R",
        "Alt_L",
        "Alt_R",
        "Meta_L",
        "Meta_R",
        "Caps_Lock",
        "Escape",
        "Return",
        "KP_Enter",
    }

    def _doc_block_edit(event: tk.Event) -> str | None:
        """Prevent free editing; selection + shortcuts still work."""
        # Our add-redaction shortcut (handled by specific binds; belt-and-suspenders)
        if event.keysym in {"a", "A"}:
            return _open_add_type_menu(event)
        # Allow pure navigation / modifiers
        if event.keysym in _NAV_KEYS:
            return None
        # Allow copy (Ctrl/Cmd+C); block cut/paste
        state = int(getattr(event, "state", 0) or 0)
        cmd = bool(state & 0x8) or bool(state & 0x4)  # Mod1/Control-ish (platform varies)
        # On macOS Command is often 0x8 (Mod1); Control 0x4
        if event.keysym.lower() == "c" and (
            state & 0x4 or state & 0x8 or state & 0x10
        ):
            return None  # copy
        # Block everything else that would change text (letters, BackSpace, Delete, …)
        return "break"

    doc.bind("<Key>", _doc_block_edit)
    doc.bind("<<Paste>>", lambda _e: "break")
    doc.bind("<<Cut>>", lambda _e: "break")
    doc.bind("<Button-1>", lambda _e: doc.focus_set())
    # Right-click / a → type menu (must return break so Text never inserts)
    doc.bind("<Button-3>", lambda e: _open_add_type_menu(e))
    doc.bind("<Control-Button-1>", lambda e: _open_add_type_menu(e))
    doc.bind("a", lambda e: _open_add_type_menu(e))
    doc.bind("A", lambda e: _open_add_type_menu(e))

    doc.tag_configure(
        "hl_REDACT", background=_HL_REDACT_BG, foreground=_TEXT_ON_AMBER
    )
    doc.tag_configure(
        "hl_SELECTED", background=_HL_SELECTED_BG, foreground=_TEXT_ON_BLUE
    )
    doc.tag_raise("hl_SELECTED")

    # One-line hint (no combobox bar)
    tk.Label(
        doc_pad,
        text="Select text → a or right-click → choose type  ·  document is not editable",
        bg=_BG_PANEL,
        fg=_TEXT_MUTED,
        font=_FONT_SMALL,
        anchor=tk.W,
    ).pack(fill=tk.X, pady=(10, 0))

    # ── Logic ─────────────────────────────────────────────────────
    def _status(extra: str = "") -> None:
        c = session.summary_counts()
        base = (
            f"{c['redact']} redacting  ·  {c['keep_clear']} keep clear  ·  "
            f"{c['user_added']} added  ·  {c['total']} total"
        )
        status_var.set(f"{base}  ·  {extra}" if extra else base)

    def _status_flash(msg: str, ms: int = 4000) -> None:
        _status(msg)
        root.after(ms, lambda: _status())

    def _filtered_findings() -> list[ReviewFinding]:
        q = _search_query().casefold()
        ft = filter_type.get()
        out: list[ReviewFinding] = []
        for f in session.findings:
            if ft != "All" and f.type_label != ft:
                continue
            if q and q not in f.original.casefold() and q not in f.placeholder.casefold():
                continue
            out.append(f)
        return out

    def _focus_list() -> None:
        list_canvas.focus_set()

    def _style_row_selected(ph: str | None) -> None:
        for key, rw in row_widgets.items():
            f = session.get(key)
            selected = key == ph
            bg = _BG_SELECTED if selected else _BG_PANEL
            muted = bool(f and not f.enabled)
            fg1 = _TEXT_MUTED if muted else _TEXT
            fg2 = _TEXT_MUTED if muted else _TEXT_MUTED
            try:
                rw["frame"].configure(bg=bg)
                rw["body"].configure(bg=bg)
                rw["line1"].configure(bg=bg, fg=fg1)
                rw["line2"].configure(bg=bg, fg=fg2)
                rw["count"].configure(bg=bg, fg=fg2)
                rw["accent"].configure(bg=_ACCENT if selected else bg)
            except tk.TclError:
                pass

    def _set_enabled(ph: str, enabled: bool) -> None:
        session.set_enabled(ph, enabled)
        selected_ph[0] = ph
        _style_row_selected(ph)
        _status()
        _refresh_doc(scroll_to_selected=True)

    def _toggle_ph(ph: str) -> None:
        f = session.get(ph)
        if not f:
            return
        _set_enabled(ph, not f.enabled)

    def _focus_ph(ph: str, *, scroll_doc: bool = True) -> None:
        if ph not in visible_ph:
            return
        selected_ph[0] = ph
        _focus_list()
        _style_row_selected(ph)
        rw = row_widgets.get(ph)
        if rw:
            try:
                list_canvas.update_idletasks()
                y = rw["frame"].winfo_y()
                hgt = list_inner.winfo_height() or 1
                list_canvas.yview_moveto(max(0.0, (y - 20) / max(hgt, 1)))
            except tk.TclError:
                pass
        _refresh_doc(scroll_to_selected=scroll_doc)

    def _make_row(parent: tk.Frame, f: ReviewFinding) -> dict:
        """Two-line compact row: surface + count / type · tag · added."""
        fr = tk.Frame(parent, bg=_BG_PANEL)
        fr.pack(fill=tk.X, pady=1)
        accent = tk.Frame(fr, bg=_BG_PANEL, width=4)
        accent.pack(side=tk.LEFT, fill=tk.Y)
        accent.pack_propagate(False)

        body = tk.Frame(fr, bg=_BG_PANEL)
        body.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 8), pady=5)

        top = tk.Frame(body, bg=_BG_PANEL)
        top.pack(fill=tk.X)
        muted = not f.enabled
        line1 = tk.Label(
            top,
            text=format_finding_primary(f),
            anchor=tk.W,
            justify=tk.LEFT,
            font=_FONT,
            bg=_BG_PANEL,
            fg=_TEXT_MUTED if muted else _TEXT,
            cursor="hand2",
        )
        line1.pack(side=tk.LEFT, fill=tk.X, expand=True)
        count_txt = f"×{f.occurrence_count}" if f.occurrence_count > 1 else ""
        count = tk.Label(
            top,
            text=count_txt,
            anchor=tk.E,
            font=_FONT_SMALL,
            bg=_BG_PANEL,
            fg=_TEXT_MUTED,
            cursor="hand2",
            padx=(6, 0),
        )
        count.pack(side=tk.RIGHT)

        line2 = tk.Label(
            body,
            text=format_finding_secondary(f),
            anchor=tk.W,
            justify=tk.LEFT,
            font=_FONT_SMALL,
            bg=_BG_PANEL,
            fg=_TEXT_MUTED,
            cursor="hand2",
        )
        line2.pack(fill=tk.X, pady=(1, 0))

        def select_me(_e=None) -> None:
            _focus_ph(f.placeholder, scroll_doc=True)

        def toggle_me(_e=None) -> str:
            _toggle_ph(f.placeholder)
            return "break"

        for w in (line1, line2, count, body, fr, accent):
            w.bind("<Button-1>", select_me)
            w.bind("<Double-Button-1>", toggle_me)

        return {
            "frame": fr,
            "body": body,
            "line1": line1,
            "line2": line2,
            "count": count,
            "accent": accent,
        }

    def _refresh_list(
        select_ph: str | None = None, *, refresh_doc: bool = True
    ) -> None:
        for child in list_inner.winfo_children():
            child.destroy()
        row_widgets.clear()
        visible_ph.clear()

        findings = _filtered_findings()
        if not findings:
            tk.Label(
                list_inner,
                text="No findings match this filter.",
                bg=_BG_PANEL,
                fg=_TEXT_MUTED,
                font=_FONT_SMALL,
                pady=28,
            ).pack(fill=tk.X)
        for f in findings:
            rw = _make_row(list_inner, f)
            row_widgets[f.placeholder] = rw
            visible_ph.append(f.placeholder)

        list_inner.update_idletasks()
        list_canvas.configure(scrollregion=list_canvas.bbox("all"))

        _status()
        target = select_ph or selected_ph[0]
        if target and target in visible_ph:
            selected_ph[0] = target
        elif visible_ph:
            selected_ph[0] = visible_ph[0]
        else:
            selected_ph[0] = None
        _style_row_selected(selected_ph[0])
        if refresh_doc:
            _refresh_doc(scroll_to_selected=False)

    def _paint_finding(f: ReviewFinding, tag: str) -> None:
        if not f.original:
            return
        start = "1.0"
        while True:
            idx = doc.search(f.original, start, stopindex=tk.END, nocase=False)
            if not idx:
                break
            end = f"{idx}+{len(f.original)}c"
            doc.tag_add(tag, idx, end)
            start = end

    def _refresh_doc(*, scroll_to_selected: bool = False) -> None:
        try:
            yview = doc.yview()
        except tk.TclError:
            yview = (0.0, 1.0)

        doc.configure(state=tk.NORMAL)
        doc.delete("1.0", tk.END)
        if preview_redacted.get():
            blocks, _ = session.apply(style="placeholder")
            doc.insert("1.0", "\n\n".join(blocks))
            doc.configure(state=tk.DISABLED)
            _status()
            return

        doc.insert("1.0", "\n\n".join(session.original_blocks))

        visible_set = set(visible_ph)
        ordered = sorted(
            (
                f
                for f in session.findings
                if f.enabled and f.placeholder in visible_set
            ),
            key=lambda f: len(f.original),
            reverse=True,
        )
        for f in ordered:
            _paint_finding(f, "hl_REDACT")

        sel = selected_ph[0]
        if sel and sel in visible_set:
            f_sel = session.get(sel)
            if f_sel and f_sel.enabled:
                _paint_finding(f_sel, "hl_SELECTED")

        doc.configure(state=tk.NORMAL)
        try:
            doc.yview_moveto(yview[0])
        except tk.TclError:
            pass

        if scroll_to_selected and sel and sel in visible_set:
            f_sel = session.get(sel)
            if f_sel and f_sel.original:
                idx = doc.search(f_sel.original, "1.0", stopindex=tk.END)
                if idx:
                    doc.see(idx)
                    doc.mark_set(tk.INSERT, idx)
        _status()

    def _current_list_index() -> int:
        if not visible_ph:
            return 0
        ph = selected_ph[0]
        if ph and ph in visible_ph:
            return visible_ph.index(ph)
        return 0

    def _focus_index(idx: int, *, scroll_doc: bool = True) -> None:
        if not visible_ph:
            return
        idx = max(0, min(idx, len(visible_ph) - 1))
        _focus_ph(visible_ph[idx], scroll_doc=scroll_doc)

    def _is_text_input_focused() -> bool:
        w = root.focus_get()
        if w is None:
            return False
        if w is search_entry:
            return True
        try:
            if str(w).startswith(str(search_entry)):
                return True
        except tk.TclError:
            pass
        cls = w.winfo_class()
        if cls in {"TEntry", "Entry", "TCombobox", "Combobox"}:
            return True
        try:
            parent = w.master
            while parent is not None:
                if parent is search_entry:
                    return True
                pcls = parent.winfo_class()
                if pcls in {"TEntry", "Entry", "TCombobox", "Combobox"}:
                    return True
                parent = getattr(parent, "master", None)
        except tk.TclError:
            pass
        return False

    def _toggle_selected(_evt=None) -> str | None:
        if _is_text_input_focused():
            return None
        ph = selected_ph[0]
        if ph:
            _toggle_ph(ph)
        return "break"

    def _current_selection() -> str | None:
        try:
            sel = doc.get(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            return None
        return sel if sel and sel.strip() else None

    def _commit_add(sel_text: str, entity_type: str) -> None:
        try:
            finding = session.add_redaction(sel_text, entity_type)
        except ValueError as exc:
            _status_flash(str(exc))
            return
        last_add_type[0] = entity_type
        nonlocal type_values
        type_values = ["All"] + sorted(
            {f.type_label for f in session.findings} | {"PERSON", "ORG", "CUSTOM"}
        )
        if filter_type.get() not in {"All", finding.type_label}:
            _set_filter("All")
        selected_ph[0] = finding.placeholder
        _refresh_list(select_ph=finding.placeholder, refresh_doc=False)
        _refresh_doc(scroll_to_selected=True)
        _focus_list()
        n = finding.occurrence_count
        extra = f"Added {finding.placeholder}" + (
            f" (×{n} places)" if n > 1 else ""
        )
        if finding.source == "auto" or (
            finding.source == "user" and n >= 1
        ):
            # Re-enable existing shows as user still; keep simple message
            pass
        _status_flash(extra)

    def _open_add_type_menu(event=None) -> str | None:
        """Type pick list for current document selection (a / right-click)."""
        if _is_text_input_focused():
            return None
        sel_text = _current_selection()
        if not sel_text:
            _status_flash("Select text in the document, then press a or right-click")
            return "break"

        surface = resolve_surface_in_blocks(session.original_blocks, sel_text)
        if not surface:
            _status_flash(
                "Could not match that selection in the document — try a continuous phrase"
            )
            return "break"

        n = count_surface_occurrences(session.original_blocks, surface)
        preview = surface.replace("\n", " ")
        if len(preview) > 40:
            preview = preview[:39] + "…"

        menu = tk.Menu(
            root,
            tearoff=0,
            bg=_BG_ELEVATED,
            fg=_TEXT,
            activebackground=_BG_SELECTED,
            activeforeground=_TEXT,
            bd=0,
            font=_FONT,
        )
        # Disabled header lines (preview + occurrence count)
        menu.add_command(
            label=f"Redact “{preview}”",
            state=tk.DISABLED,
        )
        if n > 1:
            menu.add_command(
                label=f"  also matches ×{n} places in this document",
                state=tk.DISABLED,
            )
        menu.add_separator()

        # Last-used type first
        last = last_add_type[0]
        last_label = next(
            (lab for code, lab in REVIEW_ADD_TYPES if code == last), last
        )
        menu.add_command(
            label=f"★  {last_label}  (last used)",
            command=lambda: _commit_add(sel_text, last),
        )
        menu.add_separator()

        for code, lab in REVIEW_ADD_TYPES:
            if code == last:
                continue  # already shown at top
            menu.add_command(
                label=f"    {lab}",
                command=lambda c=code: _commit_add(sel_text, c),
            )

        try:
            if event is not None and getattr(event, "x_root", None):
                menu.tk_popup(int(event.x_root), int(event.y_root))
            else:
                # Keyboard: near bottom of document pane
                menu.tk_popup(
                    doc.winfo_rootx() + 40,
                    doc.winfo_rooty() + min(120, doc.winfo_height() // 3),
                )
        finally:
            try:
                menu.grab_release()
            except tk.TclError:
                pass
        return "break"

    def _add_selection(_evt=None) -> str | None:
        """Keyboard shortcut a — open type menu for selection."""
        return _open_add_type_menu(_evt)

    def _save() -> None:
        kept = session.keep_clear_placeholders()
        if kept:
            lines = []
            for ph in kept[:12]:
                f = session.get(ph)
                if f:
                    snip = f.original.replace("\n", " ")
                    if len(snip) > 60:
                        snip = snip[:59] + "…"
                    lines.append(f"  {ph} — {snip}")
            more = f"\n  … and {len(kept) - 12} more" if len(kept) > 12 else ""
            msg = (
                f"{len(kept)} item(s) will appear in CLEAR TEXT:\n\n"
                + "\n".join(lines)
                + more
                + "\n\nSave output anyway?"
            )
            if not messagebox.askyesno("Confirm clear text", msg, parent=root):
                return
        result["session"] = session
        root.destroy()

    def _cancel() -> None:
        result["session"] = None
        root.destroy()

    def _cleanup() -> None:
        try:
            list_canvas.unbind_all("<MouseWheel>")
        except tk.TclError:
            pass

    def _on_close() -> None:
        _cleanup()
        _cancel()

    def _on_save() -> None:
        _cleanup()
        _save()

    def _nav(delta: int) -> str:
        if not visible_ph:
            return "break"
        _focus_index(_current_list_index() + delta, scroll_doc=True)
        return "break"

    def _nav_if_not_typing(delta: int, _event=None) -> str | None:
        if _is_text_input_focused():
            return None
        return _nav(delta)

    def _on_escape(_evt=None) -> str:
        w = root.focus_get()
        if w is search_entry or (
            w is not None and str(w).startswith(str(search_entry))
        ):
            _show_search_placeholder()
            _refresh_list()
            _focus_list()
            return "break"
        _on_close()
        return "break"

    root.bind("<space>", lambda e: _toggle_selected(e))
    root.bind("<Escape>", _on_escape)
    root.bind(
        "<Command-Return>" if sys.platform == "darwin" else "<Control-Return>",
        lambda _e: _on_save(),
    )
    root.bind("j", lambda e: _nav_if_not_typing(1, e))
    root.bind("k", lambda e: _nav_if_not_typing(-1, e))
    root.bind("<Down>", lambda e: _nav_if_not_typing(1, e))
    root.bind("<Up>", lambda e: _nav_if_not_typing(-1, e))
    root.bind("a", lambda e: _add_selection(e))
    root.bind("A", lambda e: _add_selection(e))

    list_canvas.bind("<Down>", lambda _e: _nav(1))
    list_canvas.bind("<Up>", lambda _e: _nav(-1))
    list_canvas.bind("j", lambda _e: _nav(1))
    list_canvas.bind("k", lambda _e: _nav(-1))
    list_canvas.bind("<space>", lambda e: _toggle_selected(e))

    root.protocol("WM_DELETE_WINDOW", _on_close)

    _refresh_list(refresh_doc=True)
    if visible_ph:
        _focus_index(0, scroll_doc=True)
    else:
        _focus_list()

    root.lift()
    try:
        root.attributes("-topmost", True)
        root.after(200, lambda: root.attributes("-topmost", False))
    except tk.TclError:
        pass

    root.mainloop()
    _cleanup()
    return result["session"]
