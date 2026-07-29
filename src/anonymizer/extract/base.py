"""Document extraction protocol."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from anonymizer.models import ExtractedDoc


class Extractor(Protocol):
    def extract(self, path: Path, **kwargs) -> ExtractedDoc:  # noqa: ANN003
        ...
