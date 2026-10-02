# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 The OpenFollow Project
"""The application icon, shipped inside the package so a source checkout and
a PyInstaller build find it the same way."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QIcon

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
ICON_PNG = ASSETS_DIR / "icon.png"
ICON_SVG = ASSETS_DIR / "icon.svg"


def app_icon() -> QIcon:
    return QIcon(str(ICON_PNG))
