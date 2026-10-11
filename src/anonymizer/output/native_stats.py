"""Stats from native (PDF/DOCX) redaction passes."""

from __future__ import annotations

from dataclasses import dataclass, field


# Honest coverage labels for summaries / front matter (not a legal warranty).
NATIVE_COVERAGE_PDF = {
    "content_stream": True,
    "outline": True,
    "metadata": True,
    "links_widgets": True,
    "images": "best_effort",
    "tagged_structure_tree": False,
    "guarantees": (
        "text layer + outline + metadata + links/widgets; "
        "not OCR-from-images or full tagged structure tree"
    ),
}

NATIVE_COVERAGE_DOCX = {
    "body_headers_notes": True,
    "revisions_accepted": True,
    "core_app_properties": True,
    "hyperlink_targets": True,
    "charts_smartart_alt_text": False,
    "guarantees": (
        "body/headers/notes/comments after accepting revisions; "
        "core/app props; matching hyperlink targets; "
        "not charts/SmartArt/alt-text catalogues"
    ),
}


@dataclass
class NativeRedactStats:
    """How many cleartext surfaces were found, applied, and residual after verify."""

    format: str  # pdf | docx
    surfaces_total: int = 0
    surfaces_found: int = 0
    surfaces_missed: int = 0
    hit_count: int = 0  # individual occurrences (rects / replacements)
    missed: list[str] = field(default_factory=list)
    output_path: str = ""
    # Post-redaction verification (independent of redaction walker)
    verified: bool = False
    residuals_found: int = 0
    residuals: list[str] = field(default_factory=list)
    scrub_errors: int = 0
    scrub_error_samples: list[str] = field(default_factory=list)
    # PDF scrub counters (0 for DOCX / when unused)
    annotations_scrubbed: int = 0
    widgets_scrubbed: int = 0
    # Image / letterhead inventory (PDF)
    images_total: int = 0
    image_pages: list[int] = field(default_factory=list)
    images_redacted: int = 0
    letterhead_redacted: bool = False
    # Coverage flags written into summaries
    coverage: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.coverage:
            if self.format == "pdf":
                self.coverage = dict(NATIVE_COVERAGE_PDF)
            elif self.format == "docx":
                self.coverage = dict(NATIVE_COVERAGE_DOCX)

    @property
    def match_rate(self) -> float:
        if self.surfaces_total <= 0:
            return 1.0
        return self.surfaces_found / self.surfaces_total

    @property
    def residual_image_risk(self) -> bool:
        """True when page images remain that text-layer redaction may not cover."""
        remaining = self.images_total - self.images_redacted
        return remaining > 0

    @property
    def is_clean(self) -> bool:
        """True when every surface was hit, verify found no residuals, no scrub errors.

        Image residual risk is reported separately and does not flip ``is_clean``
        (logos need explicit ``--redact-letterhead-images`` / future cover).
        """
        if self.surfaces_missed > 0:
            return False
        if self.scrub_errors > 0:
            return False
        if self.verified and self.residuals_found > 0:
            return False
        return True

    def summary(self) -> str:
        if self.surfaces_total == 0:
            base = f"{self.format}: no surfaces to redact"
        else:
            base = (
                f"{self.format}: redacted {self.surfaces_found}/{self.surfaces_total} "
                f"surfaces ({self.hit_count} hit(s))"
            )
        extras: list[str] = []
        if self.verified:
            if self.residuals_found:
                extras.append(f"{self.residuals_found} residual(s)")
            elif self.surfaces_missed:
                extras.append("verified (misses only)")
            else:
                extras.append("verified clean")
        if self.scrub_errors:
            extras.append(f"{self.scrub_errors} scrub error(s)")
        if self.widgets_scrubbed or self.annotations_scrubbed:
            extras.append(
                f"scrubbed {self.widgets_scrubbed} widget(s), "
                f"{self.annotations_scrubbed} annot(s)"
            )
        if self.images_total:
            if self.images_redacted:
                extras.append(
                    f"images {self.images_redacted}/{self.images_total} blacked out"
                )
            else:
                extras.append(
                    f"{self.images_total} image(s) on "
                    f"{len(self.image_pages)} page(s) — residual image risk"
                )
        if extras:
            return f"{base}; " + ", ".join(extras)
        return base

    def shareability_lines(self) -> list[str]:
        """Human lines for a short shareability report."""
        lines = [
            f"format={self.format}",
            f"match_rate={self.match_rate:.0%} "
            f"({self.surfaces_found}/{self.surfaces_total})",
            f"clean={self.is_clean}",
        ]
        if self.missed:
            lines.append(f"layout_misses={len(self.missed)}")
        if self.residuals_found:
            lines.append(f"text_residuals={self.residuals_found}")
        if self.scrub_errors:
            lines.append(f"scrub_errors={self.scrub_errors}")
        if self.images_total:
            lines.append(
                f"images={self.images_total} redacted={self.images_redacted} "
                f"image_risk={self.residual_image_risk}"
            )
        if self.letterhead_redacted:
            lines.append("letterhead_images=redacted")
        g = self.coverage.get("guarantees")
        if g:
            lines.append(f"coverage={g}")
        return lines

    def front_matter_fields(self) -> dict:
        """Keys suitable for Markdown YAML front matter / machine summary."""
        samples = list(self.residuals[:5])
        out: dict = {
            "native_format": self.format,
            "native_clean": self.is_clean,
            "native_residuals": self.residuals_found,
            "native_scrub_errors": self.scrub_errors,
            "native_match_rate": round(self.match_rate, 4),
            "native_coverage": dict(self.coverage),
        }
        if self.output_path:
            out["native_output"] = self.output_path
        if samples:
            out["native_residual_samples"] = samples
        if self.scrub_error_samples:
            out["native_scrub_error_samples"] = list(self.scrub_error_samples[:5])
        if self.residual_image_risk:
            out["native_image_risk"] = True
        return out
