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


# --- Readable colour system (light theme, dark text always) ---
# Document: soft fills + near-black text (never white-on-colour — unreadable on prose).
# Keep clear = no document mark.
_HL_REDACT_BG = "#F6E05E"  # clear but soft yellow — high contrast with dark text
_HL_REDACT_FG = "#1A202C"  # near-black
_HL_SELECTED_BG = "#90CDF4"  # light blue — selected finding still readable
_HL_SELECTED_FG = "#1A202C"

# Sidebar: system selection handles focus; we only dim “keep clear”.
# User-added uses same ink as auto + “+” prefix (green fg fights list selection).
_LIST_AUTO_FG = "#1A202C"
_LIST_USER_FG = "#1A202C"
_LIST_CLEAR_FG = "#718096"  # muted gray for ☐ rows
_CHROME_FG = "#4A5568"

_LIST_SNIPPET_MAX = 48


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


def format_finding_row(f: ReviewFinding, *, max_original: int = _LIST_SNIPPET_MAX) -> str:
    """Sidebar line: ``☑ [PERSON_1] — Tomi Lindroos`` (or with ×N / +)."""
    check = "☑" if f.enabled else "☐"
    origin = "+" if f.source == "user" else " "
    snippet = f.original.replace("\n", " ").replace("\r", "")
    if len(snippet) > max_original:
        snippet = snippet[: max_original - 1] + "…"
    count = f" (×{f.occurrence_count})" if f.occurrence_count > 1 else ""
    return f"{check}{origin} {f.placeholder} — {snippet}{count}"


def _shortcut_help_text() -> str:
    save = "⌘↩ save" if sys.platform == "darwin" else "Ctrl+Enter save"
    return (
        "↑/↓ or j/k  move  ·  space  keep clear / redact  ·  "
        f"a  add selection  ·  {save}  ·  esc  cancel"
    )


