"""Stats from native (PDF/DOCX) redaction passes."""

from __future__ import annotations

from dataclasses import dataclass, field


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
    # Post-redaction verification (re-extract text and look for cleartext)
    verified: bool = False
    residuals_found: int = 0
    residuals: list[str] = field(default_factory=list)
    # PDF scrub counters (0 for DOCX / when unused)
    annotations_scrubbed: int = 0
    widgets_scrubbed: int = 0
    # Image / letterhead inventory (PDF)
    images_total: int = 0
    image_pages: list[int] = field(default_factory=list)
    images_redacted: int = 0
    letterhead_redacted: bool = False

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
        """True when every surface was hit and post-verify found no residuals.

        Image residual risk is reported separately and does not flip ``is_clean``
        (logos need explicit ``--redact-letterhead-images`` / future cover).
        """
        if self.surfaces_missed > 0:
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
        if self.images_total:
            lines.append(
                f"images={self.images_total} redacted={self.images_redacted} "
                f"image_risk={self.residual_image_risk}"
            )
        if self.letterhead_redacted:
            lines.append("letterhead_images=redacted")
        return lines
