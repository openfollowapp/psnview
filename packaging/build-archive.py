#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 The OpenFollow Project
"""Build a portable single-file PSNView executable for Windows or Linux.

Runs PyInstaller (one-file mode, see packaging/psnview.spec) and names the
result by version, OS and architecture:

    Windows:  dist/PSNView-<version>-windows-<arch>.exe
    Linux:    dist/PSNView-<version>-linux-<arch>.tar.gz  (single binary
              inside; the tarball preserves the executable bit)

Run from the repo root:  poetry run python packaging/build-archive.py
macOS builds use packaging/build-dmg.sh instead.
"""

from __future__ import annotations

import platform
import re
import shutil
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
SPEC = ROOT / "packaging" / "psnview.spec"
APP_NAME = "PSNView"  # EXE(name=...) in the spec

# platform.system() -> (os label, PyInstaller output name)
PLATFORMS = {"Windows": ("windows", f"{APP_NAME}.exe"), "Linux": ("linux", APP_NAME)}
ARCH_ALIASES = {"amd64": "x64", "x86_64": "x64", "aarch64": "arm64", "arm64": "arm64"}


def project_version() -> str:
    try:
        return version("psnview")
    except PackageNotFoundError:
        # Not installed (e.g. `poetry install --no-root`): read pyproject directly.
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
        if not match:
            raise SystemExit("Could not determine project version") from None
        return match.group(1)


def main() -> int:
    system = platform.system()
    if system not in PLATFORMS:
        hint = " (use packaging/build-dmg.sh)" if system == "Darwin" else ""
        print(f"build-archive.py does not support {system}{hint}", file=sys.stderr)
        return 2
    os_label, built_name = PLATFORMS[system]
    machine = platform.machine().lower()
    arch = ARCH_ALIASES.get(machine, machine)
    ver = project_version()
    built = DIST / built_name

    # A stale one-dir build would block PyInstaller from writing the one-file exe.
    if built.is_dir():
        shutil.rmtree(built)

    print(f"==> Building {APP_NAME} {ver} for {os_label}-{arch}")
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", str(SPEC), "--noconfirm", "--distpath", str(DIST)],
        cwd=ROOT,
        check=True,
    )
    if not built.is_file():
        raise SystemExit(f"Expected PyInstaller output {built} not found")

    stem = f"{APP_NAME}-{ver}-{os_label}-{arch}"
    if system == "Windows":
        out = built.with_name(f"{stem}.exe")
        out.unlink(missing_ok=True)
        built.rename(out)
    else:
        print(f"==> Creating archive {stem}.tar.gz")
        out = Path(shutil.make_archive(str(DIST / stem), "gztar", root_dir=DIST, base_dir=built_name))
    print(f"==> Done: {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
