"""Interactive document review window (Tk): accept, reject, add redactions.

Dark theme, high contrast, rounded cards, screen-fitting window size.
Explicit tk colours (no global ttk style hacks). Offline; no network.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from typing import Callable

from anonymizer.anonymize.review import (
    REVIEW_ADD_TYPES,
    ReviewFinding,
    ReviewSession,
    count_surface_occurrences,
    resolve_surface_in_blocks,
)

try:
    import tkinter as tk
    from tkinter import font as tkfont
    from tkinter import messagebox
except ImportError:  # pragma: no cover
    tk = None  # type: ignore[assignment]
    tkfont = None  # type: ignore[assignment]


# ── Overlay scrollbar debug log (opt-in) ──────────────────────────
# Set ANONYMIZER_SB_DEBUG=1 for file log + hot-pink pills while diagnosing.
def _sb_debug_enabled() -> bool:
    v = os.environ.get("ANONYMIZER_SB_DEBUG", "0").strip().lower()
    return v in {"1", "true", "yes", "on"}


def _sb_log_path() -> str:
    override = os.environ.get("ANONYMIZER_SB_LOG", "").strip()
    if override:
        return override
    # Prefer /tmp on Unix for a stable path users can `tail -f`
    if sys.platform != "win32":
        return "/tmp/anonymizer-sb.log"
    return os.path.join(tempfile.gettempdir(), "anonymizer-sb.log")


_SB_LOG_T0 = time.monotonic()
_SB_LOG_LAST: dict[str, float] = {}  # rate-limit key → monotonic


def _sb_log_reset() -> None:
    """Truncate log for a fresh review session."""
    global _SB_LOG_T0
    _SB_LOG_T0 = time.monotonic()
    _SB_LOG_LAST.clear()
    if not _sb_debug_enabled():
        return
    path = _sb_log_path()
    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(f"# anonymizer scrollbar debug  t0={time.time():.3f}\n")
            fh.flush()
    except OSError:
        return
    try:
        print(f"scrollbar debug log: {path}", file=sys.stderr)
    except OSError:
        pass


def _sb_log(action: str, *, pane: str = "?", rate_hz: float = 0.0, **fields: object) -> None:
    if not _sb_debug_enabled():
        return
    if rate_hz > 0:
        key = f"{pane}:{action}"
        now = time.monotonic()
        min_gap = 1.0 / rate_hz
        prev = _SB_LOG_LAST.get(key, 0.0)
        if now - prev < min_gap:
            return
        _SB_LOG_LAST[key] = now
    t = time.monotonic() - _SB_LOG_T0
    parts = [f"t={t:.3f}", f"pane={pane}", f"action={action}"]
    for k, v in fields.items():
        if isinstance(v, float):
            parts.append(f"{k}={v:.3f}")
        else:
            parts.append(f"{k}={v}")
    line = " ".join(parts) + "\n"
    try:
        with open(_sb_log_path(), "a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()
    except OSError:
        pass


# ── Dark theme tokens (plain names in comments) ───────────────────
_BG_APP = "#0F1115"  # near-black charcoal — window
_BG_PANEL = "#1A1D24"  # dark slate — cards
_BG_ELEVATED = "#242830"  # raised charcoal — toolbars / footer
_BG_SELECTED = "#1E3A5F"  # deep navy — selected list row
_BORDER = "#3A3F4B"  # soft grey border

_TEXT = "#F3F4F6"  # off-white primary
_TEXT_MUTED = "#9CA3AF"  # muted silver
_TEXT_ON_AMBER = "#FFFBEB"  # cream on amber
_TEXT_ON_BLUE = "#EFF6FF"  # ice white on strong blue

_ACCENT = "#60A5FA"  # sky blue accent
_HL_REDACT_BG = "#CA8A04"  # warm amber
_HL_SELECTED_BG = "#1D4ED8"  # strong blue

# Overlay scrollbar pills (macOS-like; no gutter slab)
_SB_THUMB = "#8B93A7"  # idle — visible on dark panel
_SB_THUMB_HOVER = "#C4CBD8"  # hover
_SB_THUMB_ACTIVE = "#93C5FD"  # drag (soft sky)

_PAD = 16
_GAP = 12
_RADIUS = 14
_LIST_SNIPPET_MAX = 48
_SEARCH_PLACEHOLDER = "Search findings…"

_FONT = ("Helvetica", 13) if sys.platform == "darwin" else ("Segoe UI", 11)
_FONT_BOLD = ("Helvetica", 14, "bold") if sys.platform == "darwin" else ("Segoe UI", 12, "bold")
_FONT_SMALL = ("Helvetica", 12) if sys.platform == "darwin" else ("Segoe UI", 10)
_FONT_TINY = ("Helvetica", 10) if sys.platform == "darwin" else ("Segoe UI", 9)
_FONT_MONO = ("Menlo", 12) if sys.platform == "darwin" else ("Consolas", 11)
_FONT_DOC = ("Menlo", 13) if sys.platform == "darwin" else ("Consolas", 12)


def display_available() -> bool:
    if tk is None:
        return False
    if sys.platform in {"darwin", "win32"}:
        return True
    import os

    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _human_type_label(f: ReviewFinding) -> str:
    """Map engine type / placeholder label to short UI name."""
    from anonymizer.anonymize.mapping import placeholder_label

    for ent, lab in REVIEW_ADD_TYPES:
        if ent == f.entity_type:
            return lab
    for ent, lab in REVIEW_ADD_TYPES:
        if placeholder_label(ent) == f.type_label:
            return lab
    return f.type_label.replace("_", " ").title()


def format_finding_primary(f: ReviewFinding, *, max_original: int = 500) -> str:
    """Line 1: full original surface (UI applies pixel ellipsis)."""
    return f.original.replace("\n", " ").replace("\r", "")[:max_original]


def ellipsize_text(text: str, font: object, max_px: int) -> str:
    """Longest prefix of ``text`` that fits in ``max_px``, with … if truncated."""
    if max_px <= 0 or not text:
        return ""
    try:
        measure = font.measure  # tkFont.Font
    except AttributeError:
        return text
    if measure(text) <= max_px:
        return text
    ell = "…"
    ell_w = measure(ell)
    if ell_w >= max_px:
        return ell
    budget = max_px - ell_w
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if measure(text[:mid]) <= budget:
            lo = mid
        else:
            hi = mid - 1
    return (text[:lo] + ell) if lo < len(text) else text


def format_finding_secondary(f: ReviewFinding) -> str:
    """Line 2: type · tag · user-added marker."""
    parts = [_human_type_label(f), f.placeholder]
    if f.source == "user":
        parts.append("added")
    return " · ".join(parts)


def format_finding_label(f: ReviewFinding, *, max_original: int = _LIST_SNIPPET_MAX) -> str:
    """Single-line summary (tests / legacy)."""
    n = f" ×{f.occurrence_count}" if f.occurrence_count > 1 else ""
    return f"{format_finding_primary(f, max_original=max_original)}{n}  ({format_finding_secondary(f)})"


def format_finding_row(f: ReviewFinding, *, max_original: int = _LIST_SNIPPET_MAX) -> str:
    mark = "[x]" if f.enabled else "[ ]"
    return f"{mark} {format_finding_label(f, max_original=max_original)}"


def _shortcut_help_text() -> str:
    if sys.platform == "darwin":
        save = "⌘S save"
    elif sys.platform == "win32":
        save = "Ctrl+S save"
    else:
        save = "Ctrl+S save"
    return (
        "↑/↓ move  ·  space or double-click toggle  ·  "
        f"select text → a or right-click → choose type  ·  {save}  ·  esc cancel"
    )


def _save_key_sequences() -> tuple[str, ...]:
    """Platform save chords: ⌘S (mac) / Ctrl+S (Windows/Linux).

    Windows Tcl/Tk has no ``Super`` keysym — binding ``<Super-s>`` raises
    ``TclError`` after the window is built (flash-close). Prefer Control on
    non-mac platforms; Super/Meta are optional extras where supported.
    """
    if sys.platform == "darwin":
        return ("<Command-s>", "<Command-S>")
    if sys.platform == "win32":
        return ("<Control-s>", "<Control-S>")
    # Linux / other: Control first; Super/Meta may work on X11
    return (
        "<Control-s>",
        "<Control-S>",
        "<Super-s>",
        "<Super-S>",
        "<Meta-s>",
        "<Meta-S>",
    )

def _wheel_steps(event: object) -> int:
    """Signed step count for one wheel/trackpad event (clamped; never page-scale).

    macOS Aqua often reports ±1 per event (many events per gesture). Canvas
    without yscrollincrement scrolls ~10% of the window per unit — that feels
    like skipping pages. We always return a small step and rely on a pixel
    yscrollincrement for the findings canvas.
    """
    d = int(getattr(event, "delta", 0) or 0)
    if d == 0:
        return 0
    if sys.platform == "darwin":
        # Direction: positive delta → scroll up content (negative yview steps)
        return -1 if d > 0 else 1
    # Windows / X11: multiples of 120
    steps = int(-d / 120)
    if steps == 0:
        steps = -1 if d > 0 else 1
    return max(-3, min(3, steps))


class OverlayScrollbar:
    """Modern overlay scrollbar: thin rounded pill, wide hit area, auto-hide.

    Two draw modes:

    * **surface** (preferred for ``tk.Canvas`` hosts): pill items are drawn
      *on the host canvas* with a private tag. Hide = ``delete(tag)`` — no
      separate mapped window, so Aqua cannot leave a compositor ghost.
    * **owned** (for ``tk.Text`` etc.): a child Canvas overlay. Hide
      **destroys** the widget (not just ``place_forget``) so nothing remains.

    Hide is also multi-path (deadline poller + generation timer + stuck-drag).
    """

    HIDE_S = 2.0  # seconds after last scroll/drag before force-hide
    POLL_MS = 200  # global poller interval
    HIT_W = 16  # full hit strip width
    PILL_W = 7  # visual thumb width (idle)
    PILL_W_ACTIVE = 9  # hover / drag
    EDGE_PX = 28
    PAD_Y = 10
    MIN_THUMB = 36
    STUCK_DRAG_S = 0.5  # force-clear drag this long past deadline
    # When debug logging is on, use an unmistakable colour so a leftover grey
    # system indicator can be distinguished from *our* pill.
    _DEBUG_THUMB = "#FF2D55"

    # All live bars — one poller on the review root hides expired ones
    _instances: list[OverlayScrollbar] = []
    _poll_root: tk.Misc | None = None
    _poll_job: str | None = None
    _poll_last_tick: float = 0.0  # monotonic; zombie detection

    def __init__(
        self,
        parent: tk.Misc,
        *,
        command,
        root: tk.Misc,
        chrome: str = _BG_PANEL,
        name: str = "?",
        surface: tk.Canvas | None = None,
        on_event: Callable[[str], None] | None = None,
    ) -> None:
        self._root = root
        self._parent = parent
        self._command = command
        self._chrome = chrome
        self._name = name
        self._on_event = on_event
        self._tag = f"osb_{name}_{id(self)}"
        # surface mode: draw on host Canvas; owned mode: separate overlay widget
        self._surface: tk.Canvas | None = surface
        self._owns_cv = surface is None
        self._cv: tk.Canvas | None = None
        self._geo_retry_job: str | None = None
        self._hide_deadline = 0.0  # monotonic; hide when now >= deadline
        self._hide_gen = 0  # generation token for per-instance after()
        self._hide_after_job: str | None = None
        self._hovered = False
        self._edge_hover = False
        self._dragging = False
        self._first = 0.0
        self._last = 1.0
        self._placed = False
        # Gates all drawing. Cleared before any unmap/destroy.
        self._visible = False
        self._thumb_y0 = 0.0
        self._thumb_y1 = 0.0
        self._drag_offset = 0.0  # pointer y within thumb at press
        self._hide_verify_job: str | None = None

        if self._owns_cv:
            self._ensure_owned_cv()
        else:
            assert surface is not None
            self._cv = surface
            # Drag interactions on the right edge of the host canvas
            surface.bind("<ButtonPress-1>", self._on_surface_press, add="+")
            surface.bind("<B1-Motion>", self._on_drag, add="+")
            surface.bind("<ButtonRelease-1>", self._on_release, add="+")
            surface.bind("<Motion>", self._on_surface_motion, add="+")
            surface.bind("<Leave>", self._on_surface_leave, add="+")

        parent.bind("<Motion>", self._on_parent_motion, add="+")
        parent.bind("<Leave>", self._on_parent_leave, add="+")

        OverlayScrollbar._instances.append(self)
        OverlayScrollbar._ensure_poller(root)
        self._log(
            "INIT",
            n_inst=len(OverlayScrollbar._instances),
            mode="owned" if self._owns_cv else "surface",
        )

    def _make_owned_cv(self) -> tk.Canvas:
        cv = tk.Canvas(
            self._parent,
            width=self.HIT_W,
            highlightthickness=0,
            bd=0,
            bg=self._chrome,
            cursor="arrow",
        )
        cv.bind("<Configure>", self._on_configure)
        cv.bind("<Enter>", self._on_enter)
        cv.bind("<Leave>", self._on_leave)
        cv.bind("<ButtonPress-1>", self._on_press)
        cv.bind("<B1-Motion>", self._on_drag)
        cv.bind("<ButtonRelease-1>", self._on_release)
        return cv

    def _ensure_owned_cv(self) -> tk.Canvas:
        if not self._owns_cv:
            assert self._cv is not None
            return self._cv
        if self._cv is not None:
            try:
                if self._cv.winfo_exists():
                    return self._cv
            except tk.TclError:
                pass
        self._cv = self._make_owned_cv()
        self._placed = False
        self._log("CREATE_CV")
        return self._cv

    def _emit(self, event: str) -> None:
        if self._on_event is not None:
            try:
                self._on_event(event)
            except Exception:  # noqa: BLE001
                pass

    # ── logging helpers ───────────────────────────────────────────

    def _log(self, action: str, *, rate_hz: float = 0.0, **fields: object) -> None:
        fields.setdefault("placed", int(self._placed))
        fields.setdefault("visible", int(self._visible))
        fields.setdefault("drag", int(self._dragging))
        fields.setdefault("hover", int(self._hovered or self._edge_hover))
        if self._hide_deadline > 0:
            fields.setdefault(
                "deadline_in", max(0.0, self._hide_deadline - time.monotonic())
            )
        else:
            fields.setdefault("deadline_in", -1.0)
        fields.setdefault("poll_job", int(OverlayScrollbar._poll_job is not None))
        fields.setdefault("n_inst", len(OverlayScrollbar._instances))
        fields.setdefault("first", self._first)
        fields.setdefault("last", self._last)
        fields.setdefault("gen", self._hide_gen)
        fields.setdefault("mode", "owned" if self._owns_cv else "surface")
        try:
            if self._cv is not None and self._cv.winfo_exists():
                if self._owns_cv:
                    fields.setdefault("mapped", int(bool(self._cv.winfo_ismapped())))
                else:
                    # surface mode: count our tag items as "mapped" proxy
                    fields.setdefault(
                        "mapped", int(bool(self._cv.find_withtag(self._tag)))
                    )
            else:
                fields.setdefault("mapped", 0)
        except tk.TclError:
            fields.setdefault("mapped", -1)
        _sb_log(action, pane=self._name, rate_hz=rate_hz, **fields)

    def _on_configure(self, _event=None) -> None:
        """Geometry change on the overlay canvas — never paint when hidden."""
        if not self._visible:
            self._scrub_drawings()
            return
        self._redraw()

    def _arm_hide_timer(self) -> None:
        """Schedule a generation-token hide independent of the global poller."""
        self._hide_gen += 1
        gen = self._hide_gen
        self._cancel_hide_after()
        delay_ms = max(int(self.HIDE_S * 1000), 50)
        try:
            self._hide_after_job = self._root.after(
                delay_ms, lambda g=gen: self._hide_if_gen(g)
            )
            self._log("ARM_TIMER", rate_hz=10.0, delay_ms=delay_ms, gen=gen)
        except tk.TclError:
            self._hide_after_job = None
            self._log("ARM_TIMER_FAIL")

    def _cancel_hide_after(self) -> None:
        if self._hide_after_job is not None:
            try:
                self._root.after_cancel(self._hide_after_job)
            except tk.TclError:
                pass
            self._hide_after_job = None

    def _hide_if_gen(self, gen: int) -> None:
        self._hide_after_job = None
        if gen != self._hide_gen:
            self._log("GEN_STALE", gen=gen, cur=self._hide_gen)
            return
        now = time.monotonic()
        if self._dragging:
            # Re-arm shortly; stuck-drag path will force if needed
            self._log("GEN_SKIP", reason="drag")
            if now >= self._hide_deadline + self.STUCK_DRAG_S:
                self._dragging = False
                self._log("STUCK_DRAG_CLEAR", via="gen")
                self.hide(force=True)
            else:
                try:
                    self._hide_after_job = self._root.after(
                        200, lambda g=gen: self._hide_if_gen(g)
                    )
                except tk.TclError:
                    pass
            return
        if not self._visible and not self._placed:
            self._log("GEN_SKIP", reason="not_visible")
            return
        if self._hide_deadline > 0 and now < self._hide_deadline:
            # Extended by another pulse path without gen bump (shouldn't happen)
            remain_ms = max(int((self._hide_deadline - now) * 1000), 50)
            try:
                self._hide_after_job = self._root.after(
                    remain_ms, lambda g=gen: self._hide_if_gen(g)
                )
            except tk.TclError:
                pass
            return
        self._log("EXPIRE", via="gen_timer")
        self.hide(force=True)

    @classmethod
    def _ensure_poller(cls, root: tk.Misc) -> None:
        """Start or revive the global hide poller for this review window root."""
        now = time.monotonic()
        # Zombie: job id set but no tick for too long → force restart
        if (
            cls._poll_job is not None
            and cls._poll_root is root
            and cls._poll_last_tick > 0
            and (now - cls._poll_last_tick) > (cls.POLL_MS / 1000.0) * 4
        ):
            _sb_log(
                "ENSURE",
                pane="poller",
                reason="zombie_revive",
                age=now - cls._poll_last_tick,
            )
            if cls._poll_root is not None:
                try:
                    cls._poll_root.after_cancel(cls._poll_job)
                except tk.TclError:
                    pass
            cls._poll_job = None

        # New Tk root (re-opened review) → drop stale job/instances from prior window
        if cls._poll_root is not root:
            if cls._poll_job is not None and cls._poll_root is not None:
                try:
                    cls._poll_root.after_cancel(cls._poll_job)
                except tk.TclError:
                    pass
            cls._poll_job = None
            cls._instances = [s for s in cls._instances if s._root is root]
            cls._poll_root = root
            _sb_log("ENSURE", pane="poller", reason="new_root", n_inst=len(cls._instances))

        if cls._poll_job is None:
            _sb_log("ENSURE", pane="poller", reason="start", n_inst=len(cls._instances))
            cls._poll_tick()
        else:
            _sb_log(
                "ENSURE",
                pane="poller",
                reason="already_running",
                rate_hz=5.0,
                n_inst=len(cls._instances),
            )

    @classmethod
    def _poll_tick(cls) -> None:
        cls._poll_job = None
        cls._poll_last_tick = time.monotonic()
        now = cls._poll_last_tick
        reschedule = False
        try:
            alive: list[OverlayScrollbar] = []
            for sb in list(cls._instances):
                try:
                    if not sb._root.winfo_exists():
                        _sb_log("POLL_DROP", pane=sb._name, reason="root_gone")
                        continue
                    sb._expire_if_due(now)
                    alive.append(sb)
                except tk.TclError as exc:
                    _sb_log("POLL_DROP", pane=getattr(sb, "_name", "?"), reason=f"tcl:{exc}")
                    continue
                except Exception as exc:  # noqa: BLE001 — never kill poller
                    _sb_log(
                        "POLL_ERR",
                        pane=getattr(sb, "_name", "?"),
                        reason=type(exc).__name__,
                    )
                    alive.append(sb)
            cls._instances = alive
            root = cls._poll_root
            if root is None:
                _sb_log("POLL_STOP", pane="poller", reason="no_root")
                return
            if not alive:
                _sb_log("POLL_STOP", pane="poller", reason="no_instances")
                return
            try:
                if not root.winfo_exists():
                    cls._poll_root = None
                    _sb_log("POLL_STOP", pane="poller", reason="root_dead")
                    return
            except tk.TclError:
                cls._poll_root = None
                _sb_log("POLL_STOP", pane="poller", reason="root_tcl")
                return
            reschedule = True
            _sb_log(
                "POLL",
                pane="poller",
                rate_hz=5.0,
                n_inst=len(alive),
                placed=sum(1 for s in alive if s._is_showing()),
            )
        except Exception as exc:  # noqa: BLE001
            _sb_log("POLL_CRASH", pane="poller", reason=type(exc).__name__)
            reschedule = bool(cls._instances) and cls._poll_root is not None
        finally:
            if reschedule and cls._poll_root is not None:
                try:
                    cls._poll_job = cls._poll_root.after(cls.POLL_MS, cls._poll_tick)
                except tk.TclError:
                    cls._poll_job = None
                    cls._poll_root = None
                    _sb_log("POLL_STOP", pane="poller", reason="after_fail")

    @classmethod
    def shutdown_all(cls) -> None:
        """Cancel poller and clear registry (call when review window closes)."""
        _sb_log("SHUTDOWN", pane="poller", n_inst=len(cls._instances))
        if cls._poll_job is not None and cls._poll_root is not None:
            try:
                cls._poll_root.after_cancel(cls._poll_job)
            except tk.TclError:
                pass
        cls._poll_job = None
        cls._poll_root = None
        cls._poll_last_tick = 0.0
        for sb in list(cls._instances):
            try:
                sb._cancel_hide_after()
                sb._cancel_hide_verify()
                sb.hide(force=True)
            except tk.TclError:
                pass
        cls._instances.clear()

    def _is_showing(self) -> bool:
        return self._visible and (self._placed or not self._owns_cv)

    def _expire_if_due(self, now: float | None = None) -> None:
        """Hide if past deadline (and not mid-drag). Safe to call often."""
        if now is None:
            now = time.monotonic()
        if not self._is_showing() and not self._visible:
            return
        if self._hide_deadline <= 0:
            return
        if self._dragging:
            if now >= self._hide_deadline + self.STUCK_DRAG_S:
                self._log("STUCK_DRAG_CLEAR", via="expire")
                self._dragging = False
                self.hide(force=True)
            else:
                self._log("EXPIRE_SKIP", reason="drag", rate_hz=2.0)
            return
        if now >= self._hide_deadline:
            self._log("EXPIRE", via="deadline")
            self.hide(force=True)

    def destroy(self) -> None:
        try:
            OverlayScrollbar._instances.remove(self)
        except ValueError:
            pass
        self._cancel_hide_after()
        self.hide(force=True)

    # ── yscrollcommand API ────────────────────────────────────────

    def set(self, first: str | float, last: str | float) -> None:
        """Update thumb geometry only — never show or extend the hide deadline."""
        try:
            f, l = float(first), float(last)
        except (TypeError, ValueError):
            return
        self._first, self._last = max(0.0, f), min(1.0, l)
        self._log("SET", rate_hz=5.0)
        if not self._overflows():
            self.hide(force=True)
            return
        # Layout traffic also expires overdue pills (backup if poller lags)
        self._expire_if_due()
        if self._visible and (self._placed or not self._owns_cv):
            self._redraw()

    def _overflows(self) -> bool:
        # Content taller than viewport (standard Tk yscroll fractions)
        return (self._last - self._first) < 0.995

    def pulse(self) -> None:
        """User scrolled this pane: show pill and start/extend 2s hide deadline."""
        if not self._overflows():
            self.hide(force=True)
            return
        self._hide_deadline = time.monotonic() + self.HIDE_S
        OverlayScrollbar._ensure_poller(self._root)
        self._arm_hide_timer()
        self._log("PULSE")
        self.show()

    def show(self) -> None:
        was = self._visible and (self._placed or not self._owns_cv)
        self._visible = True
        if self._owns_cv:
            cv = self._ensure_owned_cv()
            try:
                # Always re-place so the strip sits on the parent’s right edge
                cv.place(
                    relx=1.0,
                    rely=0.0,
                    relheight=1.0,
                    anchor="ne",
                    width=self.HIT_W,
                )
                self._placed = True
            except tk.TclError:
                self._visible = False
                self._placed = False
                return
            # Canvas.lift() is tag_raise (items), NOT widget stacking — that
            # TclError used to abort show() and made the pill never appear.
            try:
                tk.Misc.lift(cv)
            except tk.TclError:
                try:
                    cv.tk.call("raise", cv._w)
                except tk.TclError:
                    pass
            # One geometry pass so the first DRAW has a real height
            try:
                cv.update_idletasks()
            except tk.TclError:
                pass
        # Draw immediately (surface) or on owned canvas
        self._redraw()
        if not was:
            self._log("SHOW")

    def hide(self, force: bool = False) -> None:
        """Remove the pill completely.

        * surface mode: delete tagged items on the host canvas
        * owned mode: **destroy** the overlay Canvas (place_forget left Aqua ghosts)
        """
        if self._dragging and not force:
            self._log("HIDE_SKIP", reason="drag")
            return
        was = self._visible or self._placed
        # Gate all drawing first
        self._visible = False
        self._placed = False
        self._hovered = False
        self._edge_hover = False
        self._hide_deadline = 0.0
        if force:
            self._dragging = False
        self._cancel_geo_retry()
        self._cancel_hide_after()
        self._cancel_hide_verify()

        residual = 0
        if not self._owns_cv and self._cv is not None:
            try:
                self._cv.delete(self._tag)
                residual = int(bool(self._cv.find_withtag(self._tag)))
            except tk.TclError:
                residual = -1
            self._log("HIDE", force=int(force), mapped=residual, via="tag_delete")
        else:
            # Owned overlay: destroy the widget entirely (no ghost window)
            cv = self._cv
            self._cv = None
            if cv is not None:
                try:
                    cv.delete("all")
                except tk.TclError:
                    pass
                try:
                    cv.place_forget()
                except tk.TclError:
                    pass
                try:
                    cv.destroy()
                    residual = 0
                    self._log("DESTROY")
                except tk.TclError:
                    residual = -1
            if was:
                self._log("HIDE", force=int(force), mapped=residual, via="destroy")

        if was:
            if _sb_debug_enabled():
                self._emit(f"{self._name} pill hidden")
            try:
                self._hide_verify_job = self._root.after(50, self._verify_hidden)
            except tk.TclError:
                self._hide_verify_job = None

    def _force_unmap(self) -> int:
        """Best-effort scrub; return residual item/map count (0 = clean)."""
        if not self._owns_cv:
            if self._cv is None:
                return 0
            try:
                self._cv.delete(self._tag)
                return int(bool(self._cv.find_withtag(self._tag)))
            except tk.TclError:
                return -1
        if self._cv is None:
            return 0
        try:
            exists = bool(self._cv.winfo_exists())
        except tk.TclError:
            self._cv = None
            return 0
        if not exists:
            self._cv = None
            return 0
        try:
            self._cv.destroy()
        except tk.TclError:
            pass
        self._cv = None
        return 0

    def _cancel_hide_verify(self) -> None:
        if self._hide_verify_job is not None:
            try:
                self._root.after_cancel(self._hide_verify_job)
            except tk.TclError:
                pass
            self._hide_verify_job = None

    def _verify_hidden(self) -> None:
        """Idle pass: if we intended to hide, ensure nothing is painted/mapped."""
        self._hide_verify_job = None
        if self._visible:
            return
        residual = self._force_unmap()
        self._placed = False
        if residual:
            self._log("HIDE_RETRY", mapped=residual)

    def _cancel_geo_retry(self) -> None:
        if self._geo_retry_job is not None:
            try:
                self._root.after_cancel(self._geo_retry_job)
            except tk.TclError:
                pass
            self._geo_retry_job = None

    # ── drawing ───────────────────────────────────────────────────

    def _thumb_color(self) -> str:
        # Debug: hot pink so "our" pill is unmistakable vs system grey indicators
        if _sb_debug_enabled():
            if self._dragging:
                return "#FF6B8A"
            if self._hovered or self._edge_hover:
                return "#FF4D6D"
            return self._DEBUG_THUMB
        if self._dragging:
            return _SB_THUMB_ACTIVE
        if self._hovered or self._edge_hover:
            return _SB_THUMB_HOVER
        return _SB_THUMB

    def _pill_width(self) -> int:
        return self.PILL_W_ACTIVE if (self._hovered or self._dragging) else self.PILL_W

    def _viewport_size(self) -> tuple[int, int] | None:
        """Return (width, height) of the drawing surface viewport, or None."""
        cv = self._cv
        if cv is None:
            return None
        try:
            w = int(cv.winfo_width())
            h = int(cv.winfo_height())
        except tk.TclError:
            return None
        if h < 8 or w < 4:
            return None
        return w, h

    def _geometry(self) -> tuple[float, float, float] | None:
        """Return (thumb_y0, thumb_y1, track_h) in *viewport* coords, or None."""
        size = self._viewport_size()
        if size is None:
            return None
        _w, h = size
        track_h = max(h - 2 * self.PAD_Y, 1)
        span = max(min(self._last - self._first, 1.0), 0.02)
        thumb_h = max(float(self.MIN_THUMB), track_h * span)
        thumb_h = min(thumb_h, float(track_h))
        travel = max(track_h - thumb_h, 0.0)
        denom = max(1.0 - span, 1e-6)
        t = min(max(self._first / denom, 0.0), 1.0)
        y0 = self.PAD_Y + t * travel
        y1 = y0 + thumb_h
        return y0, y1, float(track_h)

    def _draw_pill(
        self,
        cv: tk.Canvas,
        x0: float,
        y0: float,
        x1: float,
        y1: float,
        fill: str,
        *,
        tags: str | tuple[str, ...] = (),
    ) -> None:
        """Capsule: two ovals + center rect (reliable; no smooth-polygon glitches)."""
        w = max(int(x1 - x0), 2)
        h = max(int(y1 - y0), 2)
        r = w // 2
        kw: dict = {"fill": fill, "outline": fill, "width": 0}
        if tags:
            kw["tags"] = tags
        # Too short for full capsule — simple rounded oval
        if h <= w:
            cv.create_oval(x0, y0, x1, y1, **kw)
            return
        cv.create_oval(x0, y0, x1, y0 + w, **kw)
        cv.create_oval(x0, y1 - w, x1, y1, **kw)
        cv.create_rectangle(x0, y0 + r, x1, y1 - r, **kw)

    def _redraw(self) -> None:
        # Never paint when hidden
        if not self._visible:
            self._scrub_drawings()
            return
        if self._owns_cv and not self._placed:
            return
        if self._cv is None:
            return
        # Expire on any redraw path (does not rely solely on poller timing)
        self._expire_if_due()
        if not self._visible:
            return
        if self._owns_cv and not self._placed:
            return
        try:
            self._scrub_drawings()
            if not self._overflows():
                return
            geo = self._geometry()
            if geo is None:
                if self._geo_retry_job is None:
                    try:
                        self._geo_retry_job = self._root.after(50, self._geo_retry)
                    except tk.TclError:
                        self._geo_retry_job = None
                return
            self._cancel_geo_retry()
            y0, y1, _ = geo
            self._thumb_y0, self._thumb_y1 = y0, y1
            pw = self._pill_width()
            cv = self._cv
            if not self._owns_cv:
                # Host canvas: pin pill to the *viewport* right edge (canvas coords)
                try:
                    top = float(cv.canvasy(0))
                    left = float(cv.canvasx(0))
                    vw = int(cv.winfo_width())
                except tk.TclError:
                    return
                x0 = left + vw - self.HIT_W + (self.HIT_W - pw) // 2
                x1 = x0 + pw
                self._draw_pill(
                    cv, x0, top + y0, x1, top + y1, self._thumb_color(), tags=self._tag
                )
                try:
                    cv.tag_raise(self._tag)
                except tk.TclError:
                    pass
            else:
                x0 = (self.HIT_W - pw) // 2
                x1 = x0 + pw
                self._draw_pill(cv, x0, int(y0), x1, int(y1), self._thumb_color())
            self._log("DRAW", rate_hz=8.0)
        except tk.TclError:
            pass

    def _scrub_drawings(self) -> None:
        if self._cv is None:
            return
        try:
            if self._owns_cv:
                self._cv.delete("all")
            else:
                self._cv.delete(self._tag)
        except tk.TclError:
            pass

    def _geo_retry(self) -> None:
        self._geo_retry_job = None
        try:
            if not self._root.winfo_exists():
                return
        except tk.TclError:
            return
        if self._visible and (self._placed or not self._owns_cv):
            self._redraw()

    # ── interaction ───────────────────────────────────────────────

    def _moveto(self, first: float) -> None:
        span = max(self._last - self._first, 0.02)
        first = max(0.0, min(first, max(0.0, 1.0 - span)))
        try:
            self._command("moveto", first)
        except tk.TclError:
            try:
                self._command("moveto", str(first))
            except tk.TclError:
                pass

    def _y_to_first(self, y: float) -> float:
        """Map pointer y (viewport coords) to scroll first-fraction."""
        geo = self._geometry()
        if geo is None:
            return self._first
        y0, y1, track_h = geo
        thumb_h = y1 - y0
        travel = max(track_h - thumb_h, 1e-6)
        span = max(self._last - self._first, 0.02)
        top = y - self._drag_offset - self.PAD_Y
        t = min(max(top / travel, 0.0), 1.0)
        return t * max(1.0 - span, 0.0)

    def _on_enter(self, _event=None) -> None:
        self._hovered = True
        self._expire_if_due()
        if self._is_showing():
            self._redraw()

    def _on_leave(self, _event=None) -> None:
        self._hovered = False
        self._expire_if_due()
        if self._is_showing():
            self._redraw()

    def _on_press(self, event) -> None:
        """Owned-canvas press (event.y already in overlay coords)."""
        if not self._overflows() or not self._is_showing():
            return
        y = float(event.y)
        geo = self._geometry()
        if geo is None:
            return
        y0, y1, _ = geo
        if y0 <= y <= y1:
            self._dragging = True
            self._drag_offset = y - y0
        else:
            self._dragging = True
            self._drag_offset = (y1 - y0) / 2
            self._moveto(self._y_to_first(y))
        self._log("PRESS")
        self._redraw()

    def _on_surface_press(self, event) -> None:
        """Host-canvas press: only claim events on the right hit strip while visible."""
        if not self._overflows() or not self._is_showing():
            return
        try:
            w = int(self._cv.winfo_width()) if self._cv is not None else 0
        except tk.TclError:
            return
        if int(getattr(event, "x", 0) or 0) < w - self.HIT_W:
            return  # let list rows handle the click
        # event.y is viewport-relative for canvas
        y = float(event.y)
        geo = self._geometry()
        if geo is None:
            return
        y0, y1, _ = geo
        if y0 <= y <= y1:
            self._dragging = True
            self._drag_offset = y - y0
        else:
            self._dragging = True
            self._drag_offset = (y1 - y0) / 2
            self._moveto(self._y_to_first(y))
        self._log("PRESS")
        self._redraw()
        return "break"

    def _on_surface_motion(self, event) -> None:
        if not self._is_showing() or not self._overflows():
            return
        try:
            w = int(self._cv.winfo_width()) if self._cv is not None else 0
        except tk.TclError:
            return
        near = int(getattr(event, "x", 0) or 0) >= w - self.EDGE_PX
        if near != self._edge_hover:
            self._edge_hover = near
            self._redraw()

    def _on_surface_leave(self, _event=None) -> None:
        self._edge_hover = False
        self._hovered = False
        if self._is_showing():
            self._redraw()

    def _on_drag(self, event) -> None:
        if not self._dragging:
            return
        # Owned overlay: event.y is strip-local. Surface: viewport-local. Same numbers.
        self._moveto(self._y_to_first(float(event.y)))
        self._redraw()

    def _on_release(self, _event=None) -> None:
        if not self._dragging:
            return
        self._dragging = False
        self._hide_deadline = time.monotonic() + self.HIDE_S
        self._arm_hide_timer()
        self._log("RELEASE")
        self._redraw()
        OverlayScrollbar._ensure_poller(self._root)

    def _on_parent_motion(self, event) -> None:
        # Expire on motion so a still cursor isn't required for hide to "wake up"
        self._expire_if_due()
        if not self._is_showing() or not self._overflows():
            return
        try:
            w = int(self._parent.winfo_width())
        except tk.TclError:
            return
        if w <= 0:
            return
        near = int(getattr(event, "x", 0) or 0) >= w - self.EDGE_PX
        if near != self._edge_hover:
            self._edge_hover = near
            self._redraw()

    def _on_parent_leave(self, _event=None) -> None:
        self._edge_hover = False
        self._expire_if_due()
        if self._is_showing():
            self._redraw()


def _round_rect(canvas: tk.Canvas, x1: int, y1: int, x2: int, y2: int, r: int, **kwargs):
    """Draw a rounded rectangle on a canvas."""
    r = max(0, min(r, (x2 - x1) // 2, (y2 - y1) // 2))
    points = [
        x1 + r, y1,
        x2 - r, y1,
        x2, y1,
        x2, y1 + r,
        x2, y2 - r,
        x2, y2,
        x2 - r, y2,
        x1 + r, y2,
        x1, y2,
        x1, y2 - r,
        x1, y1 + r,
        x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


class RoundedCard(tk.Frame):
    """Dark card with rounded corners via background canvas."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        bg: str = _BG_PANEL,
        chrome: str = _BG_APP,
        radius: int = _RADIUS,
        pad: int = 12,
        **kwargs,
    ) -> None:
        # Outer frame matches app chrome so rounded corners “float”
        super().__init__(parent, bg=chrome, **kwargs)
        self._fill = bg
        self._radius = radius
        self._canvas = tk.Canvas(self, bg=chrome, highlightthickness=0, bd=0)
        self._canvas.pack(fill=tk.BOTH, expand=True)
        self.inner = tk.Frame(self._canvas, bg=bg)
        self._win = self._canvas.create_window(pad, pad, window=self.inner, anchor=tk.NW)
        self._shape = None
        self._pad = pad
        self._redraw_job: str | None = None
        self._canvas.bind("<Configure>", self._schedule_redraw)

    def _schedule_redraw(self, event=None) -> None:
        """Coalesce configure storms (sash drag) into one idle redraw."""
        if self._redraw_job is not None:
            try:
                self.after_cancel(self._redraw_job)
            except tk.TclError:
                pass
        try:
            self._redraw_job = self.after_idle(self._redraw)
        except tk.TclError:
            self._redraw_job = None

    def _redraw(self, event=None) -> None:
        self._redraw_job = None
        w = self._canvas.winfo_width()
        h = self._canvas.winfo_height()
        if w < 4 or h < 4:
            return
        self._canvas.delete("shape")
        _round_rect(
            self._canvas,
            1,
            1,
            w - 2,
            h - 2,
            self._radius,
            fill=self._fill,
            outline=_BORDER,
            width=1,
            tags="shape",
        )
        self._canvas.tag_lower("shape")
        iw = max(10, w - 2 * self._pad)
        ih = max(10, h - 2 * self._pad)
        self._canvas.itemconfigure(self._win, width=iw, height=ih)
        self._canvas.coords(self._win, self._pad, self._pad)


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

    _sb_log_reset()
    result: dict[str, ReviewSession | None] = {"session": None}

    root = tk.Tk()
    title = "Anonymizer review"
    if file_label:
        title = f"Anonymizer review — {file_label}"
    root.title(title)
    root.configure(bg=_BG_APP)

    # Fit on screen with room for Dock / menu bar
    root.update_idletasks()
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    w = max(1100, min(1400, int(sw * 0.88)))
    h = max(740, min(920, int(sh * 0.82)))
    x = max(0, (sw - w) // 2)
    y = max(28, (sh - h) // 2 - 24)
    root.geometry(f"{w}x{h}+{x}+{y}")
    root.minsize(1040, 720)

    selected_ph: list[str | None] = [None]
    filter_type = tk.StringVar(value="All")
    preview_redacted = tk.BooleanVar(value=False)
    status_var = tk.StringVar(value="")
    search_is_placeholder = [True]
    last_add_type: list[str] = ["PERSON"]  # sticky last-used entity type
    # Filled when _status_flash is defined (scrollbars are built earlier)
    _sb_flash: list[Callable[[str, int], None]] = [lambda _m, _ms=1200: None]

    outer = tk.Frame(root, bg=_BG_APP, padx=_PAD, pady=_PAD)
    outer.pack(fill=tk.BOTH, expand=True)

    # Pack order: footer BOTTOM first, then header TOP, then paned fills middle
    # (so Cancel/Save/status never get swallowed by the split pane)

    # ── Footer (fixed bottom — always visible) ────────────────────
    foot_bar = tk.Frame(outer, bg=_BG_ELEVATED, highlightbackground=_BORDER, highlightthickness=1)
    foot_bar.pack(side=tk.BOTTOM, fill=tk.X, pady=(_GAP, 0))
    foot_inner = tk.Frame(foot_bar, bg=_BG_ELEVATED, padx=14, pady=10)
    foot_inner.pack(fill=tk.X)

    tk.Label(
        foot_inner,
        textvariable=status_var,
        bg=_BG_ELEVATED,
        fg=_TEXT,
        font=_FONT_BOLD,
        anchor=tk.W,
    ).pack(side=tk.LEFT, fill=tk.X, expand=True)

    act = tk.Frame(foot_inner, bg=_BG_ELEVATED)
    act.pack(side=tk.RIGHT)

    def _chip_button(
        parent: tk.Frame,
        text: str,
        command,
        *,
        primary: bool = False,
    ) -> tk.Frame:
        """Rounded pill button drawn on canvas (macOS-safe colours)."""
        bg = _HL_SELECTED_BG if primary else _BG_PANEL
        fg = _TEXT_ON_BLUE if primary else _TEXT
        outline = _ACCENT if primary else _BORDER
        font = _FONT_BOLD if primary else _FONT
        pad_x, pad_y, radius = 18, 8, 10

        # Measure text for canvas size
        probe = tk.Label(parent, text=text, font=font)
        probe.update_idletasks()
        tw, th = probe.winfo_reqwidth(), probe.winfo_reqheight()
        probe.destroy()
        bw = tw + pad_x * 2
        bh = max(th + pad_y * 2, 34)

        wrap = tk.Frame(parent, bg=_BG_ELEVATED, width=bw, height=bh, cursor="hand2")
        wrap.pack_propagate(False)
        canvas = tk.Canvas(
            wrap,
            width=bw,
            height=bh,
            bg=_BG_ELEVATED,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        canvas.pack(fill=tk.BOTH, expand=True)

        def _paint(*, hover: bool = False) -> None:
            fill = _ACCENT if (primary and hover) else bg
            if not primary and hover:
                fill = _BORDER
            canvas.delete("all")
            _round_rect(
                canvas,
                1,
                1,
                bw - 2,
                bh - 2,
                radius,
                fill=fill,
                outline=outline,
                width=1,
            )
            canvas.create_text(
                bw // 2,
                bh // 2,
                text=text,
                fill=fg,
                font=font,
            )

        def _run(_e=None):
            command()

        _paint()
        canvas.bind("<Button-1>", _run)
        canvas.bind("<Enter>", lambda _e: _paint(hover=True))
        canvas.bind("<Leave>", lambda _e: _paint(hover=False))
        wrap.bind("<Button-1>", _run)
        return wrap

    _chip_button(act, "Cancel", lambda: _on_close()).pack(side=tk.LEFT, padx=(0, 8))
    _chip_button(act, "Save output", lambda: _on_save(), primary=True).pack(
        side=tk.LEFT
    )

    shortcuts = tk.Label(
        outer,
        text=_shortcut_help_text(),
        bg=_BG_APP,
        fg=_TEXT_MUTED,
        font=_FONT_SMALL,
        anchor=tk.W,
        justify=tk.LEFT,
        wraplength=max(900, w - 40),
    )
    shortcuts.pack(side=tk.BOTTOM, fill=tk.X, pady=(6, 0))

    # Header
    header = tk.Frame(outer, bg=_BG_APP)
    header.pack(side=tk.TOP, fill=tk.X, pady=(0, _GAP))
    tk.Label(
        header, text=title, bg=_BG_APP, fg=_TEXT, font=_FONT_BOLD, anchor=tk.W
    ).pack(side=tk.LEFT)
    tk.Checkbutton(
        header,
        text="Preview redacted",
        variable=preview_redacted,
        command=lambda: _refresh_doc(),
        bg=_BG_APP,
        fg=_TEXT,
        activebackground=_BG_APP,
        activeforeground=_TEXT,
        selectcolor=_BG_ELEVATED,
        font=_FONT,
        highlightthickness=0,
    ).pack(side=tk.RIGHT)

    # Main split: drag sash to resize Findings | Document
    paned = tk.PanedWindow(
        outer,
        orient=tk.HORIZONTAL,
        bg=_BG_APP,
        sashwidth=8,
        sashrelief=tk.FLAT,
        sashpad=2,
        opaqueresize=True,
        bd=0,
    )
    paned.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

    # ── Findings card (slim default — two-line rows; drag sash to widen) ──
    findings_card = RoundedCard(paned, bg=_BG_PANEL, radius=_RADIUS, pad=14)
    _findings_w = max(180, min(210, w // 5))
    paned.add(findings_card, width=_findings_w, minsize=160, stretch="always")
    side = findings_card.inner

    def _on_sash_release(_event=None) -> None:
        _schedule_ellipsize()

    paned.bind("<ButtonRelease-1>", _on_sash_release)

    tk.Label(
        side, text="Findings", bg=_BG_PANEL, fg=_TEXT, font=_FONT_BOLD, anchor=tk.W
    ).pack(fill=tk.X, pady=(0, 10))

    # Toolbar: search + funnel + filter — one shared outer height
    _CTRL_H = 36
    _CTRL_R = 9
    _ICON = 22  # funnel size matched to control height

    tools = tk.Frame(side, bg=_BG_PANEL, height=_CTRL_H)
    tools.pack(fill=tk.X, pady=(0, 10))
    tools.pack_propagate(False)

    def _rounded_shell(
        parent: tk.Frame, *, expand: bool = False
    ) -> tuple[tk.Frame, tk.Canvas]:
        """Fixed-height elevated shell with rounded border (search & filter)."""
        shell = tk.Frame(parent, bg=_BG_PANEL, height=_CTRL_H)
        if expand:
            shell.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))
        else:
            shell.pack(side=tk.LEFT, fill=tk.Y)
        shell.pack_propagate(False)
        canvas = tk.Canvas(
            shell, bg=_BG_PANEL, highlightthickness=0, bd=0, height=_CTRL_H
        )
        canvas.pack(fill=tk.BOTH, expand=True)

        def _redraw(_event=None) -> None:
            cw = max(canvas.winfo_width(), 40)
            ch = _CTRL_H
            canvas.configure(height=ch)
            canvas.delete("shell")
            _round_rect(
                canvas,
                1,
                1,
                cw - 2,
                ch - 2,
                _CTRL_R,
                fill=_BG_ELEVATED,
                outline=_BORDER,
                width=1,
                tags="shell",
            )
            canvas.tag_lower("shell")

        canvas.bind("<Configure>", _redraw)
        return shell, canvas

    # --- Search (rounded elevated field) ---
    search_shell, search_canvas = _rounded_shell(tools, expand=True)
    search_entry = tk.Entry(
        search_canvas,
        font=_FONT,
        bg=_BG_ELEVATED,
        fg=_TEXT_MUTED,
        insertbackground=_TEXT,
        relief=tk.FLAT,
        highlightthickness=0,
        bd=0,
    )
    search_win = search_canvas.create_window(
        12, _CTRL_H // 2, window=search_entry, anchor=tk.W
    )

    def _redraw_search_shell(_event=None) -> None:
        cw = max(search_canvas.winfo_width(), 40)
        ch = _CTRL_H
        search_canvas.configure(height=ch)
        search_canvas.delete("shell")
        _round_rect(
            search_canvas,
            1,
            1,
            cw - 2,
            ch - 2,
            _CTRL_R,
            fill=_BG_ELEVATED,
            outline=_BORDER,
            width=1,
            tags="shell",
        )
        search_canvas.tag_lower("shell")
        search_canvas.itemconfigure(search_win, width=max(20, cw - 24))
        search_canvas.coords(search_win, 12, ch // 2)

    search_canvas.bind("<Configure>", _redraw_search_shell)

    # --- Filter: funnel icon only → opens pick list (no separate dropdown field) ---
    type_values = ["All"] + sorted(
        {f.type_label for f in session.findings} | {"PERSON", "ORG", "CUSTOM"}
    )
    # Hit target matches control height; icon sized to _ICON and centered
    icon_box = tk.Frame(
        tools, bg=_BG_PANEL, width=_CTRL_H, height=_CTRL_H, cursor="hand2"
    )
    icon_box.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 2))
    icon_box.pack_propagate(False)
    funnel = tk.Canvas(
        icon_box,
        width=_ICON,
        height=_ICON,
        bg=_BG_PANEL,
        highlightthickness=0,
        bd=0,
        cursor="hand2",
    )
    funnel.place(relx=0.5, rely=0.5, anchor=tk.CENTER)

    def _draw_funnel(*, active: bool = False) -> None:
        funnel.delete("all")
        color = _ACCENT if active else _TEXT_MUTED
        s = _ICON / 18.0

        def _f(x: float, y: float) -> tuple[float, float]:
            return x * s, y * s

        wline = max(1.5, s)
        funnel.create_line(*_f(2, 4), *_f(16, 4), fill=color, width=wline)
        funnel.create_line(*_f(2, 4), *_f(8, 11), fill=color, width=wline)
        funnel.create_line(*_f(16, 4), *_f(10, 11), fill=color, width=wline)
        funnel.create_line(*_f(8, 11), *_f(10, 11), fill=color, width=wline)
        funnel.create_line(*_f(9, 11), *_f(9, 16), fill=color, width=wline)

    def _set_filter(value: str) -> None:
        filter_type.set(value)
        _draw_funnel(active=value != "All")
        _refresh_list()

    def _open_filter_menu(_event=None) -> None:
        menu = tk.Menu(
            root,
            tearoff=0,
            bg=_BG_ELEVATED,
            fg=_TEXT,
            activebackground=_BG_SELECTED,
            activeforeground=_TEXT,
            bd=0,
            font=_FONT,
        )
        current = filter_type.get()
        for val in type_values:
            # Checkmark on current choice (pick list, single select)
            label = f"✓  {val}" if val == current else f"    {val}"
            menu.add_command(label=label, command=lambda v=val: _set_filter(v))
        try:
            x = icon_box.winfo_rootx()
            y = icon_box.winfo_rooty() + icon_box.winfo_height()
            menu.tk_popup(x, y)
        finally:
            try:
                menu.grab_release()
            except tk.TclError:
                pass

    _draw_funnel(active=False)
    for w in (icon_box, funnel):
        w.bind("<Button-1>", _open_filter_menu)

    def _layout_toolbar() -> None:
        _redraw_search_shell()

    root.after_idle(_layout_toolbar)
    root.after(50, _layout_toolbar)

    def _show_search_placeholder() -> None:
        search_is_placeholder[0] = True
        search_entry.delete(0, tk.END)
        search_entry.insert(0, _SEARCH_PLACEHOLDER)
        search_entry.configure(fg=_TEXT_MUTED, bg=_BG_ELEVATED)

    def _begin_search_edit(_evt=None) -> None:
        if search_is_placeholder[0]:
            search_is_placeholder[0] = False
            search_entry.delete(0, tk.END)
            search_entry.configure(fg=_TEXT, bg=_BG_ELEVATED)

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
    # Click on rounded shell focuses entry
    search_canvas.bind("<Button-1>", lambda _e: search_entry.focus_set())
    _show_search_placeholder()

    # List viewport — full-width content; overlay auto-hide scrollbar
    list_frame = tk.Frame(side, bg=_BG_PANEL)
    list_frame.pack(fill=tk.BOTH, expand=True)
    list_frame.grid_rowconfigure(0, weight=1)
    list_frame.grid_columnconfigure(0, weight=1)
    list_canvas = tk.Canvas(
        list_frame,
        highlightthickness=0,
        borderwidth=0,
        bg=_BG_PANEL,
        takefocus=True,
        # Pixel step for yview_scroll units (default 0 ≈ 10% of window — too coarse)
        yscrollincrement=28,
    )
    # Owned overlay (place + lift): must be a sibling canvas above the list
    # window item. Drawing *on* list_canvas is invisible (embedded windows
    # always stack above canvas graphics on Tk).
    list_scroll = OverlayScrollbar(
        list_frame,
        command=list_canvas.yview,
        root=root,
        chrome=_BG_PANEL,
        name="list",
        on_event=lambda msg: _sb_flash[0](msg, 1200),
    )
    list_inner = tk.Frame(list_canvas, bg=_BG_PANEL)
    list_window = list_canvas.create_window((0, 0), window=list_inner, anchor=tk.NW)
    _last_list_w = [0]
    _ellipsize_job: list[str | None] = [None]

    def _ellipsize_rows(_event=None) -> None:
        """Apply … truncation to line-1 surfaces from available pixel width."""
        if _line1_font is None:
            return
        for rw in row_widgets.values():
            full = rw.get("full_text") or ""
            try:
                count_w = (
                    rw["count"].winfo_reqwidth() if rw["count"].cget("text") else 0
                )
                # body width minus count chip and small gap
                avail = int(rw["body"].winfo_width()) - int(count_w) - 10
                if avail < 24:
                    continue
                rw["line1"].configure(
                    text=ellipsize_text(full, _line1_font, avail)
                )
            except tk.TclError:
                pass

    def _schedule_ellipsize(_event=None) -> None:
        """Debounce ellipsis during sash drag (avoid O(n) work every pixel)."""
        if _ellipsize_job[0] is not None:
            try:
                root.after_cancel(_ellipsize_job[0])
            except tk.TclError:
                pass
        try:
            _ellipsize_job[0] = root.after(60, _run_ellipsize)
        except tk.TclError:
            _ellipsize_job[0] = None

    def _run_ellipsize() -> None:
        _ellipsize_job[0] = None
        _ellipsize_rows()

    def _sync_list_scrollregion(_event=None) -> None:
        """Vertical-only scrollregion; lock inner width to canvas (no horizontal grow)."""
        try:
            w = max(int(list_canvas.winfo_width()), 1)
            list_canvas.itemconfigure(list_window, width=w)
            list_inner.update_idletasks()
            h = max(int(list_inner.winfo_reqheight()), 1)
            list_canvas.configure(scrollregion=(0, 0, w, h))
            # Push fractions into overlay scrollbar (scrollregion alone may not)
            try:
                a, b = list_canvas.yview()
                list_scroll.set(a, b)
            except tk.TclError:
                pass
            if w != _last_list_w[0]:
                _last_list_w[0] = w
                _schedule_ellipsize()
        except tk.TclError:
            pass

    list_inner.bind("<Configure>", _sync_list_scrollregion)
    list_canvas.bind("<Configure>", _sync_list_scrollregion)
    list_canvas.configure(yscrollcommand=list_scroll.set)
    list_canvas.grid(row=0, column=0, sticky="nsew")

    def _list_scroll_units(steps: int) -> bool:
        """Scroll findings list; return True if the viewport actually moved."""
        if not steps:
            return False
        try:
            before = list_canvas.yview()
        except tk.TclError:
            before = None
        list_canvas.yview_scroll(steps, "units")
        try:
            after = list_canvas.yview()
            list_scroll.set(*after)
        except tk.TclError:
            return False
        # Ignore trackpad inertia at bounds (no movement → do not re-arm hide)
        moved = before is None or after != before
        if moved:
            list_scroll.pulse()
        return moved

    def _on_list_mousewheel(event) -> str:
        _list_scroll_units(_wheel_steps(event))
        return "break"

    def _bind_list_wheel(widget: tk.Misc) -> None:
        widget.bind("<MouseWheel>", _on_list_mousewheel)
        if sys.platform != "darwin":

            def _up(_e=None) -> str:
                _list_scroll_units(-1)
                return "break"

            def _down(_e=None) -> str:
                _list_scroll_units(1)
                return "break"

            widget.bind("<Button-4>", _up)
            widget.bind("<Button-5>", _down)

    # Container-level wheel (rows also bind so wheel works over labels)
    _bind_list_wheel(list_canvas)
    _bind_list_wheel(list_inner)
    _bind_list_wheel(list_frame)
    list_canvas.bind("<Button-1>", lambda _e: _focus_list())

    visible_ph: list[str] = []
    row_widgets: dict[str, dict] = {}
    _line1_font = tkfont.Font(font=_FONT) if tkfont is not None else None

    # ── Document card ─────────────────────────────────────────────
    doc_card = RoundedCard(paned, bg=_BG_PANEL, radius=_RADIUS, pad=14)
    paned.add(doc_card, minsize=360, stretch="always")
    doc_pad = doc_card.inner

    doc_header = tk.Frame(doc_pad, bg=_BG_PANEL)
    doc_header.pack(fill=tk.X, pady=(0, 8))
    tk.Label(
        doc_header, text="Document", bg=_BG_PANEL, fg=_TEXT, font=_FONT_BOLD
    ).pack(side=tk.LEFT)

    # Elevated text well with rounded corners (matches search shells / cards)
    doc_well = RoundedCard(
        doc_pad,
        bg=_BG_ELEVATED,
        chrome=_BG_PANEL,
        radius=10,
        pad=3,
    )
    doc_well.pack(fill=tk.BOTH, expand=True)
    text_wrap = tk.Frame(doc_well.inner, bg=_BG_ELEVATED)
    text_wrap.pack(fill=tk.BOTH, expand=True)
    text_wrap.grid_rowconfigure(0, weight=1)
    text_wrap.grid_columnconfigure(0, weight=1)
    doc = tk.Text(
        text_wrap,
        wrap=tk.WORD,
        font=_FONT_DOC,
        undo=False,
        padx=12,
        pady=12,
        bg=_BG_ELEVATED,
        fg=_TEXT,
        insertbackground=_TEXT,
        relief=tk.FLAT,
        highlightthickness=0,
        borderwidth=0,
        selectbackground=_HL_SELECTED_BG,
        selectforeground=_TEXT_ON_BLUE,
        cursor="xterm",  # select to redact, not free typing
    )
    # owned overlay: destroy-on-hide (Text cannot host canvas items)
    doc_scroll = OverlayScrollbar(
        text_wrap,
        command=doc.yview,
        root=root,
        chrome=_BG_ELEVATED,
        name="doc",
        on_event=lambda msg: _sb_flash[0](msg, 1200),
    )
    doc.configure(yscrollcommand=doc_scroll.set)
    doc.grid(row=0, column=0, sticky="nsew")

    def _doc_scroll_units(steps: int) -> bool:
        """Scroll document; return True if the viewport actually moved."""
        if not steps:
            return False
        try:
            before = doc.yview()
        except tk.TclError:
            before = None
        # Text units = lines; clamped steps avoid multi-page jumps
        doc.yview_scroll(steps, "units")
        try:
            after = doc.yview()
            doc_scroll.set(*after)
        except tk.TclError:
            return False
        moved = before is None or after != before
        if moved:
            doc_scroll.pulse()
        return moved

    def _on_doc_mousewheel(event) -> str:
        _doc_scroll_units(_wheel_steps(event))
        return "break"

    doc.bind("<MouseWheel>", _on_doc_mousewheel)
    if sys.platform != "darwin":

        def _doc_up(_e=None) -> str:
            _doc_scroll_units(-1)
            return "break"

        def _doc_down(_e=None) -> str:
            _doc_scroll_units(1)
            return "break"

        doc.bind("<Button-4>", _doc_up)
        doc.bind("<Button-5>", _doc_down)

    # Review canvas only: allow select/navigate/copy; block typing & paste/cut
    _NAV_KEYS = {
        "Left",
        "Right",
        "Up",
        "Down",
        "Home",
        "End",
        "Prior",
        "Next",
        "Tab",
        "ISO_Left_Tab",
        "Shift_L",
        "Shift_R",
        "Control_L",
        "Control_R",
        "Alt_L",
        "Alt_R",
        "Meta_L",
        "Meta_R",
        "Caps_Lock",
        "Escape",
        "Return",
        "KP_Enter",
    }

    def _is_save_modifier(state: int) -> bool:
        """True if platform save modifier is held (⌘ on mac / Ctrl elsewhere)."""
        if sys.platform == "darwin":
            # Command often Mod1 (0x8); some builds Mod2 (0x10)
            return bool(state & 0x8) or bool(state & 0x10)
        # Control (0x4) is the primary save modifier on Windows/Linux.
        # Super/Meta kept as optional extras on some X11/Tk builds.
        return (
            bool(state & 0x4)
            or bool(state & 0x40)
            or bool(state & 0x80)
            or bool(state & 0x8)
        )

    def _doc_block_edit(event: tk.Event) -> str | None:
        """Prevent free editing; selection + shortcuts still work."""
        # Our add-redaction shortcut (handled by specific binds; belt-and-suspenders)
        if event.keysym in {"a", "A"}:
            return _open_add_type_menu(event)
        # Allow pure navigation / modifiers
        if event.keysym in _NAV_KEYS:
            return None
        state = int(getattr(event, "state", 0) or 0)
        # Save: ⌘S / Ctrl+S (must run even when Text has focus)
        if event.keysym.lower() == "s" and _is_save_modifier(state):
            _on_save()
            return "break"
        # Allow copy (Ctrl/Cmd+C); block cut/paste
        if event.keysym.lower() == "c" and (
            state & 0x4 or state & 0x8 or state & 0x10
        ):
            return None  # copy
        # Block everything else that would change text (letters, BackSpace, Delete, …)
        return "break"

    doc.bind("<Key>", _doc_block_edit)
    doc.bind("<<Paste>>", lambda _e: "break")
    doc.bind("<<Cut>>", lambda _e: "break")
    doc.bind("<Button-1>", lambda _e: doc.focus_set())
    # Right-click / a → type menu (must return break so Text never inserts)
    doc.bind("<Button-3>", lambda e: _open_add_type_menu(e))
    doc.bind("<Control-Button-1>", lambda e: _open_add_type_menu(e))
    doc.bind("a", lambda e: _open_add_type_menu(e))
    doc.bind("A", lambda e: _open_add_type_menu(e))

    doc.tag_configure(
        "hl_REDACT", background=_HL_REDACT_BG, foreground=_TEXT_ON_AMBER
    )
    doc.tag_configure(
        "hl_SELECTED", background=_HL_SELECTED_BG, foreground=_TEXT_ON_BLUE
    )
    doc.tag_raise("hl_SELECTED")

    # ── Logic ─────────────────────────────────────────────────────
    def _status(extra: str = "") -> None:
        c = session.summary_counts()
        base = (
            f"{c['redact']} redacting  ·  {c['keep_clear']} keep clear  ·  "
            f"{c['user_added']} added  ·  {c['total']} total"
        )
        status_var.set(f"{base}  ·  {extra}" if extra else base)

    def _status_flash(msg: str, ms: int = 4000) -> None:
        _status(msg)
        root.after(ms, lambda: _status())

    _sb_flash[0] = _status_flash

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
            bg = _BG_SELECTED if selected else _BG_PANEL
            muted = bool(f and not f.enabled)
            fg1 = _TEXT_MUTED if muted else _TEXT
            fg2 = _TEXT_MUTED if muted else _TEXT_MUTED
            try:
                rw["frame"].configure(bg=bg)
                rw["body"].configure(bg=bg)
                rw["top"].configure(bg=bg)
                rw["line1"].configure(bg=bg, fg=fg1)
                rw["line2"].configure(bg=bg, fg=fg2)
                rw["count"].configure(bg=bg, fg=fg2)
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

    def _ensure_row_visible(rw: dict) -> None:
        """Scroll the findings list only if the row is not fully in the viewport."""
        try:
            list_canvas.update_idletasks()
            fr = rw["frame"]
            y1 = float(fr.winfo_y())
            y2 = y1 + float(fr.winfo_height())
            view_top = float(list_canvas.canvasy(0))
            view_bot = float(list_canvas.canvasy(list_canvas.winfo_height()))
            content_h = max(float(list_inner.winfo_height()), 1.0)

            if y1 < view_top:
                # Row top clipped above → scroll up just enough
                list_canvas.yview_moveto(max(0.0, y1 / content_h))
            elif y2 > view_bot:
                # Row bottom clipped below → scroll down just enough
                canvas_h = max(float(list_canvas.winfo_height()), 1.0)
                list_canvas.yview_moveto(max(0.0, (y2 - canvas_h) / content_h))
            # else fully visible → leave scroll alone
        except tk.TclError:
            pass

    def _focus_ph(ph: str, *, scroll_doc: bool = True) -> None:
        if ph not in visible_ph:
            return
        selected_ph[0] = ph
        _focus_list()
        _style_row_selected(ph)
        rw = row_widgets.get(ph)
        if rw:
            _ensure_row_visible(rw)
        _refresh_doc(scroll_to_selected=scroll_doc)

    def _make_row(parent: tk.Frame, f: ReviewFinding) -> dict:
        """Two-line compact row: surface + count / type · tag · added."""
        fr = tk.Frame(parent, bg=_BG_PANEL, highlightthickness=0, bd=0)
        fr.pack(fill=tk.X, pady=1)
        accent = tk.Frame(fr, bg=_BG_PANEL, width=4, highlightthickness=0, bd=0)
        accent.pack(side=tk.LEFT, fill=tk.Y)
        accent.pack_propagate(False)

        body = tk.Frame(fr, bg=_BG_PANEL, highlightthickness=0, bd=0)
        body.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 8), pady=3)

        top = tk.Frame(body, bg=_BG_PANEL, highlightthickness=0, bd=0)
        top.pack(fill=tk.X)
        muted = not f.enabled
        # width=1 keeps Labels shrinkable so long surfaces don't force the pane wider
        # (ellipsis fills available pixels in _ellipsize_rows)
        line1 = tk.Label(
            top,
            text=format_finding_primary(f),
            anchor=tk.W,
            justify=tk.LEFT,
            font=_FONT,
            bg=_BG_PANEL,
            fg=_TEXT_MUTED if muted else _TEXT,
            cursor="hand2",
            pady=0,
            highlightthickness=0,
            bd=0,
            width=1,
        )
        line1.pack(side=tk.LEFT, fill=tk.X, expand=True)
        count_txt = f"×{f.occurrence_count}" if f.occurrence_count > 1 else ""
        count = tk.Label(
            top,
            text=count_txt,
            anchor=tk.E,
            font=_FONT_TINY,
            bg=_BG_PANEL,
            fg=_TEXT_MUTED,
            cursor="hand2",
            padx=6,
            pady=0,
            highlightthickness=0,
            bd=0,
        )
        count.pack(side=tk.RIGHT)

        line2 = tk.Label(
            body,
            text=format_finding_secondary(f),
            anchor=tk.W,
            justify=tk.LEFT,
            font=_FONT_TINY,
            bg=_BG_PANEL,
            fg=_TEXT_MUTED,
            cursor="hand2",
            pady=0,
            highlightthickness=0,
            bd=0,
            width=1,
        )
        line2.pack(fill=tk.X, pady=0)

        full_primary = format_finding_primary(f)
        line1._full_text = full_primary  # type: ignore[attr-defined]

        def select_me(_e=None) -> None:
            _focus_ph(f.placeholder, scroll_doc=True)

        def toggle_me(_e=None) -> str:
            _toggle_ph(f.placeholder)
            return "break"

        for w in (line1, line2, count, body, top, fr, accent):
            w.bind("<Button-1>", select_me)
            w.bind("<Double-Button-1>", toggle_me)
            _bind_list_wheel(w)

        return {
            "frame": fr,
            "body": body,
            "top": top,
            "line1": line1,
            "line2": line2,
            "count": count,
            "accent": accent,
            "full_text": full_primary,
        }

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
                bg=_BG_PANEL,
                fg=_TEXT_MUTED,
                font=_FONT_SMALL,
                pady=28,
            ).pack(fill=tk.X)
        for f in findings:
            rw = _make_row(list_inner, f)
            row_widgets[f.placeholder] = rw
            visible_ph.append(f.placeholder)

        list_inner.update_idletasks()
        _sync_list_scrollregion()

        _status()
        target = select_ph or selected_ph[0]
        if target and target in visible_ph:
            selected_ph[0] = target
        elif visible_ph:
            selected_ph[0] = visible_ph[0]
        else:
            selected_ph[0] = None
        _style_row_selected(selected_ph[0])
        # Debounced ellipsis once widths are real
        _schedule_ellipsize()
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
        try:
            a, b = doc.yview()
            doc_scroll.set(a, b)
        except tk.TclError:
            pass

        if scroll_to_selected and sel and sel in visible_set:
            f_sel = session.get(sel)
            if f_sel and f_sel.original:
                idx = doc.search(f_sel.original, "1.0", stopindex=tk.END)
                if idx:
                    doc.see(idx)
                    doc.mark_set(tk.INSERT, idx)
                    try:
                        a, b = doc.yview()
                        doc_scroll.set(a, b)
                    except tk.TclError:
                        pass
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
        if w is search_entry:
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
                if parent is search_entry:
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

    def _current_selection() -> str | None:
        try:
            sel = doc.get(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            return None
        return sel if sel and sel.strip() else None

    def _commit_add(sel_text: str, entity_type: str) -> None:
        try:
            finding = session.add_redaction(sel_text, entity_type)
        except ValueError as exc:
            _status_flash(str(exc))
            return
        last_add_type[0] = entity_type
        nonlocal type_values
        type_values = ["All"] + sorted(
            {f.type_label for f in session.findings} | {"PERSON", "ORG", "CUSTOM"}
        )
        if filter_type.get() not in {"All", finding.type_label}:
            _set_filter("All")
        selected_ph[0] = finding.placeholder
        _refresh_list(select_ph=finding.placeholder, refresh_doc=False)
        _refresh_doc(scroll_to_selected=True)
        _focus_list()
        n = finding.occurrence_count
        extra = f"Added {finding.placeholder}" + (
            f" (×{n} places)" if n > 1 else ""
        )
        if finding.source == "auto" or (
            finding.source == "user" and n >= 1
        ):
            # Re-enable existing shows as user still; keep simple message
            pass
        _status_flash(extra)

    def _open_add_type_menu(event=None) -> str | None:
        """Type pick list for current document selection (a / right-click)."""
        if _is_text_input_focused():
            return None
        sel_text = _current_selection()
        if not sel_text:
            _status_flash("Select text in the document, then press a or right-click")
            return "break"

        surface = resolve_surface_in_blocks(session.original_blocks, sel_text)
        if not surface:
            _status_flash(
                "Could not match that selection in the document — try a continuous phrase"
            )
            return "break"

        n = count_surface_occurrences(session.original_blocks, surface)
        preview = surface.replace("\n", " ")
        if len(preview) > 40:
            preview = preview[:39] + "…"

        menu = tk.Menu(
            root,
            tearoff=0,
            bg=_BG_ELEVATED,
            fg=_TEXT,
            activebackground=_BG_SELECTED,
            activeforeground=_TEXT,
            bd=0,
            font=_FONT,
        )
        # Disabled header lines (preview + occurrence count)
        menu.add_command(
            label=f"Redact “{preview}”",
            state=tk.DISABLED,
        )
        if n > 1:
            menu.add_command(
                label=f"  also matches ×{n} places in this document",
                state=tk.DISABLED,
            )
        menu.add_separator()

        # Last-used type first
        last = last_add_type[0]
        last_label = next(
            (lab for code, lab in REVIEW_ADD_TYPES if code == last), last
        )
        menu.add_command(
            label=f"★  {last_label}  (last used)",
            command=lambda: _commit_add(sel_text, last),
        )
        menu.add_separator()

        for code, lab in REVIEW_ADD_TYPES:
            if code == last:
                continue  # already shown at top
            menu.add_command(
                label=f"    {lab}",
                command=lambda c=code: _commit_add(sel_text, c),
            )

        try:
            if event is not None and getattr(event, "x_root", None):
                menu.tk_popup(int(event.x_root), int(event.y_root))
            else:
                # Keyboard: near bottom of document pane
                menu.tk_popup(
                    doc.winfo_rootx() + 40,
                    doc.winfo_rooty() + min(120, doc.winfo_height() // 3),
                )
        finally:
            try:
                menu.grab_release()
            except tk.TclError:
                pass
        return "break"

    def _add_selection(_evt=None) -> str | None:
        """Keyboard shortcut a — open type menu for selection."""
        return _open_add_type_menu(_evt)

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
        OverlayScrollbar.shutdown_all()
        _cancel()

    def _on_save() -> None:
        OverlayScrollbar.shutdown_all()
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

    def _on_save_key(_e=None) -> str:
        _on_save()
        return "break"

    root.bind("<space>", lambda e: _toggle_selected(e))
    root.bind("<Escape>", _on_escape)
    for _seq in _save_key_sequences():
        # Skip unknown keysyms (e.g. Super on Windows Tcl/Tk) so one bad
        # sequence cannot crash the window after it has already been built.
        for _w in (root, list_canvas, doc):
            try:
                _w.bind(_seq, _on_save_key)
            except tk.TclError:
                pass
    root.bind("<Down>", lambda e: _nav_if_not_typing(1, e))
    root.bind("<Up>", lambda e: _nav_if_not_typing(-1, e))
    root.bind("a", lambda e: _add_selection(e))
    root.bind("A", lambda e: _add_selection(e))

    list_canvas.bind("<Down>", lambda _e: _nav(1))
    list_canvas.bind("<Up>", lambda _e: _nav(-1))
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

    try:
        root.mainloop()
    finally:
        OverlayScrollbar.shutdown_all()
    return result["session"]
