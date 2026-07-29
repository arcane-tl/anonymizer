"""Document-level English / Finnish language detection."""

from __future__ import annotations

import re
from functools import lru_cache

from anonymizer.models import LanguageDecision

_ALPHA_TOKEN = re.compile(r"[^\W\d_]+", re.UNICODE)

# Prefer dual-pass when unsure
MIN_ALPHA_TOKENS = 40
# Max characters sampled for detection
MAX_SAMPLE_CHARS = 12_000
CHUNK = 4_000


def sample_text_for_detection(text: str, max_chars: int = MAX_SAMPLE_CHARS) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    chunk = max_chars // 3
    mid_start = max(0, (len(text) - chunk) // 2)
    parts = [
        text[:chunk],
        text[mid_start : mid_start + chunk],
        text[-chunk:],
    ]
    return "\n".join(parts)


def count_alpha_tokens(text: str) -> int:
    return len(_ALPHA_TOKEN.findall(text))


@lru_cache(maxsize=1)
def _lingua_detector():
    from lingua import Language, LanguageDetectorBuilder

    return (
        LanguageDetectorBuilder.from_languages(Language.ENGLISH, Language.FINNISH)
        .with_preloaded_language_models()
        .build()
    )


def _detect_with_lingua(sample: str) -> tuple[list[str], str]:
    """Return (detected language codes, reason)."""
    from lingua import Language, ConfidenceValue

    detector = _lingua_detector()
    confidences: list[ConfidenceValue] = detector.compute_language_confidence_values(sample)
    if not confidences:
        return [], "no_confidence"

    # Map to en/fi scores
    scores: dict[str, float] = {"en": 0.0, "fi": 0.0}
    for cv in confidences:
        if cv.language == Language.ENGLISH:
            scores["en"] = cv.value
        elif cv.language == Language.FINNISH:
            scores["fi"] = cv.value

    primary = max(scores, key=scores.get)
    secondary = "fi" if primary == "en" else "en"
    p, s = scores[primary], scores[secondary]

    # Strong single language
    if p >= 0.75 and (p - s) >= 0.20:
        return [primary], f"confident_{primary}={p:.2f}"

    # Both meaningfully present → mixed
    if p >= 0.35 and s >= 0.25:
        return ["en", "fi"], f"mixed en={scores['en']:.2f} fi={scores['fi']:.2f}"

    # Weak primary still better than nothing
    if p >= 0.55:
        return [primary], f"weak_{primary}={p:.2f}"

    return ["en", "fi"], f"low_confidence en={scores['en']:.2f} fi={scores['fi']:.2f}"


def detect_languages(text: str) -> tuple[list[str], str]:
    """Detect document languages as en / fi list and a reason string."""
    sample = sample_text_for_detection(text)
    if not sample or not sample.strip():
        return ["en", "fi"], "empty_text"

    if count_alpha_tokens(sample) < MIN_ALPHA_TOKENS:
        return ["en", "fi"], "short_text"

    try:
        return _detect_with_lingua(sample)
    except Exception as exc:  # pragma: no cover - defensive
        return ["en", "fi"], f"detector_error:{exc}"


def resolve_language(lang_flag: str, text: str) -> LanguageDecision:
    """
    Resolve --lang flag into NLP passes.

    lang_flag: auto | en | fi | en,fi | fi,en
    """
    raw = (lang_flag or "auto").strip().lower().replace(" ", "")
    if raw in ("auto", ""):
        detected, reason = detect_languages(text)
        if set(detected) >= {"en", "fi"} or len(detected) > 1:
            passes = ["en", "fi"]
        elif detected == ["fi"]:
            passes = ["fi"]
        else:
            passes = ["en"]
        return LanguageDecision(
            mode="auto",
            detected=detected if detected else ["en", "fi"],
            nlp_passes=passes,
            reason=reason,
        )

    parts = [p for p in raw.split(",") if p]
    allowed = {"en", "fi"}
    forced = [p for p in parts if p in allowed]
    # preserve order en then fi if both
    ordered: list[str] = []
    if "en" in forced:
        ordered.append("en")
    if "fi" in forced:
        ordered.append("fi")
    if not ordered:
        raise ValueError(
            f"Invalid --lang value {lang_flag!r}. Use auto, en, fi, or en,fi."
        )
    return LanguageDecision(
        mode="forced",
        detected=list(ordered),
        nlp_passes=list(ordered),
        reason="user_override",
    )


def tesseract_lang_string(lang_flag: str, nlp_passes: list[str] | None = None) -> str:
    """Tesseract language codes for OCR."""
    raw = (lang_flag or "auto").strip().lower().replace(" ", "")
    if raw in ("auto", ""):
        return "eng+fin"
    if raw == "en":
        return "eng"
    if raw == "fi":
        return "fin"
    return "eng+fin"
