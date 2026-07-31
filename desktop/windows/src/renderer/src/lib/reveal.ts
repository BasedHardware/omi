export function revealStep(remaining: number, elapsedMs: number): number {
  if (remaining <= 0) return 0
  const base = elapsedMs / 5
  const catchUp = remaining / 8
  return Math.min(remaining, Math.max(1, Math.ceil(Math.max(base, catchUp))))
}
