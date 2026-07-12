// Orb harness — DYNAMIC (temporal) regression checks that the per-frame static
// invariants can't see:
//
//   C6 — state-change continuity: driving the real OrbAnimator timeline across
//        the audio states, the (retired) merge value must stay ~0 (no residual
//        blob snapping) AND the rendered white area must change smoothly
//        frame-to-frame. The waveform replaces the speech blob: entering an audio
//        state the ring dots glide into the line and the bars fade in; leaving it
//        they dissolve back. A one-frame snap (explode/reform) shows up as a large
//        area delta. Static bar content isolates the crossfade from the scroll.
//
//   WAVE — the bars track the level: a loud (tall-bars) waveform must be visibly
//          taller than a quiet (dots) one, and both stay within bounds.
//
//   ENTRY — the unroll/fan-out is smooth: finely sweeping the STAGED entry (the
//           ring dots straighten into the line, THEN the bars respond), no single
//           step may jump the rendered white AREA (bar fade) or its horizontal
//           SPREAD (the mass-weighted x std-dev — the fan-out position) — a dot
//           popping to its slot, or the bars snapping in, shows up as a large
//           area/spread delta. Fixing the sample time isolates the unroll from
//           the idle orbit so only the stage moves.
//
// Run: node scripts/orb/check-transitions.mjs  (exit 1 on any violation)
import { openHarness, renderPixels } from './lib/harness.mjs'
import { whiteMask } from './lib/pixels.mjs'

// The audio crossfade eases over the speech-merge envelope (~0.45s attack, 0.85s
// release) — so at 60fps no single frame may move the merge or the rendered area
// by more than a small step. A snap is ~1.0 / a large fraction.
const MAX_MERGE_STEP = 0.2
const MAX_AREA_STEP_FRAC = 0.3
// The entry sweep is sampled far finer than one real timeline (61 steps over the
// whole ring→line→bars staging), so each step is a fraction of a frame's motion —
// a genuinely continuous unroll stays well under these, a pop blows past them.
const MAX_ENTRY_AREA_STEP_FRAC = 0.18
const MAX_ENTRY_SPREAD_STEP_FRAC = 0.06

// A static speech-ish level pattern (left silence dots, right bars) held every
// frame so the AREA reflects only the ring↔waveform crossfade, not a scroll.
function staticLevels(n = 24) {
  return Array.from({ length: n }, (_, i) => {
    const u = i / (n - 1)
    if (u < 0.34) return 0
    const v = (u - 0.34) / 0.66
    return Math.max(
      0,
      Math.min(1, (0.55 + 0.45 * Math.sin(v * Math.PI * 4)) * Math.sin(v * Math.PI))
    )
  })
}

const TRANSITIONS = [
  // Release (speaking) → thinking: the bars dissolve back to the orbiting ring.
  { name: 'speaking→thinking', from: 'speaking', to: 'thinking' },
  { name: 'thinking→idle', from: 'thinking', to: 'idle' },
  { name: 'speaking→idle', from: 'speaking', to: 'idle' },
  { name: 'idle→speaking', from: 'idle', to: 'speaking' }
]

/** Vertical extent (px) of the white pixels — the waveform's rendered height. */
function whiteHeight(img) {
  const { mask, width, height } = whiteMask(img)
  let minY = Infinity
  let maxY = -Infinity
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      if (mask[y * width + x]) {
        if (y < minY) minY = y
        if (y > maxY) maxY = y
        break
      }
    }
  }
  return maxY < 0 ? 0 : maxY - minY
}

