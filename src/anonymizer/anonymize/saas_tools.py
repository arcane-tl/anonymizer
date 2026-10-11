"""SaaS / vendor label stems — not people (CV tool stacks)."""

from __future__ import annotations

_SAAS_TOOL_STEMS = frozenset(
    {
        "teams",
        "team",
        "salesforce",
        "sharepoint",
        "jira",
        "confluence",
        "microsoft",
        "powerbi",
        "excel",
        "outlook",
        "powerpoint",
        "solita",
        "slack",
        "github",
        "gitlab",
        "azure",
        "aws",
        "docker",
        "kubernetes",
        "jenkins",
        "figma",
        "miro",
        "zoom",
        "skype",
        "whatsapp",
        "notion",
        "trello",
        "asana",
        "zendesk",
        "hubspot",
        "databricks",
        "snowflake",
        "servicenow",
        "tableau",
        "retro",
        "retainer",
        "secman",
    }
)


def _strip_fi_case_tail(token: str) -> str:
    """Best-effort stem for FI inflected tool tokens (Teamsissa, Solitan)."""
    t = (token or "").casefold().strip(".,;:'\"()")
    if not t:
        return t
    for suf in (
        "ssaan",
        "ssään",
        "ssa",
        "ssä",
        "staan",
        "stään",
        "sta",
        "stä",
        "lta",
        "ltä",
        "lle",
        "lla",
        "llä",
        "ksi",
        "ina",
        "inä",
        "ien",
        "iden",
        "ihin",
        "issa",
        "issä",
        "aan",
        "ään",
        "an",
        "än",
        "en",
        "in",
        "un",
        "yn",
        "on",
        "ön",
        "n",
        "a",
        "ä",
    ):
        if len(t) > len(suf) + 3 and t.endswith(suf):
            return t[: -len(suf)]
    return t


def is_saas_tool_stem(token: str) -> bool:
    """True if *token* is a known SaaS/vendor stem (optionally FI-inflected)."""
    raw = (token or "").casefold().strip(".,;:'\"()")
    if not raw:
        return False
    if raw in _SAAS_TOOL_STEMS or raw.replace("-", "") in _SAAS_TOOL_STEMS:
        return True
    head = raw.split("-", 1)[0]
    if head in _SAAS_TOOL_STEMS:
        return True
    stem = _strip_fi_case_tail(raw)
    if stem in _SAAS_TOOL_STEMS or stem.replace("-", "") in _SAAS_TOOL_STEMS:
        return True
    if stem.split("-", 1)[0] in _SAAS_TOOL_STEMS:
        return True
    return False
