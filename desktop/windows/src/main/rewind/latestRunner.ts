/**
 * Single-flight runner with trailing-edge coalescing to the LATEST input.
 *
 * While a task is in flight, further submissions don't queue up and they aren't
 * dropped — each replaces the single "pending" slot, so only the most recent
 * input is kept. When the running task settles, the pending input (if any) runs
 * next. This guarantees the latest input is always eventually processed.
 *
 * Use it for "keep an expensive derived value tracking the newest source" work
 * (e.g. OCR of the current screen): we only care about *now*, intermediate
 * inputs are safely superseded, but the newest one must never be lost — a plain
 * "skip if busy" guard drops the newest input and strands the derived value on a
 * stale one.
 */
export function createLatestRunner<T>(run: (input: T) => Promise<void>): (input: T) => void {
  let inFlight = false
  let hasPending = false
  let pending: T | null = null

  const pump = async (input: T): Promise<void> => {
    inFlight = true
    try {
      await run(input)
    } catch {
      /* best-effort: keep draining the trailing input regardless */
    } finally {
      inFlight = false
      if (hasPending) {
        const next = pending as T
        hasPending = false
        pending = null
        void pump(next)
      }
    }
  }

  return (input: T): void => {
    if (inFlight) {
      pending = input
      hasPending = true
      return
    }
    void pump(input)
  }
}
