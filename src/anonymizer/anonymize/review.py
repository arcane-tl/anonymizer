"""Post-anonymization review: accept, reject, and add redactions."""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from typing import Iterable, Literal

from rich.console import Console
from rich.table import Table

from anonymizer.anonymize.mapping import (
    TYPE_LABELS,
    normalize_entity_text,
    placeholder_label,
)

# [ORG_1], ORG_1, org_1, [PLATE_FI_2], VIN_1, FI_HETU_1, etc.
_PLACEHOLDER_RE = re.compile(
    r"^\[?"
    r"([A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)*)"
    r"_(\d+)"
    r"\]?$"
)

# Reverse of common TYPE_LABELS for review type chips / add-redact.
_LABEL_TO_ENTITY: dict[str, str] = {}
for _ent, _lab in TYPE_LABELS.items():
    _LABEL_TO_ENTITY.setdefault(_lab, _ent)

# Types offered in the UI "Redact as…" menu (entity_type values).
REVIEW_ADD_TYPES: list[tuple[str, str]] = [
    ("PERSON", "Person"),
    ("ORG", "Organization"),
    ("EMAIL_ADDRESS", "Email"),
    ("PHONE_NUMBER", "Phone"),
    ("STREET", "Street"),
    ("CITY", "City"),
    ("LOCATION", "Location"),
    ("FI_HETU", "Finnish personal ID"),
    ("FI_BUSINESS_ID", "Business ID"),
    ("IBAN_CODE", "IBAN"),
    ("URL", "URL"),
    ("CUSTOM", "Custom / other"),
]

FindingSource = Literal["auto", "user"]


def normalize_placeholder(token: str) -> str | None:
    """Normalize user token to canonical ``[TYPE_n]`` form, or None if invalid."""
    t = token.strip()
    if not t:
        return None
    m = _PLACEHOLDER_RE.match(t)
    if not m:
        return None
    label = m.group(1).upper()
    n = m.group(2)
    return f"[{label}_{n}]"


def placeholder_type_label(placeholder: str) -> str:
    """Return type label from ``[ORG_1]`` → ``ORG``."""
    body = placeholder.strip().strip("[]")
    parts = body.rsplit("_", 1)
    if len(parts) == 2 and parts[1].isdigit():
        return parts[0].upper()
    return body.upper()


def entity_type_from_placeholder(placeholder: str) -> str:
    """Map placeholder label toward an engine entity type (best effort)."""
    label = placeholder_type_label(placeholder)
    return _LABEL_TO_ENTITY.get(label, label)


def count_surface_occurrences(blocks: list[str], surface: str) -> int:
    """Count non-overlapping exact occurrences of ``surface`` in blocks."""
    if not surface:
        return 0
    n = 0
    for b in blocks:
        start = 0
        while True:
            i = b.find(surface, start)
            if i < 0:
                break
            n += 1
            start = i + max(len(surface), 1)
    return n


def collapse_ws(text: str) -> str:
    """Strip ends and collapse internal whitespace to single spaces."""
    return " ".join(text.split())


def resolve_surface_in_blocks(blocks: list[str], text: str) -> str | None:
    """Return an exact substring of ``blocks`` suitable for redaction, or None.

    Tries stripped selection, then whitespace-collapsed form if that exact
    string appears in the document (so UI selection and apply() stay in sync).
    """
    if not text or not blocks:
        return None
    candidates: list[str] = []
    stripped = text.strip()
    if stripped:
        candidates.append(stripped)
    collapsed = collapse_ws(text)
    if collapsed and collapsed not in candidates:
        candidates.append(collapsed)
    # Prefer longer exact matches when both work
    for surface in sorted(candidates, key=len, reverse=True):
        if count_surface_occurrences(blocks, surface) > 0:
            return surface
    return None


def apply_mapping_to_text(
    text: str,
    mapping: dict[str, str],
    *,
    style: str = "placeholder",
) -> str:
    """Replace original surfaces with placeholders (or delete) in ``text``.

    Longer surfaces first so multi-token names win over substrings.
    """
    if not mapping or not text:
        return text
    pairs = sorted(mapping.items(), key=lambda kv: len(kv[1]), reverse=True)
    out = text
    for ph, original in pairs:
        if not original:
            continue
        replacement = "" if style == "remove" else ph
        out = out.replace(original, replacement)
    if style == "remove":
        out = re.sub(r"[^\S\n]{2,}", " ", out)
    return out


