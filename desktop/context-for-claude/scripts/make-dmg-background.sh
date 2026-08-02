#!/bin/bash
#
# Renders the drag-to-install background art for the Context for Claude disk image.
#
# This script is the SINGLE SOURCE OF TRUTH for the disk image's geometry. package-dmg.sh does not
# hardcode any of it — it runs `make-dmg-background.sh --print-geometry` and evals the result, so the
# painted flight path can never drift away from the icon positions Finder is told to use. Change a
# number here and both the art and the AppleScript follow.
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
#
# The ghost tile the art now flies along the path is bound by the same rule, and is drawn — not
# lifted from the .icns — for exactly that reason. See the note above GHOST_SIZE.

# ------------------------------------------------------------------ geometry (points, 1x)
#
# Finder's icon view uses top-left origin and positions items by their CENTER. The background picture
# maps 1:1 onto the same space, so every number below is shared by the art and the AppleScript.
#
# Clearances that matter, at DMG_ICON_SIZE=128:
#   app icon      x 106..234   |   Applications icon  x 486..614
#   drop targets  x  82..258   |                      x 462..638   (y 168..348)
#   flight path   x 278..442   — the corridor between the targets, 20 pt of air at each end
#   ghost tile    x 310..404   (y 149..243) — the tilted tile's bounds, inside the corridor and
#                 clear of both targets and the header; asserted below rather than trusted, because
#                 it is derived from a curve
#   header block  y   0..120   — the targets start at y 168, so nothing collides
#   item labels   Finder draws them just under the icon (~y 315..335), inside the target box
#
# The window is 720 pt wide rather than the 680 it shipped at. The corridor between the two targets
# was 108 pt, which is enough for a straight arrow and not enough for what the art has to show now:
# a dotted path *and* a tile in flight on it, with the path still legible on both sides of the tile.
# Widening the window and pushing the two slots apart buys the corridor 164 pt; the outer margins
# stay symmetric at 82 pt.
DMG_WIN_W=720          # icon-view content width  == background width in points
DMG_WIN_H=400          # icon-view content height == background height in points
DMG_TITLEBAR_H=28      # Finder's `bounds` includes the title bar; content = bounds height - this
DMG_WIN_X=180          # where the window opens on screen
DMG_WIN_Y=140
DMG_ICON_SIZE=128
DMG_APP_X=170          # center of the .app icon
DMG_APP_Y=246
DMG_LINK_X=550         # center of the /Applications symlink icon
DMG_LINK_Y=246

# The dashed drop targets. Sized to hold a 128 pt icon plus the filename Finder draws beneath it, which
# is why the box hangs lower than the icon centre rather than being centred on it. Everything below is
# derived, so a target can never drift away from the icon it is drawn around.
TARGET_W=176
TARGET_H=180
TARGET_DY=12           # the box centre sits this far below the icon centre, to take in the label
TARGET_R=18            # corner radius
TARGET_GAP=20          # air between a target's edge and the flight path
HEADER_H=120           # the band the wordmark and its sentence own; nothing else may enter it

if [[ "${1:-}" == "--print-geometry" ]]; then
    for v in DMG_WIN_W DMG_WIN_H DMG_TITLEBAR_H DMG_WIN_X DMG_WIN_Y \
             DMG_ICON_SIZE DMG_APP_X DMG_APP_Y DMG_LINK_X DMG_LINK_Y; do
        printf '%s=%s\n' "$v" "${!v}"
    done
    exit 0
fi
# Only the ten keys above cross into package-dmg.sh, because those are the only ones Finder needs:
# where the window opens, how big it is, and where the two icons go. Everything from here down
# describes paint, and paint that package-dmg.sh cannot see cannot drift away from it.

log()  { printf '\033[1m[dmg-bg]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[dmg-bg]\033[0m %s\n' "$*" >&2; exit 1; }

command -v magick >/dev/null || die "ImageMagick (magick) not found — brew install imagemagick"

