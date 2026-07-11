// Orb harness — DYNAMIC (temporal) regression checks that the per-frame static
// invariants can't see:
//
//   C6 — state-change continuity: driving the real OrbAnimator timeline through
//        speaking→thinking and thinking→idle, the merge value AND the rendered
//        white-blob area must change smoothly frame-to-frame. The shipped bug
//        snapped merge 1→0 in a single frame on the state switch (the blob
//        exploded to dots and reformed); a snap shows up as a large one-frame
//        delta. This is the exact coverage hole that let the bug ship.
//
//   C8b — audio reactivity: a loud held speech blob must have a visibly larger
//         wavy edge than a quiet one (and both stay inside the bounded range).
//
// Run: node scripts/orb/check-transitions.mjs  (exit 1 on any violation)
import { openHarness, renderPixels } from './lib/harness.mjs'
import { contourWaviness } from './lib/pixels.mjs'

// A real state change eases over ~0.4s (MERGE_XFADE) / 0.8s (thinking gather),
// so at 60fps no single frame may move merge more than a small step. A snap is
// ~1.0. Thresholds sit well below a snap and above the smooth cross-fade.
const MAX_MERGE_STEP = 0.2
const MAX_AREA_STEP_FRAC = 0.28

const TRANSITIONS = [
  // The reported glitch: release (speaking) → thinking.
  { name: 'speaking→thinking', from: 'speaking', to: 'thinking' },
  // The dissolve back to the ring must also be a smooth outward ease.
  { name: 'thinking→idle', from: 'thinking', to: 'idle' },
  // Guard the neighbours too.
  { name: 'speaking→idle', from: 'speaking', to: 'idle' },
  { name: 'idle→thinking', from: 'idle', to: 'thinking' }
]

async function main() {
  const { page, close } = await openHarness('?size=96&dpr=2')
  const failures = []
  try {
    // --- C6: continuity across state changes ---------------------------------
    for (const tr of TRANSITIONS) {
      const { merges, areas } = await page.evaluate((o) => window.orb.transitionAreas(o), {
        from: tr.from,
        to: tr.to,
        switchAt: 0.5,
        frames: 90,
        dt: 1 / 60,
        amplitude: 0.6
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
          `${tr.name}: blob area jumped ${(maxAreaStep * 100).toFixed(1)}% in one frame (> ${(
            MAX_AREA_STEP_FRAC * 100
          ).toFixed(0)}%) — explode/reform`
        )
    }

    // --- C8b: the blob visibly reacts to amplitude ---------------------------
    // Average contour waviness over a noise period at quiet vs loud held speech.
    const cvAt = async (amplitude) => {
      let sum = 0
      const N = 8
      for (let i = 0; i < N; i++) {
        const img = await renderPixels(page, {
          t: 40 + i * 0.25,
          state: 'speaking',
          stateTime: 3,
          speechMerge: 1,
          amplitude
        })
        sum += contourWaviness(img).cv
      }
      return sum / N
    }
    const quiet = await cvAt(0.2)
    const loud = await cvAt(1.0)
    console.log(
      `[orb-transitions] reactivity: quiet cv ${quiet.toFixed(4)} · loud cv ${loud.toFixed(4)} · ratio ${(
        loud / quiet
      ).toFixed(2)}`
    )
    if (!(loud > quiet * 1.2))
      failures.push(
        `reactivity: loud cv ${loud.toFixed(4)} not clearly > quiet cv ${quiet.toFixed(
          4
        )} — blob barely tracks amplitude`
      )
    for (const [name, cv] of [
      ['quiet', quiet],
      ['loud', loud]
    ]) {
      if (cv < 0.015)
        failures.push(`reactivity: ${name} cv ${cv.toFixed(4)} — reads as a plain ball`)
      if (cv > 0.2) failures.push(`reactivity: ${name} cv ${cv.toFixed(4)} — wobble past tasteful`)
    }
  } finally {
    await close()
  }

  if (failures.length) {
    console.error(`[orb-transitions] FAIL — ${failures.length} violation(s):`)
    for (const f of failures) console.error('  - ' + f)
    process.exit(1)
  }
  console.log('[orb-transitions] PASS — continuous state changes, blob tracks amplitude')
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
