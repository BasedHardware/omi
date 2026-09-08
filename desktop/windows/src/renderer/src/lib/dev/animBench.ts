// Animation perf probe (harness "A"). Under OMI_ANIM_BENCH it records frame
// intervals + long tasks during the startup entrance animations (sidebar slide,
// content fade, etc.), computes a jank summary, and reports it to main, which
// logs it as the `anim:startup` perf mark and quits. No-op otherwise, so it's
// safe to call unconditionally on mount.
// Cover the entrance-animation window (sidebar slide + content fade end ~1.3s).
const DURATION_MS = 2000

function percentile(sorted: number[], p: number): number {
  if (sorted.length === 0) return 0
  const i = Math.min(sorted.length - 1, Math.floor((p / 100) * sorted.length))
  return sorted[i]
}

export function runAnimBench(): void {
  if (!window.omi?.isAnimBench) return

  const intervals: number[] = []
  let longTaskMs = 0
  let longTaskCount = 0
  let po: PerformanceObserver | undefined
  try {
    po = new PerformanceObserver((list) => {
      for (const e of list.getEntries()) {
        longTaskMs += e.duration
        longTaskCount += 1
      }
    })
    po.observe({ entryTypes: ['longtask'] })
  } catch {
    /* longtask unsupported — frame intervals are still captured */
  }

  let last = performance.now()
  const start = last
  let maxFrame = 0
  let maxFrameAt = 0
  const tick = (now: number): void => {
    const dt = now - last
    if (dt > maxFrame) {
      maxFrame = dt
      maxFrameAt = now - start
    }
    intervals.push(dt)
    last = now
    if (now - start < DURATION_MS) {
      requestAnimationFrame(tick)
      return
    }
    po?.disconnect()
    // Drop the first interval (rAF priming) so it doesn't skew the max.
    const frames = intervals.slice(1)
    const sorted = [...frames].sort((a, b) => a - b)
    const total = frames.reduce((s, x) => s + x, 0)
    // A 60Hz frame is ~16.7ms; count anything over 25ms as a dropped frame.
    const dropped = frames.filter((x) => x > 25).length
    const stats: Record<string, number> = {
      frames: frames.length,
      durationMs: Math.round(total),
      fps: total > 0 ? Math.round((frames.length / total) * 1000) : 0,
      dropped,
      jankRatio: frames.length ? Number((dropped / frames.length).toFixed(3)) : 0,
      p95FrameMs: Number(percentile(sorted, 95).toFixed(1)),
      maxFrameMs: Number((frames.length ? Math.max(...frames) : 0).toFixed(1)),
      maxFrameAtMs: Math.round(maxFrameAt),
      longTaskMs: Math.round(longTaskMs),
      longTaskCount
    }
    window.omi.perfAnimResult(stats)
  }
  requestAnimationFrame(tick)
}
