"""Interactive document review window (Tk): accept, reject, add redactions.

High-contrast light UI with explicit colours on tk widgets (avoids macOS
dark-mode / ttk style fights that make text unreadable). Offline; no network.
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


# ── High-contrast light tokens (explicit; no reliance on system theme) ──
_BG_APP = "#E8EAED"
_BG_PANEL = "#FFFFFF"
_BG_TOOLBAR = "#F1F3F4"
_BG_SELECTED = "#D2E3FC"  # clear blue selection
_BG_LIST = "#FFFFFF"

_BORDER = "#DADCE0"

_TEXT = "#202124"  # near-black — always readable on white
_TEXT_SECONDARY = "#5F6368"  # secondary / hints (still ≥ 4.5:1 on white)
_TEXT_DISABLED = "#80868B"

_ACCENT = "#1A73E8"

# Document highlights — strong enough to see, dark text on top
_HL_REDACT_BG = "#FDD663"
_HL_REDACT_FG = "#202124"
_HL_SELECTED_BG = "#8AB4F8"
_HL_SELECTED_FG = "#202124"

_PAD = 14
_GAP = 10
_LIST_SNIPPET_MAX = 48
_SEARCH_PLACEHOLDER = "Search findings…"

_FONT = ("Helvetica", 13) if sys.platform == "darwin" else ("Segoe UI", 11)
_FONT_BOLD = ("Helvetica", 14, "bold") if sys.platform == "darwin" else ("Segoe UI", 12, "bold")
_FONT_SMALL = ("Helvetica", 12) if sys.platform == "darwin" else ("Segoe UI", 10)
_FONT_MONO = ("Menlo", 12) if sys.platform == "darwin" else ("Consolas", 11)
_FONT_DOC = ("Menlo", 13) if sys.platform == "darwin" else ("Consolas", 12)


def display_available() -> bool:
    """True if a GUI display can be opened for Tk."""
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
    root.minsize(1000, 640)
    root.geometry("1120x720")
    root.configure(bg=_BG_APP)

    # Do NOT recolour global ttk styles (breaks macOS dark mode / aqua).
    # Use default ttk for Combobox/Button only; paint everything else with tk.

    selected_ph: list[str | None] = [None]
    filter_type = tk.StringVar(value="All")
    preview_redacted = tk.BooleanVar(value=False)
    type_var = tk.StringVar(value="PERSON")
    status_var = tk.StringVar(value="")
    search_is_placeholder = [True]

    outer = tk.Frame(root, bg=_BG_APP, padx=_PAD, pady=_PAD)
    outer.pack(fill=tk.BOTH, expand=True)

    # ── Header ────────────────────────────────────────────────────
    header = tk.Frame(outer, bg=_BG_APP)
    header.pack(fill=tk.X, pady=(0, _GAP))
    tk.Label(
        header, text=title, bg=_BG_APP, fg=_TEXT, font=_FONT_BOLD, anchor=tk.W
    ).pack(side=tk.LEFT)
    # Preview: tk checkbutton with explicit colours
    preview_cb = tk.Checkbutton(
        header,
        text="Preview redacted",
        variable=preview_redacted,
        command=lambda: _refresh_doc(),
        bg=_BG_APP,
        fg=_TEXT,
        activebackground=_BG_APP,
        activeforeground=_TEXT,
        selectcolor=_BG_PANEL,
        font=_FONT,
        highlightthickness=0,
    )
    preview_cb.pack(side=tk.RIGHT)

    # ── Main split (tk paned for colour control) ───────────────────
    paned = tk.PanedWindow(
        outer,
        orient=tk.HORIZONTAL,
        bg=_BG_APP,
        sashwidth=6,
        sashrelief=tk.FLAT,
        bd=0,
    )
    paned.pack(fill=tk.BOTH, expand=True)

    # ── Findings card ─────────────────────────────────────────────
    side_card = tk.Frame(
        paned, bg=_BG_PANEL, highlightbackground=_BORDER, highlightthickness=1, bd=0
    )
    paned.add(side_card, width=360, minsize=280, stretch="always")

    side = tk.Frame(side_card, bg=_BG_PANEL, padx=12, pady=12)
    side.pack(fill=tk.BOTH, expand=True)

    tk.Label(
        side, text="Findings", bg=_BG_PANEL, fg=_TEXT, font=_FONT_BOLD, anchor=tk.W
    ).pack(fill=tk.X, pady=(0, 8))

    tools = tk.Frame(side, bg=_BG_PANEL)
    tools.pack(fill=tk.X, pady=(0, 8))

    # Search: tk.Entry — same visual weight as comboboxes; explicit colours
    search_entry = tk.Entry(
        tools,
        font=_FONT,
        bg=_BG_PANEL,
        fg=_TEXT_SECONDARY,
        insertbackground=_TEXT,
        relief=tk.SOLID,
        borderwidth=1,
        highlightthickness=1,
        highlightbackground=_BORDER,
        highlightcolor=_ACCENT,
    )
    search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5, padx=(0, 8))

    tk.Label(
        tools, text="Filter", bg=_BG_PANEL, fg=_TEXT_SECONDARY, font=_FONT_SMALL
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
    type_combo.pack(side=tk.LEFT, ipady=2)
    type_combo.bind("<<ComboboxSelected>>", lambda _e: _refresh_list())

    def _show_search_placeholder() -> None:
        search_is_placeholder[0] = True
        search_entry.delete(0, tk.END)
        search_entry.insert(0, _SEARCH_PLACEHOLDER)
        search_entry.configure(fg=_TEXT_SECONDARY, bg=_BG_PANEL)

    def _begin_search_edit(_evt=None) -> None:
        if search_is_placeholder[0]:
            search_is_placeholder[0] = False
            search_entry.delete(0, tk.END)
            search_entry.configure(fg=_TEXT, bg=_BG_PANEL)

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

    # List
    list_frame = tk.Frame(
        side, bg=_BORDER, highlightthickness=0, bd=0
    )
    list_frame.pack(fill=tk.BOTH, expand=True)
    list_outer = tk.Frame(list_frame, bg=_BG_LIST)
    list_outer.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

    list_canvas = tk.Canvas(
        list_outer,
        highlightthickness=0,
        borderwidth=0,
        bg=_BG_LIST,
        takefocus=True,
    )
    list_scroll = ttk.Scrollbar(
        list_outer, orient=tk.VERTICAL, command=list_canvas.yview
    )
    list_inner = tk.Frame(list_canvas, bg=_BG_LIST)
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
    doc_card = tk.Frame(
        paned, bg=_BG_PANEL, highlightbackground=_BORDER, highlightthickness=1, bd=0
    )
    paned.add(doc_card, minsize=400, stretch="always")

    doc_pad = tk.Frame(doc_card, bg=_BG_PANEL, padx=12, pady=12)
    doc_pad.pack(fill=tk.BOTH, expand=True)

    doc_header = tk.Frame(doc_pad, bg=_BG_PANEL)
    doc_header.pack(fill=tk.X, pady=(0, 8))
    tk.Label(
        doc_header, text="Document", bg=_BG_PANEL, fg=_TEXT, font=_FONT_BOLD
    ).pack(side=tk.LEFT)
    tk.Label(
        doc_header,
        text="Yellow = redact  ·  blue = focused  ·  space / double-click toggles",
        bg=_BG_PANEL,
        fg=_TEXT_SECONDARY,
        font=_FONT_SMALL,
    ).pack(side=tk.RIGHT)

    text_border = tk.Frame(doc_pad, bg=_BORDER)
    text_border.pack(fill=tk.BOTH, expand=True)
    text_inner = tk.Frame(text_border, bg=_BG_PANEL)
    text_inner.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

    doc = tk.Text(
        text_inner,
        wrap=tk.WORD,
        font=_FONT_DOC,
        undo=False,
        padx=12,
        pady=12,
        bg=_BG_PANEL,
        fg=_TEXT,
        insertbackground=_TEXT,
        relief=tk.FLAT,
        highlightthickness=0,
        borderwidth=0,
        selectbackground=_HL_SELECTED_BG,
        selectforeground=_TEXT,
    )
    doc_scroll = ttk.Scrollbar(text_inner, orient=tk.VERTICAL, command=doc.yview)
    doc.configure(yscrollcommand=doc_scroll.set)
    doc.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    doc_scroll.pack(side=tk.RIGHT, fill=tk.Y)
    doc.bind("<Button-1>", lambda _e: doc.focus_set())

    doc.tag_configure(
        "hl_REDACT", background=_HL_REDACT_BG, foreground=_HL_REDACT_FG
    )
    doc.tag_configure(
        "hl_SELECTED", background=_HL_SELECTED_BG, foreground=_HL_SELECTED_FG
    )
    doc.tag_raise("hl_SELECTED")

    # Add toolbar
    add_bar = tk.Frame(
        doc_pad, bg=_BG_TOOLBAR, highlightbackground=_BORDER, highlightthickness=1
    )
    add_bar.pack(fill=tk.X, pady=(10, 0))
    add_inner = tk.Frame(add_bar, bg=_BG_TOOLBAR, padx=10, pady=8)
    add_inner.pack(fill=tk.X)
    tk.Label(
        add_inner,
        text="Add redaction",
        bg=_BG_TOOLBAR,
        fg=_TEXT_SECONDARY,
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

    # ── Footer (same white panel language as cards) ───────────────
    foot = tk.Frame(
        outer, bg=_BG_PANEL, highlightbackground=_BORDER, highlightthickness=1
    )
    foot.pack(fill=tk.X, pady=(_GAP, 0))
    foot_inner = tk.Frame(foot, bg=_BG_PANEL, padx=12, pady=10)
    foot_inner.pack(fill=tk.X)

    tk.Label(
        foot_inner,
        textvariable=status_var,
        bg=_BG_PANEL,
        fg=_TEXT,
        font=_FONT_BOLD,
        anchor=tk.W,
    ).pack(side=tk.LEFT, fill=tk.X, expand=True)

    act = tk.Frame(foot_inner, bg=_BG_PANEL)
    act.pack(side=tk.RIGHT)
    ttk.Button(act, text="Cancel", command=lambda: _on_close()).pack(
        side=tk.LEFT, padx=(0, 8)
    )
    ttk.Button(act, text="Save output", command=lambda: _on_save()).pack(side=tk.LEFT)

    tk.Label(
        outer,
        text=_shortcut_help_text(),
        bg=_BG_APP,
        fg=_TEXT_SECONDARY,
        font=_FONT_SMALL,
        anchor=tk.W,
        justify=tk.LEFT,
        wraplength=1060,
    ).pack(fill=tk.X, pady=(8, 0))

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
            bg = _BG_SELECTED if selected else _BG_LIST
            fg = _TEXT_DISABLED if (f and not f.enabled) else _TEXT
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
                h = list_inner.winfo_height() or 1
                list_canvas.yview_moveto(max(0.0, (y - 20) / max(h, 1)))
            except tk.TclError:
                pass
        _refresh_doc(scroll_to_selected=scroll_doc)

    def _make_row(parent: tk.Frame, f: ReviewFinding) -> dict:
        fr = tk.Frame(parent, bg=_BG_LIST)
        fr.pack(fill=tk.X)
        accent = tk.Frame(fr, bg=_BG_LIST, width=4)
        accent.pack(side=tk.LEFT, fill=tk.Y)
        accent.pack_propagate(False)

        label = tk.Label(
            fr,
            text=format_finding_label(f),
            anchor=tk.W,
            justify=tk.LEFT,
            font=_FONT_MONO,
            bg=_BG_LIST,
            fg=_TEXT if f.enabled else _TEXT_DISABLED,
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
                bg=_BG_LIST,
                fg=_TEXT_SECONDARY,
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
