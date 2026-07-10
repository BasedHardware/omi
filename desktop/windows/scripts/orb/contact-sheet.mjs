// Orb harness — contact sheet: ~16 frames per choreography cycle plus one per
// state/preset, composited into a single PNG grid for the skeptical visual
// review. Frames are rendered deterministically (explicit t), alpha-composited
// over the bar's dark background (#151515), and flipped to top-down.
// Output: .orb-out/contact-sheet.png + .orb-out/INDEX.md
// Run: node scripts/orb/contact-sheet.mjs [preset]
import { PNG } from 'pngjs'
import { mkdirSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { openHarness, renderPixels, outDir } from './lib/harness.mjs'

const TILE = 240 // px (120 CSS × dpr 2)
const COLS = 16
const BG = [21, 21, 21]

const preset = process.argv[2] ?? 'default'

// Default-preset timings (see choreography.ts).
const ORBIT = 3.6
const MERGE_DUR = 5.2

function seq(n, fn) {
  return Array.from({ length: n }, (_, i) => fn(i, n))
}

const ROWS = [
  {
    name: `idle — one orbit step cycle (rotate → rest), t=7.2..10.8`,
    frames: seq(16, (i) => ({ t: 7.2 + (i / 15) * ORBIT, state: 'idle' }))
  },
  {
    name: `idle — merge excursion (dots pool into the puddle blob, split back out), t=0..6.2`,
    frames: seq(16, (i) => ({ t: (i / 15) * (MERGE_DUR + 1), state: 'idle' }))
  },
  {
    name: 'listening — amplitude sweep 0→1→0 while orbiting (subtle breathe)',
    frames: seq(16, (i) => ({
      t: 7.2 + (i / 15) * ORBIT,
      state: 'listening',
      stateTime: 5,
      amplitude: Math.sin((i / 15) * Math.PI)
    }))
  },
  {
    name: 'thinking — ramp into the held oscillating blob, stateTime 0..3',
    frames: seq(16, (i) => ({ t: 30 + (i / 15) * 3, state: 'thinking', stateTime: (i / 15) * 3 }))
  },
  {
    name: 'agents — dots morph into four status pills, stateTime 0..1.4',
    frames: seq(16, (i) => ({ t: 12 + (i / 15) * 1.4, state: 'agents', stateTime: (i / 15) * 1.4 }))
  },
  {
    name: 'genesis — materialize from scale 0 (ease-out spring), 0..0.6s',
    frames: seq(16, (i) => ({ t: 12, state: 'idle', genesisTime: (i / 15) * 0.6 }))
  },
  {
    name: 'morph — disc → rounded rect → disc (one continuous shape)',
    frames: seq(16, (i) => ({
      t: 12,
      state: 'idle',
      morph: i <= 8 ? i / 8 : (16 - i) / 8
    }))
  },
  {
    name: 'presets — default / calm / lively / notch: separated (t=12) then merged (t=2.6)',
    frames: ['default', 'calm', 'lively', 'notch'].flatMap((p) => [
      { t: 12, state: 'idle', preset: p },
      { t: 2.6, state: 'idle', preset: p }
    ])
  }
]

function blit(sheet, img, col, row) {
  // WebGL readback is bottom-up: flip rows while compositing over BG.
  for (let y = 0; y < TILE; y++) {
    const srcY = img.height - 1 - y
    for (let x = 0; x < TILE; x++) {
      const si = (srcY * img.width + x) * 4
      const a = img.data[si + 3] / 255
      const di = ((row * TILE + y) * sheet.width + col * TILE + x) * 4
      // Source is premultiplied (WebGL premultipliedAlpha canvas → readPixels of
      // the drawing buffer is straight in our shader output: col*alpha written
      // premultiplied). Un-premultiply then blend over BG.
      for (let ch = 0; ch < 3; ch++) {
        const c = a > 0 ? img.data[si + ch] / a : 0
        sheet.data[di + ch] = Math.round(Math.min(255, c) * a + BG[ch] * (1 - a))
      }
      sheet.data[di + 3] = 255
    }
  }
}

async function main() {
  mkdirSync(outDir, { recursive: true })
  const { page, close } = await openHarness('?size=120&dpr=2')
  const sheet = new PNG({ width: COLS * TILE, height: ROWS.length * TILE })
  // Fill background.
  for (let i = 0; i < sheet.width * sheet.height; i++) {
    sheet.data[i * 4] = BG[0]
    sheet.data[i * 4 + 1] = BG[1]
    sheet.data[i * 4 + 2] = BG[2]
    sheet.data[i * 4 + 3] = 255
  }
  try {
    for (let r = 0; r < ROWS.length; r++) {
      const row = ROWS[r]
      for (let c = 0; c < Math.min(COLS, row.frames.length); c++) {
        const spec = { preset, ...row.frames[c] }
        const img = await renderPixels(page, spec)
        blit(sheet, img, c, r)
      }
      console.log(`[orb-sheet] row ${r + 1}/${ROWS.length}: ${row.name}`)
    }
  } finally {
    await close()
  }

  const file = path.join(outDir, 'contact-sheet.png')
  writeFileSync(file, PNG.sync.write(sheet))
  const index = [
    `# Orb contact sheet (preset: ${preset})`,
    '',
    `Grid: ${COLS} columns × ${ROWS.length} rows, ${TILE}px tiles, left→right = time.`,
    'Rendered deterministically from the harness (injected u_time), composited over #151515.',
    '',
    ...ROWS.map((row, i) => `- Row ${i + 1}: ${row.name}`),
    ''
  ].join('\n')
  writeFileSync(path.join(outDir, 'INDEX.md'), index)
  console.log(`[orb-sheet] wrote ${file}`)
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