def apply_mapping_to_blocks(
    blocks: list[str],
    mapping: dict[str, str],
    *,
    style: str = "placeholder",
) -> list[str]:
    """Apply :func:`apply_mapping_to_text` to each block."""
    return [apply_mapping_to_text(b, mapping, style=style) for b in blocks]


@dataclass
class ReviewFinding:
    """One unique surface under review (auto or user-added)."""

    placeholder: str
    original: str
    entity_type: str
    enabled: bool = True  # True = will redact
    source: FindingSource = "auto"
    occurrence_count: int = 1

    @property
    def type_label(self) -> str:
        return placeholder_type_label(self.placeholder)


@dataclass
class ReviewSession:
    """In-memory review: toggle tool suggestions and add missed redactions.

    Apply from **original** blocks + active mapping (not only un-redact of
    already anonymized text) so adds and rejects compose cleanly.
    """

    original_blocks: list[str]
    findings: list[ReviewFinding] = field(default_factory=list)
    # placeholder -> finding for O(1) lookup
    _by_ph: dict[str, ReviewFinding] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self._by_ph = {f.placeholder: f for f in self.findings}

    @classmethod
    def from_mapping(
        cls,
        original_blocks: list[str],
        mapping: dict[str, str],
        *,
        pre_keep_clear: Iterable[str] | None = None,
    ) -> ReviewSession:
        """Build session from engine mapping (placeholder → original surface)."""
        keep = {k for k in (pre_keep_clear or []) if k in mapping}
        findings: list[ReviewFinding] = []
        for ph in sort_placeholders(mapping.keys()):
            original = mapping[ph]
            findings.append(
                ReviewFinding(
                    placeholder=ph,
                    original=original,
                    entity_type=entity_type_from_placeholder(ph),
                    enabled=ph not in keep,
                    source="auto",
                    occurrence_count=count_surface_occurrences(
                        original_blocks, original
                    ),
                )
            )
        return cls(original_blocks=list(original_blocks), findings=findings)

    def get(self, placeholder: str) -> ReviewFinding | None:
        return self._by_ph.get(placeholder)

    def set_enabled(self, placeholder: str, enabled: bool) -> bool:
        f = self._by_ph.get(placeholder)
        if not f:
            return False
        f.enabled = enabled
        return True

    def toggle(self, placeholder: str) -> bool | None:
        """Flip enabled; return new state or None if missing."""
        f = self._by_ph.get(placeholder)
        if not f:
            return None
        f.enabled = not f.enabled
        return f.enabled

    def keep_clear_placeholders(self) -> list[str]:
        """Placeholders the user turned off (will appear in clear text)."""
        return [f.placeholder for f in self.findings if not f.enabled]

    def active_mapping(self) -> dict[str, str]:
        """Placeholder → original for findings still enabled (to redact)."""
        return {f.placeholder: f.original for f in self.findings if f.enabled}

    def summary_counts(self) -> dict[str, int]:
        on = sum(1 for f in self.findings if f.enabled)
        off = sum(1 for f in self.findings if not f.enabled)
        added = sum(1 for f in self.findings if f.source == "user")
        return {"redact": on, "keep_clear": off, "user_added": added, "total": len(self.findings)}

    def _used_placeholders(self) -> set[str]:
        return set(self._by_ph.keys())

    def _next_placeholder(self, entity_type: str) -> str:
        label = placeholder_label(entity_type)
        used = self._used_placeholders()
        # Also respect numbers already taken even if disabled
        n = 1
        while f"[{label}_{n}]" in used:
            n += 1
        return f"[{label}_{n}]"

    def add_redaction(self, text: str, entity_type: str) -> ReviewFinding:
        """Redact ``text`` (all same surfaces) as ``entity_type``.

        ``text`` must resolve to an exact substring of the original blocks
        (see :func:`resolve_surface_in_blocks`). If an existing finding already
        covers the same normalized surface and type label, re-enable it.
        """
        surface = resolve_surface_in_blocks(self.original_blocks, text)
        if not surface:
            raise ValueError(
                "Could not find that exact text in the document. "
                "Select a continuous phrase that appears in the body."
            )
        ent = entity_type.strip().upper() or "CUSTOM"
        label = placeholder_label(ent)
        norm = normalize_entity_text(surface)

        for f in self.findings:
            if (
                placeholder_type_label(f.placeholder) == label
                and normalize_entity_text(f.original) == norm
            ):
                f.enabled = True
                # Prefer longer/exact original if user selected different casing
                if len(surface) >= len(f.original):
                    f.original = surface
                f.occurrence_count = count_surface_occurrences(
                    self.original_blocks, f.original
                )
                return f

        ph = self._next_placeholder(ent)
        finding = ReviewFinding(
            placeholder=ph,
            original=surface,
            entity_type=ent,
            enabled=True,
            source="user",
            occurrence_count=count_surface_occurrences(self.original_blocks, surface),
        )
        self.findings.append(finding)
        self._by_ph[ph] = finding
        # Keep list sorted by type then number for stable UI
        self.findings = [
            self._by_ph[k] for k in sort_placeholders(self._by_ph.keys())
        ]
        return finding

    def apply(
        self, *, style: str = "placeholder"
    ) -> tuple[list[str], dict[str, str]]:
        """Apply active redactions to original blocks.

        Returns ``(anonymized_blocks, active_mapping)``.
        """
        mapping = self.active_mapping()
        blocks = apply_mapping_to_blocks(
            self.original_blocks, mapping, style=style
        )
        return blocks, dict(mapping)


