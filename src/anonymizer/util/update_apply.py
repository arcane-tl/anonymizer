"""Apply a discovered update. The availability check stays in update_check.

The Mac droplet and the Windows options window call this only after the user
presses Update. Failures return a status the banner can show. They do not
raise.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from anonymizer.util.update_check import is_allowed_setup_url

_BREW_PATH = "/opt/homebrew/bin:/usr/local/bin"


@dataclass(frozen=True)
class ApplyStatus:
    status: str
    detail: str = ""
    html_url: str = ""
    version: str = ""

    def to_json(self) -> str:
        return json.dumps(
            {
                "status": self.status,
                "detail": self.detail,
                "html_url": self.html_url,
                "version": self.version,
            }
        )


def mac_manual_steps() -> str:
    return (
        "Update failed. Quit Anonymizer. In Terminal run: "
        "brew uninstall --cask anonymizer-app && brew uninstall anonymizer "
        "&& brew install --cask anonymizer-app. "
        "If this copy did not come from Homebrew, move Anonymizer.app out of "
        "Applications and install the new zip from the release."
    )


def windows_manual_steps(version: str) -> str:
    return (
        "Update failed. Quit Anonymizer, uninstall it in Settings → Apps, "
        f"then download and run Anonymizer-Setup-{version}.exe from the release."
    )


def _brew_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = _BREW_PATH + os.pathsep + env.get("PATH", "")
    return env


def _brew_bin() -> str | None:
    for candidate in ("/opt/homebrew/bin/brew", "/usr/local/bin/brew"):
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def homebrew_cask_installed() -> bool:
    brew = _brew_bin()
    if brew is None:
        return False
    try:
        proc = subprocess.run(
            [brew, "list", "--cask", "anonymizer-app"],
            capture_output=True,
            text=True,
            env=_brew_env(),
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def mac_can_update(app_path: str) -> bool:
    """True when this running app is the Homebrew cask in /Applications."""
    path = os.path.normpath(app_path)
    if path != "/Applications/Anonymizer.app":
        return False
    return homebrew_cask_installed()


def apply_mac_update(app_path: str, *, html_url: str, version: str) -> ApplyStatus:
    if not mac_can_update(app_path):
        return ApplyStatus("open-release", html_url=html_url, version=version)
    brew = _brew_bin()
    if brew is None:
        return ApplyStatus(
            "fail",
            detail=mac_manual_steps(),
            html_url=html_url,
            version=version,
        )
    try:
        proc = subprocess.run(
            [brew, "upgrade", "anonymizer", "anonymizer-app"],
            capture_output=True,
            text=True,
            env=_brew_env(),
            timeout=3600,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ApplyStatus(
            "fail",
            detail=mac_manual_steps(),
            html_url=html_url,
            version=version,
        )
    if proc.returncode != 0:
        return ApplyStatus(
            "fail",
            detail=mac_manual_steps(),
            html_url=html_url,
            version=version,
        )
    return ApplyStatus("ok", html_url=html_url, version=version)


def download_setup(url: str, version: str, dest: Path) -> bool:
    if not is_allowed_setup_url(url, version):
        return False
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "anonymizer-update-check"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310
            dest.write_bytes(resp.read())
    except Exception:  # noqa: BLE001
        return False
    return dest.is_file() and dest.stat().st_size > 0


def apply_windows_update(
    *,
    setup_url: str,
    version: str,
    html_url: str,
    app_dir: str,
) -> ApplyStatus:
    fail = ApplyStatus(
        "fail",
        detail=windows_manual_steps(version),
        html_url=html_url,
        version=version,
    )
    if not setup_url or not is_allowed_setup_url(setup_url, version):
        return fail
    fd, name = tempfile.mkstemp(prefix="Anonymizer-Setup-", suffix=".exe")
    os.close(fd)
    dest = Path(name)
    try:
        if not download_setup(setup_url, version, dest):
            return fail
        proc = subprocess.run(
            [
                str(dest),
                "/VERYSILENT",
                "/SUPPRESSMSGBOXES",
                "/NORESTART",
                f"/DIR={app_dir}",
            ],
            check=False,
        )
        if proc.returncode != 0:
            return fail
    except (OSError, subprocess.TimeoutExpired):
        return fail
    exe = str(Path(app_dir) / "Anonymizer.exe")
    try:
        subprocess.Popen([exe], close_fds=True)  # noqa: S603
    except OSError:
        return fail
    return ApplyStatus("ok", html_url=html_url, version=version)


def main(argv: list[str] | None = None) -> int:
    """Mac droplet entry: ``python -m anonymizer.util.update_apply mac APP``.

    Always exits 0. One JSON object on stdout.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 2 or args[0] != "mac":
        sys.stdout.write(ApplyStatus("fail", detail=mac_manual_steps()).to_json() + "\n")
        return 0
    app_path = args[1]
    # The release URL and version are optional trailing args from the banner.
    html_url = args[2] if len(args) > 2 else ""
    version = args[3] if len(args) > 3 else ""
    result = apply_mac_update(app_path, html_url=html_url, version=version)
    sys.stdout.write(result.to_json() + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
