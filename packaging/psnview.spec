# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 The OpenFollow Project
# PyInstaller spec: builds PSNView for all platforms. Run from repo root:
#   poetry run pyinstaller packaging/psnview.spec --noconfirm
#
# macOS:          one-dir build wrapped in PSNView.app (see build-dmg.sh)
# Windows/Linux:  single self-contained executable (see build-archive.py)

import os
import sys

ONEFILE = sys.platform != "darwin"

# macOS: when CODESIGN_IDENTITY is set (CI does this), PyInstaller signs every
# collected binary with the hardened runtime, a secure timestamp and the
# entitlements below, then signs the .app. Unset -> ad-hoc signature as before.
CODESIGN_IDENTITY = os.environ.get("CODESIGN_IDENTITY") or None
ENTITLEMENTS = os.path.join(SPECPATH, "entitlements.plist") if CODESIGN_IDENTITY else None

a = Analysis(
    ["../psnview/__main__.py"],
    pathex=[".."],
    binaries=[],
    datas=[],
    hiddenimports=["psnview.mainwindow"],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # Trim unused Qt modules to keep the build small
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.Qt3DCore",
        "PySide6.QtMultimedia",
        "PySide6.QtQuick",
        "PySide6.QtQml",
        "PySide6.QtPdf",
        "tkinter",
    ],
)

pyz = PYZ(a.pure)

if ONEFILE:
    # Everything packed into one executable; extracted to a temp dir at launch.
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name="PSNView",
        debug=False,
        strip=False,
        upx=False,
        console=False,
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="PSNView",
        debug=False,
        strip=False,
        upx=False,
        console=False,
        codesign_identity=CODESIGN_IDENTITY,
        entitlements_file=ENTITLEMENTS,
    )

    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        name="PSNView",
    )

    app = BUNDLE(
        coll,
        name="PSNView.app",
        icon=None,  # add packaging/psnview.icns here once we have artwork
        bundle_identifier="app.openfollow.psnview",
        info_plist={
            "CFBundleShortVersionString": "0.1.0",
            "CFBundleVersion": "0.1.0",
            "NSHighResolutionCapable": True,
            # PSN is LAN multicast; macOS 15+ prompts for local network access
            "NSLocalNetworkUsageDescription": "PSNView receives PosiStageNet tracker data from devices on your local network.",
        },
    )
