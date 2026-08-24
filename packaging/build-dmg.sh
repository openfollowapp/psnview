#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 The OpenFollow Project
#
# Build PSNView.app with PyInstaller and wrap it in a DMG.
# Run on macOS from the repo root:  bash packaging/build-dmg.sh
#
# Optional codesigning/notarization (recommended for distribution):
#   export CODESIGN_IDENTITY="Developer ID Application: ..."
#   export NOTARY_PROFILE="openfollow-notary"   # xcrun notarytool store-credentials

set -euo pipefail

VERSION="$(poetry version -s)"
DIST="dist"
APP="${DIST}/PSNView.app"
ARCH="$(uname -m)"  # arm64 or x86_64
DMG="${DIST}/PSNView-${VERSION}-macos-${ARCH}.dmg"
STAGING="${DIST}/dmg-staging"

echo "==> Building PSNView.app ${VERSION}"
poetry run pyinstaller packaging/psnview.spec --noconfirm --distpath "${DIST}"

if [[ -n "${CODESIGN_IDENTITY:-}" ]]; then
  echo "==> Codesigning"
  codesign --deep --force --options runtime --sign "${CODESIGN_IDENTITY}" "${APP}"
fi

echo "==> Creating DMG"
rm -rf "${STAGING}" "${DMG}"
mkdir -p "${STAGING}"
cp -R "${APP}" "${STAGING}/"
ln -s /Applications "${STAGING}/Applications"
hdiutil create -volname "PSNView ${VERSION}" \
  -srcfolder "${STAGING}" -ov -format UDZO "${DMG}"
rm -rf "${STAGING}"

if [[ -n "${CODESIGN_IDENTITY:-}" ]]; then
  codesign --sign "${CODESIGN_IDENTITY}" "${DMG}"
fi

if [[ -n "${NOTARY_PROFILE:-}" ]]; then
  echo "==> Notarizing"
  xcrun notarytool submit "${DMG}" --keychain-profile "${NOTARY_PROFILE}" --wait
  xcrun stapler staple "${DMG}"
fi

echo "==> Done: ${DMG}"
