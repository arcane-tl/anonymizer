"""Best-effort GitHub release check for the desktop options window.

The redaction CLI does not call this module. Failures stay silent: no stderr
and no UI log.

Environment (tests and local overrides only):

- ``ANONYMIZER_DISABLE_UPDATE_CHECK``: ``1``, ``true``, ``yes``, or ``on``
  skips the check. This wins over the override.
- ``ANONYMIZER_UPDATE_CHECK_OVERRIDE``: JSON object with ``tag_name`` and
  ``html_url``, the same shape as a GitHub release payload. When set and not
  blank, no network request is made.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass

RELEASES_LATEST_URL = "https://api.github.com/repos/arcane-tl/anonymizer/releases/latest"
TIMEOUT_SECONDS = 3.0
MAX_BODY_BYTES = 1_048_576
ENV_OVERRIDE = "ANONYMIZER_UPDATE_CHECK_OVERRIDE"
ENV_DISABLE = "ANONYMIZER_DISABLE_UPDATE_CHECK"

_STABLE_VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
_DISABLE_VALUES = frozenset({"1", "true", "yes", "on"})
_USER_AGENT = "anonymizer-update-check"
_RELEASE_HOST = "github.com"
_RELEASE_PATH_PREFIX = "/arcane-tl/anonymizer/releases/"


@dataclass(frozen=True)
class UpdateNotice:
    """A stable release newer than the running app."""

    version: str
    html_url: str


def parse_stable_version(raw: str) -> tuple[int, int, int] | None:
    """Return ``(major, minor, patch)`` or ``None`` when *raw* is not stable."""
    text = raw.strip()
    if text[:1] in {"v", "V"}:
        text = text[1:]
    match = _STABLE_VERSION.fullmatch(text)
    if match is None:
        return None
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def is_newer_stable(remote: str, current: str) -> bool:
    """True when both sides are stable and *remote* is strictly newer."""
    remote_parts = parse_stable_version(remote)
    current_parts = parse_stable_version(current)
    if remote_parts is None or current_parts is None:
        return False
    return remote_parts > current_parts


def is_allowed_release_url(url: str) -> bool:
    """True only for an https link to this repo's GitHub releases.

    Host must be exactly ``github.com`` (no lookalike, no userinfo, no
    non-default port). The path must sit under
    ``/arcane-tl/anonymizer/releases/``.
    """
    if any(ch.isspace() for ch in url) or "\\" in url:
        return False
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https":
        return False
    if parsed.username is not None or parsed.password is not None:
        return False
    if parsed.hostname != _RELEASE_HOST:
        return False
    if parsed.port not in (None, 443):
        return False
    path = parsed.path or ""
    if not path.startswith(_RELEASE_PATH_PREFIX):
        return False
    if ".." in path.split("/"):
        return False
    return True


def notice_from_payload(payload: object, current: str) -> UpdateNotice | None:
    """Build a notice from a GitHub release object, or ``None``."""
    if not isinstance(payload, dict):
        return None
    tag = payload.get("tag_name")
    url = payload.get("html_url")
    if not isinstance(tag, str) or not isinstance(url, str):
        return None
    if not is_newer_stable(tag, current):
        return None
    if not is_allowed_release_url(url):
        return None
    parts = parse_stable_version(tag)
    if parts is None:
        return None
    major, minor, patch = parts
    return UpdateNotice(version=f"{major}.{minor}.{patch}", html_url=url)


def update_check_disabled() -> bool:
    """True when the check is switched off for tests or local runs."""
    raw = (os.environ.get(ENV_DISABLE) or "").strip().casefold()
    return raw in _DISABLE_VALUES


def fetch_latest_payload(
    url: str = RELEASES_LATEST_URL,
    timeout: float = TIMEOUT_SECONDS,
) -> dict | None:
    """GET the latest-release JSON. Any failure returns ``None``."""
    try:
        req = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": _USER_AGENT,
            },
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            raw = resp.read(MAX_BODY_BYTES + 1)
        if len(raw) > MAX_BODY_BYTES:
            return None
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            return None
        return data
    except Exception:  # noqa: BLE001
        return None


def check_for_update(current_version: str) -> UpdateNotice | None:
    """Return a notice when a newer stable release exists. Never raises."""
    try:
        if update_check_disabled():
            return None
        override = os.environ.get(ENV_OVERRIDE)
        if override is not None and override.strip() != "":
            try:
                payload = json.loads(override)
            except json.JSONDecodeError:
                return None
            return notice_from_payload(payload, current_version)
        payload = fetch_latest_payload()
        if payload is None:
            return None
        return notice_from_payload(payload, current_version)
    except Exception:  # noqa: BLE001
        return None


def main(argv: list[str] | None = None) -> int:
    """Print one JSON line when an update exists. Always exits 0.

    Used by the Mac droplet as ``python -m anonymizer.util.update_check``.
    """
    del argv
    from anonymizer import __version__

    notice = check_for_update(__version__)
    if notice is not None:
        sys.stdout.write(
            json.dumps({"version": notice.version, "html_url": notice.html_url}) + "\n"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