# ------------------------------------------------------------------ the flight path
#
# What the window has to teach is a *gesture*, and the old art did not show one: a plain arrow between
# two slots states a direction and leaves the user to infer everything else. So the art now depicts the
# drag itself — the icon partway to Applications, on a dotted trail, with the ring it lands in drawn
# hotter than the one it left. Finder cannot animate a background picture, so this is the single frame
# that carries the most motion: object in transit, path behind and ahead of it, destination marked.
#
# It is an arc, not a straight line, and the arc is doing work rather than decoration. A hand dragging
# a file lifts it, carries it, and sets it down; a straight dotted line is just a dashed arrow and
# reads as static. The lift also separates the trail from the tile *vertically*, so the dots stay
# visible above and below the tile instead of disappearing behind it — on a straight line the tile
# would sit on the trail and eat the middle third of it.
#
# A cubic, not a quadratic, because a symmetric arc arrives at the destination diving at ~50° — it
# reads as plunging past the target rather than settling into it. The second control point flattens
# the approach to ~29°, so the arrowhead points into the ring.
FLIGHT_X0=$(( DMG_APP_X + TARGET_W / 2 + TARGET_GAP ))    # leaves the source slot's edge, on the
FLIGHT_Y0=$DMG_APP_Y                                      # icon centre line
FLIGHT_X3=$(( DMG_LINK_X - TARGET_W / 2 - TARGET_GAP ))   # and stops at the destination slot's edge
FLIGHT_LIFT=96         # how far the first control point pulls the curve up off the centre line
FLIGHT_SETTLE=32       # ... and the second, which flattens the arrival
FLIGHT_DROP_DY=8       # the path lands this far above the centre line, at the ring's upper left
FLIGHT_Y3=$(( DMG_APP_Y - FLIGHT_DROP_DY ))
FLIGHT_C1X=$(( FLIGHT_X0 + (FLIGHT_X3 - FLIGHT_X0) * 27 / 100 ))
FLIGHT_C1Y=$(( DMG_APP_Y - FLIGHT_LIFT ))
FLIGHT_C2X=$(( FLIGHT_X0 + (FLIGHT_X3 - FLIGHT_X0) * 74 / 100 ))
FLIGHT_C2Y=$(( DMG_APP_Y - FLIGHT_SETTLE ))

DOT_SPACING=10         # centre to centre along the arc, measured in arc length rather than in t so
DOT_R=2.9              # the trail does not bunch up where the curve slows down
HEAD_LEN=9.5           # the arrowhead that terminates the trail, pointing along the tangent. Kept
HEAD_W=4.6              # barely heavier than a dot: it is punctuation on the trail, not a second arrow

# The tile in flight. It is drawn — a blank squircle with the app icon's proportions and off-white
# ground — and NOT the app's glyph lifted out of the .icns, for two reasons that point the same way:
#
#   1. the decoy rule above. A recognisable second copy of the mark is the exact thing the header was
#      stripped of. Faded and shrunk it is weaker, but "weaker decoy" is still a decoy; a *blank* tile
#      cannot be mistaken for a second installable item because it has no identity to mistake.
#   2. the art would otherwise depend on the .icns again, and package-dmg.sh deliberately stopped
#      repainting when the .icns changes. Re-reading it would silently reintroduce stale art.
#
# What makes it read as the icon in flight is not its face, it is its situation: two thirds of the real
# icon's size, translucent, lifted off the sheet by a soft shadow, sitting on a trail that runs from the
# slot that holds the real icon to the slot it is going to. Nothing else in the window is off the ground.
GHOST_SIZE=84          # 66% of DMG_ICON_SIZE — near enough to read as the same object, far enough
GHOST_T=48             # to read as away from it. At 48% along the arc: past the lift, road ahead.
GHOST_R=$(( GHOST_SIZE * 22 / 100 ))   # the app icon's squircle radius, as a fraction of its side
GHOST_LIFT=8           # how far its shadow sits below it

# And it is tilted, which is the cheapest anti-decoy device available: Finder never draws an item
# rotated. A square tile among square boxes is a thing sitting somewhere; the same tile off-square is
# a thing being carried, and it cannot be misread as a third installable item no matter how solid the
# fill gets, because no icon in any Finder window has ever looked like that.
GHOST_TILT=7           # degrees clockwise

