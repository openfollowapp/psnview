#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 The OpenFollow Project
#
# Launch the Linux build inside a minimal Ubuntu container that mimics a bare
# desktop: an X server (Xvfb) and the GL/EGL system libraries PyInstaller
# intentionally leaves to the host, but none of the Qt/xcb helper libraries.
# This proves the single-file binary is self-contained. Passes if the app is
# still running after SMOKE_SECONDS; a missing library makes Qt abort well
# before that.
#
# Usage:  bash packaging/smoke-test-linux.sh dist/PSNView-<version>-linux-x64.tar.gz
# Needs Docker. Runs the container as linux/amd64 (emulated on Apple Silicon).

set -euo pipefail

TARBALL="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
IMAGE="${SMOKE_IMAGE:-ubuntu:22.04}"
SECONDS_ALIVE="${SMOKE_SECONDS:-15}"

echo "==> Smoke-testing $(basename "$TARBALL") in ${IMAGE} (amd64)"
docker run --rm --platform linux/amd64 \
  -v "${TARBALL}:/psnview.tar.gz:ro" \
  -e SECONDS_ALIVE="${SECONDS_ALIVE}" \
  "${IMAGE}" bash -euo pipefail -c '
    apt-get update -qq >/dev/null
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq xvfb libegl1 >/dev/null
    tar xzf /psnview.tar.gz -C /opt
    set +e
    QT_QPA_PLATFORM=xcb xvfb-run -a timeout "${SECONDS_ALIVE}" /opt/PSNView
    rc=$?
    set -e
    if [ "$rc" -eq 124 ]; then
      echo "OK: PSNView still running after ${SECONDS_ALIVE}s"
    else
      echo "FAIL: PSNView exited with status $rc"
      exit 1
    fi
  '
