// Orb harness — WAVEFORM evidence. Renders the dots→waveform visualizer at the
// two real mount aspects (wide bar pill ~120×36, compact square 26px) as time
// strips composited over the pill's dark background (#151515), flipped top-down.
// A skeptical reviewer judges these (see the session scratchpad path below).
//
// Rows:
//   1. wide scroll  — silence → speech burst → silence scrolling right→left
//   2. wide held    — a mid-speech frame, amplitude sweep (bar heights track it)
//   3. mini scroll  — the same scroll on a compact 26px square (mini visualizer)
//   4. entry        — idle ring → UNROLL/fan-out into the line → bars fade in and
//                     respond (staged: the row forms first, then the bars come
//                     alive). THE transition centerpiece.
//   5. exit         — the reverse: bars flatten to dots, then the row rolls back
//                     up into the ring.
// Run: node scripts/orb/waveform-sheet.mjs [outDir]
import { PNG } from 'pngjs'
import { mkdirSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { openHarness } from './lib/harness.mjs'

const OUT =
  process.argv[2] ??
  'C:/Users/chris/AppData/Local/Temp/claude/C--Users-chris-projects-omi/acd7159f-1dee-4e05-a85c-81b03ee3cf43/scratchpad/waveform-out'
const BG = [21, 21, 21]
const COLS = 12
const DPR = 2

// A static speech-ish level pattern (tall clusters + short valleys) for the
// transition row — lets the crossfade read without the content also scrolling.
function staticLevels(n) {
  return Array.from({ length: n }, (_, i) => {
    const u = i / (n - 1)
    // Left third mostly silence (dots), right two-thirds an envelope of bars.
    if (u < 0.34) return 0
    const v = (u - 0.34) / 0.66
    return Math.max(
      0,
      Math.min(1, (0.55 + 0.45 * Math.sin(v * Math.PI * 4)) * Math.sin(v * Math.PI))
    )
  })
}

async function renderInto(page, sheet, tileW, tileH, col, row, spec) {
  const img = await page.evaluate(
    (s) => {
      window.orb.setCanvasSize(s.w, s.h, s.dpr)
      window.orb.renderAt(s.spec)
      return window.orb.pixels()
    },
    { w: tileW / DPR, h: tileH / DPR, dpr: DPR, spec }
  )
  const data = Buffer.from(img.data, 'base64')
  for (let y = 0; y < tileH; y++) {
    const srcY = img.height - 1 - y // WebGL readback is bottom-up
    for (let x = 0; x < tileW; x++) {
      const si = (srcY * img.width + x) * 4
      const a = data[si + 3] / 255
      const di = ((row * tileH + y) * sheet.width + col * tileW + x) * 4
      for (let ch = 0; ch < 3; ch++) {
        const c = a > 0 ? data[si + ch] / a : 0
        sheet.data[di + ch] = Math.round(Math.min(255, c) * a + BG[ch] * (1 - a))
      }
      sheet.data[di + 3] = 255
    }
  }
}

function newSheet(tileW, tileH, cols, rows) {
  const sheet = new PNG({ width: cols * tileW, height: rows * tileH })
  for (let i = 0; i < sheet.width * sheet.height; i++) {
    sheet.data[i * 4] = BG[0]
    sheet.data[i * 4 + 1] = BG[1]
    sheet.data[i * 4 + 2] = BG[2]
    sheet.data[i * 4 + 3] = 255
  }
  return sheet
}

async function main() {
  mkdirSync(OUT, { recursive: true })
  const { page, close } = await openHarness('?size=96&dpr=2')
  try {
    // --- Wide strips (120×36 → 240×72 backing) --------------------------------
    const wW = 240
    const wH = 72
    const wide = newSheet(wW, wH, COLS, 2)
    for (let c = 0; c < COLS; c++) {
      const t = 0.4 + (c / (COLS - 1)) * 6.0 // 0.4..6.4 covers silence→burst→silence
      await renderInto(page, wide, wW, wH, c, 0, {
        t,
        state: 'speaking',
        stateTime: t,
        waveDemo: true
      })
      // Held row: fixed mid-speech scroll position, amplitude of the NEWEST slots
      // swept 0→1→0 by nudging the sample time so the right-hand bars breathe.
      const held = 3.0 + Math.sin((c / (COLS - 1)) * Math.PI) * 1.6
      await renderInto(page, wide, wW, wH, c, 1, {
        t: held,
        state: 'speaking',
        stateTime: held,
        waveDemo: true
      })
    }
    writeFileSync(path.join(OUT, 'wide-scroll.png'), PNG.sync.write(wide))

    // --- Mini strip (26×26 → 52×52 backing) -----------------------------------
    const mW = 52
    const mini = newSheet(mW, mW, COLS, 1)
    for (let c = 0; c < COLS; c++) {
      const t = 0.4 + (c / (COLS - 1)) * 6.0
      await renderInto(page, mini, mW, mW, c, 0, {
        t,
        state: 'speaking',
        stateTime: t,
        waveDemo: true
      })
    }
    writeFileSync(path.join(OUT, 'mini-scroll.png'), PNG.sync.write(mini))

    // --- ENTRY strip (wide): ring → unroll → line → bars respond (staged) -----
    // Mirrors the animator staging: the speech-merge envelope drives the unroll
    // FIRST, then the bar-response gain ramps in once the row is formed.
    const NCOL = 16
    const levels = staticLevels(24)
    const entry = newSheet(wW, wH, NCOL, 1)
    for (let c = 0; c < NCOL; c++) {
      const e = c / (NCOL - 1) // entry progress 0..1
      const speechMerge = Math.min(1, e / 0.55) // unroll completes ~55% in
      const waveResponse = Math.max(0, Math.min(1, (e - 0.55) / 0.4)) // ramps after
      await renderInto(page, entry, wW, wH, c, 0, {
        t: 40,
        state: 'speaking',
        stateTime: 40,
        speechMerge,
        waveResponse,
        waveLevels: levels
      })
    }
    writeFileSync(path.join(OUT, 'entry.png'), PNG.sync.write(entry))

    // --- EXIT strip (wide): bars flatten, then the row rolls back to the ring --
    const exit = newSheet(wW, wH, NCOL, 1)
    for (let c = 0; c < NCOL; c++) {
      const x = c / (NCOL - 1) // exit progress 0 (open) .. 1 (closed)
      const waveResponse = Math.max(0, 1 - x / 0.35) // response falls first
      const speechMerge = Math.max(0, Math.min(1, 1 - (x - 0.2) / 0.8)) // then unroll reverses
      await renderInto(page, exit, wW, wH, c, 0, {
        t: 40,
        state: 'speaking',
        stateTime: 40,
        speechMerge,
        waveResponse,
        waveLevels: levels
      })
    }
    writeFileSync(path.join(OUT, 'exit.png'), PNG.sync.write(exit))
  } finally {
    await close()
  }

  const index = [
    '# Orb waveform evidence',
    '',
    'All frames composited over the pill background #151515, left→right = time.',
    '',
    '- `wide-scroll.png` — 120×36 mount. Row 1: silence → speech burst → silence,',
    '  scrolling right→left (silence renders as dots, speech as vertical bars).',
    '  Row 2: a mid-speech position with the newest bars breathing (amplitude sweep).',
    '- `mini-scroll.png` — 26×26 compact mount: the same scroll as a mini visualizer',
    '  (~6 slots).',
    '- `entry.png` — 120×36, the transition centerpiece. The idle ring UNROLLS /',
    '  fans out into the horizontal line (staggered, bowing through an arc), THEN',
    '  the bars fade in and respond — the row forms first, the bars come alive after.',
    '- `exit.png` — the reverse: the bars flatten to a dot row, then the row rolls',
    '  back up into the ring. Judge for pops, uneven spacing mid-unroll, height jumps.',
    ''
  ].join('\n')
  writeFileSync(path.join(OUT, 'INDEX.md'), index)
  console.log(`[waveform-sheet] wrote strips + INDEX.md to ${OUT}`)
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
