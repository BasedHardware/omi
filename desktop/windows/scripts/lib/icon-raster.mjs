// Shared rasterization helpers for the Windows icon generators
// (gen-tray-icons.mjs and gen-app-icon.mjs). Both draw the Omi 8-dot ring at
// each native size on a supersampled coverage grid, then pack the frames into a
// multi-size .ico. Only the compositing/downsampling and per-size geometry
// differ between the two generators; the primitives below are identical, so
// they live here to stay in lockstep.
import { PNG } from 'pngjs'

export const SS = 4 // supersample factor for anti-aliasing

/** Draw a filled disc onto a supersampled boolean coverage grid. */
export function disc(grid, gridSize, cx, cy, r) {
  const r2 = r * r
  const x0 = Math.max(0, Math.floor(cx - r))
  const x1 = Math.min(gridSize - 1, Math.ceil(cx + r))
  const y0 = Math.max(0, Math.floor(cy - r))
  const y1 = Math.min(gridSize - 1, Math.ceil(cy + r))
  for (let y = y0; y <= y1; y++) {
    for (let x = x0; x <= x1; x++) {
      const dx = x + 0.5 - cx
      const dy = y + 0.5 - cy
      if (dx * dx + dy * dy <= r2) grid[y * gridSize + x] = 1
    }
  }
}

/** Draw the 8-dot ring centered at (cx, cy) with the given scale. */
export function ring(grid, gridSize, cx, cy, ringR, dotR) {
  for (let i = 0; i < 8; i++) {
    const a = (i / 8) * Math.PI * 2 - Math.PI / 2 // start at 12 o'clock
    disc(grid, gridSize, cx + ringR * Math.cos(a), cy + ringR * Math.sin(a), dotR)
  }
}

/** Pack PNG-compressed frames into a .ico (ICONDIR + entries + PNG blobs). */
export function packIco(framesBySize) {
  const entries = []
  const blobs = []
  let offset = 6 + 16 * framesBySize.length
  for (const [size, png] of framesBySize) {
    const buf = PNG.sync.write(png)
    const entry = Buffer.alloc(16)
    entry.writeUInt8(size >= 256 ? 0 : size, 0) // width (0 = 256)
    entry.writeUInt8(size >= 256 ? 0 : size, 1) // height
    entry.writeUInt8(0, 2) // palette
    entry.writeUInt8(0, 3) // reserved
    entry.writeUInt16LE(1, 4) // planes
    entry.writeUInt16LE(32, 6) // bpp
    entry.writeUInt32LE(buf.length, 8)
    entry.writeUInt32LE(offset, 12)
    entries.push(entry)
    blobs.push(buf)
    offset += buf.length
  }
  const header = Buffer.alloc(6)
  header.writeUInt16LE(0, 0)
  header.writeUInt16LE(1, 2) // type: icon
  header.writeUInt16LE(framesBySize.length, 4)
  return Buffer.concat([header, ...entries, ...blobs])
}
