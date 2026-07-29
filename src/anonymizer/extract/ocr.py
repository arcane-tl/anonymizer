"""OCR helpers for scanned PDFs."""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


def tesseract_available() -> bool:
    return shutil.which("tesseract") is not None


def ocrmypdf_available() -> bool:
    return shutil.which("ocrmypdf") is not None


def ensure_tesseract_langs(langs: str) -> None:
    """Raise RuntimeError if required Tesseract language packs are missing."""
    if not tesseract_available():
        raise RuntimeError(
            "Tesseract is not installed. On Mac: brew install tesseract tesseract-lang ocrmypdf"
        )
    needed = [p for p in langs.replace("+", " ").split() if p]
    proc = subprocess.run(
        ["tesseract", "--list-langs"],
        capture_output=True,
        text=True,
        check=False,
    )
    available = set(proc.stdout.splitlines()[1:])  # first line is header
    missing = [lang for lang in needed if lang not in available]
    if missing:
        raise RuntimeError(
            f"Missing Tesseract language data: {', '.join(missing)}. "
            "On Mac: brew install tesseract-lang "
            f"(need: {', '.join(needed)})"
        )


def ocr_pdf_to_searchable(
    source: Path,
    tesseract_langs: str = "eng+fin",
) -> Path:
    """
    Run OCR and return path to a temporary searchable PDF.
    Caller should delete the temp file when done.
    """
    ensure_tesseract_langs(tesseract_langs)

    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp_path = Path(tmp.name)
    tmp.close()

    if ocrmypdf_available():
        cmd = [
            "ocrmypdf",
            "-l",
            tesseract_langs,
            "--force-ocr",
            "--quiet",
            str(source),
            str(tmp_path),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            tmp_path.unlink(missing_ok=True)
            raise RuntimeError(
                f"ocrmypdf failed (exit {proc.returncode}): {proc.stderr or proc.stdout}"
            )
        return tmp_path

    # Fallback: page-by-page via pymupdf + tesseract CLI
    return _ocr_with_pymupdf_tesseract(source, tmp_path, tesseract_langs)


def _ocr_with_pymupdf_tesseract(
    source: Path,
    out_path: Path,
    tesseract_langs: str,
) -> Path:
    import fitz

    src = fitz.open(source)
    out = fitz.open()
    try:
        for page in src:
            # Render at ~200 DPI
            mat = fitz.Matrix(2, 2)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as img_f:
                img_path = Path(img_f.name)
            try:
                pix.save(str(img_path))
                txt_proc = subprocess.run(
                    [
                        "tesseract",
                        str(img_path),
                        "stdout",
                        "-l",
                        tesseract_langs,
                        "--psm",
                        "3",
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if txt_proc.returncode != 0:
                    logger.warning("tesseract page OCR failed: %s", txt_proc.stderr)
                    text = ""
                else:
                    text = txt_proc.stdout
            finally:
                img_path.unlink(missing_ok=True)

            # New page with text as text page (simple layout)
            new_page = out.new_page(width=page.rect.width, height=page.rect.height)
            # Insert text in a textbox covering the page
            rect = fitz.Rect(36, 36, page.rect.width - 36, page.rect.height - 36)
            new_page.insert_textbox(rect, text, fontsize=10, fontname="helv")
        out.save(str(out_path))
    finally:
        src.close()
        out.close()
    return out_path