/**
 * Alpha-weighted white AREA and horizontal SPREAD of a frame. The readback is
 * premultiplied, so the red channel is already the white mass × coverage —
 * summing it counts a fading shape *continuously* (a binary a>128 / brightness
 * mask would count a crossfading region snapping across the cutoff as a false
 * jump; that bit us on the main transitions and we fixed it the same way).
 *
 * SPREAD is the mass-weighted standard deviation of x (a continuous 2nd moment),
 * NOT a thresholded left/right extent — an extent has a cutoff nonlinearity that
 * a peak-relative gate makes worse (tall central bars raise the gate and clip
 * the short edge columns, faking a "pop"). The spread integrates all mass, so it
 * rises smoothly as the ring fans out into the line and is unmoved by a bar
 * simply growing vertically — exactly the fan-out POSITION signal we want.
 */
function whiteAreaSpan(img) {
  const { width, height, data } = img
  let area = 0
  let sumW = 0
  let sumWX = 0
  let sumWX2 = 0
  let sumWY = 0
  let sumWY2 = 0
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const r = data[(y * width + x) * 4] // premultiplied white mass
      if (r <= 40) continue // skip the near-black disc / background
      area += r
      sumW += r
      sumWX += r * x
      sumWX2 += r * x * x
      sumWY += r * y
      sumWY2 += r * y * y
    }
  }
  const spread = sumW > 0 ? Math.sqrt(Math.max(0, sumWX2 / sumW - (sumWX / sumW) ** 2)) : 0
  const vSpread = sumW > 0 ? Math.sqrt(Math.max(0, sumWY2 / sumW - (sumWY / sumW) ** 2)) : 0
  return { area, spread, vSpread, width, height }
}

