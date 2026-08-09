#!/usr/bin/env python3
"""Automated OverlayScrollbar hide diagnostics (requires display + tkinter).

Runs several scenarios, pumps the Tk event loop, and reports pass/fail from
both widget state and /tmp/anonymizer-sb.log (or $ANONYMIZER_SB_LOG).

Usage (from repo root, with .venv active):

    python scripts/debug_sb_hide.py
    python scripts/debug_sb_hide.py --review   # also open real review window path
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# Editable install / src layout
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

os.environ.setdefault("ANONYMIZER_SB_DEBUG", "1")


def _read_log() -> str:
    from anonymizer.gui.review_window import _sb_log_path

    path = _sb_log_path()
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return ""


def _hidden_state(sb) -> tuple[bool, int, int]:
    """Return (ok, mapped_or_items, item_count). ok means fully hidden."""
    if sb._visible:
        return False, 1, -1
    # Owned mode: canvas destroyed
    if getattr(sb, "_owns_cv", True):
        if sb._cv is None:
            return True, 0, 0
        try:
            if not sb._cv.winfo_exists():
                return True, 0, 0
            mapped = int(bool(sb._cv.winfo_ismapped()))
            items = len(sb._cv.find_all())
            return (mapped == 0 and items == 0), mapped, items
        except Exception:  # noqa: BLE001
            return True, 0, 0
    # Surface mode: no tagged items
    try:
        items = len(sb._cv.find_withtag(sb._tag)) if sb._cv is not None else 0
        return items == 0, items, items
    except Exception:  # noqa: BLE001
        return True, 0, 0


def _pump(root, seconds: float, step_ms: int = 50) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        try:
            root.update()
        except Exception:  # noqa: BLE001
            break
        root.after(step_ms)
        try:
            root.update()
        except Exception:  # noqa: BLE001
            break
        time.sleep(step_ms / 1000.0)


def scenario_minimal_pulse_hide() -> bool:
    """pulse() then idle → pill must hide within ~2.5s."""
    import tkinter as tk

    from anonymizer.gui.review_window import OverlayScrollbar, _sb_log_reset

    _sb_log_reset()
    OverlayScrollbar.shutdown_all()

    root = tk.Tk()
    root.geometry("320x480")
    root.withdraw()  # headless-ish but still processes after()
    root.deiconify()

    parent = tk.Frame(root, width=300, height=400, bg="#1A1D24")
    parent.pack(fill="both", expand=True)

    # Fake scrollable range
    state = {"first": 0.0, "last": 0.3}

    def cmd(action, *args):
        if action == "moveto" and args:
            state["first"] = float(args[0])
            state["last"] = min(1.0, state["first"] + 0.3)

    sb = OverlayScrollbar(parent, command=cmd, root=root, name="min", chrome="#1A1D24")
    sb.set(0.0, 0.3)
    parent.update_idletasks()
    root.update()

    sb.pulse()
    root.update()
    assert sb._visible and sb._placed, "pill should be visible after pulse"
    print("  after pulse: visible=1 OK")

    _pump(root, 2.6)
    ok, mapped, items = _hidden_state(sb)
    print(
        f"  after 2.6s idle: visible={int(sb._visible)} placed={int(sb._placed)} "
        f"mapped={mapped} items={items}  {'OK' if ok else 'FAIL'}"
    )
    log = _read_log()
    has_hide = "action=HIDE" in log and "pane=min" in log
    has_expire = "action=EXPIRE" in log or "action=HIDE" in log
    # H4: DRAW after last HIDE would mean repaint-after-hide
    hide_idx = log.rfind("action=HIDE")
    draw_after = "action=DRAW" in log[hide_idx:] if hide_idx >= 0 else False
    print(f"  log has HIDE/EXPIRE: {has_hide or has_expire}; DRAW after HIDE: {draw_after}")
    if not ok or draw_after:
        print("--- log tail ---")
        print("\n".join(log.splitlines()[-40:]))

    OverlayScrollbar.shutdown_all()
    root.destroy()
    return ok and (has_hide or has_expire) and not draw_after


def scenario_poller_kill_recovery() -> bool:
    """Kill global poller after pulse; gen-timer must still hide the pill."""
    import tkinter as tk

    from anonymizer.gui.review_window import OverlayScrollbar, _sb_log_reset

    _sb_log_reset()
    OverlayScrollbar.shutdown_all()

    root = tk.Tk()
    root.geometry("320x480")
    parent = tk.Frame(root, width=300, height=400, bg="#1A1D24")
    parent.pack(fill="both", expand=True)

    def cmd(*_a, **_k):
        pass

    sb = OverlayScrollbar(parent, command=cmd, root=root, name="kill", chrome="#1A1D24")
    sb.set(0.0, 0.25)
    root.update()
    sb.pulse()
    root.update()

    # Simulate dead poller (H1)
    if OverlayScrollbar._poll_job is not None and OverlayScrollbar._poll_root is not None:
        try:
            OverlayScrollbar._poll_root.after_cancel(OverlayScrollbar._poll_job)
        except tk.TclError:
            pass
    OverlayScrollbar._poll_job = None
    # Leave _poll_job None so poller is dead; gen timer must still fire
    print("  poller killed after pulse")

    _pump(root, 2.6)
    ok, mapped, items = _hidden_state(sb)
    print(
        f"  after 2.6s (poller dead): visible={int(sb._visible)} mapped={mapped} "
        f"items={items}  {'OK' if ok else 'FAIL'}"
    )
    log = _read_log()
    via_gen = "via=gen_timer" in log
    print(f"  hide via gen_timer: {via_gen}")
    if not ok:
        print("--- log tail ---")
        print("\n".join(log.splitlines()[-40:]))

    OverlayScrollbar.shutdown_all()
    root.destroy()
    return ok


def scenario_mousewheel_event() -> bool:
    """event_generate MouseWheel on a canvas with yscroll → pulse path hides."""
    import tkinter as tk

    from anonymizer.gui import review_window as rw
    from anonymizer.gui.review_window import OverlayScrollbar, _sb_log_reset, _wheel_steps

    _sb_log_reset()
    OverlayScrollbar.shutdown_all()

    root = tk.Tk()
    root.geometry("360x500")
    frame = tk.Frame(root, bg="#1A1D24")
    frame.pack(fill="both", expand=True)
    frame.grid_rowconfigure(0, weight=1)
    frame.grid_columnconfigure(0, weight=1)

    canvas = tk.Canvas(frame, bg="#1A1D24", highlightthickness=0, yscrollincrement=28)
    sb = OverlayScrollbar(
        frame, command=canvas.yview, root=root, name="wheel", chrome="#1A1D24"
    )
    inner = tk.Frame(canvas, bg="#1A1D24")
    win = canvas.create_window((0, 0), window=inner, anchor="nw")
    for i in range(80):
        tk.Label(inner, text=f"row {i} " + ("x" * 20), bg="#1A1D24", fg="#F3F4F6").pack(
            anchor="w"
        )
    canvas.configure(yscrollcommand=sb.set)
    canvas.grid(row=0, column=0, sticky="nsew")

    def sync(_e=None):
        canvas.configure(scrollregion=canvas.bbox("all") or (0, 0, 1, 1))
        try:
            canvas.itemconfigure(win, width=canvas.winfo_width())
        except tk.TclError:
            pass

    inner.bind("<Configure>", sync)
    canvas.bind("<Configure>", sync)

    def on_wheel(event):
        steps = _wheel_steps(event)
        if steps:
            canvas.yview_scroll(steps, "units")
            try:
                sb.set(*canvas.yview())
            except tk.TclError:
                pass
            sb.pulse()
        return "break"

    canvas.bind("<MouseWheel>", on_wheel)
    root.update_idletasks()
    root.update()
    sync()
    root.update()

    # Generate wheel events (mac delta convention)
    for _ in range(8):
        canvas.event_generate("<MouseWheel>", delta=-1 if sys.platform == "darwin" else -120)
        root.update()
        time.sleep(0.02)

    assert sb._placed or (sb._last - sb._first) >= 0.995, (
        f"expected overflow/placed after wheel; placed={sb._placed} "
        f"first={sb._first} last={sb._last}"
    )
    print(f"  after wheel: placed={int(sb._placed)} first={sb._first:.3f} last={sb._last:.3f}")

    _pump(root, 2.6)
    ok, mapped, items = _hidden_state(sb)
    print(
        f"  after 2.6s idle: visible={int(sb._visible)} mapped={mapped} "
        f"items={items}  {'OK' if ok else 'FAIL'}"
    )
    if not ok:
        print("--- log tail ---")
        print("\n".join(_read_log().splitlines()[-50:]))

    OverlayScrollbar.shutdown_all()
    root.destroy()
    return ok


def scenario_configure_reentry() -> bool:
    """Hide (destroy) must leave no residual widget/items (H4)."""
    import tkinter as tk

    from anonymizer.gui.review_window import OverlayScrollbar, _sb_log_reset

    _sb_log_reset()
    OverlayScrollbar.shutdown_all()

    root = tk.Tk()
    root.geometry("320x480")
    parent = tk.Frame(root, width=300, height=400, bg="#1A1D24")
    parent.pack(fill="both", expand=True)

    def cmd(*_a, **_k):
        pass

    sb = OverlayScrollbar(parent, command=cmd, root=root, name="reentry", chrome="#1A1D24")
    sb.set(0.0, 0.25)
    root.update()
    sb.pulse()
    root.update()
    assert sb._visible
    old_cv = sb._cv

    sb.hide(force=True)
    root.update()
    _pump(root, 0.15)

    ok, mapped, items = _hidden_state(sb)
    # Old canvas widget must be gone
    dead = False
    if old_cv is not None:
        try:
            dead = not old_cv.winfo_exists()
        except tk.TclError:
            dead = True
    else:
        dead = True
    print(
        f"  after hide: visible={int(sb._visible)} mapped={mapped} items={items} "
        f"old_cv_dead={dead}  {'OK' if ok and dead else 'FAIL'}"
    )
    log = _read_log()
    hide_idx = log.rfind("action=HIDE")
    draw_after = False
    if hide_idx >= 0:
        for ln in log[hide_idx:].splitlines()[1:]:
            if "pane=reentry" in ln and "action=DRAW" in ln:
                draw_after = True
                break
    print(f"  DRAW after HIDE: {draw_after}")
    if not ok or draw_after or not dead:
        print("--- log ---")
        print(log)

    OverlayScrollbar.shutdown_all()
    root.destroy()
    return ok and dead and not draw_after


def scenario_review_window() -> bool:
    """Drive real run_review_window with programmatic wheel + idle."""
    import tkinter as tk

    from anonymizer.anonymize.review import ReviewFinding, ReviewSession
    from anonymizer.gui.review_window import OverlayScrollbar, run_review_window, _sb_log_path

    # Long enough content + many findings for list overflow
    blocks = ["\n".join(f"Line {i} of the sample document with padding." for i in range(120))]
    findings = []
    for i in range(40):
        surface = f"Person{i} Example"
        findings.append(
            ReviewFinding(
                placeholder=f"[PERSON_{i+1}]",
                original=surface,
                entity_type="PERSON",
                enabled=True,
                source="auto",
                occurrence_count=1,
            )
        )
        blocks[0] = blocks[0] + f"\nContact {surface}."

    session = ReviewSession(original_blocks=blocks, findings=findings)

    # Patch: auto-close after test sequence instead of infinite mainloop
    from anonymizer.gui import review_window as rw

    result_ok = {"ok": False}

    original_mainloop = tk.Tk.mainloop

    def scripted_mainloop(self):  # noqa: ANN001
        try:
            self.update_idletasks()
            self.update()
            # Find list scrollbar
            lists = [s for s in OverlayScrollbar._instances if s._name == "list"]
            docs = [s for s in OverlayScrollbar._instances if s._name == "doc"]
            print(f"  instances list={len(lists)} doc={len(docs)}")
            if not lists:
                result_ok["ok"] = False
                self.destroy()
                return
            list_sb = lists[0]
            # Prefer event_generate on the list canvas parent
            parent = list_sb._parent
            for child in parent.winfo_children():
                if child.winfo_class() == "Canvas" and child is not list_sb._cv:
                    for _ in range(10):
                        child.event_generate(
                            "<MouseWheel>",
                            delta=-1 if sys.platform == "darwin" else -120,
                        )
                        self.update()
                        time.sleep(0.01)
                    break
            else:
                list_sb.set(0.0, 0.2)
                list_sb.pulse()
                self.update()

            print(f"  after scroll list visible={int(list_sb._visible)}")
            # Idle without touching other pane
            end = time.monotonic() + 2.7
            while time.monotonic() < end:
                self.update()
                time.sleep(0.05)
            hidden, mapped, items = _hidden_state(list_sb)
            print(
                f"  after idle list visible={int(list_sb._visible)} mapped={mapped} "
                f"items={items} mode={'surface' if not list_sb._owns_cv else 'owned'} "
                f"{'OK' if hidden else 'FAIL'}"
            )
            result_ok["ok"] = hidden
            log = Path(_sb_log_path()).read_text(encoding="utf-8")
            print(f"  log path: {_sb_log_path()}")
            # Show list-related lines
            lines = [
                ln
                for ln in log.splitlines()
                if "pane=list" in ln
                and any(
                    a in ln
                    for a in (
                        "PULSE",
                        "HIDE",
                        "EXPIRE",
                        "ARM_TIMER",
                        "POLL_STOP",
                    )
                )
            ]
            print("  list events:", len(lines))
            for ln in lines[-15:]:
                print("   ", ln)
        finally:
            try:
                OverlayScrollbar.shutdown_all()
            except Exception:  # noqa: BLE001
                pass
            try:
                self.destroy()
            except Exception:  # noqa: BLE001
                pass

    tk.Tk.mainloop = scripted_mainloop  # type: ignore[method-assign]
    try:
        run_review_window(session, file_label="debug_sb_hide")
    finally:
        tk.Tk.mainloop = original_mainloop  # type: ignore[method-assign]

    return bool(result_ok["ok"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--review",
        action="store_true",
        help="Also run full review-window scripted scenario",
    )
    args = ap.parse_args()

    print(f"debug log → {os.environ.get('ANONYMIZER_SB_LOG') or '(default temp)'}")
    results: list[tuple[str, bool]] = []

    print("\n[1] minimal pulse → hide")
    results.append(("minimal_pulse_hide", scenario_minimal_pulse_hide()))

    print("\n[2] poller kill → gen-timer hide")
    results.append(("poller_kill_recovery", scenario_poller_kill_recovery()))

    print("\n[3] MouseWheel event_generate → hide")
    results.append(("mousewheel_event", scenario_mousewheel_event()))

    print("\n[4] Configure re-entry during hide (H4)")
    results.append(("configure_reentry", scenario_configure_reentry()))

    if args.review:
        print("\n[5] full review window scripted")
        results.append(("review_window", scenario_review_window()))

    print("\n=== summary ===")
    all_ok = True
    for name, ok in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
        all_ok = all_ok and ok
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
