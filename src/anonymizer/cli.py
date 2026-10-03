"""Typer CLI — user-friendly extract / anonymize entrypoint."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from anonymizer import __version__
from anonymizer.anonymize.config import (
    DEFAULT_ENTITIES,
    SPACY_FALLBACKS,
    SPACY_MODELS,
    STANDARD_ENTITIES,
    AnonymizerConfig,
    ConfigError,
    entities_for_mode,
    load_config,
    normalize_mode,
    normalize_redact_style,
)
from anonymizer.anonymize.engine import DocumentAnonymizer
from anonymizer.anonymize.review import (
    ReviewSession,
    interactive_review,
    parse_reject_list,
    recount_entities,
    require_review_capable,
    resolve_review_surface,
    strip_placeholders_in_blocks,
)
from anonymizer.extract import extract_document
from anonymizer.output.markdown import render_from_extracted
from anonymizer.output.md_pdf import write_pdf_from_markdown
from anonymizer.output.native import (
    default_native_output_path,
    format_output_kinds,
    native_suffix,
    parse_output_formats,
    source_as_markdown,
    write_native_redacted,
)
from anonymizer.util.files import (
    collect_inputs,
    default_output_path,
    default_text_pdf_output_path,
    expand_user_path,
)
from anonymizer.util.progress import RunProgress

EPILOG = """
Examples:
  anonymize contract.pdf
  anonymize contract.pdf --review
  anonymize contract.pdf --format md,source,pdf
  anonymize notes.txt --format pdf
  anonymize extract report.pdf -o body.md
  anonymize standard sopimus.pdf
  anonymize doctor

Modes:
  extract   text only (no redaction)
  standard  people, phones, emails, IDs, addresses (keeps companies)
  strict    full scrub — default when you just pass a file

Outputs (--format, comma-separated; default md):
  md        Markdown ({stem}.anonymized.md)
  source    redacted original PDF/DOCX; plain text → Markdown
  pdf       reflowed text PDF ({stem}.anonymized.text.pdf)
  Compat: both=md,source ; all=md,source,pdf ; --pdf adds pdf

Review:
  --review / -r       terminal checklist (toggle false positives)
  --review-window     document window UI (GUIs use this)
  --review-cli        same as default terminal checklist (explicit)
  --reject ORG_1,PHONE_2   non-interactive un-redact