def parse_reject_list(
    user_input: str, valid: set[str]
) -> tuple[list[str], list[str]]:
    """Parse space/comma-separated tokens into (valid_keys, unknown_tokens)."""
    if not user_input or not user_input.strip():
        return [], []
    # Split on commas and whitespace
    raw_parts = re.split(r"[\s,;]+", user_input.strip())
    accepted: list[str] = []
    unknown: list[str] = []
    seen: set[str] = set()
    for part in raw_parts:
        if not part:
            continue
        # Accept-all / quit handled by caller for interactive
        key = normalize_placeholder(part)
        if key is None:
            unknown.append(part)
            continue
        if key not in valid:
            unknown.append(part)
            continue
        if key not in seen:
            seen.add(key)
            accepted.append(key)
    return accepted, unknown


def sort_placeholders(keys: Iterable[str]) -> list[str]:
    """Sort [TYPE_n] by type label then number."""

    def key_fn(ph: str) -> tuple[str, int]:
        body = ph.strip("[]")
        parts = body.rsplit("_", 1)
        if len(parts) == 2 and parts[1].isdigit():
            return parts[0], int(parts[1])
        return body, 0

    return sorted(keys, key=key_fn)


def format_review_table(mapping: dict[str, str], *, max_len: int = 80) -> Table:
    """Build a Rich table of placeholder → original (truncated for display)."""
    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
    table.add_column("Tag", style="cyan")
    table.add_column("Original text")
    for ph in sort_placeholders(mapping.keys()):
        original = mapping[ph]
        display = original.replace("\n", "↵ ")
        if len(display) > max_len:
            display = display[: max_len - 1] + "…"
        table.add_row(ph, display)
    return table


def unredact(
    text: str,
    mapping: dict[str, str],
    keep_clear: Iterable[str],
) -> str:
    """Replace selected placeholders with originals (longest first)."""
    keys = [k for k in keep_clear if k in mapping]
    # Longest placeholder first to avoid partial issues (unlikely but safe)
    keys.sort(key=len, reverse=True)
    out = text
    for ph in keys:
        out = out.replace(ph, mapping[ph])
    return out


def apply_review_to_blocks(
    blocks: list[str],
    mapping: dict[str, str],
    keep_clear: Iterable[str],
) -> tuple[list[str], dict[str, str]]:
    """Restore keep_clear placeholders in each block; return new map without them."""
    keep_set = {k for k in keep_clear if k in mapping}
    if not keep_set:
        return list(blocks), dict(mapping)
    new_blocks = [unredact(b, mapping, keep_set) for b in blocks]
    new_map = {k: v for k, v in mapping.items() if k not in keep_set}
    return new_blocks, new_map


