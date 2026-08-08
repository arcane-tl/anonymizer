"""Optional LLM-assisted entity recognition (versatile ORG/PERSON/LOCATION).

Off by default. When enabled, surfaces are matched back into the source text
(no hard-coded entity catalogs — the model proposes spans).

Providers:
  - ``xai`` — SpaceXAI / xAI OpenAI-compatible API (``XAI_API_KEY``)
  - ``ollama`` — local Ollama HTTP API (offline-friendly)

Privacy: ``xai`` sends document text to a remote API. Prefer ``ollama`` for
fully local processing.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from presidio_analyzer import RecognizerResult

logger = logging.getLogger(__name__)

_LLM_ENTITY_MAP = {
    "PERSON": "PERSON",
    "PER": "PERSON",
    "ORG": "ORG",
    "ORGANIZATION": "ORG",
    "COMPANY": "ORG",
    "BRAND": "ORG",
    "LOCATION": "LOCATION",
    "LOC": "LOCATION",
    "GPE": "LOCATION",
    "ADDRESS": "LOCATION",
    "STREET": "STREET",
    "CITY": "CITY",
    "POSTAL": "FI_POSTAL_CODE",
    "POSTAL_CODE": "FI_POSTAL_CODE",
    "FI_POSTAL_CODE": "FI_POSTAL_CODE",
    "EMAIL": "EMAIL_ADDRESS",
    "EMAIL_ADDRESS": "EMAIL_ADDRESS",
    "PHONE": "PHONE_NUMBER",
    "PHONE_NUMBER": "PHONE_NUMBER",
    "URL": "URL",
    "IBAN": "IBAN_CODE",
    "IBAN_CODE": "IBAN_CODE",
}


# Synthetic few-shot examples for *teaching format only* — not a search list.
# The tool never greps for these strings in user documents.
_TEACHING_EXAMPLES = """
Example (illustrative only — extract from the real document below, not these):
Input snippet: "Contact Ada Example at ada@example.test about ACME WIDGETS OY at Road 1, 00100 City."
Output:
[
  {"type": "PERSON", "text": "Ada Example"},
  {"type": "EMAIL_ADDRESS", "text": "ada@example.test"},
  {"type": "ORG", "text": "ACME WIDGETS OY"},
  {"type": "STREET", "text": "Road 1"},
  {"type": "FI_POSTAL_CODE", "text": "00100"},
  {"type": "CITY", "text": "City"}
]
"""


def _build_prompt(text: str, entity_types: list[str]) -> str:
    types = ", ".join(entity_types)
    return (
        "You extract privacy-sensitive entities from documents for redaction.\n"
        "Return ONLY a JSON array (no markdown). Each item:\n"
        '  {"type": "<ENTITY_TYPE>", "text": "<exact substring from the document>"}\n'
        f"Allowed types: {types}\n"
        "Rules:\n"
        "- Copy entity text EXACTLY as it appears in the Document section "
        "(preserve casing and punctuation).\n"
        "- Include people, organisations/brands/companies, streets, cities,\n"
        "  postcodes, residual locations, emails, phones, URLs when present.\n"
        "- Prefer STREET + FI_POSTAL_CODE + CITY components over one LOCATION blob\n"
        "  when the address is structured.\n"
        "- Do not invent entities. Do not copy entities from the teaching example "
        "unless they also appear in the Document.\n"
        "- If nothing found, return [].\n"
        f"{_TEACHING_EXAMPLES}\n"
        "Document:\n"
        f"{text[:12000]}"
    )


def _parse_json_array(raw: str) -> list[dict[str, Any]]:
    raw = raw.strip()
    # Strip fenced code if the model wraps JSON
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # salvage first [...] block
        m = re.search(r"\[[\s\S]*\]", raw)
        if not m:
            return []
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return []
    if not isinstance(data, list):
        return []
    return [x for x in data if isinstance(x, dict)]


def _surfaces_to_results(
    text: str,
    items: list[dict[str, Any]],
    wanted: set[str],
    score: float = 0.8,
) -> list[RecognizerResult]:
    results: list[RecognizerResult] = []
    for item in items:
        raw_type = str(item.get("type") or item.get("entity_type") or "").upper()
        mapped = _LLM_ENTITY_MAP.get(raw_type, raw_type)
        if wanted and mapped not in wanted:
            continue
        surface = str(item.get("text") or item.get("value") or "").strip()
        if len(surface) < 2:
            continue
        # Find all non-overlapping occurrences (case-sensitive first, then fold)
        start = 0
        while True:
            idx = text.find(surface, start)
            if idx < 0:
                # case-insensitive fallback for ALL CAPS variants
                idx = text.casefold().find(surface.casefold(), start)
                if idx < 0:
                    break
                surface_actual = text[idx : idx + len(surface)]
                # length may differ if casefold length differs (rare); use original surface length
                end = idx + len(surface_actual)
            else:
                end = idx + len(surface)
            results.append(
                RecognizerResult(
                    entity_type=mapped,
                    start=idx,
                    end=end,
                    score=score,
                )
            )
            start = end
    return results


def _call_xai(prompt: str, model: str) -> str:
    from openai import OpenAI

    api_key = os.environ.get("XAI_API_KEY") or os.environ.get("SPACEXAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "LLM provider 'xai' requires XAI_API_KEY in the environment."
        )
    client = OpenAI(api_key=api_key, base_url="https://api.x.ai/v1")
    # Prefer chat completions for broad compatibility
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "You extract entities as JSON only.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0,
    )
    return resp.choices[0].message.content or "[]"


def is_loopback_url(url: str) -> bool:
    """True if URL host is localhost / 127.0.0.1 / ::1 (offline-safe Ollama)."""
    from urllib.parse import urlparse

    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return host in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


def _call_ollama(prompt: str, model: str, base_url: str) -> str:
    import urllib.request

    payload = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0},
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    return str(body.get("response") or "[]")


def llm_entity_results(
    text: str,
    entity_types: list[str],
    *,
    provider: str = "ollama",
    model: str | None = None,
    ollama_url: str = "http://127.0.0.1:11434",
) -> list[RecognizerResult]:
    """Run optional LLM entity extraction and map surfaces back to offsets."""
    if not text.strip():
        return []
    provider = (provider or "ollama").lower().strip()
    if provider in {"off", "none", "false", "0"}:
        return []

    # Types the LLM is asked about (human-friendly + structural)
    ask_types = [
        t
        for t in entity_types
        if t
        in {
            "PERSON",
            "ORG",
            "LOCATION",
            "STREET",
            "CITY",
            "FI_POSTAL_CODE",
            "EMAIL_ADDRESS",
            "PHONE_NUMBER",
            "URL",
            "IBAN_CODE",
        }
    ]
    if not ask_types:
        ask_types = ["PERSON", "ORG", "STREET", "CITY", "LOCATION"]

    prompt = _build_prompt(text, ask_types)
    try:
        if provider == "xai":
            raw = _call_xai(prompt, model or os.environ.get("ANONYMIZER_LLM_MODEL", "grok-4.5"))
        elif provider == "ollama":
            raw = _call_ollama(
                prompt,
                model or os.environ.get("ANONYMIZER_LLM_MODEL", "llama3.2"),
                ollama_url,
            )
        else:
            raise RuntimeError(
                f"Unknown LLM provider {provider!r}. Use xai, ollama, or off."
            )
    except Exception as exc:
        logger.warning("LLM entity extraction failed: %s", exc)
        return []

    items = _parse_json_array(raw)
    return _surfaces_to_results(text, items, set(entity_types), score=0.82)