Tip: run "anonymize doctor" after install if anything looks wrong.
"""

# First-token verbs → mode (so `anonymize extract file.pdf` works)
_VERB_TO_MODE: dict[str, str] = {
    "extract": "extract",
    "text": "extract",
    "plain": "extract",
    "standard": "standard",
    "normal": "standard",
    "pii": "standard",
    "strict": "strict",
    "scrub": "strict",
    "full": "strict",
}
_META_COMMANDS = frozenset({"doctor", "examples", "templates", "templates-ui"})

# Options that take a following value (for argv rewrite)
_OPTS_WITH_VALUE = frozenset(
    {
        "-o",
        "--output",
        "--out-dir",
        "--map",
        "--lang",
        "--mode",
        "-m",
        "--config",
        "--entities",
        "--score-threshold",
        "--llm-provider",
        "--llm-model",
        "--reject",
        "--redact-style",
        "--format",
        "--template",
        "--templates",
        "--learn-to",
    }
)

app = typer.Typer(
    name="anonymize",
    help=(
        "Turn PDF/DOCX/text into Markdown. "
        "Default: strict anonymization. "
        "Also: extract (text only) · standard (identity PII)."
    ),
    epilog=EPILOG,
    add_completion=True,
    no_args_is_help=True,
    rich_markup_mode="rich",
    context_settings={"help_option_names": ["-h", "--help"]},
)
console = Console(stderr=True)


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True, show_path=False)],
    )
    if not verbose:
        for name in (
            "presidio-analyzer",
            "presidio_analyzer",
            "presidio-anonymizer",
        ):
            logging.getLogger(name).setLevel(logging.ERROR)


def _abs_display_path(path: Path) -> str:
    """Absolute path string for success messages (expands ~)."""
    return str(expand_user_path(path).resolve())


def _write_sensitive_text(path: Path, text: str) -> None:
    """Write file with mode 0o600 when the OS supports it (map JSON = PII)."""
    import os

    path = Path(path)
    data = text.encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o600)
    except OSError:
        path.write_bytes(data)
        try:
            path.chmod(0o600)
        except OSError:
            pass
        return
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        raise
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _report_write_success(
    *,
    quiet: bool,
    input_name: str,
    elapsed: str,
    summary: str,
    out_path: Path | None,
    map_file: Path | None,
    native_path: Path | None = None,
    text_pdf_path: Path | None = None,
    wrote_stdout: bool = False,
) -> None:
    """Tell the user exactly where files landed (main post-run UX).

    Paths are printed on their own line so long absolute paths are not
    soft-wrapped mid-segment by the terminal width.
    """
    out_disp = _abs_display_path(out_path) if out_path is not None else None
    map_disp = _abs_display_path(map_file) if map_file is not None else None
    native_disp = _abs_display_path(native_path) if native_path is not None else None
    text_pdf_disp = (
        _abs_display_path(text_pdf_path) if text_pdf_path is not None else None
    )

    # overflow=ignore keeps absolute paths intact for copy-paste / tests
    print_kw = {"overflow": "ignore", "crop": False, "soft_wrap": False}

    if quiet:
        console.print(
            f"[green]OK[/green] {input_name} · {elapsed} · {summary}",
            **print_kw,
        )
    label = "Wrote" if not quiet else "→"
    if out_disp is not None:
        console.print(f"[green]{label}[/green] {out_disp}", **print_kw)
    elif wrote_stdout:
        console.print(f"[green]{label}[/green] stdout", **print_kw)
    if native_disp is not None:
        console.print(f"[green]{label}[/green] {native_disp}", **print_kw)
    if text_pdf_disp is not None:
        console.print(f"[green]{label}[/green] {text_pdf_disp}", **print_kw)
    if (
        out_disp is None
        and not wrote_stdout
        and native_disp is None
        and text_pdf_disp is None
    ):
        console.print(f"[green]{label}[/green] (no output file)", **print_kw)
    if map_disp is not None:
        console.print(
            f"[dim]map[/dim] {map_disp} [dim](contains PII)[/dim]",
            **print_kw,
        )


def _build_config(
    *,
    mode: str,
    lang: str,
    config: Path | None,
    entities: str | None,
    score_threshold: float | None,
    include_dates: bool,
    llm: bool,
    llm_provider: str | None,
    llm_model: str | None,
    redact_style: str | None,
    output_format: str | None = None,
    write_text_pdf: bool | None = None,
    fail_on_native_miss: bool | None = None,
    native_min_match_rate: float | None = None,
    redact_letterhead_images: bool | None = None,
    template: str | None = None,
    quiet: bool = False,
) -> AnonymizerConfig:
    from anonymizer.anonymize.templates import (
        apply_templates_to_config,
        maybe_migrate_config_lists,
        resolve_enabled_ids,
    )

    cfg = load_config(config)
    if config is not None:
        migrated = maybe_migrate_config_lists(config)
        if migrated is not None and not quiet:
            console.print(
                f"[dim]Migrated config lists → template {migrated.name}[/dim]"
            )
            cfg = load_config(config)
    cfg.mode = normalize_mode(mode)
    if entities:
        cfg.entities = [e.strip() for e in entities.split(",") if e.strip()]
        cfg.entities_explicit = True
    elif not cfg.entities_explicit:
        cfg.entities = entities_for_mode(cfg.mode)
    cfg.lang = lang
    cfg.include_dates = include_dates or cfg.include_dates
    if score_threshold is not None:
        cfg.score_threshold = score_threshold
    # Explicit CLI opt-in: without --llm, force LLM off even if YAML enables it.
    if llm:
        cfg.use_llm = True
    else:
        cfg.use_llm = False
    if llm_provider:
        cfg.llm_provider = llm_provider
    if llm_model:
        cfg.llm_model = llm_model
    if redact_style is not None:
        cfg.redact_style = normalize_redact_style(redact_style)
    else:
        cfg.redact_style = normalize_redact_style(cfg.redact_style)
    if output_format is not None:
        kinds = set(parse_output_formats(output_format))
    else:
        kinds = set(parse_output_formats(cfg.output_format))
    if write_text_pdf:
        kinds.add("pdf")
    cfg.output_format = format_output_kinds(kinds)
    cfg.write_text_pdf = "pdf" in kinds
    if fail_on_native_miss is not None:
        cfg.fail_on_native_miss = fail_on_native_miss
    if native_min_match_rate is not None:
        if not 0.0 <= native_min_match_rate <= 1.0:
            console.print(
                "[red]Error:[/red] --native-min-match-rate must be between 0 and 1."
            )
            raise typer.Exit(2)
        cfg.native_min_match_rate = native_min_match_rate
    if redact_letterhead_images is not None:
        cfg.redact_letterhead_images = redact_letterhead_images
    if cfg.mode == "extract" and cfg.use_llm:
        console.print(
            "[dim]Note:[/dim] --llm is ignored in extract mode (no redaction)."
        )
        cfg.use_llm = False

    enabled = resolve_enabled_ids(
        cli_templates=template,
        config_templates=cfg.templates_enabled,
    )
    merged = apply_templates_to_config(cfg, enabled_ids=enabled, replace_lists=True)
    if not quiet and merged.template_ids:
        console.print(f"[dim]Templates:[/dim] {', '.join(merged.template_ids)}")
    if not quiet and merged.conflicts:
        console.print(
            f"[dim]Note:[/dim] {len(merged.conflicts)} surface(s) in both allow "
            f"and deny — allow wins."
        )
    return cfg


def _run_pipeline(
    path: Path,
    *,
    mode: str,
    output: Path | None,
    out_dir: Path | None,
    map_path: Path | None,
    lang: str,
    config: Path | None,
    entities: str | None,
    score_threshold: float | None,
    include_dates: bool,
    force_ocr: bool,
    no_ocr: bool,
    keep_headers: bool,
    review: bool,
    review_cli: bool,
    review_window: bool,
    reject: str | None,
    redact_style: str | None,
    output_format: str | None,
    write_text_pdf: bool = False,
    fail_on_native_miss: bool = False,
    native_min_match_rate: float | None = None,
    redact_letterhead_images: bool = False,
    llm: bool,
    llm_provider: str | None,
    llm_model: str | None,
    offline: bool,
    quiet: bool,
    verbose: bool,
    template: str | None = None,
    learn_to: str | None = None,
) -> None:
    _setup_logging(verbose)

    # Typer/Click do not expand ~; do it once for every user path.
    path = expand_user_path(path)
    if output is not None and str(output) != "-":
        output = expand_user_path(output)
    if out_dir is not None:
        out_dir = expand_user_path(out_dir)
    if map_path is not None:
        map_path = expand_user_path(map_path)
    if config is not None:
        config = expand_user_path(config)
        if not config.is_file():
            console.print(f"[red]Error:[/red] Config file not found: {config}")
            raise typer.Exit(2)

    try:
        mode = normalize_mode(mode)
    except ValueError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(2) from exc

    yaml_wanted_llm = False
    if config is not None:
        try:
            yaml_wanted_llm = bool(load_config(config).use_llm)
        except (ConfigError, ValueError, OSError):
            yaml_wanted_llm = False

    try:
        cfg = _build_config(
            mode=mode,
            lang=lang,
            config=config,
            entities=entities,
            score_threshold=score_threshold,
            include_dates=include_dates,
            llm=llm,
            llm_provider=llm_provider,
            llm_model=llm_model,
            redact_style=redact_style,
            output_format=output_format,
            write_text_pdf=write_text_pdf or None,
            fail_on_native_miss=fail_on_native_miss or None,
            native_min_match_rate=native_min_match_rate,
            redact_letterhead_images=redact_letterhead_images or None,
            template=template,
            quiet=quiet,
        )
    except (ConfigError, ValueError) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(2) from exc
    if keep_headers:
        cfg.keep_headers = True

    if yaml_wanted_llm and not llm and not quiet:
        console.print(
            "[dim]Note:[/dim] config has use_llm: true but --llm was not passed; "
            "LLM layer stays off (explicit opt-in required)."
        )

    kinds = set(parse_output_formats(cfg.output_format))
    if cfg.write_text_pdf:
        kinds.add("pdf")
    if not kinds:
        kinds = {"md"}
    out_fmt = format_output_kinds(kinds)
    cfg.output_format = out_fmt
    cfg.write_text_pdf = "pdf" in kinds
    # Per-file: md / native / text-pdf (source on plain text → Markdown)
    want_md = "md" in kinds
    want_source = "source" in kinds
    want_text_pdf = "pdf" in kinds
    if cfg.mode == "extract" and want_source:
        console.print(
            "[dim]Note:[/dim] native PDF/DOCX redaction is skipped in extract mode; "
            "source on plain text still writes Markdown."
        )

    if offline and cfg.use_llm:
        from anonymizer.anonymize.llm import is_loopback_url

        prov = cfg.llm_provider.lower()
        if prov == "xai":
            console.print(
                "[red]Error:[/red] --offline forbids remote LLM provider 'xai'. "
                "Use --llm-provider ollama on localhost or omit --llm."
            )
            raise typer.Exit(2)
        if prov == "ollama" and not is_loopback_url(cfg.ollama_url):
            console.print(
                "[red]Error:[/red] --offline forbids non-local ollama_url "
                f"({cfg.ollama_url}). Use http://127.0.0.1:11434 or omit --llm."
            )
            raise typer.Exit(2)

    if cfg.use_llm and cfg.llm_provider.lower() == "xai":
        console.print(
            "[yellow]Warning:[/yellow] Remote LLM (xai) is enabled. "
            "Document text will be sent to https://api.x.ai — not offline."
        )
    elif cfg.use_llm and cfg.llm_provider.lower() == "ollama":
        from anonymizer.anonymize.llm import is_loopback_url

        if not is_loopback_url(cfg.ollama_url):
            console.print(
                f"[yellow]Warning:[/yellow] Ollama URL is not loopback "
                f"({cfg.ollama_url}) — document text will leave this machine."
            )
        else:
            console.print(f"[dim]LLM via local Ollama ({cfg.ollama_url})[/dim]")

    if map_path is not None and cfg.mode == "extract":
        console.print(
            "[dim]Note:[/dim] --map is empty in extract mode (nothing redacted)."
        )

    review_surface = resolve_review_surface(
        review=review,
        review_cli=review_cli,
        review_window=review_window,
    )
    do_review = review_surface is not None and cfg.mode != "extract"
    if do_review:
        try:
            require_review_capable(review_surface or "cli")
        except SystemExit as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(2) from exc

    # Final render style (placeholder tags vs delete). Review uses original
    # blocks + session map; final remove style applied after session apply.
    final_redact_style = cfg.redact_style
    needs_placeholder_review = (do_review or bool(reject)) and cfg.mode != "extract"

    try:
        inputs = collect_inputs(path)
    except (ValueError, FileNotFoundError) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(2) from exc

    if len(inputs) > 1 and output is not None and str(output) != "-":
        console.print(
            "[red]Error:[/red] -o/--output is only for a single input file. "
            "Use --out-dir for a folder."
        )
        raise typer.Exit(2)

    progress = RunProgress(console, quiet=quiet)
    progress.start_batch(len(inputs))
    cb = progress.as_callback()
    anonymizer = DocumentAnonymizer(cfg)
    multi = len(inputs) > 1
    ok_count = 0

    for i, input_path in enumerate(inputs, start=1):
        progress.start_document(input_path, index=i, total=len(inputs))
        # Per-file output plan (source on plain text → Markdown)
        source_to_md = bool(want_source and source_as_markdown(input_path))
        write_md_file = bool(want_md or source_to_md)
        write_native = bool(
            want_source
            and native_suffix(input_path) is not None
            and cfg.mode != "extract"
        )
        write_text_pdf = bool(want_text_pdf)
        need_md_render = write_md_file or write_text_pdf
        if source_to_md and not want_md and not quiet:
            console.print(
                "[dim]Note:[/dim] --format source for plain text writes Markdown "
                f"({input_path.stem}.anonymized.md)."
            )
        try:
            doc = extract_document(
                input_path,
                force_ocr=force_ocr,
                no_ocr=no_ocr,
                lang_flag=cfg.lang,
                keep_headers=cfg.keep_headers,
                progress=cb,
            )
        except Exception as exc:
            console.print(f"[red]Extract failed[/red] {input_path}: {exc}")
            console.print(
                "[dim]Tip:[/dim] try [bold]anonymize doctor[/bold] "
                "or [bold]--force-ocr[/bold] for scanned PDFs."
            )
            if multi:
                continue
            raise typer.Exit(1) from exc

        if not doc.blocks:
            console.print(
                f"[yellow]Warning:[/yellow] No text extracted from {input_path}"
            )
            continue

        if doc.used_ocr and not quiet:
            ocr_meta = (doc.extra or {}).get("ocr") or {}
            low = ocr_meta.get("low_coverage_pages") or []
            low_bit = (
                f" Low-coverage page(s): {', '.join(str(p) for p in low[:8])}"
                + (f" (+{len(low) - 8} more)." if len(low) > 8 else ".")
                if low
                else ""
            )
            console.print(
                "[yellow]OCR risk:[/yellow] text came from OCR — detection can "
                "miss glyphs the recognizer never saw; page images may still "
                f"show PII after native redaction.{low_bit}"
            )

        block_texts = [b.text for b in doc.blocks]
        # Findings → review needs placeholders in the working body.
        saved_style = anonymizer.config.redact_style
        if needs_placeholder_review:
            anonymizer.config.redact_style = "placeholder"
        try:
            anon_blocks, result = anonymizer.anonymize_blocks(
                block_texts, lang_flag=cfg.lang, progress=cb
            )
        except Exception as exc:
            anonymizer.config.redact_style = saved_style
            console.print(f"[red]Anonymize failed[/red] {input_path}: {exc}")
            console.print(
                "[dim]Tip:[/dim] run [bold]anonymize doctor[/bold] "
                "to check spaCy models."
            )
            if multi:
                continue
            raise typer.Exit(1) from exc
        finally:
            anonymizer.config.redact_style = saved_style

        # Front matter / result should reflect the user's chosen final style
        result.redact_style = final_redact_style

        # --- Optional review / --reject (session: un-redact + add) ---
        pre_keep: list[str] = []
        if reject and result.mapping:
            accepted, unknown = parse_reject_list(reject, set(result.mapping.keys()))
            for u in unknown:
                console.print(
                    f"[yellow]--reject unknown tag ignored:[/yellow] {u}"
                )
            pre_keep.extend(accepted)

        if do_review and result.mapping:
            progress.substep("Review redactions…")
            label = (
                f"{input_path.name} ({i}/{len(inputs)})"
                if multi
                else input_path.name
            )
            review_risk = None
            if review_surface == "window" or (review_surface or "cli") == "window":
                from anonymizer.anonymize.review import ReviewRisk

                img_count = 0
                img_pages: list[int] = []
                if input_path.suffix.lower() == ".pdf":
                    try:
                        import pymupdf as fitz

                        _pdf = fitz.open(input_path)
                        try:
                            for _pi, _page in enumerate(_pdf):
                                n_img = len(_page.get_images(full=True) or [])
                                if n_img:
                                    img_count += n_img
                                    img_pages.append(_pi + 1)
                        finally:
                            _pdf.close()
                    except Exception:  # noqa: BLE001
                        pass
                ocr_meta = (doc.extra or {}).get("ocr") or {}
                low = tuple(ocr_meta.get("low_coverage_pages") or [])
                review_risk = ReviewRisk(
                    used_ocr=bool(doc.used_ocr),
                    low_coverage_pages=low,
                    image_count=img_count,
                    image_pages=tuple(img_pages),
                    writing_native=bool(write_native and native_suffix(input_path)),
                    residual_image_risk=bool(doc.used_ocr or img_count),
                )
            try:
                session = interactive_review(
                    result.mapping,
                    console=console,
                    file_label=label,
                    original_blocks=block_texts,
                    surface=review_surface or "cli",
                    pre_keep_clear=pre_keep,
                    learn_to=learn_to,
                    risk=review_risk,
                )
            except SystemExit as exc:
                code = exc.code if isinstance(exc.code, int) else 130
                raise typer.Exit(code) from exc
            # Apply from originals so user-added redactions are included
            apply_style = (
                "placeholder"
                if final_redact_style == "remove"
                else final_redact_style
            )
            anon_blocks, new_map = session.apply(style=apply_style)
            result.mapping = new_map
            result.entity_counts = recount_entities(new_map)
            result.anonymized_text = "\n\n".join(anon_blocks)
            kept_n = session.summary_counts()["keep_clear"]
            added_n = session.summary_counts()["user_added"]
            if not quiet and (kept_n or added_n):
                bits = []
                if kept_n:
                    bits.append(f"{kept_n} kept clear")
                if added_n:
                    bits.append(f"{added_n} added")
                console.print(f"[dim]Review: {', '.join(bits)}.[/dim]")
            # Teach for terminal checklist when --learn-to set (window teaches itself)
            if (
                learn_to
                and (kept_n or added_n)
                and not getattr(session, "taught_path", None)
                and (review_surface or "cli") == "cli"
            ):
                from anonymizer.anonymize.templates import teach_template

                try:
                    taught = teach_template(learn_to, session)
                    if not quiet:
                        console.print(
                            f"[dim]Taught template → {taught}[/dim]"
                        )
                except (OSError, TypeError, ValueError) as exc:
                    console.print(f"[yellow]Could not teach template:[/yellow] {exc}")
        elif do_review and not result.mapping:
            console.print("[dim]No redactions to review.[/dim]")
        elif pre_keep and result.mapping:
            # --reject only (no interactive review)
            session = ReviewSession.from_mapping(
                block_texts, result.mapping, pre_keep_clear=pre_keep
            )
            apply_style = (
                "placeholder"
                if final_redact_style == "remove"
                else final_redact_style
            )
            anon_blocks, new_map = session.apply(style=apply_style)
            result.mapping = new_map
            result.entity_counts = recount_entities(new_map)
            result.anonymized_text = "\n\n".join(anon_blocks)
            if not quiet:
                console.print(
                    f"[dim]Restored {len(pre_keep)} tag(s) to clear text.[/dim]"
                )

        # Final render: delete remaining findings if user chose remove style
        if final_redact_style == "remove" and result.mapping:
            progress.substep("Applying delete style…")
            anon_blocks = strip_placeholders_in_blocks(anon_blocks, result.mapping)
            result.anonymized_text = "\n\n".join(anon_blocks)
            result.redact_style = "remove"

        # Snapshot mapping before any further changes — native redaction uses
        # cleartext originals from the (post-review) map.
        native_mapping = dict(result.mapping)

        written_out: Path | None = None
        written_map: Path | None = None
        written_native: Path | None = None
        written_text_pdf: Path | None = None
        wrote_stdout = False
        md: str | None = None

        # Resolve -o: .pdf/.docx → native path; else Markdown path (when writing MD)
        explicit_native_out: Path | None = None
        explicit_md_out: Path | None = None
        if output is not None and not multi and str(output) != "-":
            if output.suffix.lower() in {".pdf", ".docx"}:
                explicit_native_out = output
            else:
                explicit_md_out = output

        if need_md_render:
            progress.substep("Rendering Markdown…")
            md = render_from_extracted(doc, anon_blocks, result)

            if write_md_file:
                if output is not None and str(output) == "-":
                    progress.substep("Writing to stdout…")
                    sys.stdout.write(md)
                    if not md.endswith("\n"):
                        sys.stdout.write("\n")
                    wrote_stdout = True
                else:
                    if explicit_md_out is not None:
                        out_path = explicit_md_out
                    else:
                        out_path = default_output_path(
                            input_path, out_dir, mode=cfg.mode
                        )
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    progress.substep(f"Writing {out_path}…")
                    out_path.write_text(md, encoding="utf-8")
                    written_out = out_path

        # Reflow PDF from anonymized Markdown (any input type; not native black-box)
        if write_text_pdf:
            if wrote_stdout:
                if not quiet:
                    console.print(
                        "[yellow]Note:[/yellow] text PDF skipped with -o - "
                        "(stdout Markdown only)."
                    )
            elif md is None:
                if not quiet:
                    console.print(
                        "[yellow]Warning:[/yellow] text PDF requested but no Markdown "
                        "was rendered; skipping."
                    )
            else:
                text_pdf_path = default_text_pdf_output_path(input_path, out_dir)
                progress.substep(f"Writing text PDF {text_pdf_path.name}…")
                try:
                    write_pdf_from_markdown(md, text_pdf_path)
                    written_text_pdf = text_pdf_path
                except Exception as exc:  # noqa: BLE001
                    console.print(
                        f"[yellow]Warning:[/yellow] text PDF write failed "
                        f"({text_pdf_path.name}): {exc}"
                    )

        # Native PDF/DOCX (black-box PDF / placeholder|remove DOCX)
        if write_native:
            if explicit_native_out is not None:
                native_path = explicit_native_out
            else:
                native_path = default_native_output_path(input_path, out_dir)
            progress.substep(f"Writing native {native_path.name}…")
            if doc.used_ocr and not quiet:
                ocr_meta = (doc.extra or {}).get("ocr") or {}
                low = ocr_meta.get("low_coverage_pages") or []
                extra = ""
                if low:
                    preview = ", ".join(str(p) for p in low[:8])
                    more = f" (+{len(low) - 8} more)" if len(low) > 8 else ""
                    extra = f" Low-coverage page(s): {preview}{more}."
                console.print(
                    "[yellow]Warning:[/yellow] source used OCR — text-layer "
                    "native redaction cannot black out glyphs still visible "
                    f"in the page image (residual image risk).{extra}"
                )
            try:
                stats = write_native_redacted(
                    input_path,
                    native_path,
                    native_mapping,
                    redact_style=final_redact_style,
                    redact_letterhead_images=cfg.redact_letterhead_images,
                )
            except Exception as exc:
                console.print(
                    f"[red]Native write failed[/red] {input_path}: {exc}"
                )
                if multi:
                    continue
                raise typer.Exit(1) from exc
            if stats is not None:
                written_native = native_path
                if not quiet:
                    console.print(f"[dim]{stats.summary()}[/dim]")
                    if stats.residual_image_risk and not cfg.redact_letterhead_images:
                        console.print(
                            "[yellow]Shareability:[/yellow] "
                            f"{stats.images_total} embedded image(s) remain "
                            "(logos/letterheads). Use "
                            "[bold]--redact-letterhead-images[/bold] to black-box "
                            "header/footer image bands."
                        )
                    for line in stats.shareability_lines():
                        console.print(f"[dim]  · {line}[/dim]")
                    if stats.surfaces_missed and stats.missed:
                        preview = ", ".join(
                            repr(s[:40]) for s in stats.missed[:5]
                        )
                        more = (
                            f" (+{stats.surfaces_missed - 5} more)"
                            if stats.surfaces_missed > 5
                            else ""
                        )
                        console.print(
                            f"[yellow]Warning:[/yellow] "
                            f"{stats.surfaces_missed} surface(s) not found "
                            f"in original layout: {preview}{more}"
                        )
                    if stats.verified and stats.residuals_found and stats.residuals:
                        preview = ", ".join(
                            repr(s[:40]) for s in stats.residuals[:5]
                        )
                        more = (
                            f" (+{stats.residuals_found - 5} more)"
                            if stats.residuals_found > 5
                            else ""
                        )
                        console.print(
                            f"[yellow]Warning:[/yellow] "
                            f"{stats.residuals_found} residual cleartext "
                            f"match(es) after native redaction: "
                            f"{preview}{more}"
                        )
                gate_fail = False
                if cfg.fail_on_native_miss and not stats.is_clean:
                    gate_fail = True
                    console.print(
                        "[red]Native redaction not clean[/red] "
                        "(misses and/or residuals) — "
                        "refusing due to --fail-on-native-miss."
                    )
                min_rate = cfg.native_min_match_rate
                if min_rate is not None and stats.match_rate < min_rate:
                    gate_fail = True
                    console.print(
                        "[red]Native match rate too low[/red] "
                        f"({stats.match_rate:.0%} < {min_rate:.0%} required)."
                    )
                if gate_fail:
                    if multi:
                        continue
                    raise typer.Exit(1)

        if map_path is not None and cfg.mode != "extract":
            if multi:
                mp = map_path
                if mp.suffix.lower() == ".json" and len(inputs) > 1:
                    mp = map_path.with_name(
                        f"{input_path.stem}{map_path.suffix}"
                    )
                else:
                    mp = Path(str(map_path))
                    if mp.is_dir() or not mp.suffix:
                        mp = Path(map_path) / f"{input_path.stem}.map.json"
            else:
                mp = map_path
            mp.parent.mkdir(parents=True, exist_ok=True)
            progress.substep(f"Writing entity map {mp.name} (contains PII)…")
            _write_sensitive_text(
                mp,
                json.dumps(result.mapping, indent=2, ensure_ascii=False) + "\n",
            )
            written_map = mp

        counts = (
            ", ".join(f"{k}={v}" for k, v in sorted(result.entity_counts.items()))
            or "none"
        )
        ocr_bit = ""
        if doc.used_ocr:
            low = ((doc.extra or {}).get("ocr") or {}).get("low_coverage_pages") or []
            ocr_bit = " · OCR (image risk)"
            if low:
                ocr_bit += f" · {len(low)} low-OCR page(s)"
        summary = (
            f"mode={result.mode} · lang={result.language.nlp_passes} · "
            f"entities: {counts}"
            + ocr_bit
            + (f" · format={out_fmt}" if out_fmt != "md" else "")
            + (" · text-pdf" if written_text_pdf is not None else "")
        )
        progress.done_document(summary)
        _report_write_success(
            quiet=quiet,
            input_name=input_path.name,
            elapsed=progress.elapsed_str().strip(),
            summary=summary,
            out_path=written_out,
            map_file=written_map,
            native_path=written_native,
            text_pdf_path=written_text_pdf,
            wrote_stdout=wrote_stdout,
        )
        ok_count += 1

    progress.done_batch(ok_count, len(inputs))


def _print_entities() -> None:
    typer.echo("Modes and default entity types:\n")
    typer.echo("extract  — no redaction")
    typer.echo("  (none)\n")
    typer.echo("standard — identity PII (keeps companies / countries / URLs)")
    for e in STANDARD_ENTITIES:
        typer.echo(f"  {e}")
    typer.echo("\nstrict   — full scrub (default)")
    for e in DEFAULT_ENTITIES:
        typer.echo(f"  {e}")
    typer.echo("\nDATE_TIME — opt-in via --include-dates (standard/strict)")


def cmd_doctor() -> None:
    """Health check for a working local install."""
    console.print(f"[bold]anonymizer doctor[/bold]  v{__version__}\n")
    ok_all = True
    rows: list[tuple[str, str, bool]] = []

    which = shutil.which("anonymize")
    if which:
        rows.append(("CLI on PATH", which, True))
    else:
        rows.append(
            (
                "CLI on PATH",
                "not found — add ~/.local/bin to PATH or open a new terminal",
                False,
            )
        )
        ok_all = False

    # Non-fatal: ~/.local/bin may shadow a newer Homebrew install
    local_cli = Path.home() / ".local" / "bin" / "anonymize"
    brew_cli = None
    for candidate in (Path("/opt/homebrew/bin/anonymize"), Path("/usr/local/bin/anonymize")):
        if candidate.is_file():
            brew_cli = candidate
            break
    if (
        which
        and brew_cli is not None
        and local_cli.is_file()
        and Path(which).resolve() == local_cli.resolve()
    ):
        rows.append(
            (
                "PATH shadow",
                f"{local_cli} shadows Homebrew ({brew_cli}) — "
                "hash -r or ANONYMIZER_BIN=/opt/homebrew/bin/anonymize",
                True,  # warning only; do not fail doctor
            )
        )

    try:
        import anonymizer as _pkg

        rows.append(("Package", str(Path(_pkg.__file__).resolve().parent), True))
    except Exception as exc:
        rows.append(("Package", str(exc), False))
        ok_all = False

    try:
        import spacy

        for lang, primary in SPACY_MODELS.items():
            loaded = None
            for name in [primary, *SPACY_FALLBACKS.get(lang, [])]:
                try:
                    spacy.load(name)
                    loaded = name
                    break
                except OSError:
                    continue
            if loaded:
                note = loaded
                # Nudge toward large models when only sm is present (EN/FI)
                if lang in {"en", "fi"} and loaded.endswith("_sm"):
                    note = f"{loaded}  (tip: larger models improve PERSON/ORG — see docs/models.md)"
                rows.append((f"spaCy ({lang})", note, True))
            else:
                # EN+FI required for default install; extra langs (sv, …) optional
                required = lang in {"en", "fi"}
                rows.append(
                    (
                        f"spaCy ({lang})",
                        f"missing — python -m spacy download {primary}"
                        + ("" if required else " (optional)"),
                        not required,
                    )
                )
                if required:
                    ok_all = False
    except Exception as exc:
        rows.append(("spaCy", f"import failed: {exc}", False))
        ok_all = False

    tess = shutil.which("tesseract")
    if tess:
        try:
            ver = subprocess.check_output(
                [tess, "--version"], text=True, stderr=subprocess.STDOUT
            ).splitlines()[0]
            rows.append(("Tesseract (OCR)", ver, True))
        except Exception:
            rows.append(("Tesseract (OCR)", tess, True))
        # Language packs used by default OCR path (eng+fin) — advisory only
        try:
            lang_out = subprocess.check_output(
                [tess, "--list-langs"], text=True, stderr=subprocess.STDOUT
            )
            available = {ln.strip() for ln in lang_out.splitlines()[1:] if ln.strip()}
            missing = [lang for lang in ("eng", "fin") if lang not in available]
            if missing:
                rows.append(
                    (
                        "Tesseract langs",
                        f"missing {', '.join(missing)} — brew install tesseract-lang",
                        True,
                    )
                )
            else:
                rows.append(("Tesseract langs", "eng, fin ok", True))
        except Exception:
            rows.append(("Tesseract langs", "could not list", True))
    else:
        rows.append(
            (
                "Tesseract (OCR)",
                "optional — brew install tesseract tesseract-lang",
                True,
            )
        )

    ocrpdf = shutil.which("ocrmypdf")
    if ocrpdf:
        rows.append(("ocrmypdf", ocrpdf, True))
    else:
        rows.append(("ocrmypdf", "optional — brew install ocrmypdf", True))

    try:
        with tempfile.NamedTemporaryFile(suffix=".md", delete=True) as fh:
            fh.write(b"ok")
        rows.append(("Temp write", "ok", True))
    except Exception as exc:
        rows.append(("Temp write", str(exc), False))
        ok_all = False

    # Document review window (optional for CLI checklist, required for --review-window / app)
    try:
        from anonymizer.gui.review_window import display_available

        if display_available():
            rows.append(("Review window (tk)", "available", True))
        else:
            tip = (
                "missing _tkinter — brew install python-tk@3.12"
                if sys.platform == "darwin"
                else "tkinter unavailable"
            )
            rows.append(("Review window (tk)", tip, False))
            # Not fatal for CLI-only use; still surface the gap clearly
    except Exception as exc:
        rows.append(("Review window (tk)", f"unavailable ({exc})", False))

    table = Table(show_header=True, header_style="bold")
    table.add_column("Check")
    table.add_column("Status")
    for label, status, good in rows:
        mark = "[green]✓[/green]" if good else "[red]✗[/red]"
        table.add_row(f"{mark} {label}", status)
    console.print(table)
    console.print()

    if ok_all:
        console.print("[green bold]You're good to go.[/green bold]")
        console.print(
            "Try:  [bold]anonymize extract some.pdf[/bold]  or  "
            "[bold]anonymize contract.pdf[/bold]"
        )
        raise SystemExit(0)

    console.print("[red bold]Some checks failed.[/red bold]")
    console.print("Fix:")
    console.print("  1. Re-run the installer, or:  [bold]source ~/.zshrc[/bold]")
    console.print(
        '  2. PATH:  [bold]export PATH="$HOME/.local/bin:$PATH"[/bold]'
    )
    console.print(
        "  3. Models:  [bold]python -m anonymizer.install_models "
        "--langs en,fi --size lg --fallback[/bold]"
    )
    raise SystemExit(1)


def cmd_examples() -> None:
    typer.echo(
        """
