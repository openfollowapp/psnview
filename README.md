<h1 align="center">PSNView</h1>

<p align="center">
  A small desktop viewer for <a href="https://posistage.net">PosiStageNet (PSN)</a> tracking data,
  by the makers of <a href="https://openfollow.app">OpenFollow</a>.
</p>

<p align="center">
  <a href="../../actions/workflows/ci.yml"><img alt="CI" src="../../actions/workflows/ci.yml/badge.svg" /></a>
  <a href="../../releases/latest"><img alt="Latest release" src="https://img.shields.io/github/v/release/openfollowapp/psnview" /></a>
</p>

<p align="center">
  <a href="../../releases">Releases</a> &nbsp;·&nbsp;
  <a href="#install">Install</a> &nbsp;·&nbsp;
  <a href="#usage">Usage</a> &nbsp;·&nbsp;
  <a href="#for-developers">Developers</a> &nbsp;·&nbsp;
  <a href="#license">License</a>
</p>

---

## What it does

PSNView listens to a PSN server on your network and shows every tracker
it sends, live — position, speed, orientation, acceleration, target
position, status, timestamp and data age. Use it to check what a
tracking system, OpenFollow or a console is actually putting on the wire
before you build a show around it.

- Joins the PSN multicast group (default `236.10.10.10:56565`) on the
  network interface you pick.
- Tracker names fill in from INFO packets; rows turn gray when a tracker
  stops updating for more than 2 s.
- The status bar shows the server name and PSN version, packet rate and
  current frame id.

## Install

Grab the build for your platform from the [Releases](../../releases) page.

| Platform | File | How to run |
|---|---|---|
| macOS (Apple Silicon) | `PSNView-<version>-macos-arm64.dmg` | Open the DMG and drag PSNView into Applications. |
| Windows | `PSNView-<version>-windows-x64.exe` | Single self-contained executable — just run it. |
| Linux | `PSNView-<version>-linux-x64.tar.gz` | Extract and run the single `PSNView` binary (X11 or XWayland). |

Good to know:

- The builds are unsigned, so macOS and Windows warn on first launch.
- On first launch macOS asks for **Local Network** access — PSN is LAN
  multicast, so allow it.
- The Windows and Linux executables unpack themselves on each start, so
  the window takes a few seconds to appear.

## Usage

1. Pick the network interface that is on the same LAN as your PSN
   server (`0.0.0.0` = any interface, usually fine).
2. Press **Start**.
3. Trackers appear as data arrives.

## Planned

- Server mode: send INFO/DATA for configurable trackers, with manual
  sliders and motion generators for console testing.
- 2D stage view, packet logging / CSV export, custom multicast address,
  config save/load.

## For developers

```bash
pipx install poetry
poetry install
poetry run psnview             # run from source
poetry run ruff check .        # lint
poetry run pytest              # end-to-end test over loopback multicast
```

Prebuilt executables are made with PyInstaller:

```bash
bash packaging/build-dmg.sh                    # macOS  -> dist/PSNView-<version>-macos-<arch>.dmg
poetry run python packaging/build-archive.py   # Windows -> single .exe, Linux -> .tar.gz
```

CI lints, tests, builds all three and launches each build as a smoke
test (Linux inside a bare `ubuntu:22.04` container, see
`packaging/smoke-test-linux.sh`). To release, bump the version with
`poetry version` (and `CFBundleShortVersionString` in
`packaging/psnview.spec`), then push a `v*` tag — CI attaches the builds
to the GitHub Release. Signed/notarized macOS builds need the Apple
secrets described in `.github/workflows/ci.yml`.

PSN decoding is done by [pypsn](https://github.com/open-stage/python-psn),
the same pure-Python library OpenFollow uses.

## License

Copyright (C) 2026 The OpenFollow Project

PSNView is free software under the GNU Affero General Public License,
version 3 or later — see [`LICENSE`](LICENSE). It bundles or depends on
PySide6/Qt (LGPL-3.0), pypsn (MIT) and PyInstaller (GPL-2.0 with
bootloader exception, build-time only).
