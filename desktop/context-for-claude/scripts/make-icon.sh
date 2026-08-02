#!/bin/bash
#
# Regenerates Resources/ContextForClaude.icns from the mark drawn in
# Sources/ContextApp/MenuBar/ContextMark.swift.
#
# ContextMark draws the app's mark (round head, two vertical-oval eyes, two curved legs) as
# vector paths inside a 20x20 design box — see ContextMark.swift's `draw(in:struckThrough:)`,
# roughly lines 36-68. The GEOMETRY table embedded in the Python helper below is a direct
# transcription of those NSRect/NSPoint literals, not a redrawing by eye, so the icon and the
# menu bar mark cannot silently drift apart. If ContextMark.swift's geometry ever changes,
# update the matching numbers here in the same commit — nothing enforces that automatically.
#
# What this script adds on top of the mark itself:
#   - a near-white rounded tile matching the app's own Ink.surface (NSColor.controlBackgroundColor,
#     white in light mode — see Sources/ContextApp/Onboarding/Ink.swift), with a hairline border so
#     a white icon still reads against a white Finder/Dock background
#   - ~10% margin between the tile and the canvas edge, following macOS's icon-grid convention, so
#     the icon does not read as oversized next to other apps
#   - a small legibility floor on stroke width and eye size at tiny target sizes, following the
#     same principle ContextMark.swift documents applying to its own 18pt menu bar rendering
#     (its header comment: stroke thickened, eyes enlarged, "until the silhouette survives at the
#     size it is actually used")
#
# Each iconset member is rendered fresh as vector primitives at its own target resolution
# (ImageMagick MVG), not rasterized once at 1024 and downscaled, so small sizes stay crisp.
#
# Requires: ImageMagick (magick), iconutil, python3 — all present on a normal macOS + Homebrew
# checkout. Safe to re-run: every size is regenerated from scratch into a fresh temp iconset and
# the destination .icns is only overwritten once iconutil succeeds.
#
# Usage: scripts/make-icon.sh

set -euo pipefail

export PATH="/bin:/usr/bin:/usr/sbin:/sbin:/opt/homebrew/bin:$PATH"

