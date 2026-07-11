// Orb harness — per-frame readPixels invariants:
//   1. zero purple pixels (strict neutral palette; band + grayscale-spread)
//   2. transparent background (1px border + corners fully alpha-0)
//   3. orb stays in bounds (never touches the canvas edge)
//   4. blob count via connected components matches the choreography
//      (8 separated dots for idle/listening/THINKING / 1 speech blob / 4 agent
//      pills / 0 at genesis-zero), with no punched holes and no stray specks
//   5. BOUNDED speech wave: for extreme amplitude inputs (silence, clipping,
//      square wave, seeded noise) the blob's iso-contour stays inside designed
//      min/max radii every frame and never flatlines to a hard circle
//   6. agents transition never bridges pills across rows
// Run: node scripts/orb/check-invariants.mjs  (exit 1 on any violation)
import { openHarness, renderPixels } from './lib/harness.mjs'
import {
  findPurple,
  checkTransparentEdges,
  components,
  whiteMask,
  countHolePixels,
  contourWaviness
} from './lib/pixels.mjs'

const CASES = [
  // Idle: calm ring — dots separated, never merged without a speech signal.
  { name: 'idle-a', spec: { t: 12, state: 'idle' }, blobs: 8 },
  { name: 'idle-b', spec: { t: 14.7, state: 'idle' }, blobs: 8 },
  // Quiet listening: identical calm ring even with ambient level present.
  {
    name: 'listening-quiet',
    spec: { t: 12, state: 'listening', stateTime: 5, amplitude: 0.4 },
    blobs: 8
  },
  // Speaking: the voice blob — wavy, solid, hole-free.
  {
    name: 'speaking-held',
    spec: { t: 40, state: 'speaking', stateTime: 3, speechMerge: 1, amplitude: 0.7 },
    blobs: 1,
    noHoles: true,
    wavy: true
  },
  // Conglomerate / dissolve mid-points (any 1..8 pieces, no holes, no specks).
  {
    name: 'speaking-gather',
    spec: { t: 1.3, state: 'speaking', stateTime: 0.3, voiceDemo: true },
    blobsBetween: [1, 8],
    noHoles: true,
    noSpecks: true
  },
  {
    name: 'speaking-mid',
    spec: { t: 1.45, state: 'speaking', stateTime: 0.45, voiceDemo: true },
    blobsBetween: [1, 8],
    noHoles: true,
    noSpecks: true
  },
  {
    name: 'speaking-dissolve',
    spec: { t: 5.5, state: 'speaking', stateTime: 4.5, voiceDemo: true },
    blobsBetween: [1, 8],
    noHoles: true,
    noSpecks: true
  },
  // Thinking: the dots STAY a separated orbiting ring — merge-into-a-blob is
  // reserved for speech. Never a transient blob at any stage after entry (this
  // is the reported-bug guard: thinking used to collapse into the center pool).
  {
    name: 'thinking-early',
    spec: { t: 30.35, state: 'thinking', stateTime: 0.35 },
    blobs: 8,
    noSpecks: true
  },
  {
    name: 'thinking-mid',
    spec: { t: 30.6, state: 'thinking', stateTime: 0.6 },
    blobs: 8,
    noSpecks: true
  },
  { name: 'thinking', spec: { t: 40, state: 'thinking', stateTime: 3 }, blobs: 8 },
  // Agents: four status pills.
  { name: 'agents', spec: { t: 40, state: 'agents', stateTime: 3 }, blobs: 4 },
  // Genesis: scale zero renders NOTHING; early spring frames stay in bounds.
  { name: 'genesis-zero', spec: { t: 12, state: 'idle', genesisTime: 0 }, empty: true },
  { name: 'genesis-early', spec: { t: 12, state: 'idle', genesisTime: 0.06 } },
  { name: 'genesis-overshoot', spec: { t: 12, state: 'idle', genesisTime: 0.28 } },
  // Morph: disc → rounded rect (half and full).
  { name: 'morph-half', spec: { t: 12, state: 'idle', morph: 0.5 } },
  { name: 'morph-rect', spec: { t: 12, state: 'idle', morph: 1 } }
]

