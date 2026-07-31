"""Generic multi-word capitalised name heuristic (brands / orgs without legal form).

No per-company or place-name lists. Filtering uses:
  - orthography (Title Case / ALL CAPS sequences)
  - spaCy stop-word and POS tags when a model is available
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from typing import List, Optional

from presidio_analyzer import AnalysisExplanation, EntityRecognizer, RecognizerResult
from presidio_analyzer.nlp_engine import NlpArtifacts

logger = logging.getLogger(__name__)

_WORD = r"[A-ZÅÄÖ][A-Za-zÅÄÖåäö0-9&'’\-]*"
_HSPACE = r"[ \t]+"

_MULTI = re.compile(
    rf"(?<![A-Za-zÅÄÖåäö0-9])"
    rf"("
    rf"{_WORD}"
    rf"(?:{_HSPACE}{_WORD}){{1,3}}"
    rf")"
    rf"(?![A-Za-zÅÄÖåäö0-9])",
    re.UNICODE,
)

# Letter-style closings detected by shape (2–3 title words), not a company catalog
_CLOSING_SHAPE = re.compile(
    r"^(?i:best|kind|warm)\s+(?i:regards)$|"
    r"^(?i:yours)\s+(?i:sincerely|faithfully)$"
)


@lru_cache(maxsize=2)
def _nlp_for_heuristic():
    """Best-effort spaCy pipeline for POS/stop; may be None (cached)."""
    try:
        import spacy
        from anonymizer.anonymize.config import SPACY_FALLBACKS, SPACY_MODELS

        for lang in ("en", "fi"):
            for name in [SPACY_MODELS[lang], *SPACY_FALLBACKS.get(lang, [])]:
                try:
                    return spacy.load(name)
                except OSError:
                    continue
    except Exception:
        pass
    return None


def _strip_leading_by_pos(text: str, start: int, end: int, nlp) -> tuple[int, int, str]:
    """Drop leading DET/ADP/VERB/PART/SCONJ/CCONJ/ADV/PRON from a span using POS."""
    surface = text[start:end]
    if nlp is None:
        return start, end, surface
    # Align via char offsets on a window
    doc = nlp(text[start:end])
    cut = 0
    for tok in doc:
        if tok.is_space:
            cut = tok.idx + len(tok)
            continue
        # Keep proper nouns / nouns / adjectives that start names
        if tok.pos_ in {"DET", "ADP", "VERB", "AUX", "PART", "SCONJ", "CCONJ", "ADV", "PRON", "INTJ"}:
            cut = tok.idx + len(tok.text)
            # include following spaces
            while cut < len(surface) and surface[cut].isspace():
                cut += 1
            continue
        if tok.is_stop and tok.pos_ not in {"PROPN", "NOUN", "ADJ"}:
            cut = tok.idx + len(tok.text)
            while cut < len(surface) and surface[cut].isspace():
                cut += 1
            continue
        break
    if cut >= len(surface):
        return start, end, surface
    new_start = start + cut
    new_surface = text[new_start:end]
    return new_start, end, new_surface


# Contract / wiki boilerplate lemmas (not a company catalog)
_LEGALISH = frozenset(
    {
        "agreement",
        "publishing",
        "rights",
        "delivery",
        "date",
        "initial",
        "author",
        "changes",
        "warranties",
        "indemnity",
        "grant",
        "section",
        "article",
        "schedule",
        "appendix",
        "promotion",
        "distribution",
        "copyright",
        "manuscript",
        "work",
        "new",
        "letter",
        "intent",
        "memorandum",
        "understanding",
        "contract",
        "law",
        "case",
        "cases",
        "summaries",
        "summary",
        "basics",
        "convention",
        "sale",
        "international",
        "european",
        "united",
        "nations",
        "nation",
        "archive",
        "internet",
        "caselist",
        "list",
        "principles",
        "school",
        "university",
        "college",
        "institute",
        "maine",
        "wikipedia",
        "wiki",
    }
)

# Form / field orthography mistaken for brands ("Payment IBAN")
_FORMISH = frozenset(
    {
        "payment",
        "iban",
        "email",
        "phone",
        "address",
        "website",
        "contact",
        "account",
        "invoice",
        "reference",
        "number",
        "code",
        "field",
        "label",
        "source",
        "url",
        "http",
        "https",
        "name",
        "legal",
        "office",
        "registered",
        "delivery",
        "vehicle",
        "network",
        "endpoint",
        "person",
        "business",
        "secondary",
        "site",
        "also",
        "trading",
        "customer",
        "supplier",
        "annex",
        "synthetic",
    }
)

_DOC_TITLE_TAILS = frozenset(
    {
        "agreement",
        "contract",
        "policy",
        "addendum",
        "amendment",
        "schedule",
        "appendix",
        "annex",
        "caselist",
        "summaries",
    }
)

_STOP_JOINERS = frozenset({"of", "and", "the", "for", "to", "a", "an", "on", "in", "uk", "fi", "en"})

# Leading role / label words before a brand (surface match)
_ROLE_PREFIX = frozenset(
    {
        "client",
        "customer",
        "supplier",
        "provider",
        "vendor",
        "seller",
        "buyer",
        "contractor",
        "partner",
        "toimittaja",
        "tilaaja",
        "asiakas",
        "myyjä",
        "ostaja",
        "brand",
        "brands",
        "brändi",
        "brändiä",
    }
)


def _valid_multi(phrase: str, nlp=None) -> bool:
    phrase = re.sub(r"[ \t]+", " ", phrase.strip())
    if len(phrase) < 4 or "\n" in phrase or "\r" in phrase:
        return False
    # Broken extracts / wiki noise
    if any(ch in phrase for ch in "«»<>{}[]|–—"):
        return False
    if _CLOSING_SHAPE.match(phrase):
        return False
    tokens = phrase.split()
    if len(tokens) < 2:
        return False
    if any(len(t.strip(".,;:'\"")) <= 1 for t in tokens):
        return False
    # License / version tags ("CC BY-SA", "CC BY")
    if re.fullmatch(r"(?i)CC(?:\s+BY(?:-[A-Z]+)*)+", phrase.strip()):
        return False
    # Tiny ALL-CAPS acronym pairs (PDF, MOU, LOI)
    if phrase.isupper() and all(len(t) <= 3 for t in tokens):
        return False
    if phrase.isupper() and len(tokens) == 1 and len(tokens[0]) <= 4:
        return False
    # Multi-word ALL-CAPS section headers (not brands like SILVER PINE)
    if len(tokens) >= 2:
        letters = [c for c in phrase if c.isalpha()]
        if letters and sum(1 for c in letters if c.isupper()) / len(letters) >= 0.9:
            if not re.search(
                r"(?i)\b(oyj|oy|ab|ltd|limited|inc|corp|llc|gmbh|plc)\b", phrase
            ):
                joiners = {"ja", "and", "of", "tai", "se", "the", "for", "to"}
                low_toks = [t.casefold().strip(".,;:-") for t in tokens]
                # 3+ tokens or contains joiners / legalish → section title
                if len(tokens) >= 3 or any(t in joiners for t in low_toks):
                    return False
                if any(t in _LEGALISH for t in low_toks):
                    return False
    # Legal / insurance collocations
    if phrase.casefold() in {
        "force majeure",
        "green card",
        "green cardiin",
        "letter of intent",
        "memorandum of understanding",
    }:
        return False
    norm_tokens = [t.strip(".,;:'\"") for t in tokens]
    norm_lower = [t.casefold() for t in norm_tokens]

    # Pure boilerplate / form labels ("Payment IBAN", "European Contract Law")
    if all(t in _LEGALISH or t in _FORMISH or t in _STOP_JOINERS for t in norm_lower):
        return False
    # Document titles ending in Agreement/Contract/…
    if norm_lower and norm_lower[-1] in _DOC_TITLE_TAILS:
        return False
    # "Letter of Intent", "Memorandum of Understanding"
    if re.search(r"(?i)\bof\b", phrase) and all(
        t in _LEGALISH or t in _STOP_JOINERS for t in norm_lower
    ):
        return False
    if nlp is not None:
        # Lowercase analysis reduces false PROPN on ALL-CAPS headers
        doc_low = nlp(phrase.casefold())
        content = [
            t
            for t in doc_low
            if not t.is_space and not t.is_punct and not t.is_stop
        ]
        if len(content) < 2:
            return False
        # Pure common-noun phrases ("publishing agreement", "force majeure").
        # Keep ALL-CAPS multi-word brands ("COPPER LAKE") unless legalish.
        if all(t.pos_ == "NOUN" and not t.is_oov for t in content):
            if not phrase.isupper():
                return False
            if any(t.lemma_.casefold() in _LEGALISH for t in content):
                return False
        # Mostly NOUN/ADJ/VERB closed-class legal headers
        if all(t.pos_ in {"NOUN", "ADJ", "VERB", "ADP"} and not t.is_oov for t in content):
            # Allow if any token is OOV-like brand, else reject boilerplate
            if not any(t.is_oov or t.pos_ == "PROPN" for t in content):
                if all(t.pos_ == "NOUN" for t in content) and not phrase.isupper():
                    return False
                if any(t.lemma_.casefold() in _LEGALISH for t in content):
                    return False
                if sum(1 for t in content if t.pos_ == "ADJ") >= 1 and all(
                    t.pos_ in {"NOUN", "ADJ"} for t in content
                ):
                    # ADJ+NOUN can be brand (Silver Pine) or boilerplate (Initial Delivery)
                    if any(t.lemma_.casefold() in _LEGALISH for t in content):
                        return False
        # Geographic names → leave to LOCATION/NER, not brand ORG.
        # Skip this for ALL-CAPS (COPPER LAKE etc. often collide with GPE).
        if not phrase.isupper():
            titled = " ".join(w.capitalize() for w in phrase.split())
            doc_geo = nlp(titled)
            if any(e.label_ in {"GPE", "LOC", "FAC"} for e in doc_geo.ents):
                return False
            # "England and Wales" style geo compounds
            if any(e.label_ == "GPE" for e in nlp(phrase).ents):
                return False
        # Prefer PERSON NER for person-shaped spans (leave brand off)
        if any(e.label_ in {"PERSON", "PER"} for e in nlp(phrase).ents):
            return False
    return True


def _strip_role_prefix(text: str, start: int, end: int) -> tuple[int, int, str]:
    """Drop leading Client/Partner/Toimittaja before a brand (≥2 tokens remain)."""
    surface = text[start:end]
    parts = surface.split()
    # role + 2-token brand → need len >= 3 before strip
    while len(parts) >= 3 and parts[0].casefold() in _ROLE_PREFIX:
        m = re.match(rf"{re.escape(parts[0])}[ \t]+", surface)
        if not m:
            break
        start = start + m.end()
        surface = text[start:end]
        parts = surface.split()
    return start, end, surface


def find_brand_orgs(text: str) -> list[tuple[int, int, str]]:
    """Return (start, end, surface) for multi-word capitalised names."""
    nlp = _nlp_for_heuristic()
    hits: list[tuple[int, int, str]] = []
    seen: set[tuple[int, int]] = set()

    for m in _MULTI.finditer(text):
        start, end = m.start(1), m.end(1)
        start, end, phrase = _strip_leading_by_pos(text, start, end, nlp)
        start, end, phrase = _strip_role_prefix(text, start, end)
        phrase = phrase.strip()
        if not _valid_multi(phrase, nlp):
            continue
        # Re-align end to stripped phrase length
        end = start + len(phrase)
        if text[start:end] != phrase:
            # whitespace-normalized fallback
            window = text[m.start(1) : m.end(1)]
            idx = window.find(phrase.split()[0])
            if idx < 0:
                continue
            # find full phrase in original window approximately
            end = start + len(phrase)
            if text[start:end] != phrase:
                continue
        span = (start, end)
        if span in seen:
            continue
        seen.add(span)
        hits.append((start, end, phrase))

    hits.sort(key=lambda h: (h[0], -(h[1] - h[0])))
    merged: list[tuple[int, int, str]] = []
    for start, end, value in hits:
        if merged and start < merged[-1][1]:
            if end - start > merged[-1][1] - merged[-1][0]:
                merged[-1] = (start, end, value)
            continue
        merged.append((start, end, value))
    return merged


class BrandOrgRecognizer(EntityRecognizer):
    """Heuristic ORG detector: capitalised multi-word sequences + spaCy filters."""

    def __init__(self) -> None:
        super().__init__(
            supported_entities=["ORG"],
            supported_language="en",
            name="BrandOrgRecognizer",
        )

    def load(self) -> None:
        return

    def analyze(
        self,
        text: str,
        entities: List[str],
        nlp_artifacts: NlpArtifacts = None,  # noqa: ANN001
        regex_flags: Optional[int] = None,  # noqa: ARG002
    ) -> List[RecognizerResult]:
        if entities and "ORG" not in entities:
            return []
        results: list[RecognizerResult] = []
        for start, end, value in find_brand_orgs(text):
            score = 0.78 if value.isupper() else 0.72
            results.append(
                RecognizerResult(
                    entity_type="ORG",
                    start=start,
                    end=end,
                    score=score,
                    analysis_explanation=AnalysisExplanation(
                        recognizer=self.name,
                        original_score=score,
                        pattern_name="multi_capitalized_heuristic",
                        pattern="orthography+POS",
                        validation_result=True,
                    ),
                )
            )
        return results
