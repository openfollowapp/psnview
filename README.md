# PSNView

A simple PosiStageNet (PSN) viewer with a Qt GUI, by the makers of
[OpenFollow](https://openfollow.app).

Phase 1: **Client** — joins the PSN multicast group (default `236.10.10.10:56565`),
decodes INFO and DATA packets with [pypsn](https://github.com/open-stage/python-psn)
(the same pure-Python PSN library OpenFollow uses) and shows all tracker fields
live: position, speed, orientation, acceleration, target position, status,
timestamp and data age.

## Install (development)

```bash
pipx install poetry
poetry install
poetry run psnview
```

## Install (prebuilt)

Download the build for your platform from the Releases page:

- **macOS** — `PSNView-<version>-macos-<arch>.dmg`: open it and drag
  PSNView into Applications. On first launch macOS will ask for Local
  Network access — PSN is LAN multicast, so allow it.
- **Windows** — `PSNView-<version>-windows-x64.exe`: a single
  self-contained executable, just run it.
- **Linux** — `PSNView-<version>-linux-x64.tar.gz`: extract the single
  `PSNView` binary and run it. Qt and its X11 helper libraries are
  bundled; only an X11/XWayland session and the basic system libraries
  (`libxcb`, `libX11`, `libGL`) are needed. If nothing appears, run it
  from a terminal to see Qt's error output.

The Windows and Linux builds unpack themselves to a temporary directory
on each launch, so the first window takes a few seconds to appear.

The builds are unsigned, so macOS/Windows will warn on first launch.

## Usage

1. Pick the network interface that is on the same LAN as your PSN server
   (`0.0.0.0` = any interface, usually fine).
2. Press **Start**.
3. Trackers appear as DATA packets arrive; names fill in from INFO packets.
   Rows turn gray when a tracker stops updating (> 2 s).

The status bar shows connection state, server name + PSN version,
packet rate and the current frame id.

## Development

```bash
poetry run ruff check .        # lint
poetry run ruff format .       # format
poetry run pytest              # end-to-end test over loopback multicast
```

CI (GitHub Actions) lints, runs the test suite on Linux (offscreen Qt,
Python 3.10 + 3.13), and builds the macOS DMG plus Windows/Linux
executables (uploaded as workflow artifacts on every push to `main`).
Each build is smoke-tested by launching it — the Linux one inside a
bare `ubuntu:22.04` container (`packaging/smoke-test-linux.sh`, needs
Docker) so missing bundled libraries fail CI instead of users.
Pushing a `v*` tag attaches all three to a GitHub Release.

To build locally:

```bash
bash packaging/build-dmg.sh                    # macOS  -> dist/PSNView-<version>-macos-<arch>.dmg
poetry run python packaging/build-archive.py   # Windows -> single .exe, Linux -> .tar.gz
```

## Releasing

1. Bump the version: `poetry version patch` (also update
   `CFBundleShortVersionString` in `packaging/psnview.spec`).
2. Pin the `pypsn` git dependency to a specific rev for reproducibility.
3. Tag and push: `git tag v0.1.x && git push --tags`.
4. CI builds and attaches the macOS DMG and the Windows/Linux archives
   to the release. For signed/notarized macOS builds, configure the
   Apple secrets documented in `.github/workflows/ci.yml`.

## Project layout

```
psnview/            application package
├── __main__.py     entry point
├── mainwindow.py   Qt main window (toolbar, table, status bar)
├── model.py        tracker state store + table model
├── receiver.py     background receive thread (pypsn socket + parser)
└── netutils.py     interface enumeration, PSN defaults
packaging/          PyInstaller spec, build scripts (DMG, exe/tar.gz), Linux smoke test
tests/              end-to-end smoke test (loopback multicast)
```

## Roadmap

- Phase 2: Server mode — send INFO/DATA for configurable trackers with
  manual sliders and motion generators (circle, sine) for console testing.
- Phase 3: 2D stage view, packet logging/CSV export, custom multicast
  address, config save/load.

## License

Copyright (C) 2026 The OpenFollow Project

PSNView is free software: you can redistribute it and/or modify it under
the terms of the GNU Affero General Public License as published by the
Free Software Foundation, either version 3 of the License, or (at your
option) any later version. See [`LICENSE`](LICENSE).

PSNView bundles or depends on third-party components under their own
licenses: PySide6/Qt (LGPL-3.0), pypsn (MIT), PyInstaller (GPL-2.0 with
bootloader exception, build-time only).
