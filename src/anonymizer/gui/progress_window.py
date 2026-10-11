"""Quiet bottom-of-screen progress strip. Does not take focus.

Launched as ``anonymize show-progress STATUS.json`` before a batch. The file
is one JSON object updated by the CLI and the shell. ``state`` of ``done`` or
``error``, or a missing file after the first read, closes the strip.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tkinter as tk
from pathlib import Path

_BG = "#0F1115"
_PANEL = "#1A1D24"
_ELEVATED = "#242830"
_TEXT = "#F3F4F6"
_MUTED = "#9CA3AF"
_ACCENT = "#60A5FA"
_TRACK = "#242830"  # same elevated fill as Review cards

_FONT = ("Helvetica", 13) if sys.platform == "darwin" else ("Segoe UI", 11)
_FONT_BOLD = ("Helvetica", 13, "bold") if sys.platform == "darwin" else ("Segoe UI", 11, "bold")
_FONT_SMALL = ("Helvetica", 12) if sys.platform == "darwin" else ("Segoe UI", 10)


def _mac_do_not_activate(root: tk.Tk) -> None:
    """Borderless window that does not become the key window when shown or clicked.

    ctypes calls into objc_msgSend crash on Apple Silicon, so this stays in Tk.
    """
    if sys.platform != "darwin":
        return
    try:
        root.tk.call(
            "::tk::unsupported::MacWindowStyle",
            "style",
            root._w,  # noqa: SLF001
            "plain",
            "noTitleBar noActivates",
        )
    except tk.TclError:
        return


def _show_progress_mac(path: Path) -> None:
    """AppKit panel. A Tk window from this process steals key focus on macOS."""
    script = Path(__file__).with_name("show_progress.applescript")
    subprocess.run(["osascript", str(script), str(path)], check=False)


def show_progress_window(path: Path | str) -> None:
    """Block until the status file says the job finished."""
    status_path = Path(path)
    if sys.platform == "darwin":
        _show_progress_mac(status_path)
        return
    root = tk.Tk()
    root.title("Anonymizer")
    root.configure(bg=_BG)
    root.resizable(False, False)
    width, height = 460, 86
    root.update_idletasks()
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    x = max(0, (sw - width) // 2)
    y = max(0, sh - height - 96)
    root.geometry(f"{width}x{height}+{x}+{y}")

    card = tk.Frame(root, bg=_PANEL, padx=16, pady=12)
    card.pack(fill=tk.BOTH, expand=True)

    top = tk.Frame(card, bg=_PANEL)
    top.pack(fill=tk.X)
    name_var = tk.StringVar(value="Starting")
    count_var = tk.StringVar(value="")
    phase_var = tk.StringVar(value="Starting")
    tk.Label(
        top, textvariable=name_var, bg=_PANEL, fg=_TEXT, font=_FONT_BOLD, anchor=tk.W
    ).pack(side=tk.LEFT, fill=tk.X, expand=True)
    tk.Label(
        top, textvariable=count_var, bg=_PANEL, fg=_MUTED, font=_FONT_SMALL, anchor=tk.E
    ).pack(side=tk.RIGHT)
    tk.Label(
        card, textvariable=phase_var, bg=_PANEL, fg=_MUTED, font=_FONT_SMALL, anchor=tk.W
    ).pack(fill=tk.X, pady=(2, 8))

    bar = tk.Canvas(card, height=6, bg=_PANEL, highlightthickness=0, bd=0)
    bar.pack(fill=tk.X)

    state = {"fraction": 0.0, "pulse": 0, "seen": False, "closed": False}

    def _draw() -> None:
        bar.update_idletasks()
        w = max(bar.winfo_width(), 10)
        h = 6
        bar.delete("all")
        bar.create_rectangle(0, 0, w, h, fill=_TRACK, outline="")
        frac = max(0.0, min(1.0, state["fraction"]))
        fill_w = int(w * frac)
        if fill_w > 0:
            bar.create_rectangle(0, 0, fill_w, h, fill=_ACCENT, outline="")
        # A short lighter cap so a long step does not look frozen.
        cap = 28
        shift = (state["pulse"] % (cap + 8)) - 8
        if 0 < fill_w:
            x1 = max(0, fill_w - cap + shift)
            x2 = min(fill_w, x1 + 18)
            if x2 > x1:
                bar.create_rectangle(x1, 0, x2, h, fill="#BFDBFE", outline="")

    def _close() -> None:
        if state["closed"]:
            return
        state["closed"] = True
        try:
            root.destroy()
        except tk.TclError:
            pass

    def _poll() -> None:
        if state["closed"]:
            return
        state["pulse"] += 1
        try:
            raw = status_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            if state["seen"]:
                _close()
                return
            root.after(200, _poll)
            return
        except OSError:
            root.after(200, _poll)
            return
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            root.after(200, _poll)
            return
        state["seen"] = True
        job = str(data.get("state") or "running")
        if job in {"done", "error"}:
            _close()
            return
        file_name = str(data.get("file") or "").strip()
        phase = str(data.get("phase") or "Starting")
        name_var.set(file_name or phase)
        phase_var.set(phase if file_name else "")
        try:
            index = int(data.get("index") or 0)
            total = int(data.get("total") or 0)
        except (TypeError, ValueError):
            index, total = 0, 0
        if total > 1 and index > 0:
            count_var.set(f"{index} of {total}")
        else:
            count_var.set("")
        try:
            state["fraction"] = float(data.get("fraction") or 0)
        except (TypeError, ValueError):
            state["fraction"] = 0.0
        _draw()
        root.after(200, _poll)

    _mac_do_not_activate(root)
    try:
        root.attributes("-topmost", False)
    except tk.TclError:
        pass
    root.protocol("WM_DELETE_WINDOW", _close)
    root.after(60, _poll)
    root.mainloop()
