"""Anonymization engine and helpers."""

from __future__ import annotations

__all__ = ["DocumentAnonymizer"]


def __getattr__(name: str):
    if name == "DocumentAnonymizer":
        from anonymizer.anonymize.engine import DocumentAnonymizer

        return DocumentAnonymizer
    raise AttributeError(name)
