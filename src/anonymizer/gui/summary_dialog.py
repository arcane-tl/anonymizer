"""Post-run summary dialog — polished card UI with optional Save summary…"""

from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from anonymizer.output.run_summary import (
    RunSummary,
    load_summaries,
)

# Visual system (no extra deps)
_BG = "#0B1220"
_BG_CARD = "#111827"
_BG_BODY = "#F1F5F9"
_BG_CHIP = "#E2E8F0"
_TEXT = "#0F172A"
_TEXT_MUTED = "#64748B"
_TEXT_ON_DARK = "#F8FAFC"
_TEXT_MUTED_DARK = "#94A3B8"
_ACCENT = "#10B981"
_ACCENT_DIM = "#059669"
_WARN = "#F59E0B"
_WARN_BG = "#FFFBEB"
_BORDER = "#CBD5E1"

_CHIP_COLORS = {
    "PERSON": ("#FEE2E2", "#991B1B"),
    "ORG": ("#DBEAFE", "#1E40AF"),
    "EMAIL_ADDRESS": ("#E0E7FF", "#3730A3"),
    "PHONE_NUMBER": ("#D1FAE5", "#065F46"),
    "LOCATION": ("#FFEDD5", "#9A3412"),
    "URL": ("#F3E8FF", "#6B21A8"),
    "DATE_TIME": ("#F1F5F9", "#334155"),
}


def _default_save_path(summaries: list[dict[str, Any]]) -> Path:
    stem = "anonymizer"
    parent = Path.home()
    if summaries:
        src = Path(str(summaries[0].get("source") or "anonymizer"))
        stem = src.stem or stem
        outs = summaries[0].get("outputs") or []
        if outs and outs[0].get("path"):
            parent = Path(str(outs[0]["path"])).parent
        else:
            parent = src.parent if src.parent.is_dir() else Path.home()
    return parent / f"{stem}.anonymizer-summary.json"


def _pill(
    parent: tk.Misc,
    text: str,
    *,
    bg: str,
    fg: str,
    padx: int = 10,
    pady: int = 4,
) -> tk.Label:
    return tk.Label(
        parent,
        text=text,
        bg=bg,
        fg=fg,
        font=("Helvetica Neue", 11, "bold"),
        padx=padx,
        pady=pady,
    )


