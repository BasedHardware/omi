// WHERE to draw a halo around the active window — and whether to draw one at all.
// Pure geometry: this module has no idea what a halo MEANS (that is glowPresets.ts)
// and no idea how one looks.
//
// Electron-free ON PURPOSE (pure functions over plain rects) so every gate below is
// unit-testable — the bug this module exists to prevent is a geometry bug, and
// geometry bugs are only caught by arithmetic, not by looking at the app.
//
// GOVERNING RULE: any failed gate ⇒ draw NOTHING. There is no "partially valid"
// halo. The v1 defect the user saw ("one long bar a couple centimetres above the
// bottom of my screen") WAS a partially-valid halo: four edge bands were computed
// from GetWindowRect, which for a maximized window deliberately hangs off-screen,
// so three bands fell off the display and only the bottom one was left. Better to
// show nothing than to show a fragment.
//
// ALL rects here are DIP (CSS px), never physical: the caller converts the DWM
// extended frame bounds to DIP (screen.screenToDipRect) BEFORE calling in, and
// every constant below (pad, radius, min size) is a DIP quantity. Padding a
// physical rect would under-pad at 150% scaling and yield a visibly thinner halo
// on scaled displays.

export type Rect = { x: number; y: number; width: number; height: number }

/** The subset of Electron's Display we need — keeps this module Electron-free. */
export type DisplayLike = { bounds: Rect; workArea: Rect }

/**
 * Overlay inflation per side. Two things must fit inside it:
 *
 *  - The glow's own reach. The outermost shadow layer is `0 0 84px 16px`, so it
 *    reaches spread + blur/2 ≈ 58 DIP. If the pad were smaller, the window's edge
 *    would CLIP the tail — and a clipped glow ends in a hard straight line, which
 *    reads as exactly the "rough / not seamless" edge we are trying to remove.
 *  - ~20 DIP of transparent margin on top of that, which absorbs DWM's
 *    unconditional rounding of OUR overlay window's corners (Win11 rounds every
 *    top-level window and Electron cannot opt out — `roundedCorners` is
 *    macOS-only). Without it the halo's corners sit inside the clipped region and
 *    "don't connect" — the same visual defect the four-window build had, from a
 *    completely different cause.
 *
 * Raise this whenever you extend the outermost shadow layer. It is DIP, so it
 * scales itself on a 150% display.
 */
export const WINDOW_PAD = 80
/**
 * How far the ring is pulled INSIDE the target's edge, so the glow's bright core
 * lands ON the window's own edge pixels instead of starting just outside them.
 *
 * Why this is not optional: a CSS *outer* box-shadow is clipped to the region
 * strictly OUTSIDE the border box. Seat the ring exactly on the target's frame and
 * the brightest layer therefore begins one pixel *off* the window — and at
 * fractional display scaling (150%, 175%) the physical→DIP→physical round-trip
 * rounds, which widens that hairline into a visible sliver of background between
 * the window edge and the start of the glow. The user caught exactly this: "a
 * little bit of space between the brightest start of the glow and the actual edge".
 *
 * Overlapping inward by a few DIP makes the seam impossible regardless of rounding
 * — the glow's core sits on top of the window's edge and the halo reads as
 * attached to it rather than floating around it. macOS does the same thing (its
 * `overlap = 4pt`, described there as "for a seamless look"); it was dropped in the
 * rewrite as an artifact of the four-band model, which was wrong — the INWARD
 * overlap is load-bearing, the four bands were not.
 */
export const RING_OVERLAP = 3
/** Win11's top-level corner radius. Matching it makes the halo hug the window. */
export const CORNER_RADIUS = 8
/** Windows does NOT round snapped/maximized windows — a rounded halo would float
 *  off the square corners. */
export const SNAPPED_CORNER_RADIUS = 0
/** Below this, a window is a tooltip/palette/splash, not something to frame. */
export const MIN_TARGET_SIZE = 100
/** Total visible life of one glow run (matches the renderer's CSS envelope). */
export const GLOW_LIFETIME_MS = 3500
/** Follow-tick cadence while a glow is up (~30fps; ≤110 samples per run). */
export const GLOW_FOLLOW_MS = 32