def strip_placeholders(text: str, mapping: dict[str, str]) -> str:
    """Remove remaining placeholder tags from text (delete-style final render).

    Map keys are left unchanged for --map; only the body is stripped.
    Longest tags first; collapse horizontal whitespace left by deletions.
    """
    if not mapping or not text:
        return text
    keys = sorted(mapping.keys(), key=len, reverse=True)
    out = text
    for ph in keys:
        out = out.replace(ph, "")
    # Collapse spaces/tabs only (keep newlines)
    out = re.sub(r"[^\S\n]{2,}", " ", out)
    return out


def strip_placeholders_in_blocks(
    blocks: list[str], mapping: dict[str, str]
) -> list[str]:
    """Apply :func:`strip_placeholders` to each block."""
    if not mapping:
        return list(blocks)
    return [strip_placeholders(b, mapping) for b in blocks]


def recount_entities(mapping: dict[str, str]) -> dict[str, int]:
    """Approximate entity_counts from remaining placeholders."""
    counts: dict[str, int] = {}
    for ph in mapping:
        body = ph.strip("[]")
        parts = body.rsplit("_", 1)
        label = parts[0] if len(parts) == 2 and parts[1].isdigit() else body
        # Map display labels back toward engine types where obvious
        type_key = {
            "EMAIL": "EMAIL_ADDRESS",
            "PHONE": "PHONE_NUMBER",
            "IBAN": "IBAN_CODE",
            "IP": "IP_ADDRESS",
            "POSTAL": "FI_POSTAL_CODE",
            "PLATE_FI": "FI_LICENSE_PLATE",
            "VAT_FI": "FI_VAT",
            "VIN": "VEHICLE_VIN",
        }.get(label, label)
        counts[type_key] = counts.get(type_key, 0) + 1
    return counts


def _truncate_display(text: str, max_len: int = 70) -> str:
    display = text.replace("\n", "↵ ").replace("\r", "")
    if len(display) > max_len:
        return display[: max_len - 1] + "…"
    return display


def print_keep_clear_summary(
    mapping: dict[str, str],
    selected: Iterable[str],
    *,
    console: Console | None = None,
    max_len: int = 100,
) -> None:
    """Print tag + original for each item kept in clear text (confirmation)."""
    console = console or Console(stderr=True)
    keys = [k for k in sort_placeholders(selected) if k in mapping]
    if not keys:
        console.print("[dim]No items checked — keeping all redactions.[/dim]")
        return

    console.print(
        f"\n[bold]Keeping {len(keys)} item(s) in clear text[/bold] "
        "[dim](second look — confirm nothing sensitive):[/dim]\n"
    )
    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
    table.add_column("Tag", style="cyan")
    table.add_column("Original text (will appear unredacted)")
    for ph in keys:
        original = mapping[ph]
        display = original.replace("\n", "↵ ").replace("\r", "")
        if len(display) > max_len:
            display = display[: max_len - 1] + "…"
        table.add_row(ph, display)
    console.print(table)
    console.print()


def _checkbox_review(
    mapping: dict[str, str],
    *,
    console: Console,
    file_label: str | None,
) -> list[str]:
    """Spacebar multi-select via questionary (all start unchecked)."""
    import questionary
    from questionary import Choice, Style

    if file_label:
        console.print(f"\n[bold]Review redactions — {file_label}[/bold]")
    else:
        console.print("\n[bold]Review redactions[/bold]")

    console.print(
        f"Found [cyan]{len(mapping)}[/cyan] unique redaction(s). "
        "[bold]Nothing is checked[/bold] — check only false positives to keep "
        "in clear text.\n"
    )
    console.print(
        "[dim]↑/↓ move · [cyan]space[/cyan] check/uncheck · "
        "[cyan]enter[/cyan] confirm · ctrl+c abort[/dim]\n"
    )

    choices = [
        Choice(
            title=f"{ph}  {_truncate_display(mapping[ph])}",
            value=ph,
            checked=False,
        )
        for ph in sort_placeholders(mapping.keys())
    ]

    # Soft palette; noinherit + noreverse avoid full-line reverse/bg on checked rows.
    # Cursor (highlighted) uses magenta so the active line is easy to spot.
    style = Style(
        [
            ("qmark", "fg:#6cb6ff bold"),
            ("question", "bold"),
            ("answer", "fg:#6cb6ff"),
            ("pointer", "fg:#d2a8ff bold"),
            ("highlighted", "noinherit noreverse fg:#d2a8ff bold"),
            ("selected", "noinherit noreverse fg:#3fb950"),
            ("text", "noinherit noreverse fg:default"),
            ("instruction", "fg:#8b949e"),
            ("separator", "fg:#8b949e"),
        ]
    )

    try:
        selected = questionary.checkbox(
            "Keep in clear text (un-redact):",
            choices=choices,
            style=style,
            instruction="(space toggle, enter confirm)",
        ).ask()
    except KeyboardInterrupt:
        console.print("\n[yellow]Review cancelled.[/yellow]")
        raise SystemExit(130) from None

    # None = cancelled (Esc / Ctrl+C depending on version)
    if selected is None:
        console.print("[yellow]Aborted — no file written.[/yellow]")
        raise SystemExit(130)

    selected_list = list(selected or [])
    print_keep_clear_summary(mapping, selected_list, console=console)
    return selected_list