Common commands
---------------
  anonymize contract.pdf
      Full scrub (strict) → contract.anonymized.md

  anonymize extract report.pdf
      Text only → report.md  (no redaction)

  anonymize extract report.pdf -o body.md
      Text only, choose output name

  anonymize standard sopimus.pdf
      Redact people / phones / emails / addresses; keep company names

  anonymize strict folder/ --out-dir out/
      Batch full scrub into out/

  anonymize doctor
      Check install and models

  anonymize --list-entities
      Show what each mode redacts

Install (once)
--------------
  curl -fsSL https://raw.githubusercontent.com/arcane-tl/anonymizer/main/scripts/install.sh | bash -s -- --yes
  # then open a new terminal, or:
  export PATH="$HOME/.local/bin:$PATH"

Templates (allow/deny packs)
----------------------------
  anonymize templates
      List builtin + user packs

  anonymize contract.pdf --template fi-field-labels,my-company
      Apply selected packs this run

  anonymize contract.pdf --review --learn-to my-company
      After review, teach keep-clear / adds into user template
""".strip()
        + "\n"
    )


def cmd_templates_ui(rest: list[str] | None = None) -> None:
    """Open the shared Tk Templates dialog (Mac droplet / desktop)."""
    rest = rest or []
    enabled = ""
    out_path = ""
    i = 0
    while i < len(rest):
        if rest[i] in {"--enabled", "-e"} and i + 1 < len(rest):
            enabled = rest[i + 1]
            i += 2
            continue
        if rest[i].startswith("--enabled="):
            enabled = rest[i].split("=", 1)[1]
            i += 1
            continue
        if rest[i] in {"--out", "-o"} and i + 1 < len(rest):
            out_path = rest[i + 1]
            i += 2
            continue
        if rest[i].startswith("--out="):
            out_path = rest[i].split("=", 1)[1]
            i += 1
            continue
        i += 1
    from anonymizer.gui.app import run_templates_ui

    raise SystemExit(run_templates_ui(enabled, out_path=out_path or None))


def cmd_templates(rest: list[str] | None = None) -> None:
    """List or show allow/deny templates."""
    from anonymizer.anonymize.templates import (
        default_enabled_ids,
        discover_templates,
        resolve_enabled_ids,
        user_templates_dir,
    )

    rest = rest or []
    packs = discover_templates()
    defaults = set(default_enabled_ids(packs))
    sub = rest[0].casefold() if rest else "list"
    if sub in {"print-enabled", "enabled"}:
        # For AppleScript / shell without opening Tk
        ids = resolve_enabled_ids(config_templates=None, all_templates=packs)
        # Prefer config if present
        try:
            from anonymizer.lists_io import default_config_path
            from anonymizer.anonymize.config import load_config

            cfg_path = default_config_path()
            if cfg_path.is_file():
                cfg = load_config(cfg_path)
                ids = resolve_enabled_ids(
                    config_templates=cfg.templates_enabled,
                    all_templates=packs,
                )
        except Exception:  # noqa: BLE001
            pass
        print(",".join(ids))
        return
    if sub in {"list", "ls", ""}:
        console.print("[bold]Templates[/bold]")
        console.print(f"[dim]User dir:[/dim] {user_templates_dir()}")
        console.print()
        table = Table(show_header=True, header_style="bold")
        table.add_column("Id")
        table.add_column("Title")
        table.add_column("Kind")
        table.add_column("Default")
        table.add_column("Allow")
        table.add_column("Deny")
        for t in packs:
            table.add_row(
                t.id,
                t.display_title(),
                "builtin" if t.builtin else "user",
                "yes" if t.id in defaults else "",
                str(len(t.allow)),
                str(len(t.deny)),
            )
        console.print(table)
        console.print()
        console.print(
            "[dim]Apply:[/dim] anonymize FILE --template id1,id2\n"
            "[dim]Teach:[/dim] anonymize FILE --review --learn-to my-pack"
        )
        return
    if sub in {"show", "cat"} and len(rest) >= 2:
        tid = rest[1]
        for t in packs:
            if t.id == tid:
                console.print(f"[bold]{t.display_title()}[/bold] ({t.id})")
                if t.description:
                    console.print(t.description.strip())
                console.print(f"[dim]path:[/dim] {t.path}")
                console.print(f"[dim]allow ({len(t.allow)}):[/dim]")
                for a in t.allow[:40]:
                    console.print(f"  · {a}")
                if len(t.allow) > 40:
                    console.print(f"  … +{len(t.allow) - 40} more")
                console.print(f"[dim]deny ({len(t.deny)}):[/dim]")
                for d in t.deny[:40]:
                    console.print(f"  · {d.text} ({d.entity_type})")
                if len(t.deny) > 40:
                    console.print(f"  … +{len(t.deny) - 40} more")
                return
        console.print(f"[red]Unknown template:[/red] {tid}")
        raise SystemExit(2)
    console.print(
        "Usage: anonymize templates [list|show ID|print-enabled]\n"
        "  anonymize templates-ui [--enabled id1,id2]\n"
        "  anonymize FILE --template id1,id2\n"
        "  anonymize FILE --review --learn-to my-pack"
    )


@app.command(
    name="anonymize",
    # Single-command app: Typer still names the command; entrypoint is `run`.
    hidden=False,
)
def main(
    path: Annotated[
        Optional[Path],
        typer.Argument(
            help="File or folder. Tip: anonymize extract FILE · anonymize standard FILE",
        ),
    ] = None,
    mode: Annotated[
        Optional[str],
        typer.Option(
            "--mode",
            "-m",
            help="extract | standard | strict (default: strict).",
            rich_help_panel="Common",
        ),
    ] = None,
    output: Annotated[
        Optional[Path],
        typer.Option(
            "--output",
            "-o",
            help="Output Markdown path (single file). Use '-' for stdout.",
            rich_help_panel="Common",
        ),
    ] = None,
    out_dir: Annotated[
        Optional[Path],
        typer.Option(
            "--out-dir",
            help="Output directory for batch / multiple files.",
            rich_help_panel="Common",
        ),
    ] = None,
    map_path: Annotated[
        Optional[Path],
        typer.Option(
            "--map",
            help="Write placeholder→original map JSON (SENSITIVE — contains PII).",
            rich_help_panel="Common",
        ),
    ] = None,
    lang: Annotated[
        str,
        typer.Option(
            "--lang",
            help="Language: auto | en | fi | sv | en,fi | en,sv | …",
            rich_help_panel="Common",
        ),
    ] = "auto",
    config: Annotated[
        Optional[Path],
        typer.Option(
            "--config",
            help="YAML config (mode, allowlist, denylist, recognizers, …). Supports ~/… paths.",
            # exists checked after expand_user_path in _run_pipeline
            # (Typer does not expand ~ before exists=True validation).
            dir_okay=False,
            rich_help_panel="Common",
        ),
    ] = None,
    quiet: Annotated[
        bool,
        typer.Option(
            "--quiet",
            "-q",
            help="Hide progress (errors still shown).",
            rich_help_panel="Common",
        ),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            "-v",
            help="Debug logging.",
            rich_help_panel="Common",
        ),
    ] = False,
    force_ocr: Annotated[
        bool,
        typer.Option(
            "--force-ocr",
            help="Force OCR on PDFs even if a text layer exists.",
            rich_help_panel="OCR",
        ),
    ] = False,
    no_ocr: Annotated[
        bool,
        typer.Option(
            "--no-ocr",
            help="Never run OCR on PDFs.",
            rich_help_panel="OCR",
        ),
    ] = False,
    keep_headers: Annotated[
        bool,
        typer.Option(
            "--keep-headers",
            help="Keep PDF page headers/footers/page numbers (default: strip).",
            rich_help_panel="Common",
        ),
    ] = False,
    review: Annotated[
        bool,
        typer.Option(
            "--review/--no-review",
            "-r",
            help=(
                "Interactive review before writing (terminal checklist by default). "
                "Use --review-window for the document UI; GUIs pass that flag."
            ),
            rich_help_panel="Common",
        ),
    ] = False,
    review_cli: Annotated[
        bool,
        typer.Option(
            "--review-cli",
            help=(
                "Terminal checklist review (same as default --review). "
                "Implies review; useful to force CLI if ANONYMIZER_REVIEW=window."
            ),
            rich_help_panel="Common",
        ),
    ] = False,
    review_window: Annotated[
        bool,
        typer.Option(
            "--review-window",
            help=(
                "Document review window (toggle false positives, select text to add). "
                "Implies review. Used by anonymize-gui / desktop apps."
            ),
            rich_help_panel="Common",
        ),
    ] = False,
    reject: Annotated[
        Optional[str],
        typer.Option(
            "--reject",
            help=(
                "Placeholders to keep in clear text without a prompt "
                "(e.g. ORG_1,PHONE_2). Works with or without --review."
            ),
            rich_help_panel="Common",
        ),
    ] = None,
    redact_style: Annotated[
        Optional[str],
        typer.Option(
            "--redact-style",
            help=(
                "How to replace findings: placeholder (default, [PERSON_1] tags) "
                "or remove (delete the text). Review works with both (checklist "
                "first, then style is applied)."
            ),
            rich_help_panel="Common",
        ),
    ] = None,
    output_format: Annotated[
        Optional[str],
        typer.Option(
            "--format",
            help=(
                "Comma-separated outputs: md (Markdown), source (redacted original "
                "PDF/DOCX; plain text → Markdown), pdf (reflowed text PDF). "
                "Examples: md | source | pdf | md,pdf | md,source,pdf. "
                "Compat: both=md+source, all=md+source+pdf. "
                "Source on PDF/DOCX is best-effort black-box; Text PDF is a separate "
                "reflowed file (.anonymized.text.pdf)."
            ),
            rich_help_panel="Common",
        ),
    ] = None,
    write_text_pdf: Annotated[
        bool,
        typer.Option(
            "--pdf/--no-pdf",
            "--write-text-pdf/--no-write-text-pdf",
            help=(
                "Deprecated: prefer --format pdf or --format md,pdf. "
                "Adds reflowed text PDF ({stem}.anonymized.text.pdf) to outputs."
            ),
            rich_help_panel="Common",
            hidden=False,
        ),
    ] = False,
    fail_on_native_miss: Annotated[
        bool,
        typer.Option(
            "--fail-on-native-miss",
            help=(
                "Exit with status 1 when native PDF/DOCX redaction misses surfaces "
                "or post-verify finds residual cleartext."
            ),
            rich_help_panel="Common",
        ),
    ] = False,
    native_min_match_rate: Annotated[
        Optional[float],
        typer.Option(
            "--native-min-match-rate",
            help=(
                "Require native surface match rate ≥ this value (0–1). "
                "Exit 1 when below threshold."
            ),
            rich_help_panel="Common",
        ),
    ] = None,
    redact_letterhead_images: Annotated[
        bool,
        typer.Option(
            "--redact-letterhead-images",
            help=(
                "For PDF native output: black-box images in header/footer bands "
                "(logos/letterheads). Recommended for shareable PDFs."
            ),
            rich_help_panel="Common",
        ),
    ] = False,
    template: Annotated[
        Optional[str],
        typer.Option(
            "--template",
            "--templates",
            help=(
                "Comma-separated template ids to apply (allow/deny packs). "
                "Default: builtin packs marked default. Empty string applies none. "
                "List packs: anonymize templates"
            ),
            rich_help_panel="Common",
        ),
    ] = None,
    learn_to: Annotated[
        Optional[str],
        typer.Option(
            "--learn-to",
            help=(
                "Pre-select this user template for Teach in the review window "
                "(or teach after terminal --review). Forks if id is a builtin."
            ),
            rich_help_panel="Common",
        ),
    ] = None,
    entities: Annotated[
        Optional[str],
        typer.Option(
            "--entities",
            help="Comma-separated entity types (overrides mode preset).",
            rich_help_panel="Advanced",
        ),
    ] = None,
    score_threshold: Annotated[
        Optional[float],
        typer.Option(
            "--score-threshold",
            help="Minimum NER score (0–1).",
            rich_help_panel="Advanced",
        ),
    ] = None,
    include_dates: Annotated[
        bool,
        typer.Option(
            "--include-dates",
            help="Also redact DATE_TIME entities.",
            rich_help_panel="Advanced",
        ),
    ] = False,
    llm: Annotated[
        bool,
        typer.Option(
            "--llm",
            help=(
                "Enable optional LLM entity layer (required even if config sets "
                "use_llm). Default provider is ollama; xai is remote."
            ),
            rich_help_panel="Advanced",
        ),
    ] = False,
    llm_provider: Annotated[
        Optional[str],
        typer.Option(
            "--llm-provider",
            help="ollama (local) or xai (remote — sends document text).",
            rich_help_panel="Advanced",
        ),
    ] = None,
    llm_model: Annotated[
        Optional[str],
        typer.Option(
            "--llm-model",
            help="Model name override.",
            rich_help_panel="Advanced",
        ),
    ] = None,
    offline: Annotated[
        bool,
        typer.Option(
            "--offline",
            help="Refuse remote xai LLM.",
            rich_help_panel="Advanced",
        ),
    ] = False,
    list_entities: Annotated[
        bool,
        typer.Option(
            "--list-entities",
            help="List entity types per mode and exit.",
            rich_help_panel="Info",
        ),
    ] = False,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            help="Show version and exit.",
            rich_help_panel="Info",
        ),
    ] = False,
) -> None:
    """Anonymize or extract documents → Markdown / source / text PDF.

    Examples:

      anonymize contract.pdf

      anonymize contract.pdf --format md,source,pdf

      anonymize contract.pdf --format source

      anonymize notes.txt --format pdf

      anonymize extract report.pdf -o body.md

      anonymize standard sopimus.pdf

      anonymize doctor
    """
    if version:
        typer.echo(f"anonymizer {__version__}")
        raise typer.Exit(0)

    if list_entities:
        _print_entities()
        raise typer.Exit(0)

    if path is None:
        # no_args_is_help usually handles this; keep a clear message
        console.print(
            "[dim]Pass a file, or try:[/dim] anonymize examples · anonymize doctor"
        )
        raise SystemExit(2)

    effective_mode = mode or "strict"
    _run_pipeline(
        path,
        mode=effective_mode,
        output=output,
        out_dir=out_dir,
        map_path=map_path,
        lang=lang,
        config=config,
        entities=entities,
        score_threshold=score_threshold,
        include_dates=include_dates,
        force_ocr=force_ocr,
        no_ocr=no_ocr,
        keep_headers=keep_headers,
        review=review,
        review_cli=review_cli,
        review_window=review_window,
        reject=reject,
        redact_style=redact_style,
        output_format=output_format,
        write_text_pdf=write_text_pdf,
        fail_on_native_miss=fail_on_native_miss,
        native_min_match_rate=native_min_match_rate,
        redact_letterhead_images=redact_letterhead_images,
        llm=llm,
        llm_provider=llm_provider,
        llm_model=llm_model,
        offline=offline,
        quiet=quiet,
        verbose=verbose,
        template=template,
        learn_to=learn_to,
    )


def _first_positional_index(args: list[str]) -> int | None:
    """Index of first non-option argument in argv-style list."""
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--":
            return i + 1 if i + 1 < len(args) else None
        if a.startswith("-"):
            # --opt=value form
            if "=" in a:
                i += 1
                continue
            if a in _OPTS_WITH_VALUE:
                i += 2
                continue
            i += 1
            continue
        return i
    return None


def _preprocess_argv(argv: list[str]) -> list[str] | None:
    """
    Rewrite friendly verbs into --mode, or handle meta commands.

    Returns None if the caller should exit (meta command already run).
    """
    # argv includes program name at [0]
    args = argv[1:]
    if not args:
        return argv

    idx = _first_positional_index(args)
    if idx is None:
        return argv

    token = args[idx]
    low = token.casefold()

    if low in _META_COMMANDS:
        if low == "doctor":
            cmd_doctor()
        elif low == "templates":
            cmd_templates(args[idx + 1 :])
        elif low == "templates-ui":
            cmd_templates_ui(args[idx + 1 :])
        else:
            cmd_examples()
        return None

    if low in _VERB_TO_MODE:
        mode = _VERB_TO_MODE[low]
        # anonymize extract file.pdf  →  anonymize --mode extract file.pdf
        new_args = args[:idx] + ["--mode", mode] + args[idx + 1 :]
        return [argv[0], *new_args]

    return argv


def run() -> None:
    rewritten = _preprocess_argv(sys.argv)
    if rewritten is None:
        return
    sys.argv = rewritten
    app()


if __name__ == "__main__":
    run()