def show_run_summary_dialog(
    parent: tk.Misc | None,
    summaries: list[dict[str, Any]],
    *,
    errors: list[str] | None = None,
) -> None:
    """Show a designed completion summary; offer Save and Show in folder."""
    if not summaries and not errors:
        messagebox.showinfo(
            "Anonymizer",
            "Done.\n\nNo summary data was produced.",
            parent=parent,
        )
        return

    own_root = parent is None
    win: tk.Misc
    if parent is not None:
        win = tk.Toplevel(parent)
        try:
            win.transient(parent)  # type: ignore[arg-type]
        except Exception:  # noqa: BLE001
            pass
    else:
        win = tk.Tk()

    win.title("Anonymizer")
    win.configure(bg=_BG_BODY)
    win.geometry("680x560")
    win.minsize(520, 420)

    # —— Header ——
    header = tk.Frame(win, bg=_BG, padx=24, pady=18)
    header.pack(fill=tk.X)

    top = tk.Frame(header, bg=_BG)
    top.pack(fill=tk.X)
    tk.Label(
        top,
        text="Run complete",
        bg=_BG,
        fg=_TEXT_ON_DARK,
        font=("Helvetica Neue", 22, "bold"),
    ).pack(side=tk.LEFT)

    unclean = [
        s
        for s in summaries
        if isinstance(s.get("native"), dict)
        and s["native"].get("native_clean") is False
    ]
    if errors:
        status_bg, status_fg, status_txt = "#7C2D12", "#FFEDD5", "Errors"
    elif unclean:
        status_bg, status_fg, status_txt = "#78350F", "#FEF3C7", "Needs attention"
    else:
        status_bg, status_fg, status_txt = _ACCENT_DIM, "#ECFDF5", "Success"

    _pill(top, status_txt, bg=status_bg, fg=status_fg).pack(side=tk.RIGHT)

    ver = ""
    if summaries:
        ver = str(summaries[0].get("tool_version") or "")
    tk.Label(
        header,
        text=f"Anonymizer {ver}".strip() if ver else "Anonymizer",
        bg=_BG,
        fg=_TEXT_MUTED_DARK,
        font=("Helvetica Neue", 12),
    ).pack(anchor=tk.W, pady=(6, 0))

    # —— Scrollable body ——
    outer = tk.Frame(win, bg=_BG_BODY)
    outer.pack(fill=tk.BOTH, expand=True)

    canvas = tk.Canvas(outer, bg=_BG_BODY, highlightthickness=0)
    scroll = ttk.Scrollbar(outer, orient=tk.VERTICAL, command=canvas.yview)
    canvas.configure(yscrollcommand=scroll.set)
    scroll.pack(side=tk.RIGHT, fill=tk.Y)
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    body = tk.Frame(canvas, bg=_BG_BODY, padx=24, pady=16)
    body_id = canvas.create_window((0, 0), window=body, anchor=tk.NW)

    def _on_configure(_event: object | None = None) -> None:
        canvas.configure(scrollregion=canvas.bbox("all"))
        canvas.itemconfigure(body_id, width=canvas.winfo_width())

    body.bind("<Configure>", _on_configure)
    canvas.bind("<Configure>", _on_configure)

    def _on_mousewheel(event: tk.Event) -> None:  # type: ignore[type-arg]
        delta = getattr(event, "delta", 0) or 0
        if delta:
            canvas.yview_scroll(int(-1 * (delta / 120)), "units")
        elif getattr(event, "num", None) == 5:
            canvas.yview_scroll(1, "units")
        elif getattr(event, "num", None) == 4:
            canvas.yview_scroll(-1, "units")

    canvas.bind_all("<MouseWheel>", _on_mousewheel)

    if errors:
        err_card = tk.Frame(body, bg=_WARN_BG, padx=14, pady=12)
        err_card.pack(fill=tk.X, pady=(0, 12))
        tk.Label(
            err_card,
            text="Some files failed",
            bg=_WARN_BG,
            fg="#92400E",
            font=("Helvetica Neue", 13, "bold"),
        ).pack(anchor=tk.W)
        tk.Label(
            err_card,
            text="\n".join(errors[:8]),
            bg=_WARN_BG,
            fg="#78350F",
            font=("Helvetica Neue", 11),
            justify=tk.LEFT,
            wraplength=600,
        ).pack(anchor=tk.W, pady=(4, 0))

    for i, data in enumerate(summaries):
        if len(summaries) > 1:
            tk.Label(
                body,
                text=f"File {i + 1}",
                bg=_BG_BODY,
                fg=_TEXT_MUTED,
                font=("Helvetica Neue", 11, "bold"),
            ).pack(anchor=tk.W, pady=(8 if i else 0, 4))
        _render_file_card(body, data)

    # —— Footer actions ——
    footer = tk.Frame(win, bg=_BG_BODY, padx=24, pady=16)
    footer.pack(fill=tk.X)
    tk.Frame(footer, bg=_BORDER, height=1).pack(fill=tk.X, pady=(0, 12))
    row = tk.Frame(footer, bg=_BG_BODY)
    row.pack(fill=tk.X)

    def on_save() -> None:
        default = _default_save_path(summaries)
        path = filedialog.asksaveasfilename(
            parent=win,
            title="Save run summary",
            initialdir=str(default.parent),
            initialfile=default.name,
            defaultextension=".json",
            filetypes=[
                ("JSON summary", "*.json"),
                ("Markdown summary", "*.md"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        p = Path(path)
        if p.suffix.casefold() in {".md", ".markdown"}:
            chunks = []
            for d in summaries:
                chunks.append(_summary_from_dict(d).to_markdown())
            p.write_text("\n".join(chunks), encoding="utf-8")
        else:
            p.write_text(
                json.dumps(summaries, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        try:
            p.chmod(0o600)
        except OSError:
            pass
        messagebox.showinfo("Anonymizer", f"Summary saved:\n{p}", parent=win)

    def on_folder() -> None:
        folder = None
        if summaries:
            outs = summaries[0].get("outputs") or []
            if outs and outs[0].get("path"):
                folder = str(Path(str(outs[0]["path"])).parent)
            else:
                folder = str(Path(str(summaries[0].get("source") or ".")).parent)
        if not folder:
            return
        import subprocess
        import sys

        if sys.platform == "darwin":
            subprocess.run(["open", folder], check=False)
        elif sys.platform == "win32":
            subprocess.run(["explorer", folder], check=False)
        else:
            subprocess.run(["xdg-open", folder], check=False)

    def on_done() -> None:
        try:
            canvas.unbind_all("<MouseWheel>")
        except Exception:  # noqa: BLE001
            pass
        win.destroy()

    _action_btn(row, "Save summary…", on_save, primary=False).pack(side=tk.LEFT)
    if summaries:
        _action_btn(row, "Show in folder", on_folder, primary=False).pack(
            side=tk.LEFT, padx=(10, 0)
        )
    _action_btn(row, "Done", on_done, primary=True).pack(side=tk.RIGHT)

    win.protocol("WM_DELETE_WINDOW", on_done)
    try:
        win.lift()
        win.attributes("-topmost", True)
        win.after(200, lambda: win.attributes("-topmost", False))
        win.focus_force()
    except Exception:  # noqa: BLE001
        pass

    if own_root:
        win.mainloop()
    else:
        win.grab_set()
        win.wait_window()


def _action_btn(
    parent: tk.Misc,
    label: str,
    command: Any,
    *,
    primary: bool,
) -> tk.Button:
    if primary:
        return tk.Button(
            parent,
            text=label,
            command=command,
            bg=_ACCENT,
            fg="#FFFFFF",
            activebackground=_ACCENT_DIM,
            activeforeground="#FFFFFF",
            font=("Helvetica Neue", 12, "bold"),
            relief=tk.FLAT,
            padx=18,
            pady=8,
            cursor="hand2",
        )
    return tk.Button(
        parent,
        text=label,
        command=command,
        bg="#FFFFFF",
        fg=_TEXT,
        activebackground=_BG_CHIP,
        font=("Helvetica Neue", 12),
        relief=tk.SOLID,
        borderwidth=1,
        highlightthickness=0,
        padx=14,
        pady=8,
        cursor="hand2",
    )


def _summary_from_dict(d: dict[str, Any]) -> RunSummary:
    return RunSummary(
        source=str(d.get("source") or ""),
        mode=str(d.get("mode") or ""),
        tool_version=str(d.get("tool_version") or ""),
        anonymized_at=str(d.get("anonymized_at") or ""),
        entity_counts=dict(d.get("entity_counts") or {}),
        outputs=list(d.get("outputs") or []),
        native=d.get("native"),
        debug_log_path=d.get("debug_log_path"),
        used_ocr=bool(d.get("used_ocr")),
        ocr=d.get("ocr"),
        detector_sources=d.get("detector_sources"),
        lang_mode=d.get("lang_mode"),
        detected_languages=list(d.get("detected_languages") or []) or None,
    )


def _render_file_card(parent: tk.Misc, data: dict[str, Any]) -> None:
    card = tk.Frame(parent, bg="#FFFFFF", padx=16, pady=14, highlightthickness=1)
    card.configure(highlightbackground=_BORDER, highlightcolor=_BORDER)
    card.pack(fill=tk.X, pady=(0, 12))

    src = Path(str(data.get("source") or ""))
    tk.Label(
        card,
        text=src.name or str(data.get("source") or "Document"),
        bg="#FFFFFF",
        fg=_TEXT,
        font=("Helvetica Neue", 15, "bold"),
    ).pack(anchor=tk.W)

    meta_bits = []
    mode = str(data.get("mode") or "")
    if mode:
        meta_bits.append(mode)
    langs = data.get("detected_languages") or []
    if langs:
        meta_bits.append(", ".join(str(x) for x in langs))
    when = str(data.get("anonymized_at") or "")
    if when:
        meta_bits.append(when)
    if meta_bits:
        tk.Label(
            card,
            text="  ·  ".join(meta_bits),
            bg="#FFFFFF",
            fg=_TEXT_MUTED,
            font=("Helvetica Neue", 11),
        ).pack(anchor=tk.W, pady=(2, 10))

    # Entity chips
    counts = dict(data.get("entity_counts") or {})
    chip_row = tk.Frame(card, bg="#FFFFFF")
    chip_row.pack(fill=tk.X, pady=(0, 10))
    if not counts:
        _pill(
            chip_row,
            "No entities redacted",
            bg=_BG_CHIP,
            fg=_TEXT_MUTED,
            padx=8,
            pady=3,
        ).pack(side=tk.LEFT)
    else:
        for key, val in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
            bg, fg = _CHIP_COLORS.get(key, (_BG_CHIP, _TEXT))
            short = key.replace("_ADDRESS", "").replace("_NUMBER", "")
            _pill(
                chip_row,
                f"{short}  {val}",
                bg=bg,
                fg=fg,
                padx=8,
                pady=3,
            ).pack(side=tk.LEFT, padx=(0, 6))

    # Outputs
    outs = list(data.get("outputs") or [])
    if outs:
        tk.Label(
            card,
            text="Outputs",
            bg="#FFFFFF",
            fg=_TEXT_MUTED,
            font=("Helvetica Neue", 10, "bold"),
        ).pack(anchor=tk.W, pady=(4, 4))
        for o in outs:
            _render_output_row(card, o)

    native = data.get("native")
    if isinstance(native, dict):
        clean = native.get("native_clean")
        nres = int(native.get("native_residuals") or 0)
        nerr = int(native.get("native_scrub_errors") or 0)
        if clean is False or nres or nerr:
            box = tk.Frame(card, bg=_WARN_BG, padx=10, pady=8)
            box.pack(fill=tk.X, pady=(10, 0))
            tk.Label(
                box,
                text="Native output needs attention",
                bg=_WARN_BG,
                fg="#92400E",
                font=("Helvetica Neue", 11, "bold"),
            ).pack(anchor=tk.W)
            detail = []
            if clean is False:
                detail.append("native_clean=false")
            if nres:
                detail.append(f"{nres} residual(s)")
            if nerr:
                detail.append(f"{nerr} scrub error(s)")
            tk.Label(
                box,
                text=" · ".join(detail),
                bg=_WARN_BG,
                fg="#78350F",
                font=("Helvetica Neue", 10),
            ).pack(anchor=tk.W)
        elif clean is True:
            box = tk.Frame(card, bg="#ECFDF5", padx=10, pady=8)
            box.pack(fill=tk.X, pady=(10, 0))
            tk.Label(
                box,
                text="Native verification clean",
                bg="#ECFDF5",
                fg="#065F46",
                font=("Helvetica Neue", 11, "bold"),
            ).pack(anchor=tk.W)


def _render_output_row(parent: tk.Misc, o: dict[str, Any]) -> None:
    row = tk.Frame(parent, bg="#F8FAFC", padx=10, pady=8)
    row.pack(fill=tk.X, pady=2)
    kind = str(o.get("kind") or "file")
    path = Path(str(o.get("path") or ""))
    carried = bool(o.get("source_metadata_carried"))
    note = str(o.get("note") or "")
    badge_bg = "#DBEAFE" if kind == "markdown" else "#E0E7FF"
    if "native" in kind or carried:
        badge_bg = "#FEF3C7"
    _pill(row, kind, bg=badge_bg, fg=_TEXT, padx=8, pady=2).pack(side=tk.LEFT)
    right = tk.Frame(row, bg="#F8FAFC")
    right.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 0))
    tk.Label(
        right,
        text=path.name or str(path),
        bg="#F8FAFC",
        fg=_TEXT,
        font=("Helvetica Neue", 12, "bold"),
        anchor=tk.W,
    ).pack(fill=tk.X)
    sub = "May carry source container metadata" if carried else "Rebuild — metadata not carried"
    if note:
        sub = note
    tk.Label(
        right,
        text=sub,
        bg="#F8FAFC",
        fg=_TEXT_MUTED,
        font=("Helvetica Neue", 10),
        anchor=tk.W,
        wraplength=480,
        justify=tk.LEFT,
    ).pack(fill=tk.X)


def show_summary_from_json_file(
    parent: tk.Misc | None,
    path: Path | str,
    *,
    errors: list[str] | None = None,
) -> None:
    show_run_summary_dialog(parent, load_summaries(path), errors=errors)