const PRESETS = ['default', 'calm', 'lively', 'notch']

/** Smallest legitimate feature ≈ a genesis-scale dot; anything under this in a
 *  normal frame is a stray speck (review round 2: the center-pool speck). */
const MIN_COMPONENT_PX = 25

// Deterministic seeded PRNG for the noise amplitude sequence.
function mulberry32(seed) {
  let a = seed
  return () => {
    a |= 0
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

async function main() {
  const { page, close } = await openHarness('?size=96&dpr=2')
  const failures = []
  let checked = 0

  try {
    for (const preset of PRESETS) {
      for (const c of CASES) {
        const img = await renderPixels(page, { ...c.spec, preset })
        checked++
        const tag = `${preset}/${c.name}`

        const purple = findPurple(img)
        if (purple.length) {
          failures.push(
            `${tag}: ${purple.length} non-neutral pixel(s), e.g. ${JSON.stringify(purple[0])}`
          )
        }
        const edges = checkTransparentEdges(img)
        if (edges.length) {
          failures.push(
            `${tag}: ${edges.length} non-transparent border pixel(s) (out of bounds / bg leak), e.g. ${JSON.stringify(edges[0])}`
          )
        }
        if (c.empty) {
          let opaque = 0
          for (let i = 3; i < img.data.length; i += 4) if (img.data[i] !== 0) opaque++
          if (opaque > 0)
            failures.push(`${tag}: expected an empty frame, found ${opaque} visible pixel(s)`)
          continue
        }
        const comps = components(whiteMask(img))
        if (c.blobs !== undefined && comps.length !== c.blobs) {
          failures.push(`${tag}: expected ${c.blobs} blob(s), found ${comps.length}`)
        }
        if (c.blobsBetween) {
          const [lo, hi] = c.blobsBetween
          if (comps.length < lo || comps.length > hi) {
            failures.push(`${tag}: expected ${lo}..${hi} blob(s), found ${comps.length}`)
          }
        }
        if (c.noHoles) {
          const holes = countHolePixels(img)
          if (holes > 3) failures.push(`${tag}: ${holes} hole pixel(s) punched inside the blob`)
        }
        if (c.noSpecks) {
          const speck = comps.find((k) => k.size < MIN_COMPONENT_PX)
          if (speck)
            failures.push(
              `${tag}: stray ${speck.size}px speck at (${speck.cx | 0},${speck.cy | 0})`
            )
        }
        if (c.wavy) {
          const { cv } = contourWaviness(img)
          if (cv < 0.015)
            failures.push(`${tag}: contour cv ${cv.toFixed(4)} — blob reads as a plain ball`)
          if (cv > 0.2) failures.push(`${tag}: contour cv ${cv.toFixed(4)} — wobble past tasteful`)
        }
      }
    }

    // --- 5. Bounded wave under EXTREME amplitude sequences ---------------------
    // For arbitrary input — dead silence, clipping 5x, a square wave, seeded
    // noise — the held speech blob's contour must stay inside designed radii
    // every frame: never spikes toward the disc edge, never flatlines into a
    // hard circle, never collapses.
    {
      const rng = mulberry32(1234)
      const seqs = {
        silence: () => 0,
        clipping: () => 5,
        square: (i) => (i % 6 < 3 ? 1 : 0),
        noise: () => rng() * 3
      }
      // Designed bounds (px at size=96 dpr=2: half-extent 96, disc 0.92·96≈88).
      const MAX_R = 0.62 * 96 // blob may never reach past ~2/3 of the half-extent
      const MIN_R = 0.16 * 96 // and never collapse below this
      for (const [name, amp] of Object.entries(seqs)) {
        for (let i = 0; i < 12; i++) {
          const img = await renderPixels(page, {
            t: 40 + i * 0.18,
            state: 'speaking',
            stateTime: 3 + i * 0.18,
            speechMerge: 1,
            amplitude: amp(i)
          })
          checked++
          const { mean, cv } = contourWaviness(img)
          const comps = components(whiteMask(img))
          const tag = `amp-${name}/frame${i}`
          if (comps.length !== 1) failures.push(`${tag}: blob split into ${comps.length} pieces`)
          if (mean > MAX_R)
            failures.push(
              `${tag}: contour mean ${mean.toFixed(1)}px exceeds max ${MAX_R.toFixed(1)}px`
            )
          if (mean < MIN_R)
            failures.push(
              `${tag}: contour mean ${mean.toFixed(1)}px under min ${MIN_R.toFixed(1)}px`
            )
          if (cv < 0.008)
            failures.push(`${tag}: cv ${cv.toFixed(4)} — flatlined to a hard circle mid-speech`)
          if (cv > 0.22)
            failures.push(`${tag}: cv ${cv.toFixed(4)} — wave spiked past the designed range`)
          const holes = countHolePixels(img)
          if (holes > 3) failures.push(`${tag}: ${holes} hole pixel(s)`)
        }
      }
    }

    // --- 5b. Thinking ORBITS: 8 separated dots that rotate (never a blob) ------
    // The reported bug: thinking collapsed the dots into a central blob, hiding
    // the orbit. Thinking now keeps the 8 dots separated and glides them
    // continuously around the ring. Sample across a slice of the rotation and
    // require: always 8 separated dots, and the ring visibly advances (the dot
    // positions rotate frame-to-frame — not static, not a blob).
    {
      let prevSig = null
      let advanced = 0
      const STEPS = 8
      for (let i = 0; i < STEPS; i++) {
        const dt = i * 0.3
        const img = await renderPixels(page, { t: 40 + dt, state: 'thinking', stateTime: 3 + dt })
        checked++
        const comps = components(whiteMask(img))
        if (comps.length !== 8) {
          failures.push(
            `thinking-orbit/frame${i}: expected 8 separated dots, found ${comps.length}`
          )
          continue
        }
        // Order-independent signature of the dot centroids; a rotating ring
        // shifts them frame-to-frame, a static (or blobbed) ring does not.
        const sig = comps
          .map((k) => `${Math.round(k.cx)},${Math.round(k.cy)}`)
          .sort()
          .join(' ')
        if (prevSig !== null && sig !== prevSig) advanced++
        prevSig = sig
      }
      if (advanced < STEPS - 2)
        failures.push(
          `thinking-orbit: ring advanced in only ${advanced}/${STEPS - 1} steps — dots not orbiting`
        )
    }

    // --- 6. Agents transition never bridges rows -------------------------------
    // Component count must stay within 4..8 and no component may exceed ~1.4×
    // a settled pill's area (a cross-row bridge is ~2× — review round 2).
    {
      const settled = await renderPixels(page, { t: 40, state: 'agents', stateTime: 3 })
      const pills = components(whiteMask(settled))
      const pillArea = pills.reduce((a, c) => a + c.size, 0) / pills.length
      for (let i = 1; i <= 13; i++) {
        const stateTime = (i / 14) * 0.7
        const img = await renderPixels(page, { t: 40 + stateTime, state: 'agents', stateTime })
        checked++
        const comps = components(whiteMask(img))
        const tag = `agents-transition/t${stateTime.toFixed(2)}`
        if (comps.length < 4 || comps.length > 8) {
          failures.push(
            `${tag}: ${comps.length} components (want 4..8 — a cross-row bridge collapses below 4)`
          )
        }
        const biggest = comps[0]?.size ?? 0
        if (biggest > pillArea * 1.4) {
          failures.push(
            `${tag}: component ${biggest}px > 1.4× pill area ${pillArea.toFixed(0)}px — rows bridged`
          )
        }
      }
    }
  } finally {
    await close()
  }

  console.log(
    `[orb-invariants] ${checked} frames checked (${PRESETS.length} presets + extremes + transitions)`
  )
  if (failures.length) {
    console.error(`[orb-invariants] FAIL — ${failures.length} violation(s):`)
    for (const f of failures) console.error('  - ' + f)
    process.exit(1)
  }
  console.log(
    '[orb-invariants] PASS — neutral palette, transparent bg, in bounds, correct blob counts, no holes/specks, bounded wave, no row bridging'
  )
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
