// Generates the Windows application icon: resources/icon.png (256x256, used by
// every BrowserWindow via `resources/icon.png?asset`) and resources/icon.ico
// (multi-size, wired to electron-builder `win.icon` for the packaged app,
// taskbar, installer, and shortcuts).
//
// WHY THIS EXISTS: the previous icon.png was macOS-style art — a near-full-bleed
// white ROUNDED-SQUARE (squircle) backing with the black 8-dot ring on top.
// macOS masks that shape to its own superellipse; Windows renders the art as-is,
// so the taskbar/Alt-Tab icon looked like a white square. Windows never masks,
// so the icon must supply its OWN shape: a TRUE CIRCLE white disc on full
// transparency, with the black 8-dot Omi ring centered on it.
//
// Every frame is DRAWN AT ITS NATIVE SIZE (supersampled 4x for anti-aliasing)
// rather than downscaled — a naive downscale fuses the 8 dots into blobs at
// small sizes (the same lesson gen-tray-icons.mjs records). The disc/ring/ico
// helpers are shared with gen-tray-icons.mjs via ./lib/icon-raster.mjs (that
// geometry passed a skeptical icon review); the only new piece is two-color
// compositing (white disc + black dots), which the single-color tray
// downsampler can't express.
//
// BRAND RULE: never purple — white disc, black mark, nothing else.
//
// Run: pnpm gen:app-icon  (writes resources/icon.png + resources/icon.ico)
import { writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { PNG } from 'pngjs'
import { SS, disc, ring, packIco } from './lib/icon-raster.mjs'

const here = dirname(fileURLToPath(import.meta.url))
const resDir = join(here, '..', 'resources')

// .ico frames Windows selects between per DPI. 256 is required by
// electron-builder; the smaller sizes keep the taskbar/Alt-Tab crisp.
const ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]
const PNG_SIZE = 256

// Mark geometry. At >= 24px: dot centers on a ring of radius 0.34*size, dot
// radius 0.095*size (the 32px look that passed the tray review). The mark's
// bounding box spans (0.34+0.095)*2 = 0.87 of the canvas — a bold ~87% glyph —
// and its outer edge (0.435*size) stays inside the disc at every size, so no
// dot clips the disc edge. At <= 20px the same trick gen-tray-icons.mjs uses:
// slightly wider ring + thinner dots so the 8 dots keep clear white gaps
// instead of fusing into a blob.
function geometry(size) {
  if (size <= 20) return { ringR: 0.36, dotR: 0.082 }
  return { ringR: 0.34, dotR: 0.095 }
}

/**
 * Composite the white disc grid and black dot grid into an RGBA PNG.
 * Per output pixel we count subpixels that are white (disc, no dot), black
 * (dot), or transparent (outside disc), then average in PREMULTIPLIED-alpha
 * space so a dot's edge blends against white and the disc's edge fades to
 * transparent without the grey halo that averaging straight-alpha would give.
 */
function compositeToPng(discGrid, dotGrid, size) {
  const png = new PNG({ width: size, height: size })
  const n = SS * SS
  const g = size * SS
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      let white = 0
      let black = 0
      for (let sy = 0; sy < SS; sy++) {
        for (let sx = 0; sx < SS; sx++) {
          const idx = (y * SS + sy) * g + (x * SS + sx)
          if (dotGrid[idx]) black++
          else if (discGrid[idx]) white++
        }
      }
      const opaque = white + black
      const o = (y * size + x) << 2
      // rgb = 255 weighted by the white fraction of covered subpixels (black = 0)
      const rgb = opaque > 0 ? Math.round((255 * white) / opaque) : 0
      png.data[o] = rgb
      png.data[o + 1] = rgb
      png.data[o + 2] = rgb
      png.data[o + 3] = Math.round((opaque / n) * 255)
    }
  }
  return png
}

function drawFrame(size) {
  const g = size * SS
  const discGrid = new Uint8Array(g * g)
  const dotGrid = new Uint8Array(g * g)
  const c = (size / 2) * SS

  // True circle disc: radius = half the canvas minus a ~1px anti-alias margin
  // so the edge is a clean feathered circle, not a hard-cut chord at the
  // outermost pixel row.
  const margin = Math.max(0.5, size * 0.004)
  disc(discGrid, g, c, c, (size / 2 - margin) * SS)

  const { ringR, dotR } = geometry(size)
  ring(dotGrid, g, c, c, ringR * size * SS, dotR * size * SS)

  return compositeToPng(discGrid, dotGrid, size)
}

const pngPath = join(resDir, 'icon.png')
writeFileSync(pngPath, PNG.sync.write(drawFrame(PNG_SIZE)))
console.log(`wrote ${pngPath}`)

const icoPath = join(resDir, 'icon.ico')
writeFileSync(
  icoPath,
  packIco(ICO_SIZES.map((s) => [s, drawFrame(s)]))
)
console.log(`wrote ${icoPath}`)
