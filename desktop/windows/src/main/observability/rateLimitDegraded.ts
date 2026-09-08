// Detects api.omi.me 429 "storms" across the main-process backend fetch helpers
// and drives a single, debounced degraded/healthy signal for the UI.
//
// Why this exists: this account sees recurring 429 storms (documented in the C/D/E
// sweep). During one, background work — task hydrate/promote/sync — quietly stops
// updating with no user-visible sign. This tracker turns "lots of 429s in a short
// window" into ONE subtle indicator that auto-clears on recovery, without spamming
// during the storm.
//
// A storm requires BOTH a count threshold AND ≥ `minDistinctKeys` distinct request
// keys within the window, so a single endpoint's retry loop can't trip the
// indicator on its own — it takes a genuine account-wide rate-limit.
//
// Pure + clock-injected: no electron, no IPC. The wiring layer feeds it request
// outcomes and reacts to onChange transitions (broadcast an IPC event, record a
// fallback). Transition-only emission is the debounce: while already degraded,
// further 429s don't re-fire; while healthy, successes don't re-fire.

export interface RateLimitDegradedOptions {
  /** Number of 429s within `windowMs` that (with the distinct-key rule) flips to degraded. */
  threshold: number
  /** Sliding window (ms) over which 429s are counted. */
  windowMs: number
  /** Minimum distinct request keys among the windowed 429s required to trip. Default 2. */
  minDistinctKeys?: number
  /** Injected clock (ms). Defaults to Date.now. Tests pass a fake. */
  now?: () => number
  /** Fired ONLY on a healthy↔degraded transition, never on repeats. */
  onChange?: (degraded: boolean) => void
}

type Hit = { at: number; key: string }

export class RateLimitDegradedTracker {
  private readonly threshold: number
  private readonly windowMs: number
  private readonly minDistinctKeys: number
  private readonly now: () => number
  private readonly onChange?: (degraded: boolean) => void
  /** Recent 429s, oldest first, pruned to `windowMs`. */
  private hits: Hit[] = []
  private degraded = false

  constructor(opts: RateLimitDegradedOptions) {
    this.threshold = Math.max(1, opts.threshold)
    this.windowMs = Math.max(1, opts.windowMs)
    this.minDistinctKeys = Math.max(1, opts.minDistinctKeys ?? 2)
    this.now = opts.now ?? Date.now
    this.onChange = opts.onChange
  }

  isDegraded(): boolean {
    return this.degraded
  }

  /**
   * Record a 429 response, keyed by request identity (e.g. "GET /v1/action-items").
   * Returns true iff this flipped healthy→degraded. `key` defaults to a single
   * bucket, which — with the distinct-key rule — means an unkeyed caller alone
   * can never trip the storm (by design; callers that care pass a real key).
   */
  record429(key = 'default'): boolean {
    const t = this.now()
    this.hits.push({ at: t, key })
    this.prune(t)
    if (
      !this.degraded &&
      this.hits.length >= this.threshold &&
      this.distinctKeys() >= this.minDistinctKeys
    ) {
      return this.setDegraded(true)
    }
    return false
  }

  /**
   * Record a successful backend response. Returns true iff this flipped
   * degraded→healthy. Recovery is deliberately conservative to avoid flicker: a
   * success only clears the state once the recent 429s have aged out of the
   * window (the storm has actually passed), not on an interleaved success while
   * 429s are still fresh.
   */
  recordSuccess(): boolean {
    const t = this.now()
    this.prune(t)
    if (this.degraded && this.hits.length === 0) {
      return this.setDegraded(false)
    }
    return false
  }

  private distinctKeys(): number {
    return new Set(this.hits.map((h) => h.key)).size
  }

  /** Drop 429 hits older than the window relative to `t`. */
  private prune(t: number): void {
    const cutoff = t - this.windowMs
    // hits is time-ordered; drop from the front.
    let i = 0
    while (i < this.hits.length && this.hits[i].at < cutoff) i++
    if (i > 0) this.hits = this.hits.slice(i)
  }

  private setDegraded(next: boolean): boolean {
    if (this.degraded === next) return false
    this.degraded = next
    this.onChange?.(next)
    return true
  }
}