# Where GHOST_T lands on the curve, and how far the *tilted* tile actually reaches from that point.
# Rotating a square grows its axis-aligned bounds by cos+sin of the angle, and it is those bounds — not
# the 84 pt side — that have to clear the icons. Derived here so the assertions below, the art, and the
# comment block above all read the same numbers.
read -r GHOST_CX GHOST_CY GHOST_HALF < <(
    awk -v t="$GHOST_T" -v side="$GHOST_SIZE" -v tilt="$GHOST_TILT" \
        -v x0="$FLIGHT_X0" -v y0="$FLIGHT_Y0" -v cx1="$FLIGHT_C1X" -v cy1="$FLIGHT_C1Y" \
        -v cx2="$FLIGHT_C2X" -v cy2="$FLIGHT_C2Y" -v x3="$FLIGHT_X3" -v y3="$FLIGHT_Y3" '
        BEGIN {
            t /= 100; u = 1 - t
            a = u*u*u; b = 3*u*u*t; c = 3*u*t*t; d = t*t*t
            r = tilt * 3.14159265358979 / 180
            printf "%d %d %d\n", int(a*x0 + b*cx1 + c*cx2 + d*x3 + 0.5), \
                                 int(a*y0 + b*cy1 + c*cy2 + d*y3 + 0.5), \
                                 int(side / 2 * (cos(r) + sin(r)) + 0.999)
        }'
)

# The tile is a picture of the drag, so it must never sit where a real icon does — a translucent tile
# overlapping the app icon or the Applications alias would read as a rendering bug, and one sitting in
# a slot would read as a third thing to drag. These hold by construction today; they are asserted
# because GHOST_CX/CY come out of a curve, and a curve is exactly the kind of number that moves when
# someone retunes FLIGHT_LIFT and looks only at the middle of the window.
GHOST_L=$(( GHOST_CX - GHOST_HALF ));      GHOST_R_EDGE=$(( GHOST_CX + GHOST_HALF ))
GHOST_T_EDGE=$(( GHOST_CY - GHOST_HALF )); GHOST_B=$(( GHOST_CY + GHOST_HALF + GHOST_LIFT ))
(( GHOST_L > DMG_APP_X + TARGET_W / 2 )) \
    || die "ghost tile (x $GHOST_L) overlaps the app drop target (ends x $(( DMG_APP_X + TARGET_W / 2 )))"
(( GHOST_R_EDGE < DMG_LINK_X - TARGET_W / 2 )) \
    || die "ghost tile (x $GHOST_R_EDGE) overlaps the Applications drop target (starts x $(( DMG_LINK_X - TARGET_W / 2 )))"
(( GHOST_T_EDGE > HEADER_H )) \
    || die "ghost tile (y $GHOST_T_EDGE) reaches into the header band (y 0..$HEADER_H)"
(( GHOST_B < DMG_WIN_H )) || die "ghost tile (y $GHOST_B) falls off the bottom of the window"

# ------------------------------------------------------------------ palette
#
# Strictly neutral greys — R=G=B on every value here. The installer must not end up the last surface
# still wearing the borrowed Anthropic paper/clay palette that Phase 0.4 of
# docs/first-run-experience.md is deleting from the app, and a static image cannot follow the system's
# semantic colours, so it commits to a hueless light ground instead. No purple (INV-UI-1) — no hue at
# all, which is asserted on the finished raster rather than argued for here. The app tile's own
# off-white then reads as the one warm object on a neutral sheet.
FIELD='#EFEFEF'        # the ground
WASH_LIGHT='#F6F6F6'   # where the light falls: across the header and the two slots
WASH_SHADE='#EAEAEA'   # the corners it falls away from
SLOT='#F7F7F7'         # the source drop-target plate, one step up from the ground
SLOT_EDGE='#C6C6C6'    # and its dashed outline, quiet: the icon is already sitting in it
SLOT_DROP='#FCFCFC'    # the destination plate, brighter — this is the one being aimed at
SLOT_EDGE_DROP='#9C9C9C'  # and its ring, dark enough to read as the live drop target from across
                          # the window. The asymmetry between the two rings is the sentence
                          # "from here, to there" said without words.
INK='#1C1C1C'          # the wordmark
MID='#6E6E6E'          # the one sentence
TRAIL='#8A8A8A'        # the dotted flight path and its arrowhead: weighty enough to read at a
                       # glance, muted enough not to fight the icons
GHOST_FILL='#FFFFFF'   # the tile in flight, and the line around it
GHOST_EDGE='#9E9E9E'

FONT_DISPLAY="$PKG_DIR/Resources/Fonts/OpenRunde-Semibold.otf"
FONT_BODY="$PKG_DIR/Resources/Fonts/OpenRunde-Regular.otf"
[[ -f "$FONT_DISPLAY" ]] || FONT_DISPLAY="Helvetica-Bold"
[[ -f "$FONT_BODY" ]]    || FONT_BODY="Helvetica"

