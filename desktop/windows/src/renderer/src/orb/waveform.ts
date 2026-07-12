// Orb waveform — the scrolling amplitude-history visualizer that REPLACES the
// merged speech blob (design pivot, Chris 2026-07-11; the live scrolling look was
// approved by the user 2026-07-11). Audio-active states (recording the user's
// voice; the spoken TTS reply) render a classic voice-memo row: evenly spaced
// vertical rounded-capsule bars whose heights track the live level. A SILENT
// sample renders as a small round DOT (a narrow circle, well below the bar
// height), so the resting waveform is a tidy row of dots — what the 8 ring dots
// fan out into on entry. New samples enter at the RIGHT and the history slides
// left.
//
// Everything here is a PURE function: the sensitivity curve, the ring buffer
// stepping, the history → slot mapping, and the slot → bar geometry. The app's
// OrbAnimator owns the stateful buffer and feeds real time/audio; the
// deterministic harness scripts a levels array straight into computeOrbFrame.
// Bars are returned in the shader's normalized short-axis units (y half-extent =
// 1, x half-extent = aspect), so the fragment shader rasterizes them directly.

/** Shader uniform-array cap for waveform slots (must match u_wave[] in shader.ts).
 *  A wide mount uses ~24–32; a compact square mount ~5–7; this only bounds cost. */
export const WAVE_MAX_SLOTS = 40

/** Look/feel of the bar row, in normalized short-axis units. */
export const WAVE = {
  /** Row half-width as a fraction of the canvas aspect (leaves an edge margin). */
  spanFrac: 0.9,
  /** Never pack more/less than this many slots regardless of aspect. */
  minSlots: 5,
  /** Target slot pitch (center-to-center) — slot count is width / pitch. */
  pitch: 0.25,
  /** Bar half-width (the rounded cap radius) as a fraction of the pitch. Sets the
   *  bar:gap ratio. */
  barRadiusFrac: 0.36,
  /** RESTING (silence) dot radius as a fraction of the bar half-width — a small
   *  round dot, clearly shorter than a bar (user: "shorten the default
   *  no-speaking bars"). Width ramps up to the full bar quickly (see widthLevel)
   *  so actual speech bars stay a uniform width; only near-silence reads as a dot. */
  restRadiusFrac: 0.5,
  /** Level by which a slot reaches its full bar WIDTH (height keeps growing past
   *  it). Keeps all speaking bars uniform-width while silence stays a slim dot. */
  widthLevel: 0.22,
  /** Tallest bar's total half-height — bounds the loudest sample so a bar can
   *  never reach the canvas edge (keeps the in-bounds invariant). */
  maxHalfExtent: 0.82
} as const

// --- Sensitivity: raw loudness → bar level (normalized, never pins) -----------

/** Input scale for the loudness→level curve. Higher = more sensitive. */
export const WAVE_LEVEL_GAIN = 2.1
/** Ceiling of the shaped level (< 1): the tallest a bar can get, so genuinely
 *  loud speech APPROACHES but never PINS at the max height (user: "the lines max
 *  out when I'm not even speaking that loud — normalize the animation a tad"). */
export const WAVE_LEVEL_CEIL = 0.9

/**
 * Compress a raw loudness (≥ 0, possibly hot) into a bar level in [0, CEIL) via a
 * saturating exponential: `CEIL·(1 − e^(−raw·GAIN))`. Silence → 0 (a resting
 * dot); moderate speech (~0.4) lands mid-range (~0.5); loud (~1.0) reads tall
 * (~0.8) yet asymptotes to CEIL — it can never pin at the maximum. Monotonic and
 * bounded for ANY input. Applied upstream (the animator, on the live sample); the
 * harness/tests feed already-shaped levels straight into waveBars.
 */
export function shapeBarLevel(raw: number): number {
  const x = Math.max(0, raw)
  return WAVE_LEVEL_CEIL * (1 - Math.exp(-x * WAVE_LEVEL_GAIN))
}

const clamp01 = (x: number): number => Math.min(1, Math.max(0, x))

/** Usable row half-width (normalized units) for a canvas of the given aspect
 *  (width / height). A square canvas (aspect 1) still gets a sensible span. */
export function waveHalfWidth(aspect: number): number {
  return Math.max(0.7, aspect) * WAVE.spanFrac
}

