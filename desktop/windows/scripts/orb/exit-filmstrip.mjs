// Focused EXIT/ENTRY filmstrips for the skeptical roll-up-vs-crossfade review.
// Drives the REAL envelope through transitionFrames (which now derives the whole
// bar staging from the same speech-merge envelope it steps — no separate gain —
// so these frames are exactly what the live app renders). One row per direction,
// many columns across the transition window, composited over the bar background.
// Output: .orb-out/exit-filmstrip.png + .orb-out/exit-filmstrip-INDEX.md
// Run: node scripts/orb/exit-filmstrip.mjs
import { PNG } from 'pngjs'
import { mkdirSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { openHarness, outDir } from './lib/harness.mjs'

const TILE = 200 // 100 CSS × dpr 2
const COLS = 28
const BG = [21, 21, 21]
const LEVELS = [0, 0, 0.3, 0.8, 0.4, 1, 0.5, 0.2]

// switchAt is where the state flips; duration frames the whole window. The exit
// roll-up lives just after the switch, the entry hand-off just after it too.
const ROWS = [
  {
    name: 'EXIT speaking→thinking: bars should flatten to DOTS on the line, THEN the dots roll up (line→arc→ring) at full opacity as the dark disc returns — NOT a bars-dim / ring-appear crossfade',
    from: 'speaking',
    to: 'thinking',
    switchAt: 0.35,
    duration: 1.8
  },
  {
    name: 'EXIT speaking→idle: same roll-up, settling to the calm ring',
    from: 'speaking',
    to: 'idle',
    switchAt: 0.35,
    duration: 1.5
  },
  {
    name: 'ENTRY idle→speaking (reference — approved): ring dots fan out to the line at full opacity, THEN bars come alive',
    from: 'idle',
    to: 'speaking',
    switchAt: 0.35,
    duration: 1.2
  }
]

function decode(res) {
  return { width: res.width, height: res.height, data: Buffer.from(res.data, 'base64') }
}
function blit(sheet, img, col, row) {
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
  const { page, close } = await openHarness('?size=100&dpr=2')
  const sheet = new PNG({ width: COLS * TILE, height: ROWS.length * TILE })
  for (let i = 0; i < sheet.width * sheet.height; i++) {
    sheet.data[i * 4] = BG[0]
    sheet.data[i * 4 + 1] = BG[1]
    sheet.data[i * 4 + 2] = BG[2]
    sheet.data[i * 4 + 3] = 255
  }
  try {
    for (let r = 0; r < ROWS.length; r++) {
      const row = ROWS[r]
      const { width, height, frames } = await page.evaluate(
        (o) => window.orb.transitionFrames(o),
        {
          from: row.from,
          to: row.to,
          switchAt: row.switchAt,
          duration: row.duration,
          count: COLS,
          waveLevels: LEVELS
        }
      )
      frames.forEach((data, c) => blit(sheet, decode({ width, height, data }), c, r))
      console.log(`[exit-filmstrip] row ${r + 1}/${ROWS.length}: ${row.name}`)
    }
  } finally {
    await close()
  }
  const file = path.join(outDir, 'exit-filmstrip.png')
  writeFileSync(file, PNG.sync.write(sheet))
  writeFileSync(
    path.join(outDir, 'exit-filmstrip-INDEX.md'),
    [
      '# Orb EXIT/ENTRY filmstrip (real animator envelope)',
      '',
      `${COLS} columns × ${ROWS.length} rows, left→right = time, state flips ~col ${Math.round(
        COLS * (0.35 / 1.8)
      )}.`,
      '',
      ...ROWS.map((row, i) => `- Row ${i + 1}: ${row.name}`),
      ''
    ].join('\n')
  )
  console.log(`[exit-filmstrip] wrote ${file}`)
}
main().catch((e) => {
  console.error(e)
  process.exit(1)
})