TMP="$(mktemp -d /tmp/cfc-dmg-bg.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

mkdir -p "$OUT_DIR"

# The dots and the arrowhead, as MVG, at a given scale.
#
# The trail is placed by ARC LENGTH, not by stepping t: a cubic travels slowest around its apex, so
# even steps in t bunch the dots exactly where the tile already crowds them. awk walks the curve
# finely, accumulates length, and then drops a dot every DOT_SPACING points of that length.
#
# The trail runs *unbroken*, straight under the tile, and the tile is composited over it. That is the
# one thing in the picture doing two jobs at once: it keeps the dotted line reading as a line rather
# than as two stubs (the tile is 76 pt of a 164 pt corridor — cut a hole in the trail for it and what
# is left either side is three dots and a rumour), and the dots visible *through* the tile are what
# prove the tile is translucent. On a near-white sheet, a near-white shape cannot look ghostly on its
# own; it looks ghostly when you can see the path continue behind it.
#
# Opacity ramps from 0.42 at the source to 0.95 at the arrowhead. The window's whole job is to move
# the eye to the right, and a trail that brightens as it goes does that on its own.
flight_mvg() {   # flight_mvg <scale>
    awk -v S="$1" \
        -v x0="$FLIGHT_X0" -v y0="$FLIGHT_Y0" -v cx1="$FLIGHT_C1X" -v cy1="$FLIGHT_C1Y" \
        -v cx2="$FLIGHT_C2X" -v cy2="$FLIGHT_C2Y" -v x3="$FLIGHT_X3" -v y3="$FLIGHT_Y3" \
        -v spacing="$DOT_SPACING" -v dotr="$DOT_R" -v headl="$HEAD_LEN" -v headw="$HEAD_W" '
    function bx(t,  u) { u = 1 - t; return u*u*u*x0 + 3*u*u*t*cx1 + 3*u*t*t*cx2 + t*t*t*x3 }
    function by(t,  u) { u = 1 - t; return u*u*u*y0 + 3*u*u*t*cy1 + 3*u*t*t*cy2 + t*t*t*y3 }
    BEGIN {
        N = 2000
        px[0] = bx(0); py[0] = by(0); len[0] = 0
        for (i = 1; i <= N; i++) {
            px[i] = bx(i / N); py[i] = by(i / N)
            len[i] = len[i-1] + sqrt((px[i]-px[i-1])^2 + (py[i]-py[i-1])^2)
        }
        total = len[N]
        stop  = total - headl - 4          # leave the last stretch to the arrowhead
        # Walked BACKWARDS from the arrowhead, not forwards from the source. The curve is not a whole
        # number of DOT_SPACINGs long, so one end has to absorb the remainder; stepping forwards puts
        # that slack between the last dot and the head, which is the one join anybody looks at.
        i = N
        for (s = stop; s >= 5; s -= spacing) {
            while (i > 1 && len[i-1] >= s) i--
            x = px[i]; y = py[i]
            o = 0.42 + 0.53 * (s / total)
            printf "fill-opacity %.2f circle %.1f,%.1f %.1f,%.1f\n", \
                   o, x*S, y*S, x*S, (y + dotr)*S
        }
        # the head, aimed along the tangent at the very end of the curve
        tx = px[N]; ty = py[N]
        dx = px[N] - px[N-40]; dy = py[N] - py[N-40]
        m = sqrt(dx*dx + dy*dy); dx /= m; dy /= m
        bxp = tx - dx*headl; byp = ty - dy*headl
        printf "fill-opacity 0.95 polygon %.1f,%.1f %.1f,%.1f %.1f,%.1f\n", \
               tx*S, ty*S, \
               (bxp - dy*headw)*S, (byp + dx*headw)*S, \
               (bxp + dy*headw)*S, (byp - dx*headw)*S
    }'
}