async function main() {
  const { page, close } = await openHarness('?size=96&dpr=2')
  const failures = []
  const levels = staticLevels()
  try {
    // --- C6: continuity across state changes ---------------------------------
    for (const tr of TRANSITIONS) {
      const { merges, areas } = await page.evaluate((o) => window.orb.transitionAreas(o), {
        from: tr.from,
        to: tr.to,
        switchAt: 0.5,
        frames: 120,
        dt: 1 / 60,
        waveLevels: levels
      })
      const maxArea = Math.max(...areas, 1)
      let maxMergeStep = 0
      let maxAreaStep = 0
      let at = -1
      for (let i = 1; i < merges.length; i++) {
        const dm = Math.abs(merges[i] - merges[i - 1])
        const da = Math.abs(areas[i] - areas[i - 1]) / maxArea
        if (dm > maxMergeStep) maxMergeStep = dm
        if (da > maxAreaStep) {
          maxAreaStep = da
          at = i
        }
      }
      console.log(
        `[orb-transitions] ${tr.name}: max merge step ${maxMergeStep.toFixed(3)}, ` +
          `max area step ${(maxAreaStep * 100).toFixed(1)}% (frame ${at})`
      )
      if (maxMergeStep > MAX_MERGE_STEP)
        failures.push(
          `${tr.name}: merge snapped ${maxMergeStep.toFixed(3)} in one frame (> ${MAX_MERGE_STEP})`
        )
      if (maxAreaStep > MAX_AREA_STEP_FRAC)
        failures.push(
          `${tr.name}: area jumped ${(maxAreaStep * 100).toFixed(1)}% in one frame (> ${(
            MAX_AREA_STEP_FRAC * 100
          ).toFixed(0)}%) — the crossfade snapped`
        )
    }

    // --- WAVE: the bars visibly track the level ------------------------------
    // A held waveform of quiet (near-silence dots) vs loud (tall bars) — the loud
    // one must be clearly taller, and neither may leave the canvas bounds.
    const heightAt = async (level) => {
      const n = 24
      const img = await renderPixels(page, {
        t: 40,
        state: 'speaking',
        stateTime: 3,
        speechMerge: 1,
        waveLevels: new Array(n).fill(level)
      })
      return whiteHeight(img)
    }
    const quiet = await heightAt(0.05)
    const loud = await heightAt(1.0)
    console.log(
      `[orb-transitions] level reactivity: quiet height ${quiet}px · loud height ${loud}px · ratio ${(
        loud / Math.max(1, quiet)
      ).toFixed(2)}`
    )
    if (!(loud > quiet * 1.8))
      failures.push(
        `reactivity: loud height ${loud}px not clearly > quiet ${quiet}px — bars barely track the level`
      )
    // Bounds: the tallest bars must stay off the canvas edge (size=96 dpr=2 →
    // 192px; half-extent 96). maxHalfExtent 0.82 → ~157px total ≈ 0.82·192.
    if (loud > 0.9 * 192)
      failures.push(`reactivity: loud height ${loud}px reaches the canvas edge (unbounded bars)`)

    // --- ENTRY: the staged unroll/fan-out sweeps smoothly --------------------
    // Sweep entry progress 0→1 in fine steps, mirroring the animator staging:
    // the speech-merge envelope drives the unroll FIRST (~55% in), then the
    // bar-response gain ramps once the row is formed. Time is fixed so only the
    // stage moves (no idle orbit drift between samples). Both the white AREA and
    // its horizontal SPREAD must move continuously — no dot pop, no bar snap.
    const ENTRY_STEPS = 60
    let prevAS = null
    let maxEntryArea = 0
    let maxEntrySpread = 0
    let atArea = -1
    let atSpread = -1
    let peakArea = 1
    const frames = []
    for (let i = 0; i <= ENTRY_STEPS; i++) {
      const e = i / ENTRY_STEPS
      const speechMerge = Math.min(1, e / 0.55) // unroll completes ~55% in
      const waveResponse = Math.max(0, Math.min(1, (e - 0.55) / 0.4)) // bars after
      const img = await renderPixels(page, {
        t: 40,
        state: 'speaking',
        stateTime: 40,
        speechMerge,
        waveResponse,
        waveLevels: levels
      })
      frames.push(whiteAreaSpan(img))
    }
    for (const f of frames) peakArea = Math.max(peakArea, f.area)
    for (let i = 0; i < frames.length; i++) {
      const f = frames[i]
      if (prevAS) {
        const da = Math.abs(f.area - prevAS.area) / peakArea
        const ds = Math.abs(f.spread - prevAS.spread) / f.width
        if (da > maxEntryArea) {
          maxEntryArea = da
          atArea = i
        }
        if (ds > maxEntrySpread) {
          maxEntrySpread = ds
          atSpread = i
        }
      }
      prevAS = f
    }
    console.log(
      `[orb-transitions] entry unroll: max area step ${(maxEntryArea * 100).toFixed(1)}% ` +
        `(frame ${atArea}), max spread step ${(maxEntrySpread * 100).toFixed(1)}% (frame ${atSpread})`
    )
    if (maxEntryArea > MAX_ENTRY_AREA_STEP_FRAC)
      failures.push(
        `entry unroll: area jumped ${(maxEntryArea * 100).toFixed(1)}% in one step ` +
          `(> ${(MAX_ENTRY_AREA_STEP_FRAC * 100).toFixed(0)}%) — the bars snapped in`
      )
    if (maxEntrySpread > MAX_ENTRY_SPREAD_STEP_FRAC)
      failures.push(
        `entry unroll: horizontal spread jumped ${(maxEntrySpread * 100).toFixed(1)}% in one step ` +
          `(> ${(MAX_ENTRY_SPREAD_STEP_FRAC * 100).toFixed(0)}%) — a dot popped to its slot`
      )

    // --- UNROLL TRAVEL: the ring's dots REALLY fan out (not a crossfade) ------
    // The smoothness check above passes for a ring↔line OPACITY CROSSFADE too (a
    // shipped bug: the dots' unroll positions were computed but the render faded a
    // rigid ring out and a separate line in). This asserts the dots genuinely
    // TRAVEL: with the bar response pinned at 0 (so NO bars ever appear — only the
    // ring dots can be on screen), sweep the unroll and require the tall ring to
    // COLLAPSE to a flat row through a bowed arc. A crossfade leaves the fading
    // ring at full height at mid-unroll, so its vertical spread would stay high.
    const unrollFrame = (speechMerge) =>
      renderPixels(page, {
        t: 40,
        state: 'speaking',
        stateTime: 40,
        speechMerge,
        waveResponse: 0, // pin the bars off — isolate the traveling dots
        waveLevels: levels
      })
    const ring = whiteAreaSpan(await unrollFrame(0)) // idle ring
    const mid = whiteAreaSpan(await unrollFrame(0.5)) // waveMix≈0.5 — mid-arc
    const line = whiteAreaSpan(await unrollFrame(1)) // dots fanned onto the line
    const vRing = ring.vSpread
    console.log(
      `[orb-transitions] unroll travel: vertical spread ring ${vRing.toFixed(1)}px → ` +
        `mid ${mid.vSpread.toFixed(1)}px → line ${line.vSpread.toFixed(1)}px · ` +
        `dot area ring ${(ring.area / 1e3).toFixed(0)}k → line ${(line.area / 1e3).toFixed(0)}k`
    )
    // The row must be flat by u=1: the ring's vertical extent has largely collapsed.
    if (!(line.vSpread < 0.5 * vRing))
      failures.push(
        `unroll travel: dots never flattened — line vertical spread ${line.vSpread.toFixed(1)}px ` +
          `not < 50% of the ring's ${vRing.toFixed(1)}px (the ring didn't fan out into a line)`
      )
    // Mid-unroll must be a BOWED ARC: strictly between the ring and the flat line —
    // NOT still a full-height ring (a lingering crossfade) and NOT already flat.
    if (!(mid.vSpread < 0.8 * vRing && mid.vSpread > 1.15 * line.vSpread))
      failures.push(
        `unroll travel: mid-unroll is not a bowed arc — vertical spread ${mid.vSpread.toFixed(1)}px ` +
          `is not between the line (${line.vSpread.toFixed(1)}px) and the ring (${vRing.toFixed(1)}px); ` +
          `a rigid ring crossfading to a line stays at full height mid-transition`
      )
    // The dots must SURVIVE the unroll at full opacity (they travel, they don't
    // fade away): the lit area on the line is a healthy fraction of the ring's.
    if (!(line.area > 0.4 * ring.area))
      failures.push(
        `unroll travel: dots faded out instead of traveling — line area ${(line.area / 1e3).toFixed(0)}k ` +
          `not > 40% of the ring's ${(ring.area / 1e3).toFixed(0)}k`
      )
    // BOTH DIRECTIONS: the vertical spread must collapse MONOTONICALLY ring→line
    // across the sweep. Since the render is a pure function of the unroll param,
    // the EXIT (line→ring) is exactly these frames reversed — a monotone collapse
    // guarantees a monotone RE-FORMATION on the way out (the row rolls back up
    // into the ring, held to the same standard as the entry). A crossfade would
    // NOT be monotone (the fading ring keeps the spread high, then it drops).
    let prevV = Infinity
    let maxVBump = 0
    const VSTEPS = 24
    for (let i = 0; i <= VSTEPS; i++) {
      const v = whiteAreaSpan(await unrollFrame(i / VSTEPS)).vSpread
      if (v > prevV) maxVBump = Math.max(maxVBump, v - prevV)
      prevV = v
    }
    // Allow a hair of pixel-quantization noise; a real crossfade bumps far more.
    if (maxVBump > 1.5)
      failures.push(
        `unroll travel: vertical spread not monotonically collapsing (max bump ${maxVBump.toFixed(1)}px) ` +
          `— the ring↔line motion isn't a clean fan-out/roll-up in both directions`
      )
  } finally {
    await close()
  }

  if (failures.length) {
    console.error(`[orb-transitions] FAIL — ${failures.length} violation(s):`)
    for (const f of failures) console.error('  - ' + f)
    process.exit(1)
  }
  console.log('[orb-transitions] PASS — continuous state changes, bars track the level, bounded')
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