def _text_fallback_review(
    mapping: dict[str, str],
    *,
    console: Console,
    file_label: str | None,
) -> list[str]:
    """Legacy type-tags prompt if questionary is unavailable."""
    if file_label:
        console.print(f"\n[bold]Review redactions — {file_label}[/bold]")
    else:
        console.print("\n[bold]Review redactions[/bold]")

    console.print(
        f"Found [cyan]{len(mapping)}[/cyan] unique redaction(s). "
        "List below: tag → text from the original document.\n"
    )
    console.print(format_review_table(mapping))
    console.print(
        "\n[dim]Enter tags to KEEP in clear text (false positives), "
        "separated by spaces or commas.[/dim]"
    )
    console.print(
        "[dim]Examples: [cyan]ORG_2[/cyan]  or  [cyan][ORG_2][/cyan]  ·  "
        "empty line = accept all redactions  ·  [cyan]q[/cyan] = abort[/dim]"
    )

    try:
        line = console.input("[bold]>[/bold] ")
    except (EOFError, KeyboardInterrupt):
        console.print("\n[yellow]Review cancelled.[/yellow]")
        raise SystemExit(130) from None

    raw = (line or "").strip()
    if not raw:
        console.print("[dim]Keeping all redactions.[/dim]")
        return []
    if raw.casefold() in {"q", "quit", "abort"}:
        console.print("[yellow]Aborted — no file written.[/yellow]")
        raise SystemExit(130)
    if raw.casefold() in {"a", "all", "accept"}:
        console.print("[dim]Keeping all redactions.[/dim]")
        return []

    valid = set(mapping.keys())
    accepted, unknown = parse_reject_list(raw, valid)
    for u in unknown:
        console.print(f"[yellow]Unknown or invalid tag ignored:[/yellow] {u}")
    print_keep_clear_summary(mapping, accepted, console=console)
    return accepted


def resolve_review_surface(
    *,
    review: bool = False,
    review_cli: bool = False,
    review_window: bool = False,
    env: str | None = None,
) -> str | None:
    """Pick review UI surface: ``cli``, ``window``, or ``None`` if review is off.

    Priority: ``--review-cli`` → ``--review-window`` → ``ANONYMIZER_REVIEW`` →
    default **cli** when any review flag is set.

    Environment values: ``cli`` / ``terminal`` | ``window`` / ``gui`` / ``ui``.
    """
    if not (review or review_cli or review_window):
        return None
    if review_cli:
        return "cli"
    if review_window:
        return "window"
    raw = (
        env
        if env is not None
        else os.environ.get("ANONYMIZER_REVIEW", "")
    )
    val = str(raw).strip().lower()
    if val in {"cli", "terminal"}:
        return "cli"
    if val in {"window", "gui", "ui"}:
        return "window"
    # Default for plain --review: terminal checklist (predictable for CLI installs)
    return "cli"