render() {
    local S="$1" out="$2"
    local W=$((DMG_WIN_W * S)) H=$((DMG_WIN_H * S))

    # --- the ground: a hueless wash, light across the middle where the slots sit and falling away at
    #     the corners. Blurred hard so it reads as light on a sheet, never as shapes.
    magick -size "${W}x${H}" "xc:$FIELD" \
        -fill "$WASH_LIGHT" -draw "ellipse $((360 * S)),$((230 * S)) $((460 * S)),$((260 * S)) 0,360" \
        -fill "$WASH_LIGHT" -draw "ellipse $((150 * S)),$((40 * S)) $((260 * S)),$((120 * S)) 0,360" \
        -fill "$WASH_SHADE" -draw "ellipse $((780 * S)),$((450 * S)) $((170 * S)),$((130 * S)) 0,360" \
        -fill "$WASH_SHADE" -draw "ellipse $((-60 * S)),$((450 * S)) $((150 * S)),$((120 * S)) 0,360" \
        -fill "$WASH_SHADE" -draw "ellipse $((750 * S)),$((-40 * S)) $((130 * S)),$((100 * S)) 0,360" \
        -blur "0x$((48 * S))" \
        "$TMP/sheet-$S.png"

    # --- the two drop targets: a plate a step lighter than the ground, dashed like the affordance in
    #     the reference installer, centred on the icon positions and hanging low enough to take in the
    #     filename Finder draws under each icon. The destination gets a soft halo behind its plate and
    #     a darker ring, so the two boxes are not interchangeable at a glance.
    local tw=$((TARGET_W * S)) th=$((TARGET_H * S))
    local app_cx=$((DMG_APP_X * S))   app_cy=$(((DMG_APP_Y + TARGET_DY) * S))
    local link_cx=$((DMG_LINK_X * S)) link_cy=$(((DMG_LINK_Y + TARGET_DY) * S))
    local halo=$((16 * S))
    local dash="stroke-dasharray $((7 * S)) $((5 * S))"
    magick -size "${W}x${H}" xc:none \
        -fill "rgba(255,255,255,0.95)" -stroke none \
        -draw "roundrectangle $((link_cx - tw / 2 - halo)),$((link_cy - th / 2 - halo)) $((link_cx + tw / 2 + halo)),$((link_cy + th / 2 + halo)) $((TARGET_R * S)),$((TARGET_R * S))" \
        -blur "0x$((14 * S))" \
        -fill "$SLOT" -stroke "$SLOT_EDGE" -strokewidth $((2 * S)) \
        -draw "$dash roundrectangle $((app_cx - tw / 2)),$((app_cy - th / 2)) $((app_cx + tw / 2)),$((app_cy + th / 2)) $((TARGET_R * S)),$((TARGET_R * S))" \
        -fill "$SLOT_DROP" -stroke "$SLOT_EDGE_DROP" \
        -draw "$dash roundrectangle $((link_cx - tw / 2)),$((link_cy - th / 2)) $((link_cx + tw / 2)),$((link_cy + th / 2)) $((TARGET_R * S)),$((TARGET_R * S))" \
        "$TMP/targets-$S.png"

    # --- the dotted flight path and its arrowhead.
    magick -size "${W}x${H}" xc:none \
        -fill "$TRAIL" -stroke none \
        -draw "$(flight_mvg "$S")" \
        "$TMP/flight-$S.png"

    # --- the tile in flight: a soft shadow on the sheet, then the tile itself over it, translucent
    #     enough that the trail's tone shows through the edges and it never reads as a solid object
    #     someone forgot to place in a slot.
    # Drawn square and rotated afterwards, so these are the UNROTATED edges — GHOST_L/GHOST_R_EDGE are
    # the grown bounds the clearance assertions use and would draw an 94 pt tile if used here.
    local grad=$((GHOST_R * S))
    local gx1=$(((GHOST_CX - GHOST_SIZE / 2) * S)) gy1=$(((GHOST_CY - GHOST_SIZE / 2) * S))
    local gx2=$(((GHOST_CX + GHOST_SIZE / 2) * S)) gy2=$(((GHOST_CY + GHOST_SIZE / 2) * S))
    magick -size "${W}x${H}" xc:none \
        -fill "rgba(0,0,0,0.22)" -stroke none \
        -draw "roundrectangle $((gx1 + 3 * S)),$((gy1 + GHOST_LIFT * S)) $((gx2 - 3 * S)),$((gy2 + GHOST_LIFT * S)) $grad,$grad" \
        -blur "0x$((8 * S))" \
        -fill "$GHOST_FILL" -stroke "$GHOST_EDGE" -strokewidth $((2 * S)) \
        -draw "fill-opacity 0.62 stroke-opacity 0.72 roundrectangle $gx1,$gy1 $gx2,$gy2 $grad,$grad" \
        -virtual-pixel transparent \
        -distort SRT "$((GHOST_CX * S)),$((GHOST_CY * S)) 1 $GHOST_TILT" \
        "$TMP/ghost-$S.png"

    # --- wordmark + the one sentence, upper left. No mark: see the note by APP_NAME.
    #
    # x=44 is the left margin the mark used to start on, so the header block still begins where it
    # always did — the type moved into the space the mark vacated rather than the whole block
    # shifting. The baselines (70 and 102) are untouched, so nothing about the header's height or its
    # clearance from the drop targets at y 168 has changed.
    # The base is promoted to sRGB TrueColor BEFORE anything is composited onto it, and that is not
    # tidiness. Every colour in the sheet is R=G=B, so ImageMagick writes it as a two-channel greyscale
    # PNG — and a composite takes the colourspace of the image it is compositing *onto*. Reading that
    # file back as the base therefore flattens the chroma out of every layer that lands on it. Today
    # every layer is grey anyway so nothing is lost, but it means a coloured element added to the
    # targets, the trail or the tile would silently render grey, and the INV-UI-1 check at the end of
    # this function — which measures the finished raster — could never see the thing it is there to
    # catch. Verified: with this line removed, a purple TRAIL renders grey and the check still passes.
    magick "$TMP/sheet-$S.png" -colorspace sRGB -type TrueColor \
        "$TMP/targets-$S.png" -compose over -composite \
        "$TMP/flight-$S.png" -compose over -composite \
        "$TMP/ghost-$S.png" -compose over -composite \
        -gravity NorthWest \
        -font "$FONT_DISPLAY" -pointsize $((27 * S)) -fill "$INK" -stroke none \
        -annotate "+$((44 * S))+$((70 * S))" "$APP_NAME" \
        -font "$FONT_BODY" -pointsize $((15 * S)) -fill "$MID" \
        -annotate "+$((45 * S))+$((102 * S))" "Drag $APP_NAME into Applications to install" \
        -alpha remove -alpha off \
        -strip +dither -colors 255 \
        -colorspace sRGB -type TrueColor -define png:color-type=2 \
        -define png:compression-level=9 \
        "$out"
    # 255 colours, and explicitly NOT dithered: a neutral wash plus black type needs nowhere near
    # truecolour, and the background travels inside every download. `-dither FloydSteinberg` was the
    # obvious setting and is the wrong one here — asked to dither, the quantiser collapses the palette
    # to 29 greys and leans on error diffusion to fake the rest, which both costs fidelity and fills
    # the smooth areas with noise that PNG cannot compress. Measured on this art, @2x:
    #
    #     unquantised           334 kB   12838 colours   (reference)
    #     -dither FloydSteinberg 175 kB      29 colours   RMSE 0.84%
    #     +dither                115 kB     226 colours   RMSE 0.068%
    #
    # Undithered is smaller AND twelve times closer to the reference, because 226 greys across the
    # narrow range this image occupies leaves nothing to band. TrueColor is forced because an all-grey
    # image would otherwise be written as a greyscale PNG, and Finder's background picture is safest as
    # plain sRGB.

    # INV-UI-1 on the artifact rather than on the palette constants: every colour above is R=G=B, so a
    # finished raster that carries any saturation at all means something introduced a hue — a stray
    # fill, a font atlas, a quantiser choosing off-grey neighbours. Purple cannot survive a check that
    # rejects *all* hue, and this is the only form of the rule a static image can be held to.
    local sat; sat="$(magick "$out" -colorspace HSL -channel G -separate -format '%[fx:maxima]' info:)"
    [[ "$sat" == "0" ]] || die "$(basename "$out") is not hueless (max saturation $sat) — INV-UI-1"
}

log "rendering ${DMG_WIN_W}x${DMG_WIN_H} at 1x and 2x"
log "flight path x $FLIGHT_X0..$FLIGHT_X3, ghost tile ${GHOST_SIZE}pt tilted ${GHOST_TILT}° at $GHOST_CX,$GHOST_CY (bounds x $GHOST_L..$GHOST_R_EDGE, y $GHOST_T_EDGE..$(( GHOST_CY + GHOST_HALF )))"
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
