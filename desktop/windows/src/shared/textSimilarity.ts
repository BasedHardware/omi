const MIN_NEAR_DUPLICATE_CHARS = 32

export function normalizeForTextSimilarity(text: string): string {
  return text.toLowerCase().replace(/\s+/g, ' ').trim()
}

function bigramCounts(text: string): Map<string, number> {
  const counts = new Map<string, number>()
  for (let i = 0; i < text.length - 1; i++) {
    const gram = text.slice(i, i + 2)
    counts.set(gram, (counts.get(gram) ?? 0) + 1)
  }
  return counts
}

export function textSimilarityRatio(a: string, b: string): number {
  const left = normalizeForTextSimilarity(a)
  const right = normalizeForTextSimilarity(b)
  if (left === right) return 1
  if (!left || !right) return 0

  const maxLen = Math.max(left.length, right.length)
  const minLen = Math.min(left.length, right.length)
  if (maxLen < MIN_NEAR_DUPLICATE_CHARS) return 0
  if (minLen / maxLen < 0.6) return 0

  const leftCounts = bigramCounts(left)
  const rightCounts = bigramCounts(right)
  let overlap = 0
  for (const [gram, count] of leftCounts) {
    overlap += Math.min(count, rightCounts.get(gram) ?? 0)
  }
  return (2 * overlap) / Math.max(1, left.length + right.length - 2)
}

export function isNearDuplicateText(a: string, b: string, threshold = 0.92): boolean {
  const left = normalizeForTextSimilarity(a)
  const right = normalizeForTextSimilarity(b)
  if (left === right) return true
  if (Math.max(left.length, right.length) < MIN_NEAR_DUPLICATE_CHARS) return false
  return textSimilarityRatio(left, right) >= threshold
}
