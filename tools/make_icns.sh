#!/usr/bin/env bash
# Rebuild the app icon from packaging/macos/app_icon.svg (FR-79).
#
# The .icns it writes is committed, so building the app needs none of the SVG
# rasterisers below: this script is only run when the icon itself changes.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE="${SCRIPT_DIR}/packaging/macos/app_icon.svg"
TARGET="${SCRIPT_DIR}/src/cubit/menubar/assets/cubit.icns"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "iconutil is macOS only." >&2
  exit 1
fi

if [[ ! -f "${SOURCE}" ]]; then
  echo "The icon source is missing: ${SOURCE}" >&2
  exit 1
fi

# Whichever rasteriser the machine happens to have. macOS ships none that reads
# SVG, so this is the one step that needs something from Homebrew.
render() {  # render <size> <output>
  local size="$1" out="$2"
  if command -v rsvg-convert >/dev/null 2>&1; then
    rsvg-convert -w "${size}" -h "${size}" -o "${out}" "${SOURCE}"
  elif command -v inkscape >/dev/null 2>&1; then
    inkscape "${SOURCE}" --export-type=png --export-filename="${out}" \
      --export-width="${size}" --export-height="${size}" >/dev/null 2>&1
  elif command -v magick >/dev/null 2>&1; then
    magick -background none "${SOURCE}" -resize "${size}x${size}" "${out}"
  else
    echo "No SVG rasteriser found. Install one with:" >&2
    echo "  brew install librsvg        # or inkscape, or imagemagick" >&2
    exit 1
  fi
}

ICONSET="$(mktemp -d "${TMPDIR:-/tmp}/cubit-iconset.XXXXXX")/cubit.iconset"
mkdir -p "${ICONSET}"
trap 'rm -rf "$(dirname "${ICONSET}")"' EXIT

# The sizes iconutil expects, each one rendered from the vector rather than
# resampled from a bigger PNG, so the small ones stay crisp.
for size in 16 32 64 128 256 512 1024; do
  render "${size}" "${ICONSET}/icon_${size}x${size}.png"
done
for pair in "32 16" "64 32" "256 128" "512 256" "1024 512"; do
  set -- ${pair}
  cp "${ICONSET}/icon_${1}x${1}.png" "${ICONSET}/icon_${2}x${2}@2x.png"
done
rm -f "${ICONSET}/icon_64x64.png" "${ICONSET}/icon_1024x1024.png"

mkdir -p "$(dirname "${TARGET}")"
iconutil --convert icns --output "${TARGET}" "${ICONSET}"

echo "Wrote ${TARGET}"
