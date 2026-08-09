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


# Document highlights: one colour for all redactions + one for list selection.
_HL_REDACT_BG = "#f5e6c8"  # soft amber — readable on light theme
_HL_REDACT_FG = "#1a1a1a"
_HL_SELECTED_BG = "#2f6fed"  # clear focus blue
_HL_SELECTED_FG = "#ffffff"
_HL_KEEP_CLEAR_BG = "#e8e8e8"
_HL_KEEP_CLEAR_FG = "#555555"

_LIST_SNIPPET_MAX = 48


def display_available() -> bool:
    """True if a GUI display can be opened for Tk."""
    if tk is None:
        return False
    if sys.platform == "darwin":
        return True
    if sys.platform == "win32":
        return True
    # Linux: need DISPLAY
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

    # --- state ---
    selected_ph: list[str | None] = [None]
    filter_type = tk.StringVar(value="All")
    search_var = tk.StringVar(value="")
    preview_redacted = tk.BooleanVar(value=False)
    type_var = tk.StringVar(value="PERSON")
    status_var = tk.StringVar(value="")

    # --- layout ---
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

    # Sidebar (a bit wider for “[TAG] — original”)
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

    ttk.Entry(side, textvariable=search_var).pack(fill=tk.X, pady=(0, 4))
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

    # visible placeholders order matching listbox
    visible_ph: list[str] = []

    side_btns = ttk.Frame(side)
    side_btns.pack(fill=tk.X, pady=6)
    ttk.Button(
        side_btns, text="Keep clear", command=lambda: _set_selected(False)
    ).pack(side=tk.LEFT, padx=(0, 4))
    ttk.Button(
        side_btns, text="Redact", command=lambda: _set_selected(True)
    ).pack(side=tk.LEFT)

    # Document pane
    doc_frame = ttk.Frame(body)
    body.add(doc_frame, weight=3)

    hint = ttk.Label(
        doc_frame,
        text=(
            "Soft highlight = will be redacted. Blue = selected finding (from the list). "
            "Keep clear leaves text visible. Select missed text → Add redaction."
        ),
        wraplength=720,
        foreground="#555",
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

    # Three semantic highlight tags only
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
    doc.tag_configure(
        "hl_KEEP_CLEAR",
        background=_HL_KEEP_CLEAR_BG,
        foreground=_HL_KEEP_CLEAR_FG,
        overstrike=True,
    )
    # Selection must paint above general redact marks
    doc.tag_raise("hl_SELECTED")
    doc.tag_raise("hl_KEEP_CLEAR")

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

    # Footer: status + always-visible shortcuts + actions
    foot = ttk.Frame(outer)
    foot.pack(fill=tk.X, pady=(8, 0))

    status_row = ttk.Frame(foot)
    status_row.pack(fill=tk.X)
    ttk.Label(status_row, textvariable=status_var, foreground="#444").pack(side=tk.LEFT)
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
        foreground="#555",
        wraplength=1080,
    ).pack(anchor=tk.W)

    def _status() -> None:
        c = session.summary_counts()
        status_var.set(
            f"{c['redact']} redacting · {c['keep_clear']} keep clear · "
            f"{c['user_added']} added by you · {c['total']} total"
        )

    def _filtered_findings():
        q = search_var.get().strip().casefold()
        ft = filter_type.get()
        out = []
        for f in session.findings:
            if ft != "All" and f.type_label != ft:
                continue
            if q and q not in f.original.casefold() and q not in f.placeholder.casefold():
                continue
            out.append(f)
        return out

    def _refresh_list(select_ph: str | None = None) -> None:
        listbox.delete(0, tk.END)
        visible_ph.clear()
        for f in _filtered_findings():
            listbox.insert(tk.END, format_finding_row(f))
            visible_ph.append(f.placeholder)
            if not f.enabled:
                listbox.itemconfig(tk.END, foreground="#888")
            elif f.source == "user":
                listbox.itemconfig(tk.END, foreground="#6b4f00")
        _status()
        if select_ph and select_ph in visible_ph:
            idx = visible_ph.index(select_ph)
            listbox.selection_clear(0, tk.END)
            listbox.selection_set(idx)
            listbox.see(idx)
            selected_ph[0] = select_ph

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

    def _refresh_doc() -> None:
        # Preserve scroll position across rehighlight
        try:
            yview = doc.yview()
        except tk.TclError:
            yview = (0.0, 1.0)

        doc.configure(state=tk.NORMAL)
        doc.delete("1.0", tk.END)
        if preview_redacted.get():
            blocks, _ = session.apply(style="placeholder")
            text = "\n\n".join(blocks)
            doc.insert("1.0", text)
            doc.configure(state=tk.DISABLED)
            _status()
            return

        text = "\n\n".join(session.original_blocks)
        doc.insert("1.0", text)

        # 1) All enabled redactions — one shared colour (longest first)
        ordered = sorted(
            (f for f in session.findings if f.enabled),
            key=lambda f: len(f.original),
            reverse=True,
        )
        for f in ordered:
            _paint_finding(f, "hl_REDACT")

        # 2) Selected finding — focus colour on top
        sel = selected_ph[0]
        if sel:
            f_sel = session.get(sel)
            if f_sel and f_sel.enabled:
                _paint_finding(f_sel, "hl_SELECTED")

        # 3) Keep-clear (false positives) — muted + strike
        for f in session.findings:
            if not f.enabled:
                _paint_finding(f, "hl_KEEP_CLEAR")

        doc.configure(state=tk.NORMAL)  # allow selection for add
        try:
            doc.yview_moveto(yview[0])
        except tk.TclError:
            pass
        _status()

    def _on_list_select(_evt=None) -> None:
        sel = listbox.curselection()
        if not sel:
            return
        ph = visible_ph[sel[0]]
        selected_ph[0] = ph
        f = session.get(ph)
        if not f or not f.original:
            _refresh_doc()
            return
        _refresh_doc()
        # Scroll document to first occurrence of the focused finding
        doc.configure(state=tk.NORMAL)
        idx = doc.search(f.original, "1.0", stopindex=tk.END)
        if idx:
            doc.see(idx)
            doc.mark_set(tk.INSERT, idx)

    def _set_selected(enabled: bool) -> None:
        ph = selected_ph[0]
        if not ph:
            sel = listbox.curselection()
            if sel:
                ph = visible_ph[sel[0]]
        if not ph:
            return
        session.set_enabled(ph, enabled)
        _refresh_list(select_ph=ph)
        _refresh_doc()

    def _toggle_selected(_evt=None) -> str:
        ph = selected_ph[0]
        if not ph:
            sel = listbox.curselection()
            if sel:
                ph = visible_ph[sel[0]]
        if ph:
            session.toggle(ph)
            _refresh_list(select_ph=ph)
            _refresh_doc()
        return "break"

    def _add_selection() -> None:
        try:
            sel_text = doc.get(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            messagebox.showinfo(
                "Add redaction",
                "Select text in the document first, then click Add redaction.",
                parent=root,
            )
            return
        surface = sel_text.strip()
        if not surface:
            return
        if len(surface) > 500:
            if not messagebox.askyesno(
                "Long selection",
                f"Redact {len(surface)} characters as one finding?",
                parent=root,
            ):
                return
        ent = type_var.get().strip() or "CUSTOM"
        try:
            finding = session.add_redaction(surface, ent)
        except ValueError as exc:
            messagebox.showerror("Add redaction", str(exc), parent=root)
            return
        type_combo.configure(
            values=["All"]
            + sorted({f.type_label for f in session.findings} | {"PERSON", "ORG"})
        )
        _refresh_list(select_ph=finding.placeholder)
        _refresh_doc()

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

    def _on_close() -> None:
        _cancel()

    listbox.bind("<<ListboxSelect>>", _on_list_select)
    listbox.bind("<space>", _toggle_selected)
    root.bind("<space>", _toggle_selected)
    root.bind("<Escape>", lambda _e: _cancel())
    root.bind(
        "<Command-Return>" if sys.platform == "darwin" else "<Control-Return>",
        lambda _e: _save(),
    )
    root.bind("a", lambda _e: _add_selection())
    root.bind("A", lambda _e: _add_selection())

    def _nav(delta: int) -> str:
        if not visible_ph:
            return "break"
        sel = listbox.curselection()
        idx = int(sel[0]) if sel else 0
        idx = max(0, min(len(visible_ph) - 1, idx + delta))
        listbox.selection_clear(0, tk.END)
        listbox.selection_set(idx)
        listbox.see(idx)
        selected_ph[0] = visible_ph[idx]
        _on_list_select()
        return "break"

    root.bind("j", lambda _e: _nav(1))
    root.bind("k", lambda _e: _nav(-1))
    root.bind("<Down>", lambda _e: _nav(1))
    root.bind("<Up>", lambda _e: _nav(-1))

    root.protocol("WM_DELETE_WINDOW", _on_close)

    # Select first finding by default so blue focus is visible immediately
    _refresh_list()
    if visible_ph:
        listbox.selection_set(0)
        selected_ph[0] = visible_ph[0]
    _refresh_doc()
    if selected_ph[0]:
        f0 = session.get(selected_ph[0])
        if f0 and f0.original:
            idx = doc.search(f0.original, "1.0", stopindex=tk.END)
            if idx:
                doc.see(idx)

    root.lift()
    try:
        root.attributes("-topmost", True)
        root.after(200, lambda: root.attributes("-topmost", False))
    except tk.TclError:
        pass

    root.mainloop()
    return result["session"]