def run_review_window(
    session: ReviewSession,
    *,
    file_label: str | None = None,
    on_allowlist: Callable[[str], None] | None = None,
    on_denylist: Callable[[str, str], None] | None = None,
) -> ReviewSession | None:
    """Open the review UI. Returns session on Save, ``None`` on Cancel.

    Blocks until the window is closed.
    """
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

    side = ttk.Frame(body, width=360)
    body.add(side, weight=1)

    filt_row = ttk.Frame(side)
    filt_row.pack(fill=tk.X, pady=(0, 4))
    ttk.Label(filt_row, text="Findings").pack(side=tk.LEFT)
    type_values = ["All"] + sorted(
        {f.type_label for f in session.findings} | {"PERSON", "ORG", "CUSTOM"}
    )
    type_combo = ttk.Combobox(
        filt_row,
        textvariable=filter_type,
        values=type_values,
        width=12,
        state="readonly",
    )
    type_combo.pack(side=tk.RIGHT, padx=4)
    ttk.Label(filt_row, text="Filter").pack(side=tk.RIGHT)
    type_combo.bind("<<ComboboxSelected>>", lambda _e: _refresh_list())

    search_entry = ttk.Entry(side, textvariable=search_var)
    search_entry.pack(fill=tk.X, pady=(0, 4))
    search_var.trace_add("write", lambda *_: _refresh_list())

    list_frame = ttk.Frame(side)
    list_frame.pack(fill=tk.BOTH, expand=True)
    listbox = tk.Listbox(
        list_frame,
        font=("Menlo", 11) if sys.platform == "darwin" else ("Consolas", 10),
        activestyle="dotbox",
        exportselection=False,
        width=42,
    )
    scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=listbox.yview)
    listbox.configure(yscrollcommand=scroll.set)
    listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scroll.pack(side=tk.RIGHT, fill=tk.Y)

    visible_ph: list[str] = []

    side_btns = ttk.Frame(side)
    side_btns.pack(fill=tk.X, pady=6)
    ttk.Button(
        side_btns, text="Keep clear", command=lambda: _set_selected(False)
    ).pack(side=tk.LEFT, padx=(0, 4))
    ttk.Button(
        side_btns, text="Redact", command=lambda: _set_selected(True)
    ).pack(side=tk.LEFT)

    doc_frame = ttk.Frame(body)
    body.add(doc_frame, weight=3)

    hint = ttk.Label(
        doc_frame,
        text=(
            "Yellow = will be redacted. Light blue = selected in the list. "
            "Keep clear removes the highlight (plain text). "
            "Select missed text → Add redaction. “+” in the list = you added."
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

    status_row = ttk.Frame(foot)
    status_row.pack(fill=tk.X)
    ttk.Label(status_row, textvariable=status_var, foreground="#44403C").pack(
        side=tk.LEFT
    )
    right = ttk.Frame(status_row)
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
        q = search_var.get().strip().casefold()
        ft = filter_type.get()
        out: list[ReviewFinding] = []
        for f in session.findings:
            if ft != "All" and f.type_label != ft:
                continue
            if q and q not in f.original.casefold() and q not in f.placeholder.casefold():
                continue
            out.append(f)
        return out

    def _style_list_row(index: int, f: ReviewFinding) -> None:
        """Only mute keep-clear rows; enabled rows use default system colours."""
        if not f.enabled:
            listbox.itemconfig(index, foreground=_LIST_CLEAR_FG)
        # User-added is marked with “+” in the label, not a special ink colour.

    def _refresh_list(
        select_ph: str | None = None, *, refresh_doc: bool = True
    ) -> None:
        listbox.delete(0, tk.END)
        visible_ph.clear()
        for f in _filtered_findings():
            listbox.insert(tk.END, format_finding_row(f))
            visible_ph.append(f.placeholder)
            _style_list_row(tk.END, f)
        _status()
        target = select_ph or selected_ph[0]
        if target and target in visible_ph:
            idx = visible_ph.index(target)
            listbox.selection_clear(0, tk.END)
            listbox.selection_set(idx)
            listbox.activate(idx)
            listbox.see(idx)
            selected_ph[0] = target
        elif visible_ph:
            # Filter hid the previous selection — focus first visible row
            selected_ph[0] = visible_ph[0]
            listbox.selection_clear(0, tk.END)
            listbox.selection_set(0)
            listbox.activate(0)
            listbox.see(0)
        else:
            selected_ph[0] = None
            listbox.selection_clear(0, tk.END)
        if refresh_doc:
            # Document highlights follow the same filter as the list
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
            # Preview always shows full apply (filter is review-UI only)
            blocks, _ = session.apply(style="placeholder")
            doc.insert("1.0", "\n\n".join(blocks))
            doc.configure(state=tk.DISABLED)
            _status()
            return

        doc.insert("1.0", "\n\n".join(session.original_blocks))

        # Only highlight findings visible under current filter/search
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
        sel = listbox.curselection()
        if sel:
            return max(0, min(int(sel[0]), len(visible_ph) - 1))
        return 0

    def _focus_index(idx: int, *, scroll_doc: bool = True) -> None:
        if not visible_ph:
            return
        idx = max(0, min(idx, len(visible_ph) - 1))
        ph = visible_ph[idx]
        selected_ph[0] = ph
        listbox.selection_clear(0, tk.END)
        listbox.selection_set(idx)
        listbox.activate(idx)
        listbox.see(idx)
        _refresh_doc(scroll_to_selected=scroll_doc)

    def _on_list_select(_evt=None) -> None:
        sel = listbox.curselection()
        if not sel:
            return
        idx = int(sel[0])
        if idx < 0 or idx >= len(visible_ph):
            return
        selected_ph[0] = visible_ph[idx]
        listbox.activate(idx)
        _refresh_doc(scroll_to_selected=True)

    def _set_selected(enabled: bool) -> None:
        ph = selected_ph[0]
        if not ph:
            sel = listbox.curselection()
            if sel and int(sel[0]) < len(visible_ph):
                ph = visible_ph[int(sel[0])]
        if not ph:
            return
        session.set_enabled(ph, enabled)
        _refresh_list(select_ph=ph, refresh_doc=False)
        _refresh_doc(scroll_to_selected=True)

    def _is_text_input_focused() -> bool:
        """True when keystrokes should go to search / combobox, not shortcuts."""
        w = root.focus_get()
        if w is None:
            return False
        if w is search_entry or w is type_menu or w is type_combo:
            return True
        # ttk.Entry / Combobox internal children (macOS)
        try:
            if w == search_entry or str(w).startswith(str(search_entry)):
                return True
        except tk.TclError:
            pass
        cls = w.winfo_class()
        if cls in {"TEntry", "Entry", "TCombobox", "Combobox"}:
            return True
        # Walk parents — focus is often an inner entry of Combobox
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
            return None  # allow space in search box
        ph = selected_ph[0]
        if not ph:
            sel = listbox.curselection()
            if sel and int(sel[0]) < len(visible_ph):
                ph = visible_ph[int(sel[0])]
        if ph:
            session.toggle(ph)
            _refresh_list(select_ph=ph, refresh_doc=False)
            _refresh_doc(scroll_to_selected=True)
        return "break"

    def _add_selection(_evt=None) -> str | None:
        if _is_text_input_focused():
            return None  # type “a” into search normally
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
        # Ensure filter still shows the new row
        if filter_type.get() not in {"All", finding.type_label}:
            filter_type.set("All")
        selected_ph[0] = finding.placeholder
        _refresh_list(select_ph=finding.placeholder, refresh_doc=False)
        _refresh_doc(scroll_to_selected=True)
        listbox.focus_set()
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
        """j/k from root: ignore when typing in search or combobox."""
        if _is_text_input_focused():
            return None
        return _nav(delta)

    def _shortcut_space(_evt=None) -> str | None:
        return _toggle_selected(_evt)

    def _shortcut_add(_evt=None) -> str | None:
        return _add_selection(_evt)

    listbox.bind("<<ListboxSelect>>", _on_list_select)
    # Listbox owns arrow keys (break default so we don't double-step with root)
    listbox.bind("<Down>", lambda _e: _nav(1))
    listbox.bind("<Up>", lambda _e: _nav(-1))
    listbox.bind("j", lambda _e: _nav(1))
    listbox.bind("k", lambda _e: _nav(-1))
    listbox.bind("<space>", _toggle_selected)
    listbox.bind("a", _add_selection)
    listbox.bind("A", _add_selection)

    # Root shortcuts only when not typing in search / filter combobox
    root.bind("<space>", _shortcut_space)
    root.bind("<Escape>", lambda _e: _cancel())
    root.bind(
        "<Command-Return>" if sys.platform == "darwin" else "<Control-Return>",
        lambda _e: _save(),
    )
    # j/k / a from document focus etc.; never bind root Up/Down (fights Listbox)
    root.bind("j", lambda e: _nav_if_not_typing(1, e))
    root.bind("k", lambda e: _nav_if_not_typing(-1, e))
    root.bind("a", _shortcut_add)
    root.bind("A", _shortcut_add)

    root.protocol("WM_DELETE_WINDOW", _cancel)

    # Initial list build also paints doc for visible findings only
    _refresh_list(refresh_doc=True)
    if visible_ph:
        _focus_index(0, scroll_doc=True)

    listbox.focus_set()
    root.lift()
    try:
        root.attributes("-topmost", True)
        root.after(200, lambda: root.attributes("-topmost", False))
    except tk.TclError:
        pass

    root.mainloop()
    return result["session"]
