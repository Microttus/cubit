#!/usr/bin/env bash
# Build Cubit.app and its drag-to-install disk image (FR-79).
#
# Everything the app needs is inside the bundle: Python, rumps, Flask, the web
# app's templates and fonts, and the menu bar icons. Someone who installs the
# DMG never has to see pip, a terminal or a virtual environment.

set -euo pipefail
trap 'echo "[build_macos_app] ERROR at line ${LINENO}: ${BASH_COMMAND}" >&2' ERR

APP_NAME="Cubit"
# The same reverse-DNS name the LaunchAgent uses (cubit.menubar.login.LABEL).
BUNDLE_ID="${BUNDLE_ID:-no.icecubesol.cubit}"
COPYRIGHT="Copyright © 2026 IceCube Solutions"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/.venv-build"
DIST_DIR="${SCRIPT_DIR}/dist"
ICON_ICNS="${SCRIPT_DIR}/src/cubit/menubar/assets/cubit.icns"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "The menu bar app is macOS only, and so is this build." >&2
  exit 1
fi

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "Python was not found: ${PYTHON_BIN}" >&2
  echo "Set PYTHON_BIN to a Python 3.11+ executable." >&2
  exit 1
fi

PYTHON_BIN="$(command -v "${PYTHON_BIN}")"
PYTHON_BIN="$(cd "$(dirname "${PYTHON_BIN}")" && pwd -P)/$(basename "${PYTHON_BIN}")"

