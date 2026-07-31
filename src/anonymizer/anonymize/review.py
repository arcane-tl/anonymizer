"""Post-anonymization review: list placeholders and restore false positives."""

from __future__ import annotations

import re
import sys
from typing import Iterable

from rich.console import Console
from rich.table import Table

# [ORG_1], ORG_1, org_1, [PLATE_FI_2], VIN_1, FI_HETU_1, etc.
_PLACEHOLDER_RE = re.compile(
    r"^\[?"
    r"([A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)*)"
    r"_(\d+)"
    r"\]?$"
)


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


def interactive_review(
    mapping: dict[str, str],
    *,
    console: Console | None = None,
    file_label: str | None = None,
) -> list[str]:
    """Interactive review: checkbox UI (space toggle) or text fallback.

    Returns list of canonical ``[TYPE_n]`` keys to un-redact.
    Raises ``SystemExit(130)`` if user aborts.
    """
    console = console or Console(stderr=True)
    if not mapping:
        console.print("[dim]No redactions to review.[/dim]")
        return []

    try:
        import questionary  # noqa: F401
    except ImportError:
        console.print(
            "[yellow]Note:[/yellow] install [bold]questionary[/bold] for "
            "spacebar checkbox review; falling back to typing tags."
        )
        return _text_fallback_review(
            mapping, console=console, file_label=file_label
        )

    return _checkbox_review(mapping, console=console, file_label=file_label)


def require_tty_for_review() -> None:
    """Exit with a clear error if --review is used without a terminal."""
    if not sys.stdin.isatty():
        raise SystemExit(
            "Error: --review requires an interactive terminal.\n"
            "Use --reject ORG_1,PHONE_2 for non-interactive un-redaction, "
            "or omit --review."
        )
