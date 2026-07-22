// Generates the three tray-state .ico files. Windows tray icons must be
// multi-size .ico so the OS picks the right frame per DPI (16px at 100%,
// 20px at 125%, 24px at 150%, 32px at 200%).
//
// Every frame is DRAWN AT ITS NATIVE SIZE (supersampled 4x for anti-aliasing)
// instead of downscaling one large image — a naive downscale fuses the
// 8-dot ring into blobs at 16px (found by skeptical icon review, 2026-07-10).
// The mark is the Omi ring of 8 dots, drawn programmatically so geometry can
// be tuned per size: small frames get a wider ring and guaranteed inter-dot
// gaps; the listening badge gets a carved transparent moat and edge margin.
//
// States (NEVER purple — white/grey only):
//   idle       → white 8-dot ring
//   listening  → ring shrunk toward top-left + solid white badge dot at
//                bottom-right, separated by a carved transparent moat
//   paused     → the ring dimmed to ~55% grey
//
// Run: pnpm gen:tray-icons  (writes resources/tray/{idle,listening,paused}.ico)
import { writeFileSync, mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { PNG } from 'pngjs'
import { SS, disc, ring, packIco } from './lib/icon-raster.mjs'

const here = dirname(fileURLToPath(import.meta.url))
const outDir = join(here, '..', 'resources', 'tray')

const SIZES = [16, 20, 24, 32, 48, 64, 128, 256]

/** Per-size geometry. Small sizes are hand-tuned so dots never fuse:
 *  ring radius uses the full canvas and dot gaps stay >= ~2px. */
function geometry(size) {
  if (size <= 20) {
    return { ringR: size * 0.375, dotR: size * 0.078 } // 16: R=6.0, dot r=1.25 → 2.2px gaps
  }
  return { ringR: size * 0.34, dotR: size * 0.095 } // matches the 32px look that passed review
}

/** Carve a disc back OUT of the coverage grid (the transparent moat). */
function carve(grid, gridSize, cx, cy, r) {
  const r2 = r * r
  const x0 = Math.max(0, Math.floor(cx - r))
  const x1 = Math.min(gridSize - 1, Math.ceil(cx + r))
  const y0 = Math.max(0, Math.floor(cy - r))
  const y1 = Math.min(gridSize - 1, Math.ceil(cy + r))
  for (let y = y0; y <= y1; y++) {
    for (let x = x0; x <= x1; x++) {
      const dx = x + 0.5 - cx
      const dy = y + 0.5 - cy
      if (dx * dx + dy * dy <= r2) grid[y * gridSize + x] = 0
    }
  }
}

/** Downsample the supersampled coverage grid into a PNG with the given RGB. */
function toPng(grid, size, rgb) {
  const png = new PNG({ width: size, height: size })
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      let cov = 0
      for (let sy = 0; sy < SS; sy++) {
        for (let sx = 0; sx < SS; sx++) {
          cov += grid[(y * SS + sy) * (size * SS) + (x * SS + sx)]
        }
      }
      const o = (y * size + x) << 2
      png.data[o] = rgb[0]
      png.data[o + 1] = rgb[1]
      png.data[o + 2] = rgb[2]
      png.data[o + 3] = Math.round((cov / (SS * SS)) * 255)
    }
  }
  return png
}

function drawFrame(size, state) {
  const g = size * SS
  const grid = new Uint8Array(g * g)
  const { ringR, dotR } = geometry(size)
  const c = (size / 2) * SS

  if (state === 'listening') {
    // Mark shrunk toward the top-left so the badge gets clear space, with a
    // carved moat and >= 1px edge margin (per skeptical review at 16px).
    const shrink = 0.74
    const mc = size * 0.42 * SS
    ring(grid, g, mc, mc, ringR * shrink * SS, Math.max(dotR * shrink, size * 0.062) * SS)
    const badgeR = Math.max(size * 0.17, 2.6) // 16px → 2.75px radius (5.5px disc)
    const margin = Math.max(1, size * 0.05)
    const bc = (size - margin - badgeR) * SS
    const moat = Math.max(2, size * 0.08) // >= 2px carved gap at every size
    carve(grid, g, bc, bc, (badgeR + moat) * SS)
    disc(grid, g, bc, bc, badgeR * SS)
  } else {
    ring(grid, g, c, c, ringR * SS, dotR * SS)
  }

  const rgb = state === 'paused' ? [140, 140, 140] : [255, 255, 255]
  return toPng(grid, size, rgb)
}

mkdirSync(outDir, { recursive: true })
for (const state of ['idle', 'listening', 'paused']) {
  const frames = SIZES.map((s) => [s, drawFrame(s, state)])
  const outPath = join(outDir, `${state}.ico`)
  writeFileSync(outPath, packIco(frames))
  console.log(`wrote ${outPath}`)
}
