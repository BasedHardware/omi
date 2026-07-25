// Pure geometry + matching helpers for the Rewind search highlight overlay.
// Kept free of React/DOM so they are unit-testable in isolation.

export type Rect = { left: number; top: number; width: number; height: number }

const ZERO_RECT: Rect = { left: 0, top: 0, width: 0, height: 0 }

/**
 * The letterboxed content rect of an image drawn with `object-contain` inside a
 * container of the given size — i.e. where the visible pixels actually land.
 * Returns a zero rect for degenerate (non-positive) inputs.
 */
export function containedImageRect(
  containerW: number,
  containerH: number,
  imageW: number,
  imageH: number
): Rect {
  if (containerW <= 0 || containerH <= 0 || imageW <= 0 || imageH <= 0) return ZERO_RECT
  const scale = Math.min(containerW / imageW, containerH / imageH)
  const width = imageW * scale
  const height = imageH * scale
  return { left: (containerW - width) / 2, top: (containerH - height) / 2, width, height }
}

/** Map a normalized (0..1) OCR box onto pixel coords within a contained rect. */
export function normalizedBoxToRect(
  box: { x: number; y: number; w: number; h: number },
  contained: Rect
): Rect {
  return {
    left: contained.left + box.x * contained.width,
    top: contained.top + box.y * contained.height,
    width: box.w * contained.width,
    height: box.h * contained.height
  }
}

/** Lowercased highlight terms from a raw query (whitespace-split, length >= 2 to
 *  align with the FTS prefix tokens that produced the results). */
export function highlightTerms(query: string): string[] {
  return query
    .trim()
    .toLowerCase()
    .split(/\s+/)
    .filter((t) => t.length >= 2)
}

/** True when a line's text contains any of the (already-lowercased) terms. */
export function lineTextMatches(lineText: string, lowerTerms: string[]): boolean {
  if (lowerTerms.length === 0) return false
  const lower = lineText.toLowerCase()
  return lowerTerms.some((t) => lower.includes(t))
}
