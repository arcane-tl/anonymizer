"""Post-run summary dialog (Tk) with optional Save summary…"""

from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from anonymizer.output.run_summary import (
    RunSummary,
    format_summaries_plain,
    load_summaries,
)


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


def show_run_summary_dialog(
    parent: tk.Misc | None,
    summaries: list[dict[str, Any]],
    *,
    errors: list[str] | None = None,
) -> None:
    """Show a scrollable summary; offer Save summary… and Show in folder."""
    if not summaries and not errors:
        messagebox.showinfo(
            "Anonymizer",
            "Done.\n\nNo summary data was produced.",
            parent=parent,
        )
        return

    win = tk.Toplevel(parent) if parent is not None else tk.Tk()
    win.title("Anonymizer — run summary")
    win.geometry("560x420")
    try:
        win.transient(parent)  # type: ignore[arg-type]
    except Exception:  # noqa: BLE001
        pass

    frm = ttk.Frame(win, padding=12)
    frm.pack(fill=tk.BOTH, expand=True)

    text = tk.Text(frm, wrap=tk.WORD, height=18, width=68)
    text.pack(fill=tk.BOTH, expand=True, side=tk.TOP)
    scroll = ttk.Scrollbar(text, command=text.yview)
    text.configure(yscrollcommand=scroll.set)
    scroll.pack(side=tk.RIGHT, fill=tk.Y)

    body = format_summaries_plain(summaries) if summaries else ""
    if errors:
        body += ("\n\n" if body else "") + "Some files failed:\n" + "\n".join(
            errors[:8]
        )
    text.insert("1.0", body.strip() + "\n")
    text.configure(state=tk.DISABLED)

    # Warn if any native run was not clean
    unclean = [
        s
        for s in summaries
        if isinstance(s.get("native"), dict)
        and s["native"].get("native_clean") is False
    ]
    if unclean:
        warn = ttk.Label(
            frm,
            text=(
                f"Warning: {len(unclean)} native output(s) reported residuals "
                "or scrub errors — see summary above. Prefer Markdown when you "
                "need a rebuild without source container metadata."
            ),
            wraplength=520,
            foreground="#8B4513",
        )
        warn.pack(fill=tk.X, pady=(8, 0))

    btns = ttk.Frame(frm)
    btns.pack(fill=tk.X, pady=(12, 0))

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
                s = RunSummary(
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
                    detected_languages=list(d.get("detected_languages") or [])
                    or None,
                )
                chunks.append(s.to_markdown())
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

    ttk.Button(btns, text="Save summary…", command=on_save).pack(side=tk.LEFT)
    if summaries:
        ttk.Button(btns, text="Show in folder", command=on_folder).pack(
            side=tk.LEFT, padx=(8, 0)
        )
    ttk.Button(btns, text="OK", command=win.destroy).pack(side=tk.RIGHT)

    win.grab_set()
    win.wait_window()


def show_summary_from_json_file(
    parent: tk.Misc | None,
    path: Path | str,
    *,
    errors: list[str] | None = None,
) -> None:
    show_run_summary_dialog(parent, load_summaries(path), errors=errors)
