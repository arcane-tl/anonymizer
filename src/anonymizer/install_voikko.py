"""Install the native Voikko library and Finnish dictionary on Windows.

Mac installers use Homebrew (``brew install libvoikko``), which ships the
library and the dictionary. This module is what ``install.ps1`` and the
Windows release build run. The Python package ``libvoikko`` is a normal
dependency; it still needs this native library and the ``5/mor-standard``
dictionary before ``Voikko("fi")`` works.
"""

from __future__ import annotations

import argparse
import io
import os
import platform
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

_DICT_URL = "https://www.puimula.org/htp/testing/voikko-snapshot-v5/dict.zip"
_DLL_URLS = {
    "amd64": (
        "https://www.puimula.org/htp/testing/voikko-sdk/"
        "win-crossbuild/libvoikko-4.3%2Bwin1/win64/libvoikko-1.dll"
    ),
    "x86": (
        "https://www.puimula.org/htp/testing/voikko-sdk/"
        "win-crossbuild/libvoikko-4.3%2Bwin1/win32/libvoikko-1.dll"
    ),
}


def default_windows_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "voikko"


def bundled_arm64_dll() -> Path:
    return (
        Path(__file__).resolve().parent
        / "vendor"
        / "voikko"
        / "win-arm64"
        / "libvoikko-1.dll"
    )


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".partial")
    with urllib.request.urlopen(url, timeout=120) as response:  # noqa: S310
        tmp.write_bytes(response.read())
    tmp.replace(dest)


def _machine() -> str:
    """Architecture of this Python process, not the host PC.

    An x64 interpreter emulated on Windows ARM still reports the host as
    ARM64 from ``platform.machine()``. ``PROCESSOR_ARCHITECTURE`` matches
    the process, so the x64 installer gets the official x64 DLL.
    """
    if sys.maxsize <= 2**32:
        return "x86"
    arch = os.environ.get("PROCESSOR_ARCHITECTURE", "").casefold()
    if arch == "amd64" or arch == "x86_64":
        return "amd64"
    if arch in {"arm64", "aarch64"}:
        return "arm64"
    machine = platform.machine().casefold()
    if machine in {"amd64", "x86_64"}:
        return "amd64"
    if machine in {"arm64", "aarch64"}:
        return "arm64"
    return "amd64"


def install_windows_voikko(dest: Path | None = None) -> Path:
    """Place ``libvoikko-1.dll`` and the standard Finnish dictionary in ``dest``."""
    target = Path(dest) if dest is not None else default_windows_dir()
    target.mkdir(parents=True, exist_ok=True)

    dictionary = target / "5" / "mor-standard" / "mor.vfst"
    if not dictionary.is_file():
        blob = io.BytesIO()
        with urllib.request.urlopen(_DICT_URL, timeout=120) as response:  # noqa: S310
            blob.write(response.read())
        blob.seek(0)
        with zipfile.ZipFile(blob) as archive:
            archive.extractall(target)
    if not dictionary.is_file():
        raise RuntimeError(f"Finnish dictionary missing after extract: {dictionary}")

    dll = target / "libvoikko-1.dll"
    if not dll.is_file():
        kind = _machine()
        if kind == "arm64":
            bundled = bundled_arm64_dll()
            if not bundled.is_file():
                raise RuntimeError(
                    "Windows ARM64 Voikko library is missing from the package: "
                    f"{bundled}"
                )
            shutil.copyfile(bundled, dll)
        else:
            _download(_DLL_URLS[kind], dll)
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install native Voikko for Anonymizer")
    parser.add_argument(
        "--dest",
        type=Path,
        default=None,
        help="Directory for the DLL and dictionary (default: %%LOCALAPPDATA%%\\voikko)",
    )
    args = parser.parse_args(argv)
    if sys.platform != "win32":
        print("Voikko native install is handled by Homebrew on macOS (brew install libvoikko).")
        return 0
    path = install_windows_voikko(args.dest)
    print(f"Voikko ready: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