log()  { printf '\033[1m[make-icon]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[make-icon]\033[0m %s\n' "$*" >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUT_ICNS="$PACKAGE_ROOT/Resources/ContextForClaude.icns"
MAGICK="${MAGICK_BIN:-/opt/homebrew/bin/magick}"

command -v "$MAGICK" >/dev/null 2>&1 || die "ImageMagick not found at $MAGICK (set MAGICK_BIN)"
command -v iconutil >/dev/null 2>&1 || die "iconutil not found"
command -v python3 >/dev/null 2>&1 || die "python3 not found"

WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/context-icon.XXXXXX")"
trap 'rm -rf "$WORK_DIR"' EXIT
ICONSET_DIR="$WORK_DIR/ContextForClaude.iconset"
mkdir -p "$ICONSET_DIR"

# size:filename pairs iconutil requires for a complete .icns. Sizes repeat (32, 256, 512) because
# each is both the @1x asset for one slot and the @2x asset for the slot below it — iconutil wants
# both files present even though the pixels are identical.
ICONSET_MEMBERS=(
  "16:icon_16x16.png"
  "32:icon_16x16@2x.png"
  "32:icon_32x32.png"
  "64:icon_32x32@2x.png"
  "128:icon_128x128.png"
  "256:icon_128x128@2x.png"
  "256:icon_256x256.png"
  "512:icon_256x256@2x.png"
  "512:icon_512x512.png"
  "1024:icon_512x512@2x.png"
)

# Renders one square PNG at $1 px into $2 by generating an MVG (ImageMagick's native vector
# format) from the geometry table and rasterizing it directly at that resolution.
render_size() {
  local size="$1" out="$2"
  local mvg="$WORK_DIR/icon_${size}.mvg"

  python3 - "$size" > "$mvg" <<'PY'
import sys

N = float(sys.argv[1])

# --- macOS icon-grid convention: the glyph sits on a tile with roughly 10% margin per side so
# it doesn't read as oversized next to every other app in the Dock / Finder / Screen Recording
# picker. ---
MARGIN_RATIO = 0.098          # tile occupies ~80.4% of the canvas, centered
CORNER_RATIO = 0.225          # rounded-rect corner radius as a fraction of the tile side
TILE_FILL = "white"           # Ink.surface == NSColor.controlBackgroundColor, white in light mode
TILE_BORDER = "#DADADA"       # hairline so a white icon still reads against a white background
TILE_BORDER_RATIO = 0.006

# --- Small-size legibility floor. ContextMark.swift documents thickening its own stroke and
# enlarging its own eyes so the silhouette survives at the 18pt menu bar size; the same floor is
# applied here so the smallest iconset members don't fade into hairlines. It is a max(), so it is
# a no-op once the natural scale exceeds it (64px and up). ---
MIN_STROKE_PX = 1.35
MIN_EYE_RX_PX = 0.55
MIN_EYE_RY_PX = 0.75

# The 16px slot is a special case, verified by eye (see make-icon.sh's usage comment / commit
# message): at N=16 the leg attachment sits so close to the head's bottom stroke — by design, the
# legs start half a unit *inside* the head oval, see ContextMark.swift's own p(7.7, 6.4) vs. the
# head's y: 5.9 — that the default margin and stroke floor above fuse the head-bottom arc and the
# legs into one blob. Below 20px only, trade some of the tile margin back to the glyph and use a
# lighter stroke floor, which opens a visible gap again without changing anything above 32px.
if N < 20:
    MARGIN_RATIO = 0.06
    MIN_STROKE_PX = 1.0
    MIN_EYE_RX_PX = 0.5
    MIN_EYE_RY_PX = 0.6

tile = N * (1 - 2 * MARGIN_RATIO)
origin = (N - tile) / 2
s = tile / 20.0  # ContextMark's design box is 20x20 (ContextMark.swift line ~34-38).


def X(x):
    return origin + x * s


def Y(y_appkit):
    # ContextMark draws in AppKit's y-up space (NSBezierPath on a non-flipped NSImage). MVG is
    # y-down, so flip within the 20-unit design box before scaling and offsetting.
    return origin + (20.0 - y_appkit) * s


# ---- Geometry transcribed from ContextMark.swift `draw(in:struckThrough:)` ----

# Head: NSBezierPath(ovalIn: NSRect(x: 3.4, y: 5.9, width: 13.2, height: 12.6)), stroke 1.9 * s.
head_cx = X(3.4 + 13.2 / 2)
head_cy = Y(5.9 + 12.6 / 2)
head_rx = 13.2 / 2 * s
head_ry = 12.6 / 2 * s
head_stroke = max(1.9 * s, MIN_STROKE_PX)

# Eyes: vertical ovals at x centers [7.9, 12.1], NSRect(width: 1.56, height: 2.1), y: 11.0.
eyes = []
for cx in (7.9, 12.1):
    ex = X(cx)
    ey = Y(11.0 + 2.1 / 2)
    erx = max(1.56 / 2 * s, MIN_EYE_RX_PX)
    ery = max(2.1 / 2 * s, MIN_EYE_RY_PX)
    eyes.append((ex, ey, erx, ery))

# Legs: straight down out of the head, then a short foot curving outward. Mirrored around x = 10;
# the right leg's x literals in ContextMark.swift are each 20 - (the left leg's).
leg_stroke = max(1.7 * s, MIN_STROKE_PX)


def leg_path(x0, x1, cx1, cx2, x2):
    return (
        f"M {X(x0):.3f},{Y(6.4):.3f} "
        f"L {X(x1):.3f},{Y(3.3):.3f} "
        f"C {X(cx1):.3f},{Y(2.7):.3f} {X(cx2):.3f},{Y(2.5):.3f} {X(x2):.3f},{Y(2.6):.3f}"
    )


left_leg = leg_path(7.7, 7.3, 7.2, 6.5, 5.8)
right_leg = leg_path(12.3, 12.7, 12.8, 13.5, 14.2)

border_w = max(tile * TILE_BORDER_RATIO, 1.0)
corner = tile * CORNER_RATIO

mvg = []
mvg.append("push graphic-context")
mvg.append(f"viewbox 0 0 {N:.0f} {N:.0f}")

# Tile.
mvg.append(f"fill {TILE_FILL} stroke {TILE_BORDER} stroke-width {border_w:.3f}")
mvg.append(
    f"roundrectangle {origin:.3f},{origin:.3f} {origin + tile:.3f},{origin + tile:.3f} "
    f"{corner:.3f},{corner:.3f}"
)

# Head.
mvg.append(f"fill none stroke black stroke-width {head_stroke:.3f}")
mvg.append(f"ellipse {head_cx:.3f},{head_cy:.3f} {head_rx:.3f},{head_ry:.3f} 0,360")

# Eyes.
mvg.append("fill black stroke none")
for ex, ey, erx, ery in eyes:
    mvg.append(f"ellipse {ex:.3f},{ey:.3f} {erx:.3f},{ery:.3f} 0,360")

# Legs.
mvg.append(
    f"fill none stroke black stroke-width {leg_stroke:.3f} "
    f"stroke-linecap round stroke-linejoin round"
)
mvg.append(f"path '{left_leg}'")
mvg.append(f"path '{right_leg}'")

mvg.append("pop graphic-context")

print("\n".join(mvg))
PY

  "$MAGICK" -size "${size}x${size}" -background none "mvg:$mvg" -antialias "PNG32:$out"
}

log "rendering iconset members"
for member in "${ICONSET_MEMBERS[@]}"; do
  size="${member%%:*}"
  name="${member##*:}"
  render_size "$size" "$ICONSET_DIR/$name"
  log "  $name (${size}x${size})"
done

TMP_ICNS="$WORK_DIR/ContextForClaude.icns"
iconutil -c icns "$ICONSET_DIR" -o "$TMP_ICNS"
mv "$TMP_ICNS" "$OUT_ICNS"
log "wrote $OUT_ICNS"