/** How many time samples (slots) fit across the row at this aspect. Scales from
 *  ~6 on a square mini mount to WAVE_MAX_SLOTS on a wide bar, bounded both ways. */
export function slotCountForAspect(aspect: number): number {
  const n = Math.round((2 * waveHalfWidth(aspect)) / WAVE.pitch)
  return Math.max(WAVE.minSlots, Math.min(WAVE_MAX_SLOTS, n))
}

/** One rendered slot: center x on the y=0 centerline, half-width `halfW` and
 *  TOTAL half-height `halfH`. All normalized short-axis units. Fed to the shader
 *  as a rounded box of half-extent (halfW, halfH) with corner = min(halfW, halfH)
 *  — so a slot with halfW==halfH is a circle (the resting dot) and a tall slot is
 *  a round-capped vertical bar. */
export type WaveBar = { x: number; halfW: number; halfH: number }

/**
 * Lay out `levels` (per-slot bar level 0..1, oldest→newest = left→right) into
 * evenly spaced slots. A level of 0 yields a small round dot (radius restR); the
 * width ramps to the full bar by WAVE.widthLevel (so speech bars are uniform
 * width) while the height grows on up to WAVE.maxHalfExtent. Pure — the same call
 * the animator and the harness both make. Levels are assumed already shaped (see
 * shapeBarLevel); this is geometry only.
 */
export function waveBars(levels: number[], aspect: number): WaveBar[] {
  const n = levels.length
  if (n === 0) return []
  const halfW = waveHalfWidth(aspect)
  const pitch = (2 * halfW) / n
  const barW = pitch * WAVE.barRadiusFrac // full bar half-width
  const restR = barW * WAVE.restRadiusFrac // resting round-dot radius (< barW)
  const growthH = Math.max(0, WAVE.maxHalfExtent - restR)
  return levels.map((lvl, i) => {
    const l = clamp01(lvl)
    // Width reaches the full bar quickly (by widthLevel) so only near-silence is
    // a slim dot; height grows the whole way from the dot radius to the max.
    const wl = Math.min(1, l / WAVE.widthLevel)
    return {
      x: -halfW + pitch * (i + 0.5),
      halfW: restR + wl * (barW - restR),
      halfH: restR + l * growthH
    }
  })
}

/**
 * Push one loudness sample into a fixed-length history ring, returning the new
 * write index. The ring is sized WAVE_MAX_SLOTS; the newest sample lands at
 * `writeIndex`, so the last `slotCount` entries (see historySlots) are what the
 * row shows. Initialize the buffer to 0 (silence) so an unfilled ring reads as
 * resting dots, never garbage.
 */
export function historyPush(buf: Float32Array, writeIndex: number, level: number): number {
  buf[writeIndex % buf.length] = clamp01(level)
  return (writeIndex + 1) % buf.length
}

/**
 * The last `slotCount` samples, oldest → newest (newest last = rightmost slot).
 * `writeIndex` is where the NEXT push will land, so the newest existing sample is
 * at writeIndex-1. Reads wrap the ring; a slotCount larger than the buffer is
 * clamped to the buffer length.
 */
export function historySlots(buf: Float32Array, writeIndex: number, slotCount: number): number[] {
  const len = buf.length
  const n = Math.min(slotCount, len)
  const out = new Array<number>(n)
  for (let j = 0; j < n; j++) {
    // Oldest of the window first: writeIndex - n + j (the +len keeps it positive).
    const idx = (((writeIndex - n + j) % len) + len) % len
    out[j] = buf[idx]
  }
  return out
}

/** One deterministic ease of the displayed bar levels toward their targets, so a
 *  new sample (or a scroll shift) never snaps a bar's height in a single frame —
 *  the row flows. Fast enough to keep up with speech, slow enough to smooth the
 *  per-slot steps. Callers step it per frame with their dt. */
export function stepWaveLevels(
  display: Float32Array,
  target: number[],
  dt: number,
  tau = 0.05
): void {
  const k = 1 - Math.exp(-dt / Math.max(1e-6, tau))
  for (let i = 0; i < display.length; i++) {
    const tv = target[i] ?? 0
    display[i] += (tv - display[i]) * k
  }
}
