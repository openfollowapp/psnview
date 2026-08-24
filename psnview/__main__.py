# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 The OpenFollow Project
"""Entry point: `python -m psnview` or the `psnview` console script."""

from __future__ import annotations

import sys


def main() -> int:
    from PySide6.QtWidgets import QApplication

    # Absolute import: PyInstaller runs this file as a top-level script,
    # where relative imports have no parent package.
    from psnview.mainwindow import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("PSNView")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
