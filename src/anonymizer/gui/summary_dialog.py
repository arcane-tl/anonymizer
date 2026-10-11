"""Post-run summary dialog — Review-aligned dark theme with per-output Open/Reveal."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any

from anonymizer.output.run_summary import (
    RunSummary,
    load_summaries,
)

# Match review_window.py tokens so Review → Summary feels continuous.
_BG_APP = "#0F1115"
_BG_PANEL = "#1A1D24"
_BG_ELEVATED = "#242830"
_BORDER = "#3A3F4B"
_TEXT = "#F3F4F6"
_TEXT_MUTED = "#9CA3AF"
_TEXT_ON_BLUE = "#EFF6FF"
_ACCENT = "#60A5FA"
_HL_SELECTED_BG = "#1D4ED8"
_OK_BG = "#0F2E22"
_OK_FG = "#6EE7B7"
_ERR_BG = "#3F1D1D"
_ERR_FG = "#FCA5A5"

_FONT = ("Helvetica", 13) if sys.platform == "darwin" else ("Segoe UI", 11)
_FONT_BOLD = ("Helvetica", 14, "bold") if sys.platform == "darwin" else ("Segoe UI", 12, "bold")
_FONT_TITLE = ("Helvetica", 20, "bold") if sys.platform == "darwin" else ("Segoe UI", 16, "bold")
_FONT_SMALL = ("Helvetica", 12) if sys.platform == "darwin" else ("Segoe UI", 10)
_FONT_TINY = ("Helvetica", 10) if sys.platform == "darwin" else ("Segoe UI", 9)

# Soft tinted chips on dark panels (bg, fg)
_CHIP_COLORS = {
    "PERSON": ("#3F1D1D", "#FCA5A5"),
    "ORG": ("#1E3A5F", "#93C5FD"),
    "EMAIL_ADDRESS": ("#312E81", "#C7D2FE"),
    "PHONE_NUMBER": ("#064E3B", "#6EE7B7"),
    "LOCATION": ("#431407", "#FDBA74"),
    "URL": ("#3B0764", "#E9D5FF"),
    "DATE_TIME": ("#1F2937", "#D1D5DB"),
    "IBAN_CODE": ("#164E63", "#A5F3FC"),
    "CREDIT_CARD": ("#4C1D95", "#DDD6FE"),
    "IP_ADDRESS": ("#1E293B", "#CBD5E1"),
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


def _round_rect(canvas: tk.Canvas, x1: int, y1: int, x2: int, y2: int, r: int, **kwargs):
    r = max(0, min(r, (x2 - x1) // 2, (y2 - y1) // 2))
    points = [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


def _pill(
    parent: tk.Misc,
    text: str,
    *,
    bg: str,
    fg: str,
    chrome: str | None = None,
    font: tuple = _FONT_TINY,
    padx: int = 10,
    pady: int = 4,
) -> tk.Frame:
    """Rounded status/entity chip. Canvas sits on the parent chrome colour."""
    chrome_bg = chrome or str(parent.cget("bg"))
    probe = tk.Label(parent, text=text, font=font)
    probe.update_idletasks()
    tw, th = probe.winfo_reqwidth(), probe.winfo_reqheight()
    probe.destroy()
    bw, bh = tw + padx * 2, th + pady * 2
    wrap = tk.Frame(parent, bg=chrome_bg, width=bw, height=bh)
    wrap.pack_propagate(False)
    canvas = tk.Canvas(
        wrap, width=bw, height=bh, bg=chrome_bg, highlightthickness=0, bd=0
    )
    canvas.pack()
    _round_rect(canvas, 1, 1, bw - 1, bh - 1, bh // 2, fill=bg, outline=bg)
    canvas.create_text(bw // 2, bh // 2, text=text, fill=fg, font=font)
    return wrap


def _open_path(path: Path | str) -> None:
    p = str(path)
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", p], check=False)
        elif sys.platform == "win32":
            os.startfile(p)  # type: ignore[attr-defined]
        else:
            subprocess.run(["xdg-open", p], check=False)
    except OSError:
        messagebox.showerror("Anonymizer", f"Could not open:\n{p}")


def _reveal_path(path: Path | str) -> None:
    p = Path(path)
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", "-R", str(p)], check=False)
        elif sys.platform == "win32":
            subprocess.run(["explorer", "/select,", str(p)], check=False)
        else:
            folder = p.parent if p.exists() else Path(p).parent
            subprocess.run(["xdg-open", str(folder)], check=False)
    except OSError:
        messagebox.showerror("Anonymizer", f"Could not reveal:\n{p}")


def _chip_button(
    parent: tk.Misc,
    text: str,
    command: Any,
    *,
    primary: bool = False,
    chrome: str = _BG_APP,
    compact: bool = False,
) -> tk.Frame:
    """Rounded pill button (same construction as Review)."""
    bg = _HL_SELECTED_BG if primary else _BG_ELEVATED
    fg = _TEXT_ON_BLUE if primary else _TEXT
    font = _FONT_BOLD if primary and not compact else (_FONT_SMALL if compact else _FONT)
    outline = _ACCENT if primary else _BORDER
    pad_x, pad_y, radius = (12, 5, 8) if compact else (16, 8, 10)

    probe = tk.Label(parent, text=text, font=font)
    probe.update_idletasks()
    tw, th = probe.winfo_reqwidth(), probe.winfo_reqheight()
    probe.destroy()
    bw = tw + pad_x * 2
    bh = max(th + pad_y * 2, 28 if compact else 34)

    wrap = tk.Frame(parent, bg=chrome, width=bw, height=bh, cursor="hand2")
    wrap.pack_propagate(False)
    canvas = tk.Canvas(
        wrap, width=bw, height=bh, bg=chrome, highlightthickness=0, bd=0, cursor="hand2"
    )
    canvas.pack(fill=tk.BOTH, expand=True)

    def _paint(*, hover: bool = False) -> None:
        fill = _ACCENT if (primary and hover) else bg
        if not primary and hover:
            fill = _BORDER
        canvas.delete("all")
        _round_rect(
            canvas, 1, 1, bw - 2, bh - 2, radius, fill=fill, outline=outline, width=1
        )
        canvas.create_text(bw // 2, bh // 2, text=text, fill=fg, font=font)

    def _run(_e: object | None = None) -> None:
        command()

    _paint()
    canvas.bind("<Button-1>", _run)
    canvas.bind("<Enter>", lambda _e: _paint(hover=True))
    canvas.bind("<Leave>", lambda _e: _paint(hover=False))
    wrap.bind("<Button-1>", _run)
    return wrap


def show_run_summary_dialog(
    parent: tk.Misc | None,
    summaries: list[dict[str, Any]],
    *,
    errors: list[str] | None = None,
) -> None:
    """Show a Review-themed completion summary with per-output Open/Reveal."""
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
    win.configure(bg=_BG_APP)
    win.geometry("820x640")
    win.minsize(640, 460)

    # —— Header ——
    header = tk.Frame(win, bg=_BG_APP, padx=24, pady=20)
    header.pack(fill=tk.X)

    top = tk.Frame(header, bg=_BG_APP)
    top.pack(fill=tk.X)
    tk.Label(
        top,
        text="Run complete",
        bg=_BG_APP,
        fg=_TEXT,
        font=_FONT_TITLE,
    ).pack(side=tk.LEFT)

    if errors:
        status_bg, status_fg, status_txt = _ERR_BG, _ERR_FG, "Errors"
    else:
        status_bg, status_fg, status_txt = _OK_BG, _OK_FG, "Success"

    _pill(top, status_txt, bg=status_bg, fg=status_fg, font=_FONT_SMALL).pack(
        side=tk.RIGHT
    )

    ver = ""
    if summaries:
        ver = str(summaries[0].get("tool_version") or "")
    n_files = len(summaries)
    n_outs = sum(len(s.get("outputs") or []) for s in summaries)
    subtitle_bits = []
    if ver:
        subtitle_bits.append(f"Anonymizer {ver}")
    if n_files:
        subtitle_bits.append(f"{n_files} file{'s' if n_files != 1 else ''}")
    if n_outs:
        subtitle_bits.append(f"{n_outs} output{'s' if n_outs != 1 else ''}")
    tk.Label(
        header,
        text="  ·  ".join(subtitle_bits) if subtitle_bits else "Anonymizer",
        bg=_BG_APP,
        fg=_TEXT_MUTED,
        font=_FONT_SMALL,
    ).pack(anchor=tk.W, pady=(6, 0))

    # —— Scrollable body ——
    outer = tk.Frame(win, bg=_BG_APP)
    outer.pack(fill=tk.BOTH, expand=True, padx=24)

    canvas = tk.Canvas(outer, bg=_BG_APP, highlightthickness=0, bd=0)
    # Custom thumb — native Tk scrollbars stay Aqua-white on macOS.
    bar = tk.Canvas(outer, width=8, bg=_BG_APP, highlightthickness=0, bd=0)
    scroll_state = {"first": 0.0, "last": 1.0}

    def _paint_thumb() -> None:
        bar.delete("thumb")
        first, last = scroll_state["first"], scroll_state["last"]
        if last - first >= 0.995:
            if bar.winfo_ismapped():
                bar.pack_forget()
            return
        if not bar.winfo_ismapped():
            bar.pack(side=tk.RIGHT, fill=tk.Y, padx=(8, 0))
        h = max(bar.winfo_height(), 1)
        y1 = int(first * h) + 2
        y2 = max(y1 + 28, int(last * h) - 2)
        bar.create_rectangle(1, y1, 7, y2, fill="#8B93A7", outline="", tags="thumb")

    def _yscroll(first: str, last: str) -> None:
        try:
            scroll_state["first"] = float(first)
            scroll_state["last"] = float(last)
        except ValueError:
            return
        _paint_thumb()

    def _bar_jump(event: tk.Event) -> None:  # type: ignore[type-arg]
        h = max(bar.winfo_height(), 1)
        canvas.yview_moveto(max(0.0, min(1.0, event.y / h - 0.05)))

    bar.bind("<Button-1>", _bar_jump)
    bar.bind("<B1-Motion>", _bar_jump)
    bar.bind("<Configure>", lambda _e: _paint_thumb())
    canvas.configure(yscrollcommand=_yscroll)
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    body = tk.Frame(canvas, bg=_BG_APP, padx=0, pady=4)
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
        err_card = tk.Frame(
            body,
            bg=_ERR_BG,
            padx=14,
            pady=12,
            highlightthickness=1,
            highlightbackground="#7F1D1D",
        )
        err_card.pack(fill=tk.X, pady=(0, 12))
        tk.Label(
            err_card,
            text="Some files failed",
            bg=_ERR_BG,
            fg=_ERR_FG,
            font=_FONT_BOLD,
        ).pack(anchor=tk.W)
        tk.Label(
            err_card,
            text="\n".join(errors[:8]),
            bg=_ERR_BG,
            fg=_TEXT_MUTED,
            font=_FONT_SMALL,
            justify=tk.LEFT,
            wraplength=640,
        ).pack(anchor=tk.W, pady=(4, 0))

    all_output_paths: list[Path] = []
    for i, data in enumerate(summaries):
        if len(summaries) > 1:
            tk.Label(
                body,
                text=f"File {i + 1}",
                bg=_BG_APP,
                fg=_TEXT_MUTED,
                font=_FONT_TINY,
            ).pack(anchor=tk.W, pady=(8 if i else 0, 4))
        paths = _render_file_card(body, data)
        all_output_paths.extend(paths)

    # —— Footer ——
    footer = tk.Frame(win, bg=_BG_APP, padx=24, pady=16)
    footer.pack(fill=tk.X)
    tk.Frame(footer, bg=_BORDER, height=1).pack(fill=tk.X, pady=(0, 14))
    row = tk.Frame(footer, bg=_BG_APP)
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
            chunks = [_summary_from_dict(d).to_markdown() for d in summaries]
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

    def on_open_all() -> None:
        for p in all_output_paths:
            if p.exists():
                _open_path(p)

    def on_done() -> None:
        try:
            canvas.unbind_all("<MouseWheel>")
        except Exception:  # noqa: BLE001
            pass
        win.destroy()

    left = tk.Frame(row, bg=_BG_APP)
    left.pack(side=tk.LEFT)
    _chip_button(left, "Save summary…", on_save, chrome=_BG_APP).pack(side=tk.LEFT)
    if len(all_output_paths) > 1:
        _chip_button(left, "Open all", on_open_all, chrome=_BG_APP).pack(
            side=tk.LEFT, padx=(10, 0)
        )
    elif len(all_output_paths) == 1:
        only = all_output_paths[0]
        _chip_button(
            left, "Reveal in folder", lambda: _reveal_path(only), chrome=_BG_APP
        ).pack(side=tk.LEFT, padx=(10, 0))

    _chip_button(row, "Done", on_done, primary=True, chrome=_BG_APP).pack(
        side=tk.RIGHT
    )

    win.protocol("WM_DELETE_WINDOW", on_done)

    def _center() -> None:
        win.update_idletasks()
        w = win.winfo_width()
        h = win.winfo_height()
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2 - 40)
        win.geometry(f"{w}x{h}+{x}+{y}")

    try:
        win.after(30, _center)
        win.lift()
        win.attributes("-topmost", True)
        win.after(250, lambda: win.attributes("-topmost", False))
        win.focus_force()
    except Exception:  # noqa: BLE001
        pass

    if own_root:
        win.mainloop()
    else:
        win.grab_set()
        win.wait_window()


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


def _render_file_card(parent: tk.Misc, data: dict[str, Any]) -> list[Path]:
    """Render one source-file card; return output paths for Open all."""
    card = tk.Frame(
        parent,
        bg=_BG_PANEL,
        padx=16,
        pady=14,
        highlightthickness=1,
        highlightbackground=_BORDER,
        highlightcolor=_BORDER,
    )
    card.pack(fill=tk.X, pady=(0, 12))

    src = Path(str(data.get("source") or ""))
    tk.Label(
        card,
        text=src.name or str(data.get("source") or "Document"),
        bg=_BG_PANEL,
        fg=_TEXT,
        font=_FONT_BOLD,
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
        # Shorten ISO timestamp for the card
        meta_bits.append(when.replace("T", " ").rstrip("Z")[:19])
    if meta_bits:
        tk.Label(
            card,
            text="  ·  ".join(meta_bits),
            bg=_BG_PANEL,
            fg=_TEXT_MUTED,
            font=_FONT_SMALL,
        ).pack(anchor=tk.W, pady=(2, 10))

    counts = dict(data.get("entity_counts") or {})
    chip_row = tk.Frame(card, bg=_BG_PANEL)
    chip_row.pack(fill=tk.X, pady=(0, 10))
    if not counts:
        _pill(
            chip_row,
            "No entities redacted",
            bg=_BG_ELEVATED,
            fg=_TEXT_MUTED,
            padx=8,
            pady=3,
        ).pack(side=tk.LEFT)
    else:
        for key, val in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
            bg, fg = _CHIP_COLORS.get(key, (_BG_ELEVATED, _TEXT))
            short = key.replace("_ADDRESS", "").replace("_NUMBER", "").replace("_CODE", "")
            _pill(
                chip_row,
                f"{short}  {val}",
                bg=bg,
                fg=fg,
                padx=8,
                pady=3,
            ).pack(side=tk.LEFT, padx=(0, 6))

    paths: list[Path] = []
    outs = list(data.get("outputs") or [])
    if outs:
        tk.Label(
            card,
            text="Outputs",
            bg=_BG_PANEL,
            fg=_TEXT_MUTED,
            font=_FONT_TINY,
        ).pack(anchor=tk.W, pady=(4, 6))
        for o in outs:
            p = _render_output_row(card, o)
            if p is not None:
                paths.append(p)

    return paths


def _ellipsize(text: str, font: tkfont.Font, max_px: int) -> str:
    if max_px <= 0 or not text:
        return ""
    if font.measure(text) <= max_px:
        return text
    ell = "…"
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if font.measure(text[:mid] + ell) <= max_px:
            lo = mid
        else:
            hi = mid - 1
    return (text[:lo] + ell) if lo else ell


# Fixed kind column so every filename and note shares one left edge.
_KIND_COL_PX = 108

_KIND_LABELS = {
    "markdown": "Markdown",
    "md": "Markdown",
    "text_pdf": "Text PDF",
    "pdf": "Text PDF",
    "native_pdf": "PDF",
    "native_docx": "Word",
    "docx": "Word",
    "source": "Source",
}


def _kind_label(kind: str) -> str:
    key = kind.strip().lower()
    if key in _KIND_LABELS:
        return _KIND_LABELS[key]
    return kind.replace("_", " ").strip().title() or "File"


def _render_output_row(parent: tk.Misc, o: dict[str, Any]) -> Path | None:
    row = tk.Frame(parent, bg=_BG_ELEVATED, padx=10, pady=8)
    row.pack(fill=tk.X, pady=2)
    row.grid_columnconfigure(0, minsize=_KIND_COL_PX, weight=0)
    row.grid_columnconfigure(1, weight=1)
    row.grid_columnconfigure(2, weight=0)

    kind = str(o.get("kind") or "file")
    path = Path(str(o.get("path") or ""))
    carried = bool(o.get("source_metadata_carried"))
    note = str(o.get("note") or "")
    label = _kind_label(kind)

    if kind.lower() in {"markdown", "md"}:
        badge_bg, badge_fg = ("#1E3A5F", "#93C5FD")
    elif "pdf" in kind.lower():
        badge_bg, badge_fg = ("#312E81", "#C7D2FE")
    else:
        badge_bg, badge_fg = ("#1F2937", "#E5E7EB")

    _pill(row, label, bg=badge_bg, fg=badge_fg, padx=8, pady=2).grid(
        row=0, column=0, sticky="nw"
    )

    mid = tk.Frame(row, bg=_BG_ELEVATED)
    mid.grid(row=0, column=1, sticky="nsew", padx=(12, 10))

    actions = tk.Frame(row, bg=_BG_ELEVATED)
    actions.grid(row=0, column=2, sticky="ne")
    has_path = bool(path.as_posix() and str(path) not in {".", ""})
    if has_path:
        _chip_button(
            actions,
            "Open",
            lambda p=path: _open_path(p),
            chrome=_BG_ELEVATED,
            compact=True,
        ).pack(side=tk.LEFT, padx=(0, 6))
        _chip_button(
            actions,
            "Reveal",
            lambda p=path: _reveal_path(p),
            chrome=_BG_ELEVATED,
            compact=True,
        ).pack(side=tk.LEFT)
    name_font = tkfont.Font(font=_FONT_BOLD)
    full_name = path.name or str(path)
    name_lbl = tk.Label(
        mid,
        text=full_name,
        bg=_BG_ELEVATED,
        fg=_TEXT,
        font=_FONT_BOLD,
        anchor=tk.W,
    )
    name_lbl.pack(fill=tk.X)
    sub = (
        "May carry source container metadata"
        if carried
        else "Rebuild — metadata not carried"
    )
    if note:
        sub = note
    note_lbl = tk.Label(
        mid,
        text=sub,
        bg=_BG_ELEVATED,
        fg=_TEXT_MUTED,
        font=_FONT_TINY,
        anchor=tk.W,
        justify=tk.LEFT,
    )
    note_lbl.pack(fill=tk.X)

    def _fit(_event: object | None = None) -> None:
        width = mid.winfo_width()
        if width <= 1:
            return
        name_lbl.configure(text=_ellipsize(full_name, name_font, width - 4))
        note_lbl.configure(wraplength=max(width - 4, 80))

    mid.bind("<Configure>", _fit)
    return path if has_path else None


def show_summary_from_json_file(
    parent: tk.Misc | None,
    path: Path | str,
    *,
    errors: list[str] | None = None,
) -> None:
    show_run_summary_dialog(parent, load_summaries(path), errors=errors)
