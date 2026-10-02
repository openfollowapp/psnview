# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 The OpenFollow Project
"""The application icon ships with the package and renders."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from psnview.icon import ICON_PNG, ICON_SVG, app_icon


def test_icon_assets_are_shipped():
    assert ICON_PNG.is_file()
    assert ICON_SVG.is_file()


def test_app_icon_renders():
    QApplication.instance() or QApplication([])
    pixmap = app_icon().pixmap(64, 64)
    assert not pixmap.isNull()
    assert pixmap.width() == 64 and pixmap.height() == 64
