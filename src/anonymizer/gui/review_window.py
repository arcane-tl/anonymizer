"""Interactive document review window (Tk): accept, reject, add redactions.

Used by CLI ``--review`` and the desktop GUI. Offline; no network.
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


# --- Readable colour system ---
# Document: soft fills + dark text (never dark-on-dark).
_HL_REDACT_BG = "#F6E05E"
_HL_REDACT_FG = "#1A202C"
_HL_SELECTED_BG = "#63B3ED"  # stronger light blue for focus
_HL_SELECTED_FG = "#1A202C"

# Sidebar list: white text on dark background (selected = slightly lighter)
_LIST_FG = "#FFFFFF"
_LIST_CLEAR_FG = "#A0AEC0"  # muted white-grey for keep-clear
_LIST_ROW_BG = "#1A202C"
_LIST_SEL_BG = "#2B6CB0"  # selected finding — blue, still white text
_LIST_SEL_FG = "#FFFFFF"

_CHROME_FG = "#4A5568"  # hints, shortcuts, search placeholder
_STATUS_BG = "#2D3748"  # totals strip
_STATUS_FG = "#FFFFFF"

_LIST_SNIPPET_MAX = 48
_SEARCH_PLACEHOLDER = "Search findings…"


def display_available() -> bool:
    """True if a GUI display can be opened for Tk."""
    if tk is None:
        return False
    if sys.platform == "darwin":
        return True
    if sys.platform == "win32":
        return True
    import os

    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def format_finding_label(f: ReviewFinding, *, max_original: int = _LIST_SNIPPET_MAX) -> str:
    """Label text without checkbox: ``[PERSON_1] — Tomi Lindroos`` (+ for user-added)."""
    origin = "+ " if f.source == "user" else ""
    snippet = f.original.replace("\n", " ").replace("\r", "")
    if len(snippet) > max_original:
        snippet = snippet[: max_original - 1] + "…"
    count = f" (×{f.occurrence_count})" if f.occurrence_count > 1 else ""
    return f"{origin}{f.placeholder} — {snippet}{count}"


# Back-compat alias for tests that imported the old name
def format_finding_row(f: ReviewFinding, *, max_original: int = _LIST_SNIPPET_MAX) -> str:
    """Include a simple [x]/[ ] prefix for pure-function tests."""
    mark = "[x]" if f.enabled else "[ ]"
    return f"{mark} {format_finding_label(f, max_original=max_original)}"


def _shortcut_help_text() -> str:
    save = "⌘↩ save" if sys.platform == "darwin" else "Ctrl+Enter save"
    return (
        "↑/↓ or j/k  move  ·  space / click checkbox  toggle redact  ·  "
        "double-click row  toggle  ·  "
        f"a  add selection  ·  {save}  ·  esc  cancel"
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
    root.minsize(960, 580)
    root.geometry("1120x700")

    selected_ph: list[str | None] = [None]
    filter_type = tk.StringVar(value="All")
    search_var = tk.StringVar(value="")
    preview_redacted = tk.BooleanVar(value=False)
    type_var = tk.StringVar(value="PERSON")
    status_var = tk.StringVar(value="")
    # Prevent search placeholder from filtering
    search_is_placeholder = [True]

    outer = ttk.Frame(root, padding=8)
    outer.pack(fill=tk.BOTH, expand=True)

    header = ttk.Frame(outer)
    header.pack(fill=tk.X, pady=(0, 6))
    ttk.Label(
        header,
        text=title,
        font=("Segoe UI", 13, "bold"),
    ).pack(side=tk.LEFT)
    ttk.Checkbutton(
        header,
        text="Preview redacted",
        variable=preview_redacted,
        command=lambda: _refresh_doc(),
    ).pack(side=tk.RIGHT)

    body = ttk.Panedwindow(outer, orient=tk.HORIZONTAL)
    body.pack(fill=tk.BOTH, expand=True)

    side = ttk.Frame(body, width=380)
    body.add(side, weight=1)

    # One row: Findings | search (expand, placeholder) | Filter combobox
    filt_row = ttk.Frame(side)
    filt_row.pack(fill=tk.X, pady=(0, 6))
    ttk.Label(filt_row, text="Findings").pack(side=tk.LEFT, padx=(0, 8))

    search_entry = ttk.Entry(filt_row)
    search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

    def _show_search_placeholder() -> None:
        search_is_placeholder[0] = True
        search_entry.delete(0, tk.END)
        search_entry.insert(0, _SEARCH_PLACEHOLDER)
        search_entry.configure(foreground=_CHROME_FG)

    def _hide_search_placeholder(_evt=None) -> None:
        if search_is_placeholder[0]:
            search_is_placeholder[0] = False
            search_entry.delete(0, tk.END)
            search_entry.configure(foreground="#1A202C")

    def _on_search_focus_out(_evt=None) -> None:
        if not search_entry.get().strip():
            _show_search_placeholder()

    def _search_query() -> str:
        if search_is_placeholder[0]:
            return ""
        return search_entry.get().strip()

    search_entry.bind("<FocusIn>", _hide_search_placeholder)
    search_entry.bind("<FocusOut>", _on_search_focus_out)
    search_entry.bind("<KeyRelease>", lambda _e: _on_search_changed())
    _show_search_placeholder()

    type_values = ["All"] + sorted(
        {f.type_label for f in session.findings} | {"PERSON", "ORG", "CUSTOM"}
    )
    ttk.Label(filt_row, text="Filter").pack(side=tk.LEFT, padx=(0, 4))
    type_combo = ttk.Combobox(
        filt_row,
        textvariable=filter_type,
        values=type_values,
        width=11,
        state="readonly",
    )
    type_combo.pack(side=tk.LEFT)
    type_combo.bind("<<ComboboxSelected>>", lambda _e: _refresh_list())

    # Scrollable checklist (native checkboxes)
    list_outer = ttk.Frame(side)
    list_outer.pack(fill=tk.BOTH, expand=True)
    list_canvas = tk.Canvas(
        list_outer, highlightthickness=0, borderwidth=0, bg=_LIST_ROW_BG
    )
    list_scroll = ttk.Scrollbar(
        list_outer, orient=tk.VERTICAL, command=list_canvas.yview
    )
    list_inner = ttk.Frame(list_canvas)
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
        # macOS: event.delta; Linux: Button-4/5 handled separately if needed
        if sys.platform == "darwin":
            list_canvas.yview_scroll(int(-1 * event.delta), "units")
        else:
            list_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    list_canvas.bind_all("<MouseWheel>", _on_mousewheel)

    visible_ph: list[str] = []
    # placeholder -> row widgets
    row_widgets: dict[str, dict] = {}
    # suppress checkbox command feedback loops during rebuild
    rebuild_lock = [False]

    legend = ttk.Label(
        side,
        text="☑ Redact   ☐ Keep clear   ·  click checkbox or double-click row",
        foreground=_CHROME_FG,
        font=("Segoe UI", 9),
    )
    legend.pack(fill=tk.X, pady=(6, 0))

    doc_frame = ttk.Frame(body)
    body.add(doc_frame, weight=3)

    hint = ttk.Label(
        doc_frame,
        text=(
            "Yellow = will be redacted. Light blue = selected finding. "
            "Uncheck a finding to keep it clear. "
            "Select missed text in the document → choose type → Add redaction."
        ),
        wraplength=720,
        foreground=_CHROME_FG,
    )
    hint.pack(anchor=tk.W, pady=(0, 4))

    text_wrap = ttk.Frame(doc_frame)
    text_wrap.pack(fill=tk.BOTH, expand=True)
    doc = tk.Text(
        text_wrap,
        wrap=tk.WORD,
        font=("Menlo", 12) if sys.platform == "darwin" else ("Consolas", 11),
        undo=False,
        padx=8,
        pady=8,
    )
    doc_scroll = ttk.Scrollbar(text_wrap, orient=tk.VERTICAL, command=doc.yview)
    doc.configure(yscrollcommand=doc_scroll.set)
    doc.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    doc_scroll.pack(side=tk.RIGHT, fill=tk.Y)

    doc.tag_configure(
        "hl_REDACT",
        background=_HL_REDACT_BG,
        foreground=_HL_REDACT_FG,
    )
    doc.tag_configure(
        "hl_SELECTED",
        background=_HL_SELECTED_BG,
        foreground=_HL_SELECTED_FG,
    )
    doc.tag_raise("hl_SELECTED")

    add_row = ttk.Frame(doc_frame)
    add_row.pack(fill=tk.X, pady=6)
    ttk.Label(add_row, text="Redact selection as").pack(side=tk.LEFT)
    type_menu = ttk.Combobox(
        add_row,
        textvariable=type_var,
        values=[t[0] for t in REVIEW_ADD_TYPES],
        width=16,
        state="readonly",
    )
    type_menu.pack(side=tk.LEFT, padx=6)
    ttk.Button(add_row, text="Add redaction", command=lambda: _add_selection()).pack(
        side=tk.LEFT, padx=4
    )

    foot = ttk.Frame(outer)
    foot.pack(fill=tk.X, pady=(8, 0))

    # Totals report: dark bar + white text so counts stand out
    status_bar = tk.Frame(foot, bg=_STATUS_BG, padx=10, pady=6)
    status_bar.pack(fill=tk.X)
    status_label = tk.Label(
        status_bar,
        textvariable=status_var,
        bg=_STATUS_BG,
        fg=_STATUS_FG,
        font=("Segoe UI", 11, "bold"),
        anchor=tk.W,
    )
    status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

    actions_row = ttk.Frame(foot)
    actions_row.pack(fill=tk.X, pady=(8, 0))
    right = ttk.Frame(actions_row)
    right.pack(side=tk.RIGHT)
    ttk.Button(right, text="Cancel", command=lambda: _cancel()).pack(
        side=tk.LEFT, padx=(0, 8)
    )
    ttk.Button(right, text="Save output", command=lambda: _save()).pack(side=tk.LEFT)

    shortcuts_row = ttk.Frame(foot)
    shortcuts_row.pack(fill=tk.X, pady=(6, 0))
    ttk.Label(
        shortcuts_row,
        text=_shortcut_help_text(),
        foreground=_CHROME_FG,
        wraplength=1080,
    ).pack(anchor=tk.W)

    def _status() -> None:
        c = session.summary_counts()
        status_var.set(
            f"{c['redact']} redacting · {c['keep_clear']} keep clear · "
            f"{c['user_added']} added by you · {c['total']} total"
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

    def _on_search_changed() -> None:
        if search_is_placeholder[0]:
            return
        search_var.set(search_entry.get())
        _refresh_list()

    def _style_row_selected(ph: str | None) -> None:
        """Selected list row: light blue bg + dark text (never black-on-black)."""
        for key, rw in row_widgets.items():
            f = session.get(key)
            selected = key == ph
            bg = _LIST_SEL_BG if selected else _LIST_ROW_BG
            if f and not f.enabled:
                fg = _LIST_CLEAR_FG
            else:
                fg = _LIST_SEL_FG if selected else _LIST_FG
            try:
                rw["frame"].configure(bg=bg)
                rw["label"].configure(bg=bg, fg=fg)
            except tk.TclError:
                pass

    def _set_enabled(ph: str, enabled: bool, *, from_checkbox: bool = False) -> None:
        session.set_enabled(ph, enabled)
        selected_ph[0] = ph
        if not from_checkbox and ph in row_widgets:
            rebuild_lock[0] = True
            try:
                row_widgets[ph]["var"].set(enabled)
            finally:
                rebuild_lock[0] = False
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
        _style_row_selected(ph)
        # Ensure row visible in canvas
        rw = row_widgets.get(ph)
        if rw:
            try:
                list_canvas.update_idletasks()
                y = rw["frame"].winfo_y()
                h = list_inner.winfo_height() or 1
                ch = list_canvas.winfo_height() or 1
                # fraction so row is in view
                list_canvas.yview_moveto(max(0.0, (y - 20) / max(h, 1)))
            except tk.TclError:
                pass
        _refresh_doc(scroll_to_selected=scroll_doc)

    def _make_row(parent: ttk.Frame, f: ReviewFinding) -> dict:
        # tk.Frame + tk.Label so selected row can use a real light-blue background
        fr = tk.Frame(parent, bg=_LIST_ROW_BG, padx=2, pady=2)
        fr.pack(fill=tk.X, pady=1, padx=2)

        var = tk.BooleanVar(value=f.enabled)

        def on_check() -> None:
            if rebuild_lock[0]:
                return
            _set_enabled(f.placeholder, bool(var.get()), from_checkbox=True)

        cb = ttk.Checkbutton(fr, variable=var, command=on_check)
        cb.pack(side=tk.LEFT, padx=(4, 6))

        label = tk.Label(
            fr,
            text=format_finding_label(f),
            anchor=tk.W,
            justify=tk.LEFT,
            font=("Menlo", 11) if sys.platform == "darwin" else ("Consolas", 10),
            bg=_LIST_ROW_BG,
            fg=_LIST_FG if f.enabled else _LIST_CLEAR_FG,
            cursor="hand2",
        )
        label.pack(side=tk.LEFT, fill=tk.X, expand=True, pady=2)

        def select_me(_e=None) -> None:
            _focus_ph(f.placeholder, scroll_doc=True)

        def toggle_me(_e=None) -> str:
            _toggle_ph(f.placeholder)
            return "break"

        label.bind("<Button-1>", select_me)
        label.bind("<Double-Button-1>", toggle_me)
        fr.bind("<Button-1>", select_me)
        fr.bind("<Double-Button-1>", toggle_me)
        cb.bind(
            "<Button-1>",
            lambda _e: selected_ph.__setitem__(0, f.placeholder),
        )

        return {"frame": fr, "var": var, "label": label, "cb": cb}

    def _refresh_list(
        select_ph: str | None = None, *, refresh_doc: bool = True
    ) -> None:
        rebuild_lock[0] = True
        try:
            for child in list_inner.winfo_children():
                child.destroy()
            row_widgets.clear()
            visible_ph.clear()

            for f in _filtered_findings():
                rw = _make_row(list_inner, f)
                row_widgets[f.placeholder] = rw
                visible_ph.append(f.placeholder)

            list_inner.update_idletasks()
            list_canvas.configure(scrollregion=list_canvas.bbox("all"))
        finally:
            rebuild_lock[0] = False

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
            doc.tag_add(f"ph::{f.placeholder}", idx, end)
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
                "Select text in the document first, then click Add redaction.",
                parent=root,
            )
            return "break"
        surface = sel_text
        if not surface.strip():
            return "break"
        if len(surface.strip()) > 500:
            if not messagebox.askyesno(
                "Long selection",
                f"Redact {len(surface.strip())} characters as one finding?",
                parent=root,
            ):
                return "break"
        ent = type_var.get().strip() or "CUSTOM"
        try:
            finding = session.add_redaction(surface, ent)
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

    def _nav(delta: int) -> str:
        if not visible_ph:
            return "break"
        idx = _current_list_index() + delta
        _focus_index(idx, scroll_doc=True)
        return "break"

    def _nav_if_not_typing(delta: int, event=None) -> str | None:
        if _is_text_input_focused():
            return None
        return _nav(delta)

    # Keyboard: bind on root when not typing; also on list canvas
    root.bind("<space>", lambda e: _toggle_selected(e))
    root.bind("<Escape>", lambda _e: _cancel())
    root.bind(
        "<Command-Return>" if sys.platform == "darwin" else "<Control-Return>",
        lambda _e: _save(),
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

    def _cleanup_bindings() -> None:
        try:
            list_canvas.unbind_all("<MouseWheel>")
        except tk.TclError:
            pass

    def _on_close() -> None:
        _cleanup_bindings()
        _cancel()

    def _on_save_wrap() -> None:
        _cleanup_bindings()
        _save()

    # Rebind action buttons to cleanup mousewheel on close/save
    for child in right.winfo_children():
        child.destroy()
    ttk.Button(right, text="Cancel", command=_on_close).pack(side=tk.LEFT, padx=(0, 8))
    ttk.Button(right, text="Save output", command=_on_save_wrap).pack(side=tk.LEFT)

    root.protocol("WM_DELETE_WINDOW", _on_close)

    _refresh_list(refresh_doc=True)
    if visible_ph:
        _focus_index(0, scroll_doc=True)

    list_canvas.focus_set()
    root.lift()
    try:
        root.attributes("-topmost", True)
        root.after(200, lambda: root.attributes("-topmost", False))
    except tk.TclError:
        pass

    root.mainloop()
    _cleanup_bindings()
    return result["session"]