# The build removes and recreates VENV_DIR, so the interpreter driving it must
# live outside that directory: an activated build environment would delete its
# own interpreter part-way through and fail at 'python -m venv'.
if [[ -d "${VENV_DIR}" ]]; then
  VENV_REAL="$(cd "${VENV_DIR}" && pwd -P)"
  case "${PYTHON_BIN}" in
    "${VENV_REAL}"/*)
      echo "Python resolves inside the build environment this script recreates:" >&2
      echo "  ${PYTHON_BIN}" >&2
      echo "Run 'deactivate' first, or set PYTHON_BIN to a Python outside" >&2
      echo "  ${VENV_REAL}" >&2
      exit 1
      ;;
  esac
fi

if ! "${PYTHON_BIN}" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
  echo "Python 3.11 or newer is required." >&2
  exit 1
fi

if [[ ! -f "${ICON_ICNS}" ]]; then
  echo "The app icon is missing: ${ICON_ICNS}" >&2
  echo "Rebuild it with: ./tools/make_icns.sh" >&2
  exit 1
fi

APP_VERSION="$(${PYTHON_BIN} - "${SCRIPT_DIR}/pyproject.toml" <<'PY'
from __future__ import annotations

import re
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text(encoding="utf-8")
match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
if match is None:
    raise SystemExit("Could not read the project version from pyproject.toml")
print(match.group(1))
PY
)"

PYTHON_VERSION="$(${PYTHON_BIN} -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")')"
PYTHON_ARCH="$(${PYTHON_BIN} -c 'import platform; print(platform.machine())')"
HOST_ARCH="$(uname -m)"

if [[ "${HOST_ARCH}" == "arm64" && "${PYTHON_ARCH}" == "x86_64" ]]; then
  echo "Warning: the Mac is arm64, but Python is running as x86_64." >&2
  echo "The app this builds will need Rosetta 2." >&2
fi

BUILD_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/cubit-app.XXXXXX")"
BUILD_SUCCEEDED=false

cleanup() {
  if [[ "${BUILD_SUCCEEDED}" == "true" ]]; then
    rm -rf "${BUILD_ROOT}"
  else
    echo "Build diagnostics were kept at: ${BUILD_ROOT}" >&2
  fi
}
trap cleanup EXIT

WORK_DIR="${BUILD_ROOT}/work"
SPEC_DIR="${BUILD_ROOT}/spec"
DMG_STAGE="${BUILD_ROOT}/dmg"
mkdir -p "${WORK_DIR}" "${SPEC_DIR}" "${DMG_STAGE}" "${DIST_DIR}"

APP_PATH="${DIST_DIR}/${APP_NAME}.app"
DMG_PATH="${DIST_DIR}/Cubit-${APP_VERSION}-macOS.dmg"
ZIP_PATH="${DIST_DIR}/Cubit-${APP_VERSION}-macOS.zip"

rm -rf "${VENV_DIR}" "${APP_PATH}" "${DIST_DIR}/${APP_NAME}" "${DMG_PATH}" "${ZIP_PATH}"

printf 'Building %s %s\n' "${APP_NAME}" "${APP_VERSION}"
printf 'Bundle identifier:   %s\n' "${BUNDLE_ID}"
printf 'Host architecture:   %s\n' "${HOST_ARCH}"
printf 'Python architecture: %s\n' "${PYTHON_ARCH}"
printf 'Python version:      %s\n' "${PYTHON_VERSION}"

"${PYTHON_BIN}" -m venv "${VENV_DIR}"
"${VENV_DIR}/bin/python" -m pip install --quiet --upgrade pip wheel
"${VENV_DIR}/bin/python" -m pip install --quiet "${SCRIPT_DIR}[menubar,build]"

# --collect-data cubit brings the web app's templates, stylesheet, fonts and
# the menu bar icons along; without them the bundle starts and then fails at
# the first page render.
"${VENV_DIR}/bin/pyinstaller" \
  --noconfirm \
  --clean \
  --onedir \
  --windowed \
  --noupx \
  --name "${APP_NAME}" \
  --icon "${ICON_ICNS}" \
  --osx-bundle-identifier "${BUNDLE_ID}" \
  --paths "${SCRIPT_DIR}/src" \
  --collect-data cubit \
  --collect-all rumps \
  --collect-submodules ruamel.yaml \
  --exclude-module tkinter \
  --exclude-module pytest \
  --distpath "${DIST_DIR}" \
  --workpath "${WORK_DIR}" \
  --specpath "${SPEC_DIR}" \
  "${SCRIPT_DIR}/launcher.py"

if [[ ! -d "${APP_PATH}" ]]; then
  echo "PyInstaller did not create the expected bundle:" >&2
  echo "  ${APP_PATH}" >&2
  find "${DIST_DIR}" -maxdepth 2 -print >&2 || true
  exit 1
fi

APP_EXECUTABLE="${APP_PATH}/Contents/MacOS/${APP_NAME}"
INFO_PLIST="${APP_PATH}/Contents/Info.plist"
LICENSE_DIR="${APP_PATH}/Contents/Resources/licenses"

if [[ ! -x "${APP_EXECUTABLE}" ]]; then
  echo "The bundle has no executable: ${APP_EXECUTABLE}" >&2
  exit 1
fi

# LSUIElement is what makes this a menu bar app: no Dock icon, no app switcher
# entry, nothing but the icon at the top right (FR-63).
"${VENV_DIR}/bin/python" - "${INFO_PLIST}" "${APP_NAME}" "${APP_VERSION}" "${COPYRIGHT}" <<'PY'
from __future__ import annotations

import plistlib
import sys
from pathlib import Path

plist_path, app_name, app_version, copyright_line = (
    Path(sys.argv[1]),
    sys.argv[2],
    sys.argv[3],
    sys.argv[4],
)

with plist_path.open("rb") as stream:
    values = plistlib.load(stream)

values.update(
    {
        "CFBundleName": app_name,
        "CFBundleDisplayName": app_name,
        "CFBundleShortVersionString": app_version,
        "CFBundleVersion": app_version,
        "LSUIElement": True,
        "LSApplicationCategoryType": "public.app-category.productivity",
        "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True,
        "NSHumanReadableCopyright": copyright_line,
    }
)

with plist_path.open("wb") as stream:
    plistlib.dump(values, stream, sort_keys=False)
PY

# The licences of what is inside travel with it, the bundled font included.
mkdir -p "${LICENSE_DIR}"
cp "${SCRIPT_DIR}/LICENSE" "${LICENSE_DIR}/PROJECT-LICENSE.txt"
cp "${SCRIPT_DIR}/src/cubit/web/static/fonts/OFL.txt" "${LICENSE_DIR}/JetBrainsMono-OFL.txt"
"${VENV_DIR}/bin/python" - "${LICENSE_DIR}/THIRD-PARTY.txt" <<'PY'
from __future__ import annotations

import sys
from importlib.metadata import distributions
from pathlib import Path

lines = ["Third-party packages bundled inside Cubit.app", ""]
seen = {}
for distribution in distributions():
    name = distribution.metadata["Name"]
    if name:
        seen[name] = distribution.metadata.get("License-Expression") or (
            distribution.metadata.get("License") or "see the package's own metadata"
        )
for name in sorted(seen, key=str.lower):
    lines.append(f"{name}: {seen[name].splitlines()[0]}")

Path(sys.argv[1]).write_text("\n".join(lines) + "\n", encoding="utf-8")
PY

plutil -lint "${INFO_PLIST}" >/dev/null
xattr -cr "${APP_PATH}"

# Ad-hoc signing. Enough for the app to run on the machine that built it and on
# any Mac where the user clears quarantine; a Developer ID and notarisation are
# what a public download needs, and that is a paid account away.
codesign --force --deep --sign - --timestamp=none "${APP_PATH}"
codesign --verify --deep --strict --verbose=1 "${APP_PATH}"

# The smoke test: the bundle with arguments is the CLI, which is also how the
# menu bar app starts the web app inside the bundle (FR-79).
BUNDLE_VERSION_OUTPUT="$("${APP_EXECUTABLE}" --version)"
if [[ "${BUNDLE_VERSION_OUTPUT}" != "cubit ${APP_VERSION}" ]]; then
  echo "The bundled CLI answered '--version' with:" >&2
  echo "  ${BUNDLE_VERSION_OUTPUT}" >&2
  echo "Expected: cubit ${APP_VERSION}" >&2
  exit 1
fi

ditto "${APP_PATH}" "${DMG_STAGE}/${APP_NAME}.app"
ln -s /Applications "${DMG_STAGE}/Applications"
hdiutil create \
  -volname "${APP_NAME} ${APP_VERSION}" \
  -srcfolder "${DMG_STAGE}" \
  -ov \
  -format UDZO \
  "${DMG_PATH}" >/dev/null

ditto -c -k --sequesterRsrc --keepParent "${APP_PATH}" "${ZIP_PATH}"

BUILD_SUCCEEDED=true

cat <<OUTPUT

Build completed successfully.

Application:
  ${APP_PATH}

Drag-to-install disk image:
  ${DMG_PATH}

Portable archive:
  ${ZIP_PATH}

Try it with:
  open "${APP_PATH}"

If a login item is already running the menu bar app, quit it first, or there
will be two Cubit icons up there: cubit menubar uninstall-login
OUTPUT
