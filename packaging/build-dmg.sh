#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 The OpenFollow Project
#
# Build PSNView.app with PyInstaller and wrap it in a DMG.
# Run on macOS from the repo root:  bash packaging/build-dmg.sh
#
# By default the build is unsigned (ad-hoc). CI signs and notarizes releases by
# setting these before calling the script (see .github/workflows/ci.yml):
#   CODESIGN_IDENTITY      "Developer ID Application: ..." or its SHA-1 hash
#   APPLE_NOTARY_KEY_FILE  path to the App Store Connect API key (.p8)
#   APPLE_NOTARY_KEY_ID    key ID of that API key
#   APPLE_NOTARY_ISSUER    issuer ID of that API key
#
# Signed flow: PyInstaller signs -> notarize + staple the .app -> build the DMG
# from the stapled app -> sign, notarize + staple the DMG. Stapling the app
# itself lets the first launch pass Gatekeeper offline (venues without internet).

set -euo pipefail

VERSION="$(poetry version -s)"
DIST="dist"
APP="${DIST}/PSNView.app"
ARCH="$(uname -m)"  # arm64 or x86_64
DMG="${DIST}/PSNView-${VERSION}-macos-${ARCH}.dmg"
STAGING="${DIST}/dmg-staging"

SIGN="${CODESIGN_IDENTITY:-}"
NOTARIZE="${APPLE_NOTARY_KEY_FILE:-}"
if [[ -n "${NOTARIZE}" && -z "${SIGN}" ]]; then
  echo "error: notarization requires CODESIGN_IDENTITY" >&2
  exit 1
fi

# notarize <zip|dmg>: submit to Apple, wait for the verdict, print the
# notarization log and fail on anything but "Accepted".
notarize() {
  echo "==> Notarizing $1"
  local args=(--key "${APPLE_NOTARY_KEY_FILE}" --key-id "${APPLE_NOTARY_KEY_ID:?}" --issuer "${APPLE_NOTARY_ISSUER:?}")
  local out id status
  out="$(xcrun notarytool submit "$1" "${args[@]}" --wait --timeout 30m --output-format json)"
  echo "${out}"
  read -r id status < <(python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["id"], d["status"])' <<<"${out}")
  if [[ "${status}" != "Accepted" ]]; then
    xcrun notarytool log "${id}" "${args[@]}" || true
    echo "error: notarization of $1 failed (${status})" >&2
    exit 1
  fi
}

echo "==> Building PSNView.app ${VERSION}"
if [[ -n "${SIGN}" ]]; then
  echo "==> Signing with ${SIGN}"
  # PyInstaller signs every binary inside-out with the hardened runtime and the
  # entitlements from psnview.spec. Make a failed bundle signature fatal and
  # verify the result, instead of PyInstaller's default warn-and-continue.
  export PYINSTALLER_STRICT_BUNDLE_CODESIGN_ERROR=1 PYINSTALLER_VERIFY_BUNDLE_SIGNATURE=1
fi
poetry run pyinstaller packaging/psnview.spec --noconfirm --distpath "${DIST}"

if [[ -n "${SIGN}" ]]; then
  codesign --verify --deep --strict --verbose=2 "${APP}"
fi

if [[ -n "${NOTARIZE}" ]]; then
  # notarytool only accepts zip/dmg/pkg, so ship the app as a zip.
  ZIP="${DIST}/PSNView-notarize.zip"
  rm -f "${ZIP}"
  ditto -c -k --keepParent "${APP}" "${ZIP}"
  notarize "${ZIP}"
  rm -f "${ZIP}"
  xcrun stapler staple "${APP}"
fi

echo "==> Creating DMG"
rm -rf "${STAGING}" "${DMG}"
mkdir -p "${STAGING}"
ditto "${APP}" "${STAGING}/PSNView.app"
ln -s /Applications "${STAGING}/Applications"
hdiutil create -volname "PSNView ${VERSION}" \
  -srcfolder "${STAGING}" -ov -format UDZO "${DMG}"
rm -rf "${STAGING}"

if [[ -n "${SIGN}" ]]; then
  codesign --force --timestamp --sign "${SIGN}" "${DMG}"
fi

if [[ -n "${NOTARIZE}" ]]; then
  notarize "${DMG}"
  xcrun stapler staple "${DMG}"
  echo "==> Gatekeeper assessment"
  spctl --assess --type execute --verbose=2 "${APP}"
  spctl --assess --type open --context context:primary-signature --verbose=2 "${DMG}"
fi

echo "==> Done: ${DMG}"
