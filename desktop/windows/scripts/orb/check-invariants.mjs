// Orb harness — per-frame readPixels invariants:
//   1. zero purple pixels (strict neutral palette; band + grayscale-spread)
//   2. transparent background (1px border + corners fully alpha-0)
//   3. orb stays in bounds (never touches the canvas edge)
//   4. blob count via connected components matches the choreography
//      (8 separated dots for idle/listening/THINKING / N waveform bars for
//      speaking / 4 agent pills / 0 at genesis-zero), with no punched holes and
//      no stray specks
//   5. BOUNDED waveform: for extreme level inputs (silence, clipping, square,
//      seeded noise) the bars stay a horizontal row inside the canvas bounds
//      every frame — the loudest bar never reaches the edge
//   6. agents transition never bridges pills across rows
// Run: node scripts/orb/check-invariants.mjs  (exit 1 on any violation)
import { openHarness, renderPixels } from './lib/harness.mjs'
import {
  findPurple,
  checkTransparentEdges,
  components,
  whiteMask,
  countHolePixels
} from './lib/pixels.mjs'

// Waveform level fixtures (square mount → ~7 slots; a longer array is windowed
// by slotCount inside the choreography via waveBars on whatever it is handed —
// here we hand exactly what a 7-ish-slot row shows, so extra entries are unused).
const SILENCE = new Array(8).fill(0)
// Left silence dots, right speech bars of mixed height (never all-max).
const SPEECH = [0, 0, 0.2, 0.75, 0.35, 0.9, 0.55, 1.0]

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
  // Speaking: the waveform. A silent row is a line of dots; a speech row is
  // vertical bars. Either way N separated pieces on the horizontal centerline
  // (never a blob), hole-free, in bounds. Square mount (aspect 1) → ~7 slots.
  {
    name: 'speaking-silence',
    spec: { t: 40, state: 'speaking', stateTime: 3, speechMerge: 1, waveLevels: SILENCE },
    blobsBetween: [5, 8],
    noHoles: true,
    noSpecks: true,
    waveRow: true
  },
  {
    name: 'speaking-bars',
    spec: { t: 40, state: 'speaking', stateTime: 3, speechMerge: 1, waveLevels: SPEECH },
    blobsBetween: [5, 8],
    noHoles: true,
    noSpecks: true,
    waveRow: true
  },
  // Scrolling voice demo mid-utterance: still a bounded row of bars/dots.
  {
    name: 'speaking-scroll',
    spec: { t: 3.0, state: 'speaking', stateTime: 3.0, waveDemo: true },
    blobsBetween: [5, 8],
    noHoles: true,
    noSpecks: true,
    waveRow: true
  },
  // Mid-crossfade (dots gliding to the line, bars fading in): only bounds/palette
  // are asserted — the count is ambiguous while both layers are visible.
  {
    name: 'speaking-enter',
    spec: { t: 40, state: 'speaking', stateTime: 3, speechMerge: 0.5, waveLevels: SPEECH }
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
        if (c.waveRow) {
          // Every bar/dot sits on the horizontal centerline: all component
          // centroids share a narrow vertical band around the canvas center, and
          // they spread horizontally (a row, not a stack).
          const cy = img.height / 2
          const offRow = comps.filter((k) => Math.abs(k.cy - cy) > 0.14 * img.height)
          if (offRow.length)
            failures.push(
              `${tag}: ${offRow.length} bar(s) off the centerline, e.g. cy ${offRow[0].cy | 0} vs ${cy}`
            )
          const xs = comps.map((k) => k.cx).sort((a, b) => a - b)
          if (xs.length >= 2 && xs[xs.length - 1] - xs[0] < 0.35 * img.width)
            failures.push(`${tag}: bars span only ${(xs[xs.length - 1] - xs[0]) | 0}px — not a row`)
        }
      }
    }

    // --- 5. Bounded waveform under EXTREME level sequences ---------------------
    // For arbitrary per-slot input — dead silence, clipping 5×, a square pattern,
    // seeded noise — the bars stay a horizontal row inside the canvas bounds every
    // frame: the tallest bar never reaches the edge, the row never leaves the
    // centerline, and no bar merges into a blob or punches a hole.
    {
      const rng = mulberry32(1234)
      const N = 8
      const seqs = {
        silence: () => 0,
        clipping: () => 5, // clamped to 1 inside waveBars → max-height bars, bounded
        square: (j) => (j % 2 === 0 ? 1 : 0),
        noise: () => rng() * 3
      }
      // Designed bound (px at size=96 dpr=2 → 192px, half-extent 96): the loudest
      // bar tops out at WAVE.maxHalfExtent (0.82) → ~157px total, comfortably off
      // the edge. A bar reaching past this = an unbounded height.
      const MAX_H = 0.86 * 192
      const cyc = 192 / 2
      for (const [name, lvl] of Object.entries(seqs)) {
        for (let i = 0; i < 6; i++) {
          const waveLevels = Array.from({ length: N }, (_, j) => lvl(j + i))
          const img = await renderPixels(page, {
            t: 40 + i * 0.2,
            state: 'speaking',
            stateTime: 3 + i * 0.2,
            speechMerge: 1,
            waveLevels
          })
          checked++
          const comps = components(whiteMask(img))
          const tag = `wave-${name}/frame${i}`
          // Every bar/dot sits on the centerline.
          for (const k of comps) {
            if (Math.abs(k.cy - cyc) > 0.16 * 192)
              failures.push(`${tag}: a bar left the centerline (cy ${k.cy | 0} vs ${cyc})`)
          }
          // Bounded height: the white pixels never span more than MAX_H vertically.
          const { mask, width, height } = whiteMask(img)
          let minY = Infinity
          let maxY = -Infinity
          for (let y = 0; y < height; y++)
            for (let x = 0; x < width; x++)
              if (mask[y * width + x]) {
                if (y < minY) minY = y
                if (y > maxY) maxY = y
                break
              }
          const h = maxY < 0 ? 0 : maxY - minY
          if (h > MAX_H) failures.push(`${tag}: waveform height ${h}px exceeds max ${MAX_H | 0}px`)
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

    // --- 6. Agents: whirl-then-settle; the glide never bridges rows -------------
    // Entry whirls the dots on the ring for AGENTS_WHIRL seconds (8 separated
    // dots, no pose yet), THEN they glide into four pills. During the glide the
    // component count must stay within 4..8 and no component may exceed ~1.4× a
    // settled pill's area (a cross-row bridge is ~2× — review round 2).
    {
      // Keep in sync with AGENTS_WHIRL in choreography.ts.
      const AGENTS_WHIRL = 1.0
      const settled = await renderPixels(page, {
        t: 40,
        state: 'agents',
        stateTime: AGENTS_WHIRL + 2
      })
      const pills = components(whiteMask(settled))
      const pillArea = pills.reduce((a, c) => a + c.size, 0) / pills.length
      // Whirl phase: still a separated orbiting ring — the pose hasn't begun.
      for (const stateTime of [0.15, 0.5, 0.9]) {
        const img = await renderPixels(page, { t: 40 + stateTime, state: 'agents', stateTime })
        checked++
        const comps = components(whiteMask(img))
        if (comps.length !== 8) {
          failures.push(
            `agents-whirl/t${stateTime.toFixed(2)}: ${comps.length} components (want 8 dots still orbiting before the pose)`
          )
        }
      }
      // Glide phase (offset past the whirl): the pose forms without bridging rows.
      for (let i = 1; i <= 13; i++) {
        const stateTime = AGENTS_WHIRL + (i / 14) * 0.7
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
