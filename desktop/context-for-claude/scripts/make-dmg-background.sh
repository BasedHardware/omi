#!/bin/bash
#
# Renders the drag-to-install background art for the Context for Claude disk image.
#
# This script is the SINGLE SOURCE OF TRUTH for the disk image's geometry. package-dmg.sh does not
# hardcode any of it — it runs `make-dmg-background.sh --print-geometry` and evals the result, so the
# painted arrow can never drift away from the icon positions Finder is told to use. Change a number
# here and both the art and the AppleScript follow.
#
#   ./make-dmg-background.sh                  render into Resources/DMG/
#   ./make-dmg-background.sh --print-geometry emit KEY=VALUE lines for package-dmg.sh to eval
#
# Output (Resources/DMG/):
#   background.png      what ships on the volume: the 2x raster tagged 144 ppi, so Finder lays it out
#                       at 1x points and draws it crisp on Retina (Finder never scales a background
#                       picture — it draws it at its natural *point* size, anchored top-left).
#   background@1x.png   the plain 72 ppi renders, kept for inspection and as the fallback if a Finder
#   background@2x.png   build ever mis-reads the density tag (CFC_DMG_BACKGROUND_1X=1).
#
set -euo pipefail

# PATH gets clobbered in some agent shells; make the tools we call resolvable.
export PATH="/bin:/usr/bin:/usr/sbin:/sbin:/opt/homebrew/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

APP_NAME="Context for Claude"
OUT_DIR="$PKG_DIR/Resources/DMG"

# The header is a wordmark and one sentence, and deliberately **no mark**.
#
# It used to carry the app's own glyph, lifted out of the .icns, at the top left. That put the mark
# on screen twice: Finder draws the real app icon in the left-hand slot 130 pt below it, and the
# whole point of this window is that the user drags *that* icon. A second, smaller copy of it is not
# branding, it is a decoy — the one thing an install window must not have is two things that look
# like the app. The wordmark starts on the same left margin the mark used to occupy, so the header
# block did not move; there is simply one fewer object in it.

# ------------------------------------------------------------------ geometry (points, 1x)
#
# Finder's icon view uses top-left origin and positions items by their CENTER. The background picture
# maps 1:1 onto the same space, so every number below is shared by the art and the AppleScript.
#
# Clearances that matter, at DMG_ICON_SIZE=128:
#   app icon      x 114..242   |   Applications icon  x 438..566
#   drop targets  x  90..266   |                      x 414..590   (y 168..348)
#   arrow         x 286..394   — 20 pt of air between it and each target
#   header block  y   0..120   — the targets start at y 168, so nothing collides
#   item labels   Finder draws them just under the icon (~y 315..335), inside the target box
DMG_WIN_W=680          # icon-view content width  == background width in points
DMG_WIN_H=400          # icon-view content height == background height in points
DMG_TITLEBAR_H=28      # Finder's `bounds` includes the title bar; content = bounds height - this
DMG_WIN_X=180          # where the window opens on screen
DMG_WIN_Y=140
DMG_ICON_SIZE=128
DMG_APP_X=178          # center of the .app icon
DMG_APP_Y=246
DMG_LINK_X=502         # center of the /Applications symlink icon
DMG_LINK_Y=246

# The dashed drop targets. Sized to hold a 128 pt icon plus the filename Finder draws beneath it, which
# is why the box hangs lower than the icon centre rather than being centred on it. Everything below is
# derived, so a target can never drift away from the icon it is drawn around.
TARGET_W=176
TARGET_H=180
TARGET_DY=12           # the box centre sits this far below the icon centre, to take in the label
TARGET_R=18            # corner radius
TARGET_GAP=20          # air between a target's edge and the arrow

if [[ "${1:-}" == "--print-geometry" ]]; then
    for v in DMG_WIN_W DMG_WIN_H DMG_TITLEBAR_H DMG_WIN_X DMG_WIN_Y \
             DMG_ICON_SIZE DMG_APP_X DMG_APP_Y DMG_LINK_X DMG_LINK_Y; do
        printf '%s=%s\n' "$v" "${!v}"
    done
    exit 0