def interactive_review(
    mapping: dict[str, str],
    *,
    console: Console | None = None,
    file_label: str | None = None,
    original_blocks: list[str] | None = None,
    force_cli: bool = False,
    surface: str | None = None,
    pre_keep_clear: Iterable[str] | None = None,
) -> ReviewSession:
    """Interactive review: terminal checklist or document window.

    Returns a :class:`ReviewSession` after the user saves.
    Raises ``SystemExit(130)`` if the user aborts.

    Parameters
    ----------
    original_blocks
        Pre-anonymization block texts (required for accurate add/remove apply).
        If omitted, empty blocks are used and only the mapping list is reviewed.
    force_cli
        Deprecated alias: if True, force terminal checklist. Prefer ``surface``.
    surface
        ``"cli"`` (terminal checklist, default) or ``"window"`` (Tk document UI).
        GUIs should pass ``"window"``; plain CLI ``--review`` uses ``"cli"``.
    pre_keep_clear
        Placeholders already rejected (e.g. from ``--reject``) start unchecked.
    """
    console = console or Console(stderr=True)
    blocks = list(original_blocks or [])

    if not mapping and not blocks:
        console.print("[dim]No redactions to review.[/dim]")
        return ReviewSession.from_mapping(blocks, {})

    session = ReviewSession.from_mapping(
        blocks, mapping, pre_keep_clear=pre_keep_clear
    )

    if not session.findings:
        console.print("[dim]No redactions to review.[/dim]")
        return session

    use_surface = "cli" if force_cli else (surface or "cli")
    use_surface = str(use_surface).strip().lower()
    if use_surface not in {"cli", "window"}:
        use_surface = "cli"

    if use_surface == "window":
        try:
            from anonymizer.gui.review_window import display_available, run_review_window
        except Exception as exc:  # pragma: no cover - missing tk
            raise SystemExit(
                "Error: --review-window requires tkinter (desktop GUI support).\n"
                f"Details: {exc}\n"
                "Use plain --review for the terminal checklist, or install a "
                "Python build with tkinter."
            ) from exc

        if not display_available():
            raise SystemExit(
                "Error: --review-window requires a desktop display.\n"
                "Use plain --review for the terminal checklist, "
                "or run from a graphical session."
            )

        try:
            console.print(
                "[dim]Opening review window "
                "(toggle false positives, select text to add redactions)…[/dim]"
            )
            finished = run_review_window(session, file_label=file_label)
        except SystemExit:
            raise
        except Exception as exc:  # pragma: no cover - UI env issues
            raise SystemExit(
                f"Error: review window failed ({exc}).\n"
                "Use plain --review for the terminal checklist."
            ) from exc

        if finished is None:
            console.print("[yellow]Review cancelled — no file written.[/yellow]")
            raise SystemExit(130)
        kept = finished.keep_clear_placeholders()
        if kept:
            print_keep_clear_summary(
                {f.placeholder: f.original for f in finished.findings},
                kept,
                console=console,
            )
        return finished

    # Terminal checklist (default for CLI --review)
    try:
        import questionary  # noqa: F401

        has_q = True
    except ImportError:
        has_q = False

    if has_q:
        keep = _checkbox_review(mapping, console=console, file_label=file_label)
    else:
        console.print(
            "[yellow]Note:[/yellow] install [bold]questionary[/bold] for "
            "spacebar checkbox review; falling back to typing tags."
        )
        keep = _text_fallback_review(
            mapping, console=console, file_label=file_label
        )
    for ph in keep:
        session.set_enabled(ph, False)
    return session


def require_review_capable(surface: str) -> None:
    """Exit if the chosen review surface cannot run in this environment."""
    surface = (surface or "cli").strip().lower()
    if surface == "window":
        try:
            from anonymizer.gui.review_window import display_available

            if display_available():
                return
        except Exception:
            pass
        raise SystemExit(
            "Error: --review-window requires a desktop display and tkinter.\n"
            "Use plain --review for the terminal checklist, "
            "or run the Anonymizer GUI app."
        )
    # cli surface
    if not sys.stdin.isatty():
        raise SystemExit(
            "Error: --review requires an interactive terminal.\n"
            "Use --reject ORG_1,PHONE_2 for non-interactive un-redaction, "
            "--review-window in a desktop GUI, or omit --review."
        )


def require_tty_for_review(*, allow_gui: bool = True) -> None:
    """Backward-compatible gate used by older call sites.

    Prefer :func:`require_review_capable` with an explicit surface.
    """
    if allow_gui:
        try:
            from anonymizer.gui.review_window import display_available

            if display_available():
                return
        except Exception:
            pass
    if not sys.stdin.isatty():
        raise SystemExit(
            "Error: --review requires an interactive terminal or desktop display.\n"
            "Use --reject ORG_1,PHONE_2 for non-interactive un-redaction, "
            "--review-cli on a TTY, or omit --review."
        )
