# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec: frozen GUI only (CLI stays in runtime/ venv).
# Build:  pyinstaller packaging/windows/Anonymizer.spec
# From repo root, with anonymizer installed in the active env.

import sys
from pathlib import Path

block_cipher = None
root = Path(SPECPATH).resolve().parents[1]
gui_entry = root / "src" / "anonymizer" / "gui" / "__main__.py"

a = Analysis(
    [str(gui_entry)],
    pathex=[str(root / "src")],
    binaries=[],
    datas=[],
    hiddenimports=[
        "anonymizer",
        "anonymizer.gui",
        "anonymizer.gui.app",
        "anonymizer.lists_io",
        "yaml",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Keep GUI slim — detection runs in separate anonymize CLI process
        "spacy",
        "thinc",
        "torch",
        "presidio_analyzer",
        "presidio_anonymizer",
        "pymupdf",
        "fitz",
        "lingua",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="Anonymizer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # windowed GUI
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
