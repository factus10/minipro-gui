#!/bin/bash
# Build a signed, notarized and stapled "minipro GUI.app" and .dmg.
#
#   packaging/build_macos.sh               # build, sign, notarize, staple
#   packaging/build_macos.sh --no-notarize # build and sign only (quick local test)
#   packaging/build_macos.sh --resume ID   # finish after the app's notarization timed out:
#                                          # wait for submission ID, then staple and make the dmg
#
# Environment:
#   SIGN_IDENTITY   codesign identity (default: the first "Developer ID Application")
#   NOTARY_PROFILE  notarytool keychain profile (default: minipro-gui)
#   BUNDLE_ID       bundle identifier (default: io.github.minipro-gui)
#   BUILD_ROOT      scratch directory (default: /tmp/minipro-gui-build)
#
# Everything is built under BUILD_ROOT, outside the source tree: folders such
# as an iCloud-synced ~/Documents add file flags and extended attributes that
# codesign rejects. Only the finished .dmg is copied back into ./dist.
#
# One-time notarization setup, with an App Store Connect API key:
#   xcrun notarytool store-credentials minipro-gui \
#       --key AuthKey_XXXXXXXXXX.p8 --key-id XXXXXXXXXX --issuer <issuer UUID>
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT=$PWD
APP_NAME="minipro GUI"
NOTARIZE=1
RESUME_ID=""
case "${1:-}" in
    --no-notarize) NOTARIZE=0 ;;
    --resume) RESUME_ID=${2:?usage: $0 --resume <submission id>} ;;
esac
NOTARY_PROFILE=${NOTARY_PROFILE:-minipro-gui}
ENTITLEMENTS="$ROOT/packaging/entitlements.plist"
# Apple usually answers in minutes, but a new app's first submissions can take hours.
NOTARY_TIMEOUT=${NOTARY_TIMEOUT:-3h}

step() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }

if [[ -z "${SIGN_IDENTITY:-}" ]]; then
    SIGN_IDENTITY=$(security find-identity -v -p codesigning |
        sed -n 's/.*"\(Developer ID Application: .*\)"/\1/p' | head -1)
fi
[[ -n "$SIGN_IDENTITY" ]] || { echo "No 'Developer ID Application' identity found." >&2; exit 1; }

if (( NOTARIZE )); then
    # Fail early rather than after a long build if credentials are missing.
    if ! xcrun notarytool history --keychain-profile "$NOTARY_PROFILE" >/dev/null 2>&1; then
        cat >&2 <<EOF
Notarization credentials for keychain profile "$NOTARY_PROFILE" aren't set up.
See the top of $0 for the one-time setup command, or build without notarizing:
  $0 --no-notarize
EOF
        exit 1
    fi
fi

VERSION=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' minipro_gui/__init__.py)
ARCH=$(uname -m)
BUILD_ROOT=${BUILD_ROOT:-/tmp/minipro-gui-build}
DIST="$BUILD_ROOT/dist"
APP="$DIST/$APP_NAME.app"
DMG="$DIST/minipro-gui-$VERSION-macos-$ARCH.dmg"

sign() { codesign --force --timestamp --options runtime --sign "$SIGN_IDENTITY" "$@"; }

# Print notarytool's result and stop unless Apple accepted the submission.
check_accepted() {
    local out=$1 id
    sed 's/Current status: In Progress\.*//g' <<<"$out"
    if ! grep -q 'status: Accepted' <<<"$out"; then
        id=$(sed -n 's/^ *id: //p' <<<"$out" | head -1)
        if grep -q 'Timeout' <<<"$out"; then
            echo "Apple hasn't finished yet. When it has, continue with:" >&2
            echo "  $0 --resume $id" >&2
        else
            echo "Notarization failed. See why with:" >&2
            echo "  xcrun notarytool log $id --keychain-profile $NOTARY_PROFILE" >&2
        fi
        exit 1
    fi
}

notarize() {
    check_accepted "$(xcrun notarytool submit "$1" --keychain-profile "$NOTARY_PROFILE" \
        --wait --timeout "$NOTARY_TIMEOUT" 2>&1 || true)"
}

if [[ -n "$RESUME_ID" ]]; then
    [[ -d "$APP" ]] || { echo "No built app at $APP to resume with." >&2; exit 1; }
    step "Waiting for notarization of the app (submission $RESUME_ID)"
    check_accepted "$(xcrun notarytool wait "$RESUME_ID" --keychain-profile "$NOTARY_PROFILE" \
        --timeout "$NOTARY_TIMEOUT" 2>&1 || true)"
    xcrun stapler staple "$APP"
else
    step "Building $APP_NAME $VERSION ($ARCH)"
    # Synced folders can mark the venv's files hidden, which stops Qt finding its plugins.
    chflags -R nohidden .venv 2>/dev/null || true
    [[ -f packaging/icon.icns ]] || uv run python packaging/make_icon.py
    rm -rf "$BUILD_ROOT" && mkdir -p "$BUILD_ROOT"
    uv run --with pyinstaller pyinstaller --noconfirm --clean \
        --distpath "$DIST" --workpath "$BUILD_ROOT/pyinstaller" packaging/minipro_gui.spec
    rm -rf "$DIST/$APP_NAME"  # the unbundled COLLECT folder; only the .app is shipped
    # Files copied out of the venv can carry flags and attributes codesign rejects.
    chflags -R nohidden "$APP"
    xattr -cr "$APP"

    step "Signing with: $SIGN_IDENTITY"
    # Inside-out: every loose Mach-O file, then each framework bundle, then the app.
    while IFS= read -r -d '' f; do
        if file -b "$f" | grep -q 'Mach-O'; then sign "$f"; fi
    done < <(find "$APP/Contents" -type f ! -path '*.framework/*' -print0)
    while IFS= read -r -d '' fw; do
        sign "$fw"
    done < <(find "$APP/Contents" -type d -name '*.framework' -print0 | sort -rz)
    sign --entitlements "$ENTITLEMENTS" "$APP"
    codesign --verify --deep --strict --verbose=2 "$APP"

    step "Checking the signed app starts"
    "$APP/Contents/MacOS/$APP_NAME" --self-test

    if (( NOTARIZE )); then
        step "Notarizing the app"
        ZIP="$BUILD_ROOT/notarize-app.zip"
        ditto -c -k --keepParent "$APP" "$ZIP"
        notarize "$ZIP"
        xcrun stapler staple "$APP"
        rm -f "$ZIP"
    fi
fi

step "Creating $(basename "$DMG")"
STAGE="$BUILD_ROOT/dmg"
rm -rf "$STAGE" && mkdir -p "$STAGE"
ditto "$APP" "$STAGE/$APP_NAME.app"
ln -s /Applications "$STAGE/Applications"
hdiutil create -quiet -volname "$APP_NAME" -srcfolder "$STAGE" -ov -format UDZO "$DMG"
codesign --force --timestamp --sign "$SIGN_IDENTITY" "$DMG"

if (( NOTARIZE )); then
    step "Notarizing the disk image"
    notarize "$DMG"
    xcrun stapler staple "$DMG"
    step "Gatekeeper assessment"
    spctl --assess --type execute --verbose=2 "$APP"
    spctl --assess --type open --context context:primary-signature --verbose=2 "$DMG"
fi

mkdir -p "$ROOT/dist"
cp "$DMG" "$ROOT/dist/"
step "Done"
du -sh "$APP" "$DMG"
echo "Disk image: $ROOT/dist/$(basename "$DMG")"
