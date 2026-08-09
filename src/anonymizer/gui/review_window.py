"""Interactive document review window (Tk): accept, reject, add redactions.

Used by CLI ``--review`` and the desktop GUI. Offline; no network.
"""

from __future__ import annotations

import sys
from typing import Callable

from anonymizer.anonymize.review import REVIEW_ADD_TYPES, ReviewSession

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except ImportError:  # pragma: no cover
    tk = None  # type: ignore[assignment]


# Highlight colors (light theme)
_TAG_COLORS = {
    "PERSON": "#f9e2af",
    "ORG": "#cba6f7",
    "EMAIL": "#a6e3a1",
    "PHONE": "#94e2d5",
    "STREET": "#89b4fa",
    "CITY": "#89b4fa",
    "LOCATION": "#89dceb",
    "DEFAULT": "#f2cdcd",
    "USER": "#fab387",
    "KEEP_CLEAR": "#6c7086",
}


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
    root.minsize(900, 560)
    root.geometry("1100x680")

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

    # Sidebar
    side = ttk.Frame(body, width=320)
    body.add(side, weight=1)

    filt_row = ttk.Frame(side)
    filt_row.pack(fill=tk.X, pady=(0, 4))
    ttk.Label(filt_row, text="Filter").pack(side=tk.LEFT)
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
    type_combo.pack(side=tk.LEFT, padx=4)
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
            "Yellow/coloured marks = will redact. Uncheck mistakes (Keep clear). "
            "Select missed text → choose type → Add redaction."
        ),
        wraplength=700,
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

    # Configure tags
    for key, color in _TAG_COLORS.items():
        if key == "KEEP_CLEAR":
            doc.tag_configure(
                f"hl_{key}",
                background="#e6e6e6",
                foreground="#444",
                overstrike=True,
            )
        elif key == "USER":
            doc.tag_configure(
                f"hl_{key}",
                background=color,
                borderwidth=2,
                relief=tk.SOLID,
            )
        else:
            doc.tag_configure(f"hl_{key}", background=color)

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
    # Human labels in dropdown via map — keep entity codes for simplicity
    ttk.Button(add_row, text="Add redaction", command=lambda: _add_selection()).pack(
        side=tk.LEFT, padx=4
    )

    # Footer
    foot = ttk.Frame(outer)
    foot.pack(fill=tk.X, pady=(8, 0))
    ttk.Label(foot, textvariable=status_var, foreground="#444").pack(side=tk.LEFT)

    right = ttk.Frame(foot)
    right.pack(side=tk.RIGHT)
    ttk.Button(right, text="Cancel", command=lambda: _cancel()).pack(
        side=tk.LEFT, padx=(0, 8)
    )
    ttk.Button(right, text="Save output", command=lambda: _save()).pack(side=tk.LEFT)

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
            mark = "☑" if f.enabled else "☐"
            origin = "+" if f.source == "user" else " "
            count = f"×{f.occurrence_count}" if f.occurrence_count > 1 else "  "
            snippet = f.original.replace("\n", " ")
            if len(snippet) > 42:
                snippet = snippet[:41] + "…"
            line = f"{mark}{origin} {f.placeholder:14} {count}  {snippet}"
            listbox.insert(tk.END, line)
            visible_ph.append(f.placeholder)
            if not f.enabled:
                listbox.itemconfig(tk.END, foreground="#888")
            elif f.source == "user":
                listbox.itemconfig(tk.END, foreground="#b35c00")
        _status()
        if select_ph and select_ph in visible_ph:
            idx = visible_ph.index(select_ph)
            listbox.selection_clear(0, tk.END)
            listbox.selection_set(idx)
            listbox.see(idx)
            selected_ph[0] = select_ph

    def _hl_tag_for(f) -> str:
        if not f.enabled:
            return "hl_KEEP_CLEAR"
        if f.source == "user":
            return "hl_USER"
        lab = f.type_label
        if lab in _TAG_COLORS:
            return f"hl_{lab}"
        for prefix in ("PERSON", "ORG", "EMAIL", "PHONE", "STREET", "CITY", "LOCATION"):
            if lab.startswith(prefix):
                return f"hl_{prefix}"
        return "hl_DEFAULT"

    def _refresh_doc() -> None:
        doc.configure(state=tk.NORMAL)
        doc.delete("1.0", tk.END)
        if preview_redacted.get():
            blocks, _ = session.apply(style="placeholder")
            text = "\n\n".join(blocks)
            doc.insert("1.0", text)
            doc.configure(state=tk.DISABLED)
            return

        text = "\n\n".join(session.original_blocks)
        doc.insert("1.0", text)

        # Apply highlights: enabled findings first by length so longer wins visually
        ordered = sorted(
            session.findings,
            key=lambda f: len(f.original),
            reverse=True,
        )
        for f in ordered:
            if not f.original:
                continue
            start = "1.0"
            tag = _hl_tag_for(f)
            while True:
                idx = doc.search(f.original, start, stopindex=tk.END, nocase=False)
                if not idx:
                    break
                end = f"{idx}+{len(f.original)}c"
                doc.tag_add(tag, idx, end)
                # store placeholder on tag bind via mark — use tag name unique
                doc.tag_add(f"ph::{f.placeholder}", idx, end)
                start = end

        doc.configure(state=tk.NORMAL)  # allow selection for add
        _status()

    def _on_list_select(_evt=None) -> None:
        sel = listbox.curselection()
        if not sel:
            return
        ph = visible_ph[sel[0]]
        selected_ph[0] = ph
        f = session.get(ph)
        if not f or not f.original:
            return
        # Scroll document to first occurrence
        doc.configure(state=tk.NORMAL)
        idx = doc.search(f.original, "1.0", stopindex=tk.END)
        if idx:
            doc.see(idx)
            doc.tag_remove(tk.SEL, "1.0", tk.END)
            end = f"{idx}+{len(f.original)}c"
            doc.tag_add(tk.SEL, idx, end)
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
        # Update filter types
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
                    lines.append(f"  {ph}  {snip}")
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
    root.bind("<Command-Return>" if sys.platform == "darwin" else "<Control-Return>", lambda _e: _save())
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

    _refresh_list()
    _refresh_doc()
    root.lift()
    try:
        root.attributes("-topmost", True)
        root.after(200, lambda: root.attributes("-topmost", False))
    except tk.TclError:
        pass

    root.mainloop()
    return result["session"]
