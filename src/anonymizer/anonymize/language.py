"""Document-level language detection (EN / FI / SV)."""

from __future__ import annotations

import re
from functools import lru_cache

from anonymizer.anonymize.config import SUPPORTED_LANGS
from anonymizer.models import LanguageDecision

_ALPHA_TOKEN = re.compile(r"[^\W\d_]+", re.UNICODE)

# Prefer dual-pass when unsure
MIN_ALPHA_TOKENS = 40
# Max characters sampled for detection
MAX_SAMPLE_CHARS = 12_000
CHUNK = 4_000

# Lingua language enum mapping
_LINGUA_CODES = ("en", "fi", "sv")


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
        LanguageDetectorBuilder.from_languages(
            Language.ENGLISH, Language.FINNISH, Language.SWEDISH
        )
        .with_preloaded_language_models()
        .build()
    )


def _detect_with_lingua(sample: str) -> tuple[list[str], str]:
    """Return (detected language codes, reason)."""
    from lingua import Language, ConfidenceValue

    detector = _lingua_detector()
    confidences: list[ConfidenceValue] = detector.compute_language_confidence_values(
        sample
    )
    if not confidences:
        return [], "no_confidence"

    lang_map = {
        Language.ENGLISH: "en",
        Language.FINNISH: "fi",
        Language.SWEDISH: "sv",
    }
    scores: dict[str, float] = {c: 0.0 for c in _LINGUA_CODES}
    for cv in confidences:
        code = lang_map.get(cv.language)
        if code:
            scores[code] = cv.value

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    primary, p = ranked[0]
    second, s = ranked[1]
    third, t = ranked[2]

    # Strong single language
    if p >= 0.75 and (p - s) >= 0.20:
        return [primary], f"confident_{primary}={p:.2f}"

    # Two meaningfully present
    present = [code for code, sc in ranked if sc >= 0.25]
    if p >= 0.35 and s >= 0.25:
        # Keep top 2 (or 3 if all present)
        if t >= 0.22 and len(present) >= 3:
            codes = [c for c, _ in ranked if scores[c] >= 0.22]
            return codes, (
                f"mixed en={scores['en']:.2f} fi={scores['fi']:.2f} "
                f"sv={scores['sv']:.2f}"
            )
        pair = [primary, second]
        # stable order: en, fi, sv
        order = [c for c in ("en", "fi", "sv") if c in pair]
        return order, f"mixed {' '.join(f'{c}={scores[c]:.2f}' for c in order)}"

    # Weak primary still better than nothing
    if p >= 0.55:
        return [primary], f"weak_{primary}={p:.2f}"

    return (
        ["en", "fi"],
        f"low_confidence en={scores['en']:.2f} fi={scores['fi']:.2f} "
        f"sv={scores['sv']:.2f}",
    )


def detect_languages(text: str) -> tuple[list[str], str]:
    """Detect document languages as en / fi / sv list and a reason string."""
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

    lang_flag: auto | en | fi | sv | en,fi | fi,sv | en,fi,sv | …
    """
    raw = (lang_flag or "auto").strip().lower().replace(" ", "")
    allowed = set(SUPPORTED_LANGS)

    if raw in ("auto", ""):
        detected, reason = detect_languages(text)
        if not detected:
            passes = ["en", "fi"]
            detected = ["en", "fi"]
        elif len(detected) > 1:
            # stable order
            passes = [c for c in SUPPORTED_LANGS if c in detected]
        else:
            passes = list(detected)
        return LanguageDecision(
            mode="auto",
            detected=detected,
            nlp_passes=passes,
            reason=reason,
        )

    parts = [p for p in raw.split(",") if p]
    forced = [p for p in parts if p in allowed]
    # preserve user order but unique
    ordered: list[str] = []
    for p in forced:
        if p not in ordered:
            ordered.append(p)
    if not ordered:
        raise ValueError(
            f"Invalid --lang value {lang_flag!r}. Use auto, or one/more of: "
            f"{', '.join(SUPPORTED_LANGS)} (e.g. en, fi, sv, en,fi)."
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
    tess = {"en": "eng", "fi": "fin", "sv": "swe"}
    if raw in ("auto", ""):
        if nlp_passes:
            parts = [tess[p] for p in nlp_passes if p in tess]
            if parts:
                return "+".join(parts)
        return "eng+fin"
    if raw in tess:
        return tess[raw]
    parts = [tess[p] for p in raw.split(",") if p in tess]
    if parts:
        # unique preserve order
        seen: list[str] = []
        for p in parts:
            if p not in seen:
                seen.append(p)
        return "+".join(seen)
    return "eng+fin"