/** Shell surfaces that share explorer.exe with real windows. Never frame these —
 *  the desktop, the taskbar, and the Start/search flyout are not "your window". */
const SHELL_CLASSES = new Set([
  'Progman',
  'WorkerW',
  'Shell_TrayWnd',
  'Shell_SecondaryTrayWnd',
  'Windows.UI.Core.CoreWindow',
  'ForegroundStaging'
])

/** Win32's canonical "parked off-screen" corner — a minimized/hidden window's
 *  rect reads as this, and it must never be treated as a real position. */
const PARKED_COORD = -32000

/**
 * DIP rounding tolerance. On a fractionally-scaled display (150%, 175%) the
 * physical→DIP conversion rounds, so a maximized window's frame lands within a
 * pixel or two of the work area rather than exactly on it. Gates that compare
 * edges for equality must allow this much slop or they'd reject every real
 * maximized window on a scaled monitor.
 */
const EDGE_TOL = 2

const near = (a: number, b: number): boolean => Math.abs(a - b) <= EDGE_TOL

export type GlowRejectReason =
  | 'no-window'
  | 'shell-window'
  | 'not-visible'
  | 'minimized'
  | 'too-small'
  | 'offscreen'
  | 'fullscreen'
  | 'untrusted-bounds'

export type GlowTargetInput = {
  /** The target window's frame in DIP (from DWM extended frame bounds). */
  targetDip: Rect | null
  /** All displays, in DIP. */
  displays: DisplayLike[]
  className: string | null
  maximized: boolean
  minimized: boolean
  visible: boolean
}

export type GlowPlan = {
  /** Bounds for the overlay BrowserWindow (target inflated by WINDOW_PAD). */
  windowBounds: Rect
  /** Inset of the ring inside the overlay window == WINDOW_PAD. */
  pad: number
  /** How far the ring is pulled inside the target's edge (see RING_OVERLAP). */
  overlap: number
  /** Ring corner radius (0 when the target's own corners are square). */
  radius: number
  /** True when the outward glow would land off-screen/under the taskbar, so the
   *  ring's `inset` shadow layer is the only thing the user can actually see. */
  maximized: boolean
}

export type GlowDecision = { ok: true; plan: GlowPlan } | { ok: false; reason: GlowRejectReason }

/** Grow a rect by `pad` on every side. */
export function inflate(rect: Rect, pad: number): Rect {
  return {
    x: rect.x - pad,
    y: rect.y - pad,
    width: rect.width + pad * 2,
    height: rect.height + pad * 2
  }
}

export function isShellClass(className: string | null): boolean {
  return !className || SHELL_CLASSES.has(className)
}

/** Big enough to be a window the user is working in. */
export function isGlowableTarget(rect: Rect): boolean {
  return rect.width >= MIN_TARGET_SIZE && rect.height >= MIN_TARGET_SIZE
}

function overlaps(a: Rect, b: Rect): boolean {
  return a.x < b.x + b.width && a.x + a.width > b.x && a.y < b.y + b.height && a.y + a.height > b.y
}

/** Does the rect have any pixels on a real display? The direct guard against the
 *  stray-bar class of bug: a rect nobody can see must never be drawn around. */
export function intersectsAnyDisplay(rect: Rect, displays: DisplayLike[]): boolean {
  return displays.some((d) => overlaps(rect, d.bounds))
}

/** Exclusive fullscreen: the frame is EXACTLY a display's bounds (not its work
 *  area — a maximized window stops at the taskbar). Never paint over a game. */
export function isExclusiveFullscreen(rect: Rect, displays: DisplayLike[]): boolean {
  return displays.some(
    (d) =>
      near(rect.x, d.bounds.x) &&
      near(rect.y, d.bounds.y) &&
      near(rect.width, d.bounds.width) &&
      near(rect.height, d.bounds.height)
  )
}