fi

log()  { printf '\033[1m[dmg-bg]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[dmg-bg]\033[0m %s\n' "$*" >&2; exit 1; }

command -v magick >/dev/null || die "ImageMagick (magick) not found — brew install imagemagick"

# ------------------------------------------------------------------ palette
#
# Strictly neutral greys — R=G=B on every value here. The installer must not end up the last surface
# still wearing the borrowed Anthropic paper/clay palette that Phase 0.4 of
# docs/first-run-experience.md is deleting from the app, and a static image cannot follow the system's
# semantic colours, so it commits to a hueless light ground instead. No purple (INV-UI-1) — no hue at
# all. The app tile's own off-white then reads as the one warm object on a neutral sheet.
FIELD='#EFEFEF'        # the ground
WASH_LIGHT='#F8F8F8'   # where the light falls: across the header and the two slots
WASH_SHADE='#EAEAEA'   # the corners it falls away from
SLOT='#F7F7F7'         # the drop-target plate, one step up from the ground
SLOT_EDGE='#C6C6C6'    # its dashed outline
INK='#1C1C1C'          # the wordmark
MID='#6E6E6E'          # the one sentence
ARROW='#8A8A8A'        # weighty enough to read at a glance, muted enough not to fight the icons

FONT_DISPLAY="$PKG_DIR/Resources/Fonts/OpenRunde-Semibold.otf"
FONT_BODY="$PKG_DIR/Resources/Fonts/OpenRunde-Regular.otf"
[[ -f "$FONT_DISPLAY" ]] || FONT_DISPLAY="Helvetica-Bold"
[[ -f "$FONT_BODY" ]]    || FONT_BODY="Helvetica"

TMP="$(mktemp -d /tmp/cfc-dmg-bg.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

mkdir -p "$OUT_DIR"

