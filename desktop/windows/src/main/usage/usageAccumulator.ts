export type UsageDelta = { exePath: string; ms: number }

// Accepts one foreground sample per poll tick and credits the time between
// consecutive samples to the EARLIER sample's app. Gaps beyond maxGapMs (sleep,
// lock, monitor stall) are dropped so suspended time isn't counted. Null/empty
// samples reset the cursor without crediting anything.
export class UsageAccumulator {
  private totals = new Map<string, number>()
  private prev: { exePath: string; ts: number } | null = null

  constructor(private readonly maxGapMs: number) {}

  addSample(exePath: string | null, ts: number): void {
    if (this.prev) {
      const delta = ts - this.prev.ts
      if (delta > 0 && delta <= this.maxGapMs) {
        this.totals.set(this.prev.exePath, (this.totals.get(this.prev.exePath) ?? 0) + delta)
      }
    }
    this.prev = exePath ? { exePath, ts } : null
  }

  drain(): UsageDelta[] {
    const out: UsageDelta[] = []
    for (const [exePath, ms] of this.totals) out.push({ exePath, ms })
    this.totals.clear()
    return out
  }
}
