"""Automatic local AI check (Apple Foundation Models) for redaction quality.

When Apple on-device Foundation Models are available, runs a second pass that:
  - audits existing findings (keep / drop / unsure)
  - proposes missed PII surfaces (exact substring rematch required)

Silently skips when FM is unavailable. Ollama/xAI are **not** used here
(those remain opt-in via ``--llm``).
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from anonymizer.anonymize.review import (
    ReviewSession,
    entity_type_from_placeholder,
    resolve_surface_in_blocks,
)

logger = logging.getLogger(__name__)

Decision = Literal["keep", "drop", "unsure"]

# Types safe to auto-drop when Review is off (high false-positive classes).
AUTO_DROP_TYPES = frozenset({"ORG", "LOCATION", "CITY"})

# Types the miss-scan may propose (aligned with LLM extract ask-set).
MISS_TYPES = frozenset(
    {
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
        "FI_HETU",
        "FI_BUSINESS_ID",
    }
)

HELPER_NAMES = ("anonymizer-fm-check", "anonymizer-fm-check.exe")


@dataclass
class FindingVerdict:
    placeholder: str
    decision: Decision
    reason: str = ""
    confidence: str = "medium"  # low | medium | high


@dataclass
class MissProposal:
    entity_type: str
    text: str
    reason: str = ""
    confidence: str = "medium"


@dataclass
class AiCheckResult:
    ran: bool
    provider: str = ""  # apple | skipped | error
    skip_reason: str = ""
    verdicts: list[FindingVerdict] = field(default_factory=list)
    misses: list[MissProposal] = field(default_factory=list)
    latency_s: float = 0.0
    raw_error: str = ""

    @property
    def drop_placeholders(self) -> list[str]:
        return [v.placeholder for v in self.verdicts if v.decision == "drop"]

    @property
    def high_confidence_drops(self) -> list[str]:
        return [
            v.placeholder
            for v in self.verdicts
            if v.decision == "drop" and (v.confidence or "").lower() == "high"
        ]

    @property
    def high_confidence_misses(self) -> list[MissProposal]:
        return [m for m in self.misses if (m.confidence or "").lower() == "high"]


def _context_around(text: str, surface: str, radius: int = 70) -> str:
    if not surface:
        return ""
    idx = text.find(surface)
    if idx < 0:
        idx = text.casefold().find(surface.casefold())
    if idx < 0:
        return surface[:120]
    a = max(0, idx - radius)
    b = min(len(text), idx + len(surface) + radius)
    snippet = text[a:b].replace("\n", " ")
    return snippet


def build_ai_check_prompt(
    *,
    findings: list[dict[str, str]],
    miss_chunks: list[str],
    entity_types: list[str],
) -> str:
    types = ", ".join(entity_types)
    payload = {
        "findings": findings,
        "miss_scan_chunks": miss_chunks,
        "allowed_miss_types": entity_types,
    }
    return (
        "You are a privacy redaction assistant for EN/FI documents.\n"
        "Return ONLY a JSON object (no markdown fences) with this shape:\n"
        "{\n"
        '  "verdicts": [{"id": "<placeholder>", "decision": "keep|drop|unsure", '
        '"confidence": "high|medium|low", "reason": "<short>"}],\n'
        '  "misses": [{"type": "<ENTITY_TYPE>", "text": "<exact substring>", '
        '"confidence": "high|medium|low", "reason": "<short>"}]\n'
        "}\n"
        "Rules:\n"
        "- For each finding id, decide keep (real PII), drop (false positive / "
        "boilerplate / OCR junk), or unsure.\n"
        "- Prefer drop for contract boilerplate ORG/LOCATION that are not real "
        "parties (e.g. legal phrases), not for emails/phones/IDs.\n"
        "- Misses: only exact substrings that appear in miss_scan_chunks; "
        f"allowed types: {types}. Do not invent text.\n"
        "- If nothing to add, misses may be [].\n"
        "- Keep reasons under 12 words.\n"
        "Input:\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )


def parse_ai_check_response(
    raw: str,
    *,
    valid_placeholders: set[str],
) -> tuple[list[FindingVerdict], list[MissProposal]]:
    raw = (raw or "").strip()
    if raw.startswith("```"):
        import re

        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        import re

        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            return [], []
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return [], []
    if not isinstance(data, dict):
        return [], []

    verdicts: list[FindingVerdict] = []
    for item in data.get("verdicts") or []:
        if not isinstance(item, dict):
            continue
        ph = str(item.get("id") or item.get("placeholder") or "").strip()
        if ph and not ph.startswith("["):
            ph = f"[{ph.strip('[]')}]"
        if ph not in valid_placeholders:
            continue
        dec = str(item.get("decision") or "unsure").lower().strip()
        if dec not in {"keep", "drop", "unsure"}:
            dec = "unsure"
        conf = str(item.get("confidence") or "medium").lower().strip()
        if conf not in {"high", "medium", "low"}:
            conf = "medium"
        verdicts.append(
            FindingVerdict(
                placeholder=ph,
                decision=dec,  # type: ignore[arg-type]
                reason=str(item.get("reason") or "")[:120],
                confidence=conf,
            )
        )

    misses: list[MissProposal] = []
    for item in data.get("misses") or []:
        if not isinstance(item, dict):
            continue
        et = str(item.get("type") or item.get("entity_type") or "").upper().strip()
        text = str(item.get("text") or item.get("value") or "").strip()
        if len(text) < 2 or et not in MISS_TYPES:
            continue
        conf = str(item.get("confidence") or "medium").lower().strip()
        if conf not in {"high", "medium", "low"}:
            conf = "medium"
        misses.append(
            MissProposal(
                entity_type=et,
                text=text,
                reason=str(item.get("reason") or "")[:120],
                confidence=conf,
            )
        )
    return verdicts, misses


def find_fm_helper() -> Path | None:
    """Locate ``anonymizer-fm-check`` beside the app, on PATH, or next to package."""
    env = os.environ.get("ANONYMIZER_FM_CHECK")
    if env:
        p = Path(env)
        if p.is_file() and os.access(p, os.X_OK):
            return p

    for name in HELPER_NAMES:
        which = shutil.which(name)
        if which:
            return Path(which)

    # Bundled next to anonymizer package (dev) or Mac app Resources via cwd tricks
    here = Path(__file__).resolve()
    candidates = [
        here.parents[3] / "packaging" / "macos" / "fm-check" / "anonymizer-fm-check",
        here.parents[2] / "bin" / "anonymizer-fm-check",
        Path("/Applications/Anonymizer.app/Contents/MacOS/anonymizer-fm-check"),
        Path("/Applications/Anonymizer.app/Contents/Resources/anonymizer-fm-check"),
    ]
    for c in candidates:
        if c.is_file() and os.access(c, os.X_OK):
            return c
    return None


def apple_fm_available() -> tuple[bool, str]:
    """Probe whether Apple on-device FM can run. Returns (ok, reason)."""
    helper = find_fm_helper()
    if helper is not None:
        try:
            proc = subprocess.run(
                [str(helper), "--available"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            out = (proc.stdout or "").strip()
            if proc.returncode == 0 and out.upper().startswith("AVAILABLE"):
                return True, "helper"
            reason = (proc.stderr or out or f"exit {proc.returncode}").strip()
            # Fall through to Python bindings
            helper_reason = reason
        except (OSError, subprocess.TimeoutExpired) as exc:
            helper_reason = str(exc)
    else:
        helper_reason = "helper not found"

    try:
        from applefoundationmodels import apple_intelligence_available

        if apple_intelligence_available():
            return True, "python-bindings"
    except Exception as exc:  # noqa: BLE001
        return False, f"{helper_reason}; python: {exc}"

    return False, helper_reason


def _call_apple_python(prompt: str) -> str:
    from applefoundationmodels import Session

    with Session(
        instructions=(
            "You output JSON only for privacy redaction review. "
            "No markdown fences. No commentary."
        )
    ) as session:
        resp = session.generate(prompt)
    return getattr(resp, "content", None) or str(resp)


def _call_apple_helper(prompt: str, helper: Path) -> str:
    payload = json.dumps({"prompt": prompt}, ensure_ascii=False).encode("utf-8")
    proc = subprocess.run(
        [str(helper)],
        input=payload,
        capture_output=True,
        timeout=180,
        check=False,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or b"").decode("utf-8", errors="replace")
        raise RuntimeError(f"fm-check failed ({proc.returncode}): {err[:400]}")
    return proc.stdout.decode("utf-8", errors="replace")


def _chunk_text(text: str, *, max_chars: int = 6000, max_chunks: int = 3) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    step = max_chars - 200
    i = 0
    while i < len(text) and len(chunks) < max_chunks:
        chunks.append(text[i : i + max_chars])
        i += step
    return chunks


def run_ai_check(
    *,
    original_blocks: list[str],
    mapping: dict[str, str],
    entity_types: list[str] | None = None,
    enabled: bool = True,
) -> AiCheckResult:
    """Run Apple FM AI check, or skip silently when unavailable / disabled."""
    if not enabled:
        return AiCheckResult(ran=False, provider="skipped", skip_reason="disabled")
    if not mapping:
        return AiCheckResult(ran=False, provider="skipped", skip_reason="no findings")

    ok, how = apple_fm_available()
    if not ok:
        return AiCheckResult(ran=False, provider="skipped", skip_reason=how)

    full = "\n\n".join(original_blocks)
    findings_payload: list[dict[str, str]] = []
    for ph, original in mapping.items():
        findings_payload.append(
            {
                "id": ph,
                "type": entity_type_from_placeholder(ph),
                "text": original,
                "context": _context_around(full, original),
            }
        )

    ask_types = [t for t in (entity_types or sorted(MISS_TYPES)) if t in MISS_TYPES]
    if not ask_types:
        ask_types = sorted(MISS_TYPES)

    prompt = build_ai_check_prompt(
        findings=findings_payload,
        miss_chunks=_chunk_text(full),
        entity_types=ask_types,
    )

    t0 = time.perf_counter()
    try:
        helper = find_fm_helper()
        if how == "helper" and helper is not None:
            raw = _call_apple_helper(prompt, helper)
            provider = "apple"
        else:
            raw = _call_apple_python(prompt)
            provider = "apple"
    except Exception as exc:  # noqa: BLE001
        logger.warning("AI check failed: %s", exc)
        return AiCheckResult(
            ran=False,
            provider="error",
            skip_reason=str(exc),
            raw_error=str(exc),
            latency_s=time.perf_counter() - t0,
        )

    verdicts, misses = parse_ai_check_response(
        raw, valid_placeholders=set(mapping.keys())
    )
    # Rematch miss texts into blocks; drop non-matches
    rematched: list[MissProposal] = []
    for m in misses:
        surface = resolve_surface_in_blocks(original_blocks, m.text)
        if not surface:
            continue
        rematched.append(
            MissProposal(
                entity_type=m.entity_type,
                text=surface,
                reason=m.reason,
                confidence=m.confidence,
            )
        )

    return AiCheckResult(
        ran=True,
        provider=provider,
        verdicts=verdicts,
        misses=rematched,
        latency_s=time.perf_counter() - t0,
    )


def apply_ai_check_to_session(
    session: ReviewSession,
    result: AiCheckResult,
    *,
    auto_apply: bool,
) -> dict[str, int]:
    """Merge AI check into a ReviewSession.

    When ``auto_apply`` is False (Review UI): pre-uncheck all drops; add
    high-confidence misses as enabled user findings (UI can still toggle).

    When ``auto_apply`` is True (Review off): only high-confidence drops for
    ``AUTO_DROP_TYPES``, and high-confidence rematched misses.
    """
    stats = {"drops": 0, "misses": 0, "kept": 0, "unsure": 0}
    if not result.ran:
        return stats

    drop_set: set[str] = set()
    for v in result.verdicts:
        if v.decision == "keep":
            stats["kept"] += 1
            continue
        if v.decision == "unsure":
            stats["unsure"] += 1
            continue
        # drop
        et = entity_type_from_placeholder(v.placeholder)
        if auto_apply:
            if v.confidence != "high":
                stats["unsure"] += 1
                continue
            if et not in AUTO_DROP_TYPES:
                # Do not auto-clear emails/phones/etc.
                stats["unsure"] += 1
                continue
        drop_set.add(v.placeholder)

    for ph in drop_set:
        if session.set_enabled(ph, False):
            stats["drops"] += 1

    miss_list = result.high_confidence_misses if auto_apply else [
        m for m in result.misses if m.confidence in {"high", "medium"}
    ]
    for m in miss_list:
        try:
            session.add_redaction(m.text, m.entity_type)
            stats["misses"] += 1
        except ValueError:
            continue
    return stats
