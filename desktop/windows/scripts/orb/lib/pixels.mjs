// Pixel-level analysis helpers for the orb harness checks. All functions take
// the raw RGBA readback ({ width, height, data }) from renderPixels().
// NOTE: WebGL readPixels rows are bottom-up; none of these checks care about
// vertical orientation (bounds/components/centroids are orientation-agnostic
// up to a flip, and assertions are symmetric), so no flip is performed here.
// The contact sheet DOES flip for human eyes (see contact-sheet.mjs).

/** Iterate pixels, calling fn(x, y, r, g, b, a). */
export function eachPixel({ width, height, data }, fn) {
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const i = (y * width + x) * 4
      fn(x, y, data[i], data[i + 1], data[i + 2], data[i + 3])
    }
  }
}

/**
 * Invariant: zero purple pixels. The orb palette is strictly neutral, so we
 * assert BOTH the specific purple-band relationship (blue notably > red AND
 * red > green) and a general grayscale bound (channel spread) on every
 * non-transparent pixel. Returns a list of violations (empty = pass).
 */
export function findPurple(img, { spread = 24 } = {}) {
  const bad = []
  eachPixel(img, (x, y, r, g, b, a) => {
    if (a < 8) return
    const purpleBand = b > r + 12 && r > g + 12
    const magentaBand = b > g + 20 && r > g + 20
    const chroma = Math.max(r, g, b) - Math.min(r, g, b)
    if (purpleBand || magentaBand || chroma > spread) {
      if (bad.length < 8) bad.push({ x, y, r, g, b, a })
      else bad.length++ // count without storing
    }
  })
  return bad
}

/** Invariant: fully transparent background — corners and a 1px border. */
export function checkTransparentEdges(img) {
  const { width, height, data } = img
  const violations = []
  const check = (x, y) => {
    const a = data[(y * width + x) * 4 + 3]
    if (a !== 0) violations.push({ x, y, a })
  }
  for (let x = 0; x < width; x++) {
    check(x, 0)
    check(x, height - 1)
  }
  for (let y = 0; y < height; y++) {
    check(0, y)
    check(width - 1, y)
  }
  return violations
}

/** Binary mask of "white dot" pixels (bright + opaque-ish). */
export function whiteMask(img, { threshold = 200 } = {}) {
  const { width, height, data } = img
  const mask = new Uint8Array(width * height)
  for (let i = 0; i < width * height; i++) {
    const r = data[i * 4]
    const g = data[i * 4 + 1]
    const b = data[i * 4 + 2]
    const a = data[i * 4 + 3]
    if (a > 128 && r > threshold && g > threshold && b > threshold) mask[i] = 1
  }
  return { mask, width, height }
}

/** Connected components (4-connectivity) of a binary mask → array of
 *  { size, cx, cy } sorted by size desc. Used for blob counting + centroids. */
export function components({ mask, width, height }, { minSize = 4 } = {}) {
  const labels = new Int32Array(width * height).fill(-1)
  const comps = []
  const stack = []
  for (let start = 0; start < mask.length; start++) {
    if (!mask[start] || labels[start] !== -1) continue
    const id = comps.length
    let size = 0
    let sx = 0
    let sy = 0
    stack.push(start)
    labels[start] = id
    while (stack.length) {
      const i = stack.pop()
      const x = i % width
      const y = (i / width) | 0
      size++
      sx += x
      sy += y
      for (const [dx, dy] of [
        [1, 0],
        [-1, 0],
        [0, 1],
        [0, -1]
      ]) {
        const nx = x + dx
        const ny = y + dy
        if (nx < 0 || ny < 0 || nx >= width || ny >= height) continue
        const ni = ny * width + nx
        if (mask[ni] && labels[ni] === -1) {
          labels[ni] = id
          stack.push(ni)
        }
      }
    }
    comps.push({ size, cx: sx / size, cy: sy / size })
  }
  return comps.filter((c) => c.size >= minSize).sort((a, b) => b.size - a.size)
}

/**
 * Count enclosed holes in the white mask: flood-fill non-white from the image
 * border; any unreached non-white pixel is enclosed by white (a punched hole).
 * Returns the number of hole PIXELS (0 = solid shapes).
 */
export function countHolePixels(img, opts = {}) {
  const { mask, width, height } = whiteMask(img, opts)
  const visited = new Uint8Array(width * height)
  const stack = []
  const push = (x, y) => {
    const i = y * width + x
    if (!visited[i] && !mask[i]) {
      visited[i] = 1
      stack.push(i)
    }
  }
  for (let x = 0; x < width; x++) {
    push(x, 0)
    push(x, height - 1)
  }
  for (let y = 0; y < height; y++) {
    push(0, y)
    push(width - 1, y)
  }
  while (stack.length) {
    const i = stack.pop()
    const x = i % width
    const y = (i / width) | 0
    if (x > 0) push(x - 1, y)
    if (x < width - 1) push(x + 1, y)
    if (y > 0) push(x, y - 1)
    if (y < height - 1) push(x, y + 1)
  }
  let holes = 0
  for (let i = 0; i < mask.length; i++) if (!mask[i] && !visited[i]) holes++
  return holes
}

/**
 * Radial contour profile of the largest white blob: max white radius per angle
 * bin around the blob centroid. Returns { mean, cv } — the coefficient of
 * variation quantifies the "wavy edge" (0 = perfect circle).
 */
export function contourWaviness(img, { bins = 72 } = {}) {
  const wm = whiteMask(img)
  const comps = components(wm)
  if (!comps.length) return { mean: 0, cv: 0 }
  const { cx, cy } = comps[0]
  const radii = new Array(bins).fill(0)
  const { mask, width, height } = wm
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      if (!mask[y * width + x]) continue
      const dx = x - cx
      const dy = y - cy
      const bin = Math.floor(((Math.atan2(dy, dx) + Math.PI) / (2 * Math.PI)) * bins) % bins
      const r = Math.hypot(dx, dy)
      if (r > radii[bin]) radii[bin] = r
    }
  }
  const used = radii.filter((r) => r > 0)
  const mean = used.reduce((a, b) => a + b, 0) / used.length
  const variance = used.reduce((a, b) => a + (b - mean) ** 2, 0) / used.length
  return { mean, cv: Math.sqrt(variance) / mean }
}

/** Bounding box of all non-transparent pixels (null if none). */
export function opaqueBounds(img) {
  let minX = Infinity
  let minY = Infinity
  let maxX = -Infinity
  let maxY = -Infinity
  eachPixel(img, (x, y, _r, _g, _b, a) => {
    if (a === 0) return
    if (x < minX) minX = x
    if (y < minY) minY = y
    if (x > maxX) maxX = x
    if (y > maxY) maxY = y
  })
  return minX === Infinity ? null : { minX, minY, maxX, maxY }
}
