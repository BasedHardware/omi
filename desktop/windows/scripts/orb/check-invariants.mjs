// Orb harness — per-frame readPixels invariants:
//   1. zero purple pixels (strict neutral palette; band + grayscale-spread)
//   2. transparent background (1px border + corners fully alpha-0)
//   3. orb stays in bounds (never touches the canvas edge)
//   4. blob count via connected components matches the choreography
//      (8 separated dots / 1 thinking blob / 4 agent pills / 0 at genesis-zero)
// Run: node scripts/orb/check-invariants.mjs  (exit 1 on any violation)
import { openHarness, renderPixels } from './lib/harness.mjs'
import { findPurple, checkTransparentEdges, components, whiteMask } from './lib/pixels.mjs'

const CASES = [
  // Idle, dots separated (outside the merge excursion window).
  { name: 'idle-separated-a', spec: { t: 12, state: 'idle' }, blobs: 8 },
  { name: 'idle-separated-b', spec: { t: 14.7, state: 'idle' }, blobs: 8 },
  // Idle, fully merged (inside the excursion hold).
  { name: 'idle-merged', spec: { t: 2.6, state: 'idle' }, blobs: 1 },
  // Idle, mid-transition — anything between one puddle and eight dots is legal.
  { name: 'idle-merging', spec: { t: 0.9, state: 'idle' }, blobsBetween: [1, 8] },
  { name: 'idle-splitting', spec: { t: 4.4, state: 'idle' }, blobsBetween: [1, 8] },
  // Listening at high amplitude.
  { name: 'listening-loud', spec: { t: 12, state: 'listening', stateTime: 5, amplitude: 0.9 }, blobs: 8 },
  // Thinking: the held blob.
  { name: 'thinking', spec: { t: 40, state: 'thinking', stateTime: 3 }, blobs: 1 },
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
          failures.push(`${tag}: ${purple.length} non-neutral pixel(s), e.g. ${JSON.stringify(purple[0])}`)
        }
        const edges = checkTransparentEdges(img)
        if (edges.length) {
          failures.push(`${tag}: ${edges.length} non-transparent border pixel(s) (out of bounds / bg leak), e.g. ${JSON.stringify(edges[0])}`)
        }
        if (c.empty) {
          let opaque = 0
          for (let i = 3; i < img.data.length; i += 4) if (img.data[i] !== 0) opaque++
          if (opaque > 0) failures.push(`${tag}: expected an empty frame, found ${opaque} visible pixel(s)`)
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
      }
    }
  } finally {
    await close()
  }

  console.log(`[orb-invariants] ${checked} frames checked across ${PRESETS.length} presets`)
  if (failures.length) {
    console.error(`[orb-invariants] FAIL — ${failures.length} violation(s):`)
    for (const f of failures) console.error('  - ' + f)
    process.exit(1)
  }
  console.log('[orb-invariants] PASS — zero purple, transparent bg, in bounds, blob counts correct')
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
