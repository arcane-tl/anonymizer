"""Stats from native (PDF/DOCX) redaction passes."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class NativeRedactStats:
    """How many cleartext surfaces were found and applied in the source file."""

    format: str  # pdf | docx
    surfaces_total: int = 0
    surfaces_found: int = 0
    surfaces_missed: int = 0
    hit_count: int = 0  # individual occurrences (rects / replacements)
    missed: list[str] = field(default_factory=list)
    output_path: str = ""

    @property
    def match_rate(self) -> float:
        if self.surfaces_total <= 0:
            return 1.0
        return self.surfaces_found / self.surfaces_total

    def summary(self) -> str:
        if self.surfaces_total == 0:
            return f"{self.format}: no surfaces to redact"
        return (
            f"{self.format}: redacted {self.surfaces_found}/{self.surfaces_total} "
            f"surfaces ({self.hit_count} hit(s))"
        )