render() {
    local S="$1" out="$2"
    local W=$((DMG_WIN_W * S)) H=$((DMG_WIN_H * S))

    # --- the ground: a hueless wash, light across the middle where the slots sit and falling away at
    #     the corners. Blurred hard so it reads as light on a sheet, never as shapes.
    magick -size "${W}x${H}" "xc:$FIELD" \
        -fill "$WASH_LIGHT" -draw "ellipse $((340 * S)),$((230 * S)) $((440 * S)),$((260 * S)) 0,360" \
        -fill "$WASH_LIGHT" -draw "ellipse $((150 * S)),$((40 * S)) $((260 * S)),$((120 * S)) 0,360" \
        -fill "$WASH_SHADE" -draw "ellipse $((740 * S)),$((450 * S)) $((170 * S)),$((130 * S)) 0,360" \
        -fill "$WASH_SHADE" -draw "ellipse $((-60 * S)),$((450 * S)) $((150 * S)),$((120 * S)) 0,360" \
        -fill "$WASH_SHADE" -draw "ellipse $((710 * S)),$((-40 * S)) $((130 * S)),$((100 * S)) 0,360" \
        -blur "0x$((48 * S))" \
        "$TMP/sheet-$S.png"

    # --- the two drop targets: a plate a step lighter than the ground, dashed like the affordance in
    #     the reference installer, centred on the icon positions and hanging low enough to take in the
    #     filename Finder draws under each icon.
    local tw=$((TARGET_W * S)) th=$((TARGET_H * S))
    local app_cx=$((DMG_APP_X * S))   app_cy=$(((DMG_APP_Y + TARGET_DY) * S))
    local link_cx=$((DMG_LINK_X * S)) link_cy=$(((DMG_LINK_Y + TARGET_DY) * S))
    local dash="stroke-dasharray $((7 * S)) $((5 * S))"
    magick -size "${W}x${H}" xc:none \
        -fill "$SLOT" -stroke "$SLOT_EDGE" -strokewidth $((2 * S)) \
        -draw "$dash roundrectangle $((app_cx - tw / 2)),$((app_cy - th / 2)) $((app_cx + tw / 2)),$((app_cy + th / 2)) $((TARGET_R * S)),$((TARGET_R * S))" \
        -draw "$dash roundrectangle $((link_cx - tw / 2)),$((link_cy - th / 2)) $((link_cx + tw / 2)),$((link_cy + th / 2)) $((TARGET_R * S)),$((TARGET_R * S))" \
        "$TMP/targets-$S.png"

    # --- the arrow, on the icon centre line, spanning the gap between the two targets. Both ends are
    #     derived from the target boxes, so widening a target moves the arrow instead of colliding.
    local ay=$((DMG_APP_Y * S))
    local a_x1=$(((DMG_APP_X + TARGET_W / 2 + TARGET_GAP) * S))
    local a_x2=$(((DMG_LINK_X - TARGET_W / 2 - TARGET_GAP) * S))
    local head=$((26 * S))
    local shaft_end=$((a_x2 - head))
    local half=$((4 * S))
    magick -size "${W}x${H}" xc:none \
        -fill "$ARROW" -stroke none \
        -draw "roundrectangle $a_x1,$((ay - half)) $((shaft_end + 2 * S)),$((ay + half)) $half,$half" \
        -draw "polygon $shaft_end,$((ay - 14 * S)) $shaft_end,$((ay + 14 * S)) $a_x2,$ay" \
        "$TMP/arrow-$S.png"

    # --- wordmark + the one sentence, upper left. No mark: see the note by APP_NAME.
    #
    # x=44 is the left margin the mark used to start on, so the header block still begins where it
    # always did — the type moved into the space the mark vacated rather than the whole block
    # shifting. The baselines (70 and 102) are untouched, so nothing about the header's height or its
    # clearance from the drop targets at y 168 has changed.
    magick "$TMP/sheet-$S.png" \
        "$TMP/targets-$S.png" -compose over -composite \
        "$TMP/arrow-$S.png" -compose over -composite \
        -gravity NorthWest \
        -font "$FONT_DISPLAY" -pointsize $((27 * S)) -fill "$INK" -stroke none \
        -annotate "+$((44 * S))+$((70 * S))" "$APP_NAME" \
        -font "$FONT_BODY" -pointsize $((15 * S)) -fill "$MID" \
        -annotate "+$((45 * S))+$((102 * S))" "Drag $APP_NAME into Applications to install" \
        -alpha remove -alpha off \
        -strip -dither FloydSteinberg -colors 255 \
        -colorspace sRGB -type TrueColor -define png:color-type=2 \
        -define png:compression-level=9 \
        "$out"
    # 255 dithered colours: a neutral wash plus black type needs nowhere near truecolour, and this takes
    # the 2x raster from 1.2 MB to 0.5 MB (RMSE 0.7%, invisible at 200% zoom) — the background travels
    # inside every download. TrueColor is forced because an all-grey image would otherwise be written as
    # a greyscale PNG, and Finder's background picture is safest as plain sRGB.
}

log "rendering ${DMG_WIN_W}x${DMG_WIN_H} at 1x and 2x"
render 1 "$OUT_DIR/background@1x.png"
render 2 "$OUT_DIR/background@2x.png"

# What ships on the volume. Finder draws a background picture at its natural size in POINTS and never
# scales it, so a plain 2x raster would show up twice too big. Tagging the 2x raster at 144 ppi makes
# NSImage report it as ${DMG_WIN_W}x${DMG_WIN_H} points while keeping every device pixel — the layout
# is identical to 1x and Retina gets a sharp image. sips writes the tag; ImageMagick's -density/-units
# pair silently converts to PixelsPerCentimeter here and lands on 56.69 ppi instead.
cp "$OUT_DIR/background@2x.png" "$OUT_DIR/background.png"
sips -s dpiWidth 144 -s dpiHeight 144 "$OUT_DIR/background.png" >/dev/null
[[ "$(magick identify -format '%x %U' "$OUT_DIR/background.png")" == "144 PixelsPerInch" ]] \
    || die "background.png did not take the 144 ppi tag — Finder would draw it at twice its point size"

for f in background.png background@1x.png background@2x.png; do
    log "$(magick identify -format '%f  %wx%h px  %x ppi' "$OUT_DIR/$f")"
done
