#!/usr/bin/env bash
# Build production-signed AAB and APK artifacts for Kora Bourse.
# Usage: bash scripts/build_mobile_release.sh [--skip-tests]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
MOBILE_DIR="$PROJECT_DIR/mobile/brvm_mobile"
DIST_DIR="$PROJECT_DIR/mobile/dist"

RUN_TESTS=1
case "${1:-}" in
  "") ;;
  --skip-tests) RUN_TESTS=0 ;;
  --help|-h)
    echo "Usage: bash scripts/build_mobile_release.sh [--skip-tests]"
    exit 0
    ;;
  *)
    echo "[release] ERROR: unknown option '$1' (expected --skip-tests)" >&2
    exit 2
    ;;
esac

cd "$PROJECT_DIR"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
if [[ -z "${JAVA_HOME:-}" && -d "/Applications/Android Studio.app/Contents/jbr/Contents/Home" ]]; then
  export JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home"
fi
if [[ -n "${JAVA_HOME:-}" ]]; then
  export PATH="$JAVA_HOME/bin:$PATH"
fi

command -v flutter >/dev/null 2>&1 || {
  echo "[release] ERROR: flutter is not available in PATH." >&2
  exit 1
}
[[ -f "$MOBILE_DIR/android/key.properties" ]] || {
  echo "[release] ERROR: $MOBILE_DIR/android/key.properties is missing; production signing is required." >&2
  exit 1
}

VERSION="$(awk '/^version: /{print $2; exit}' "$MOBILE_DIR/pubspec.yaml")"
if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+\+[0-9]+$ ]]; then
  echo "[release] ERROR: expected version MAJOR.MINOR.PATCH+BUILD in pubspec.yaml, got '$VERSION'." >&2
  exit 1
fi
VERSION_NAME="${VERSION%%+*}"
VERSION_CODE="${VERSION##*+}"
echo "[release] building Kora Bourse $VERSION_NAME (versionCode $VERSION_CODE)"

PYTHON="$PROJECT_DIR/.venv/bin/python"
[[ -x "$PYTHON" ]] || PYTHON=python3
if [[ "$RUN_TESTS" == "1" ]]; then
  echo "[release] running backend tests..."
  DATABASE_URL= "$PYTHON" -m pytest -q "$PROJECT_DIR/tests"
  echo "[release] running Flutter analysis and tests..."
  (
    cd "$MOBILE_DIR"
    flutter analyze
    flutter test
  )
else
  echo "[release] skipping tests (--skip-tests)"
fi

(
  cd "$MOBILE_DIR"
  echo "[release] building AAB..."
  flutter build appbundle --release
  echo "[release] building APK..."
  flutter build apk --release
)

AAB_SOURCE="$MOBILE_DIR/build/app/outputs/bundle/release/app-release.aab"
APK_SOURCE="$MOBILE_DIR/build/app/outputs/flutter-apk/app-release.apk"
AAB_DEST="$DIST_DIR/KoraBourse-v$VERSION_NAME.aab"
APK_DEST="$DIST_DIR/KoraBourse-v$VERSION_NAME.apk"
mkdir -p "$DIST_DIR"
cp "$AAB_SOURCE" "$AAB_DEST"
cp "$APK_SOURCE" "$APK_DEST"
unzip -tq "$AAB_DEST"
unzip -tq "$APK_DEST"

if command -v shasum >/dev/null 2>&1; then
  AAB_SHA="$(shasum -a 256 "$AAB_DEST" | awk '{print $1}')"
  APK_SHA="$(shasum -a 256 "$APK_DEST" | awk '{print $1}')"
else
  AAB_SHA="$(sha256sum "$AAB_DEST" | awk '{print $1}')"
  APK_SHA="$(sha256sum "$APK_DEST" | awk '{print $1}')"
fi

printf '[release] AAB: %s\n' "$AAB_DEST"
printf '[release] APK: %s\n' "$APK_DEST"
printf '[release] AAB SHA-256: %s\n' "$AAB_SHA"
printf '[release] APK SHA-256: %s\n' "$APK_SHA"
