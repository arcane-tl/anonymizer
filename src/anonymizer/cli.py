"""Typer CLI entrypoint for anonymize."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.logging import RichHandler

from anonymizer import __version__
from anonymizer.anonymize.config import DEFAULT_ENTITIES, AnonymizerConfig, load_config
from anonymizer.anonymize.engine import DocumentAnonymizer
from anonymizer.extract import extract_document
from anonymizer.output.markdown import render_from_extracted
from anonymizer.util.files import collect_inputs, default_output_path

app = typer.Typer(
    name="anonymize",
    help="Anonymize PDF/DOCX/text documents to Markdown (local, EN+FI).",
    add_completion=False,
    no_args_is_help=True,
)
console = Console(stderr=True)


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True, show_path=False)],
    )
    # Quiet noisy third-party loggers unless verbose
    if not verbose:
        for name in (
            "presidio-analyzer",
            "presidio_analyzer",
            "presidio-anonymizer",
        ):
            logging.getLogger(name).setLevel(logging.ERROR)


@app.command()
def main(
    path: Optional[Path] = typer.Argument(
        None,
        help="Input file or directory of documents.",
        exists=False,
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output Markdown path (single file). Use '-' for stdout.",
    ),
    out_dir: Optional[Path] = typer.Option(
        None,
        "--out-dir",
        help="Output directory when processing multiple files.",
    ),
    map_path: Optional[Path] = typer.Option(
        None,
        "--map",
        help="Write placeholder→original map JSON (SENSITIVE — contains PII).",
    ),
    lang: str = typer.Option(
        "auto",
        "--lang",
        help="Language mode: auto | en | fi | en,fi",
    ),
    entities: Optional[str] = typer.Option(
        None,
        "--entities",
        help="Comma-separated entity types to redact.",
    ),
    score_threshold: Optional[float] = typer.Option(
        None,
        "--score-threshold",
        help="Minimum NER score (0–1).",
    ),
    include_dates: bool = typer.Option(
        False,
        "--include-dates",
        help="Also redact DATE_TIME entities.",
    ),
    force_ocr: bool = typer.Option(
        False,
        "--force-ocr",
        help="Force OCR on PDFs even if a text layer exists.",
    ),
    no_ocr: bool = typer.Option(
        False,
        "--no-ocr",
        help="Never run OCR on PDFs.",
    ),
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        help="YAML config file (allowlist/denylist/entities).",
        exists=True,
        dir_okay=False,
    ),
    list_entities: bool = typer.Option(
        False,
        "--list-entities",
        help="List default entity types and exit.",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Debug logging."),
    version: bool = typer.Option(False, "--version", help="Show version and exit."),
) -> None:
    """Anonymize documents: remove names, orgs, and other PII → Markdown."""
    if version:
        typer.echo(f"anonymizer {__version__}")
        raise typer.Exit(0)

    if list_entities:
        for e in DEFAULT_ENTITIES + ["DATE_TIME (opt-in via --include-dates)"]:
            typer.echo(e)
        raise typer.Exit(0)

    if path is None:
        console.print("[red]Error:[/red] PATH is required (or use --list-entities / --version).")
        raise typer.Exit(2)

    _setup_logging(verbose)
    log = logging.getLogger("anonymizer")

    cfg = load_config(config)
    cfg.lang = lang
    cfg.include_dates = include_dates or cfg.include_dates
    if score_threshold is not None:
        cfg.score_threshold = score_threshold
    if entities:
        cfg.entities = [e.strip() for e in entities.split(",") if e.strip()]

    try:
        inputs = collect_inputs(path)
    except (ValueError, FileNotFoundError) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(2) from exc

    if len(inputs) > 1 and output is not None and str(output) != "-":
        console.print(
            "[red]Error:[/red] -o/--output is only valid for a single input file. "
            "Use --out-dir for batch mode."
        )
        raise typer.Exit(2)

    anonymizer = DocumentAnonymizer(cfg)
    multi = len(inputs) > 1

    for input_path in inputs:
        log.info("Processing %s", input_path)
        try:
            doc = extract_document(
                input_path,
                force_ocr=force_ocr,
                no_ocr=no_ocr,
                lang_flag=cfg.lang,
            )
        except Exception as exc:
            console.print(f"[red]Extract failed[/red] {input_path}: {exc}")
            if multi:
                continue
            raise typer.Exit(1) from exc

        if not doc.blocks:
            console.print(f"[yellow]Warning:[/yellow] No text extracted from {input_path}")
            continue

        block_texts = [b.text for b in doc.blocks]
        try:
            anon_blocks, result = anonymizer.anonymize_blocks(
                block_texts, lang_flag=cfg.lang
            )
        except Exception as exc:
            console.print(f"[red]Anonymize failed[/red] {input_path}: {exc}")
            if multi:
                continue
            raise typer.Exit(1) from exc

        md = render_from_extracted(doc, anon_blocks, result)

        # Resolve output path
        if output is not None and str(output) == "-":
            sys.stdout.write(md)
            if not md.endswith("\n"):
                sys.stdout.write("\n")
        else:
            if output is not None and not multi:
                out_path = output
                out_path.parent.mkdir(parents=True, exist_ok=True)
            else:
                out_path = default_output_path(input_path, out_dir)
            out_path.write_text(md, encoding="utf-8")
            log.info("Wrote %s", out_path)

        if map_path is not None:
            # For multi-input, suffix map by stem if single map_path is a dir-like intent
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
            mp.write_text(
                json.dumps(result.mapping, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            log.warning(
                "Wrote entity map %s (contains original PII — keep private)",
                mp,
            )

        # Summary to stderr
        counts = ", ".join(f"{k}={v}" for k, v in sorted(result.entity_counts.items())) or "none"
        console.print(
            f"[green]OK[/green] {input_path.name} · "
            f"lang={result.language.nlp_passes} ({result.language.reason}) · "
            f"entities: {counts}"
            + (" · OCR" if doc.used_ocr else "")
        )


# Typer needs a callable for console_scripts — expose `app` and a main wrapper
def run() -> None:
    app()


if __name__ == "__main__":
    app()
