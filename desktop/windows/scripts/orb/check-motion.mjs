// Orb harness — motion-profile check. Renders a frame sequence across one
// rotate phase of the idle orbit, tracks a dot centroid image-side (connected
// components + nearest-neighbor), and asserts the ease-in-out velocity S-curve
// MATHEMATICALLY on the rendered output (not on the source formula):
//   - starts and ends near zero velocity
//   - peaks in the middle third
//   - rises then falls (unimodal, small tolerance for pixel quantization)
//   - total travel ≈ stepDegrees
//   - the rest phase between steps is genuinely still
// Run: node scripts/orb/check-motion.mjs  (exit 1 on failure)
import { openHarness, renderPixels } from './lib/harness.mjs'
import { whiteMask, components } from './lib/pixels.mjs'

// Default preset timings (choreography.ts): orbitPeriod 3.6s, restFraction
// 0.34, step 45°. Cycle 2 starts at t=7.2 — outside the idle merge excursion
// (0..5.2s of each 22s period) — rotate window [7.2, 9.576].
const T0 = 7.2
const ROTATE = 3.6 * (1 - 0.34)
const SAMPLES = 28
const STEP_RAD = (45 * Math.PI) / 180

async function centroidAngle(page, t, prev) {
  const img = await renderPixels(page, { t, state: 'idle' })
  const comps = components(whiteMask(img))
  if (comps.length !== 8) throw new Error(`expected 8 dots at t=${t}, got ${comps.length}`)
  const cx = img.width / 2
  const cy = img.height / 2
  // Track the component nearest the previously tracked one (or take the first).
  let chosen = comps[0]
  if (prev) {
    let best = Infinity
    for (const c of comps) {
      const d = (c.cx - prev.cx) ** 2 + (c.cy - prev.cy) ** 2
      if (d < best) {
        best = d
        chosen = c
      }
    }
  }
  return { ...chosen, angle: Math.atan2(chosen.cy - cy, chosen.cx - cx) }
}

function unwrap(angles) {
  const out = [angles[0]]
  for (let i = 1; i < angles.length; i++) {
    let a = angles[i]
    while (a - out[i - 1] > Math.PI) a -= 2 * Math.PI
    while (a - out[i - 1] < -Math.PI) a += 2 * Math.PI
    out.push(a)
  }
  return out
}

async function main() {
  const { page, close } = await openHarness('?size=96&dpr=2')
  const failures = []
  try {
    // --- Rotate phase: S-curve ------------------------------------------------
    let prev = null
    const angles = []
    const dt = ROTATE / (SAMPLES - 1)
    for (let i = 0; i < SAMPLES; i++) {
      prev = await centroidAngle(page, T0 + i * dt, prev)
      angles.push(prev.angle)
    }
    const a = unwrap(angles)
    const travel = Math.abs(a[a.length - 1] - a[0])
    if (Math.abs(travel - STEP_RAD) > 0.06) {
      failures.push(`travel ${travel.toFixed(3)} rad != step ${STEP_RAD.toFixed(3)} rad`)
    }
    const v = []
    for (let i = 1; i < a.length; i++) v.push(Math.abs(a[i] - a[i - 1]) / dt)
    const peak = Math.max(...v)
    const peakIdx = v.indexOf(peak)
    if (peak <= 0) failures.push('no motion detected in the rotate phase')
    if (v[0] > 0.18 * peak)
      failures.push(`start velocity ${v[0].toFixed(3)} not near zero (peak ${peak.toFixed(3)})`)
    if (v[v.length - 1] > 0.18 * peak) {
      failures.push(
        `end velocity ${v[v.length - 1].toFixed(3)} not near zero (peak ${peak.toFixed(3)})`
      )
    }
    if (peakIdx < v.length / 3 || peakIdx > (2 * v.length) / 3) {
      failures.push(`velocity peak at sample ${peakIdx}/${v.length} — not in the middle third`)
    }
    // Unimodal: rises to the peak, falls after (2px-quantization tolerance).
    const tol = 0.12 * peak
    for (let i = 1; i <= peakIdx; i++) {
      if (v[i] < v[i - 1] - tol) failures.push(`velocity dip before peak at sample ${i}`)
    }
    for (let i = peakIdx + 1; i < v.length; i++) {
      if (v[i] > v[i - 1] + tol) failures.push(`velocity bump after peak at sample ${i}`)
    }

    // --- Rest phase: still ------------------------------------------------------
    const restStart = T0 + ROTATE + 0.08
    const restEnd = T0 + 3.6 - 0.08
    let rprev = null
    const rest = []
    for (let i = 0; i < 6; i++) {
      rprev = await centroidAngle(page, restStart + (i / 5) * (restEnd - restStart), rprev)
      rest.push(rprev.angle)
    }
    const ru = unwrap(rest)
    const restTravel = Math.abs(ru[ru.length - 1] - ru[0])
    if (restTravel > 0.01)
      failures.push(`rest phase moved ${restTravel.toFixed(4)} rad (should be still)`)

    console.log(
      `[orb-motion] rotate travel ${travel.toFixed(3)} rad, peak v ${peak.toFixed(3)} rad/s at sample ${peakIdx + 1}/${v.length}, rest travel ${restTravel.toFixed(4)} rad`
    )
  } finally {
    await close()
  }

  if (failures.length) {
    console.error(`[orb-motion] FAIL — ${failures.length} issue(s):`)
    for (const f of failures) console.error('  - ' + f)
    process.exit(1)
  }
  console.log('[orb-motion] PASS — ease-in-out S-curve verified on rendered frames')
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