/** Snapped (Win+Left/Right, or a half/edge Snap Layout): the frame fills one axis
 *  of a work area and is flush against a work-area edge on the other. Corners are
 *  square, exactly like maximized. */
export function isSnapped(rect: Rect, displays: DisplayLike[]): boolean {
  return displays.some((d) => {
    const wa = d.workArea
    const right = wa.x + wa.width
    const bottom = wa.y + wa.height
    const fillsHeight = near(rect.height, wa.height) && near(rect.y, wa.y)
    const fillsWidth = near(rect.width, wa.width) && near(rect.x, wa.x)
    const touchesSide = near(rect.x, wa.x) || near(rect.x + rect.width, right)
    const touchesTopBottom = near(rect.y, wa.y) || near(rect.y + rect.height, bottom)
    return (fillsHeight && touchesSide) || (fillsWidth && touchesTopBottom)
  })
}

/** Is the rect inside some display's work area (allowing edge slop)? */
function withinSomeWorkArea(rect: Rect, displays: DisplayLike[]): boolean {
  return displays.some((d) => {
    const wa = d.workArea
    return (
      rect.x >= wa.x - EDGE_TOL &&
      rect.y >= wa.y - EDGE_TOL &&
      rect.x + rect.width <= wa.x + wa.width + EDGE_TOL &&
      rect.y + rect.height <= wa.y + wa.height + EDGE_TOL
    )
  })
}

/** Win11 rounds free-floating windows but squares off snapped/maximized ones. */
export function cornerRadiusFor(state: { maximized: boolean; snapped: boolean }): number {
  return state.maximized || state.snapped ? SNAPPED_CORNER_RADIUS : CORNER_RADIUS
}

/**
 * The single gate. Returns the overlay plan, or the reason we are drawing nothing.
 *
 * The `untrusted-bounds` gate is the regression guard for the shipped bug: a
 * maximized (or snapped) window's true frame IS the work area — that is what DWM's
 * extended frame bounds returns. If the rect we were handed for a maximized window
 * spills outside the work area, we are looking at a GetWindowRect-style frame
 * (which includes the invisible resize border and hangs off-screen by design),
 * i.e. our geometry source is wrong. Draw nothing rather than paint a fragment.
 */
export function planGlow(input: GlowTargetInput): GlowDecision {
  const { targetDip, displays, className, maximized, minimized, visible } = input
  if (!targetDip || displays.length === 0) return { ok: false, reason: 'no-window' }
  if (isShellClass(className)) return { ok: false, reason: 'shell-window' }
  if (!visible) return { ok: false, reason: 'not-visible' }
  if (minimized || targetDip.x <= PARKED_COORD || targetDip.y <= PARKED_COORD) {
    return { ok: false, reason: 'minimized' }
  }
  if (targetDip.width <= 0 || targetDip.height <= 0 || !isGlowableTarget(targetDip)) {
    return { ok: false, reason: 'too-small' }
  }
  if (!intersectsAnyDisplay(targetDip, displays)) return { ok: false, reason: 'offscreen' }
  if (isExclusiveFullscreen(targetDip, displays)) return { ok: false, reason: 'fullscreen' }

  const snapped = isSnapped(targetDip, displays)
  if ((maximized || snapped) && !withinSomeWorkArea(targetDip, displays)) {
    return { ok: false, reason: 'untrusted-bounds' }
  }

  const windowBounds = inflate(targetDip, WINDOW_PAD)
  // The inflated overlay could, in principle, be pushed entirely off a display by
  // a pathological target; re-check rather than assume.
  if (!intersectsAnyDisplay(windowBounds, displays)) return { ok: false, reason: 'offscreen' }

  return {
    ok: true,
    plan: {
      windowBounds,
      pad: WINDOW_PAD,
      overlap: RING_OVERLAP,
      radius: cornerRadiusFor({ maximized, snapped }),
      maximized: maximized || snapped
    }
  }
}
