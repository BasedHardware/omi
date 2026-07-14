// Generates the Windows application icon: resources/icon.png (256x256, used by
// every BrowserWindow via `resources/icon.png?asset`) and resources/icon.ico
// (multi-size, wired to electron-builder `win.icon` for the packaged app,
// taskbar, installer, and shortcuts).
//
// WHY THIS EXISTS: the shipped macOS-style art (resources/icon-source.png) is a
// near-full-bleed white ROUNDED-SQUARE (squircle) backing with the small black
// 8-dot Omi ring centered on it. macOS masks that shape to its own superellipse;
// Windows renders the art as-is, so the taskbar/Alt-Tab icon looked like a white
// square. Windows never masks, so the icon must supply its OWN circular shape.
//
// This does NOT redraw the mark — an earlier procedural redraw changed the ring
// proportions and read wrong. Instead it CROPS the original art into a circle:
// flatten the source over white (its transparent squircle corners become white),
// zoom a hair around center so the dots read a touch larger, then apply an
// anti-aliased circular alpha mask. The dot pixels are the ORIGINAL art's, at
// their original size/position (× the slight zoom below).
//
// The circle is deliberately smaller than the canvas (real transparent margin),
// matching Spotify's Windows taskbar icon: its green disc measures 94.5% of the
// canvas at 256px (93.8% at 32px), extracted via PrivateExtractIcons and
// measured. A near-full-bleed circle read "too big", so CIRCLE_RATIO tracks
// Spotify. Because only the white BACKING is clipped to the smaller circle while
// the dots stay mapped 1:1 from the source, shrinking the circle does NOT shrink
// the dots — they keep the original art's absolute size (× ZOOM).
//
// Every output size is resampled directly from the flattened source at a
// supersampled grid (area-averaged 4x), so both the circle edge and the dots
// stay anti-aliased at 16px without a naive one-image downscale.
//
// BRAND RULE: never purple — white backing, black mark, nothing else.
//
// Run: pnpm gen:app-icon  (writes resources/icon.png + resources/icon.ico)
import { readFileSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { PNG } from 'pngjs'
import { packIco } from './lib/icon-raster.mjs'

const here = dirname(fileURLToPath(import.meta.url))
const resDir = join(here, '..', 'resources')

// .ico frames Windows selects between per DPI. 256 is required by
// electron-builder; the smaller sizes keep the taskbar/Alt-Tab crisp.
const ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]
const PNG_SIZE = 256
const SSG = 4 // supersample factor for anti-aliasing every rendered size

// The user asked for "dots the same as the square but a bit bigger." ZOOM grows
// the mark around center relative to the original art: 1.0 keeps the exact
// original dots, 1.05 makes them ~5% larger (dots and spacing scale together, so
// composition is unchanged).
const ZOOM = 1.05

// Circle diameter as a fraction of the canvas, tracking Spotify's taskbar icon
// (measured 94.5% at 256px). The remaining ~5.5% is real transparent margin so
// the disc reads as a circle, not a near-square full-bleed blob.
const CIRCLE_RATIO = 0.945

// Load the original art once and flatten it over white: the squircle body is
// white and its transparent corners become white, leaving an opaque grayscale
// image (white backing + black/greys for the anti-aliased dots). One channel
// suffices since the art is grayscale.
const SRC = PNG.sync.read(readFileSync(join(resDir, 'icon-source.png')))
const SRC_N = SRC.width // 256
const flatLuma = new Float32Array(SRC_N * SRC_N)
for (let i = 0; i < SRC_N * SRC_N; i++) {
  const o = i << 2
  const a = SRC.data[o + 3] / 255
  flatLuma[i] = SRC.data[o] * a + 255 * (1 - a)
}

/** Bilinear sample of the flattened source luma at (u,v) in source-pixel space. */
function sampleFlat(u, v) {
  // center-zoom: sample a smaller region around center to magnify content
  const cc = (SRC_N - 1) / 2
  const su = cc + (u - cc) / ZOOM
  const sv = cc + (v - cc) / ZOOM
  const x = Math.min(SRC_N - 1, Math.max(0, su))
  const y = Math.min(SRC_N - 1, Math.max(0, sv))
  const x0 = Math.floor(x)
  const y0 = Math.floor(y)
  const x1 = Math.min(SRC_N - 1, x0 + 1)
  const y1 = Math.min(SRC_N - 1, y0 + 1)
  const fx = x - x0
  const fy = y - y0
  const a = flatLuma[y0 * SRC_N + x0]
  const b = flatLuma[y0 * SRC_N + x1]
  const d = flatLuma[y1 * SRC_N + x0]
  const e = flatLuma[y1 * SRC_N + x1]
  return a * (1 - fx) * (1 - fy) + b * fx * (1 - fy) + d * (1 - fx) * fy + e * fx * fy
}

/**
 * Render one size: for each output pixel, average an SSG×SSG grid of subpixels.
 * A subpixel inside the inscribed circle contributes the flattened source luma
 * (opaque); outside contributes transparent. Averaging luma over the covered
 * subpixels and alpha over all subpixels gives premultiplied-correct edges for
 * both the circle boundary and the dots.
 */
function drawFrame(size) {
  const png = new PNG({ width: size, height: size })
  const n = SSG * SSG
  const cx = size / 2
  const cy = size / 2
  const r = (CIRCLE_RATIO * size) / 2 // smaller than the canvas → transparent margin
  const r2 = r * r
  for (let py = 0; py < size; py++) {
    for (let px = 0; px < size; px++) {
      let cov = 0
      let sumL = 0
      for (let sy = 0; sy < SSG; sy++) {
        for (let sx = 0; sx < SSG; sx++) {
          const ox = px + (sx + 0.5) / SSG // output-pixel-space coord
          const oy = py + (sy + 0.5) / SSG
          const dx = ox - cx
          const dy = oy - cy
          if (dx * dx + dy * dy <= r2) {
            // map output coord -> source-pixel space and sample the art
            const u = (ox / size) * SRC_N
            const v = (oy / size) * SRC_N
            sumL += sampleFlat(u, v)
            cov++
          }
        }
      }
      const o = (py * size + px) << 2
      const rgb = cov > 0 ? Math.round(sumL / cov) : 0
      png.data[o] = rgb
      png.data[o + 1] = rgb
      png.data[o + 2] = rgb
      png.data[o + 3] = Math.round((cov / n) * 255)
    }
  }
  return png
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
