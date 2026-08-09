"""Interactive document review window (Tk): accept, reject, add redactions.

Dark theme, high contrast, rounded cards, screen-fitting window size.
Explicit tk colours (no global ttk style hacks). Offline; no network.
"""

from __future__ import annotations

import sys
from typing import Callable

from anonymizer.anonymize.review import REVIEW_ADD_TYPES, ReviewFinding, ReviewSession

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


def format_finding_label(f: ReviewFinding, *, max_original: int = _LIST_SNIPPET_MAX) -> str:
    origin = "+ " if f.source == "user" else ""
    snippet = f.original.replace("\n", " ").replace("\r", "")
    if len(snippet) > max_original:
        snippet = snippet[: max_original - 1] + "…"
    count = f" (×{f.occurrence_count})" if f.occurrence_count > 1 else ""
    return f"{origin}{f.placeholder} — {snippet}{count}"


def format_finding_row(f: ReviewFinding, *, max_original: int = _LIST_SNIPPET_MAX) -> str:
    mark = "[x]" if f.enabled else "[ ]"
    return f"{mark} {format_finding_label(f, max_original=max_original)}"


def _shortcut_help_text() -> str:
    save = "⌘↩ save" if sys.platform == "darwin" else "Ctrl+Enter save"
    return (
        "↑/↓ or j/k move  ·  spacebar or double-click toggle  ·  "
        f"a add selection  ·  {save}  ·  esc cancel"
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
    type_var = tk.StringVar(value="PERSON")
    status_var = tk.StringVar(value="")
    search_is_placeholder = [True]

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
        """Label-based button (macOS tk.Button ignores custom colours)."""
        bg = _HL_SELECTED_BG if primary else _BG_PANEL
        fg = _TEXT_ON_BLUE if primary else _TEXT
        chip = tk.Frame(
            parent,
            bg=bg,
            highlightbackground=_BORDER if not primary else _ACCENT,
            highlightthickness=1,
            cursor="hand2",
        )
        lbl = tk.Label(
            chip,
            text=text,
            bg=bg,
            fg=fg,
            font=_FONT_BOLD if primary else _FONT,
            padx=16,
            pady=7,
            cursor="hand2",
        )
        lbl.pack()

        def _run(_e=None):
            command()

        chip.bind("<Button-1>", _run)
        lbl.bind("<Button-1>", _run)
        return chip

    _chip_button(act, "Cancel", lambda: _on_close()).pack(side=tk.LEFT, padx=(0, 8))
    _chip_button(act, "Save output", lambda: _on_save(), primary=True).pack(side=tk.LEFT)

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

    # Main split: two equal-ish columns (pack is more reliable than PanedWindow+Canvas)
    main = tk.Frame(outer, bg=_BG_APP)
    main.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

    # ── Findings card ─────────────────────────────────────────────
    findings_card = RoundedCard(main, bg=_BG_PANEL, radius=_RADIUS, pad=14)
    findings_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))
    side = findings_card.inner

    tk.Label(
        side, text="Findings", bg=_BG_PANEL, fg=_TEXT, font=_FONT_BOLD, anchor=tk.W
    ).pack(fill=tk.X, pady=(0, 10))

    tools = tk.Frame(side, bg=_BG_PANEL)
    tools.pack(fill=tk.X, pady=(0, 10))

    search_entry = tk.Entry(
        tools,
        font=_FONT,
        bg=_BG_ELEVATED,
        fg=_TEXT_MUTED,
        insertbackground=_TEXT,
        relief=tk.FLAT,
        highlightthickness=1,
        highlightbackground=_BORDER,
        highlightcolor=_ACCENT,
    )
    search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=6, padx=(0, 8))

    tk.Label(
        tools, text="Filter", bg=_BG_PANEL, fg=_TEXT_MUTED, font=_FONT_SMALL
    ).pack(side=tk.LEFT, padx=(0, 6))

    type_values = ["All"] + sorted(
        {f.type_label for f in session.findings} | {"PERSON", "ORG", "CUSTOM"}
    )
    type_combo = ttk.Combobox(
        tools,
        textvariable=filter_type,
        values=type_values,
        width=12,
        state="readonly",
        font=_FONT,
    )
    type_combo.pack(side=tk.LEFT, ipady=3)
    type_combo.bind("<<ComboboxSelected>>", lambda _e: _refresh_list())

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
    doc_card = RoundedCard(main, bg=_BG_PANEL, radius=_RADIUS, pad=14)
    doc_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6, 0))
    doc_pad = doc_card.inner

    doc_header = tk.Frame(doc_pad, bg=_BG_PANEL)
    doc_header.pack(fill=tk.X, pady=(0, 8))
    tk.Label(
        doc_header, text="Document", bg=_BG_PANEL, fg=_TEXT, font=_FONT_BOLD
    ).pack(side=tk.LEFT)
    tk.Label(
        doc_header,
        text="Amber = redact  ·  blue = focused  ·  space / double-click toggles",
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
    )
    doc_scroll = ttk.Scrollbar(text_wrap, orient=tk.VERTICAL, command=doc.yview)
    doc.configure(yscrollcommand=doc_scroll.set)
    doc.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    doc_scroll.pack(side=tk.RIGHT, fill=tk.Y)
    doc.bind("<Button-1>", lambda _e: doc.focus_set())

    doc.tag_configure(
        "hl_REDACT", background=_HL_REDACT_BG, foreground=_TEXT_ON_AMBER
    )
    doc.tag_configure(
        "hl_SELECTED", background=_HL_SELECTED_BG, foreground=_TEXT_ON_BLUE
    )
    doc.tag_raise("hl_SELECTED")

    # Add bar (elevated)
    add_bar = tk.Frame(doc_pad, bg=_BG_ELEVATED, highlightbackground=_BORDER, highlightthickness=1)
    add_bar.pack(fill=tk.X, pady=(10, 0))
    add_inner = tk.Frame(add_bar, bg=_BG_ELEVATED, padx=10, pady=8)
    add_inner.pack(fill=tk.X)
    tk.Label(
        add_inner,
        text="Add redaction",
        bg=_BG_ELEVATED,
        fg=_TEXT_MUTED,
        font=_FONT_SMALL,
    ).pack(side=tk.LEFT, padx=(0, 8))
    type_menu = ttk.Combobox(
        add_inner,
        textvariable=type_var,
        values=[t[0] for t in REVIEW_ADD_TYPES],
        width=16,
        state="readonly",
        font=_FONT,
    )
    type_menu.pack(side=tk.LEFT, padx=(0, 8), ipady=2)
    ttk.Button(
        add_inner, text="Add selection", command=lambda: _add_selection()
    ).pack(side=tk.LEFT)

    # ── Logic ─────────────────────────────────────────────────────
    def _status() -> None:
        c = session.summary_counts()
        status_var.set(
            f"{c['redact']} redacting  ·  {c['keep_clear']} keep clear  ·  "
            f"{c['user_added']} added  ·  {c['total']} total"
        )

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
            fg = _TEXT_MUTED if (f and not f.enabled) else _TEXT
            try:
                rw["frame"].configure(bg=bg)
                rw["label"].configure(bg=bg, fg=fg)
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
        fr = tk.Frame(parent, bg=_BG_PANEL)
        fr.pack(fill=tk.X, pady=1)
        accent = tk.Frame(fr, bg=_BG_PANEL, width=4)
        accent.pack(side=tk.LEFT, fill=tk.Y)
        accent.pack_propagate(False)

        label = tk.Label(
            fr,
            text=format_finding_label(f),
            anchor=tk.W,
            justify=tk.LEFT,
            font=_FONT_MONO,
            bg=_BG_PANEL,
            fg=_TEXT if f.enabled else _TEXT_MUTED,
            cursor="hand2",
            padx=10,
            pady=8,
        )
        label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        def select_me(_e=None) -> None:
            _focus_ph(f.placeholder, scroll_doc=True)

        def toggle_me(_e=None) -> str:
            _toggle_ph(f.placeholder)
            return "break"

        for w in (label, fr, accent):
            w.bind("<Button-1>", select_me)
            w.bind("<Double-Button-1>", toggle_me)

        return {"frame": fr, "label": label, "accent": accent}

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
        if w is search_entry or w is type_menu or w is type_combo:
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
                if parent in (search_entry, type_menu, type_combo):
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

    def _add_selection(_evt=None) -> str | None:
        if _is_text_input_focused():
            return None
        try:
            sel_text = doc.get(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            messagebox.showinfo(
                "Add redaction",
                "Select text in the document first, then click Add selection.",
                parent=root,
            )
            return "break"
        if not sel_text.strip():
            return "break"
        if len(sel_text.strip()) > 500:
            if not messagebox.askyesno(
                "Long selection",
                f"Redact {len(sel_text.strip())} characters as one finding?",
                parent=root,
            ):
                return "break"
        ent = type_var.get().strip() or "CUSTOM"
        try:
            finding = session.add_redaction(sel_text, ent)
        except ValueError as exc:
            messagebox.showerror("Add redaction", str(exc), parent=root)
            return "break"
        type_combo.configure(
            values=["All"]
            + sorted({f.type_label for f in session.findings} | {"PERSON", "ORG"})
        )
        if filter_type.get() not in {"All", finding.type_label}:
            filter_type.set("All")
        selected_ph[0] = finding.placeholder
        _refresh_list(select_ph=finding.placeholder, refresh_doc=False)
        _refresh_doc(scroll_to_selected=True)
        _focus_list()
        return "break"

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
