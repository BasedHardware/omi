// Orb harness — TRANSITION contact sheet: renders the real OrbAnimator timeline
// across each state change (16 frames per row, left→right = time, switch near
// the middle) so a human/skeptical reviewer can confirm the blob morphs
// CONTINUOUSLY — no explode-to-dots-and-reform snap (C6). Composited over the
// bar's dark background, flipped top-down. Also includes an amplitude sweep so
// the reviewer can judge the blob's audio reactivity (C8b).
// Output: .orb-out/transitions.png + .orb-out/transitions-INDEX.md
// Run: node scripts/orb/contact-sheet-transitions.mjs [preset]
import { PNG } from 'pngjs'
import { mkdirSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { openHarness, outDir } from './lib/harness.mjs'

const TILE = 200 // px (100 CSS × dpr 2)
const COLS = 16
const BG = [21, 21, 21]
const preset = process.argv[2] ?? 'default'

const TRANSITIONS = [
  { name: 'speaking → thinking (PTT release): must NOT explode to dots', from: 'speaking', to: 'thinking' },
  { name: 'thinking → idle: blob dissolves back to the ring (smooth outward ease)', from: 'thinking', to: 'idle' },
  { name: 'idle → thinking: ring gathers into the autonomous blob', from: 'idle', to: 'thinking' },
  { name: 'speaking → idle: blob dissolves as speech ends', from: 'speaking', to: 'idle' }
]

function decode(res) {
  return { width: res.width, height: res.height, data: Buffer.from(res.data, 'base64') }
}

function blit(sheet, img, col, row) {
  // WebGL readback is bottom-up: flip while compositing over BG (premultiplied).
  for (let y = 0; y < TILE; y++) {
    const srcY = img.height - 1 - y
    for (let x = 0; x < TILE; x++) {
      const si = (srcY * img.width + x) * 4
      const a = img.data[si + 3] / 255
      const di = ((row * TILE + y) * sheet.width + col * TILE + x) * 4
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
  const { page, close } = await openHarness(`?size=100&dpr=2&preset=${preset}`)
  const rows = [...TRANSITIONS, { name: 'amplitude sweep 0→1→0 on the held speech blob', ampSweep: true }]
  const sheet = new PNG({ width: COLS * TILE, height: rows.length * TILE })
  for (let i = 0; i < sheet.width * sheet.height; i++) {
    sheet.data[i * 4] = BG[0]
    sheet.data[i * 4 + 1] = BG[1]
    sheet.data[i * 4 + 2] = BG[2]
    sheet.data[i * 4 + 3] = 255
  }
  try {
    for (let r = 0; r < rows.length; r++) {
      const row = rows[r]
      if (row.ampSweep) {
        for (let c = 0; c < COLS; c++) {
          const amp = Math.sin((c / (COLS - 1)) * Math.PI) * 1.2
          const img = decode(
            await page.evaluate(
              (s) => (window.orb.renderAt(s), window.orb.pixels()),
              { t: 40, state: 'speaking', stateTime: 3, speechMerge: 1, amplitude: amp, preset }
            )
          )
          blit(sheet, img, c, r)
        }
      } else {
        const { width, height, frames } = await page.evaluate(
          (o) => window.orb.transitionFrames(o),
          { from: row.from, to: row.to, switchAt: 0.45, duration: 1.4, count: COLS, amplitude: 0.6, preset }
        )
        frames.forEach((data, c) => blit(sheet, decode({ width, height, data }), c, r))
      }
      console.log(`[orb-transitions-sheet] row ${r + 1}/${rows.length}: ${row.name}`)
    }
  } finally {
    await close()
  }

  const file = path.join(outDir, 'transitions.png')
  writeFileSync(file, PNG.sync.write(sheet))
  const index = [
    `# Orb TRANSITION contact sheet (preset: ${preset})`,
    '',
    `Grid: ${COLS} columns × ${rows.length} rows, ${TILE}px tiles, left→right = time.`,
    'The four transition rows render the REAL OrbAnimator timeline (envelope +',
    'enterMerge cross-fade + spin ease) across a state change near column 5.',
    'A correct fix shows the blob morphing continuously — NO frame where it',
    'suddenly bursts into 8 separate dots and reforms.',
    '',
    ...rows.map((row, i) => `- Row ${i + 1}: ${row.name}`),
    ''
  ].join('\n')
  writeFileSync(path.join(outDir, 'transitions-INDEX.md'), index)
  console.log(`[orb-transitions-sheet] wrote ${file}`)
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
