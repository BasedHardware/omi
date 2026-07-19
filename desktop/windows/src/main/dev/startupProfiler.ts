// Env-gated startup burst profiler (OMI_STARTUP_PROFILE=<path>). Measurement-only
// tooling for the startup-lag investigation: samples per-Electron-process CPU +
// working set via app.getAppMetrics() and the MAIN-process event-loop lag at high
// frequency for the first N seconds after app-ready, and appends JSONL to the file
// named by the env var. Entirely inert unless the env var is set, so packaged
// builds and normal dev runs pay nothing. Not tree-shaken by DEV gating on purpose
// — the whole module is a no-op without the env var, and keeping it env-gated (not
// DEV-gated) lets a packaged build be profiled too.
import { app } from 'electron'
import { appendFileSync, mkdirSync } from 'fs'
import { dirname } from 'path'

const SAMPLE_INTERVAL_MS = 150
const DEFAULT_DURATION_MS = 20_000
// Event-loop lag probe cadence: schedule a timer for this delay and measure how
// late it actually fires. The overshoot is main-thread blocking (sync DB reads,
// koffi init, GC) — the thing that stalls IPC/window coordination at startup.
const LAG_PROBE_MS = 50

function profilePath(): string {
  return process.env.OMI_STARTUP_PROFILE ?? ''
}

let started = false
let maxLagMs = 0

// Per-step attribution: wrap a synchronous startup operation so its duration is
// recorded to the profile file. Inert (just calls fn) unless OMI_STARTUP_PROFILE
// is set. Used to attribute the first-paint main-thread stall to specific calls.
export function timedStep<T>(name: string, fn: () => T): T {
  const path = profilePath()
  if (!path) return fn()
  const t = performance.now()
  try {
    return fn()
  } finally {
    const ms = performance.now() - t
    if (ms >= 3)
      appendFileSync(path, JSON.stringify({ ev: 'step', name, ms: Math.round(ms) }) + '\n')
  }
}

/**
 * Start the startup profiler if OMI_STARTUP_PROFILE is set. Call once at app
 * 'ready'. Samples until DEFAULT_DURATION_MS elapses, then flushes a summary line.
 */
export function startStartupProfiler(): void {
  const path = profilePath()
  if (!path || started) return
  started = true
  mkdirSync(dirname(path), { recursive: true })

  const t0 = performance.now()
  const emit = (obj: Record<string, unknown>): void => {
    appendFileSync(path, JSON.stringify({ t: Math.round(performance.now() - t0), ...obj }) + '\n')
  }
  emit({ ev: 'start', pid: process.pid, cores: require('os').cpus().length })

  // Main event-loop lag probe: a self-rescheduling timer that logs how much it
  // overshot LAG_PROBE_MS. Overshoot == main thread was busy that long.
  let lastLag = performance.now()
  const lagProbe = (): void => {
    const now = performance.now()
    const lag = now - lastLag - LAG_PROBE_MS
    lastLag = now
    if (lag > 1) {
      if (lag > maxLagMs) maxLagMs = lag
      emit({ ev: 'lag', ms: Math.round(lag) })
    }
    if (now - t0 < DEFAULT_DURATION_MS) setTimeout(lagProbe, LAG_PROBE_MS)
  }
  setTimeout(lagProbe, LAG_PROBE_MS)

  // Per-process CPU + memory sampler.
  const sampler = setInterval(() => {
    if (performance.now() - t0 >= DEFAULT_DURATION_MS) {
      clearInterval(sampler)
      emit({ ev: 'end', maxLagMs: Math.round(maxLagMs) })
      return
    }
    try {
      const metrics = app.getAppMetrics()
      let totalCpu = 0
      const procs = metrics.map((m) => {
        const cpu = m.cpu?.percentCPUUsage ?? 0
        totalCpu += cpu
        return {
          type: m.type,
          name: m.name ?? '',
          cpu: Math.round(cpu * 10) / 10,
          rssMB: Math.round((m.memory?.workingSetSize ?? 0) / 1024)
        }
      })
      emit({ ev: 'sample', nProc: metrics.length, totalCpu: Math.round(totalCpu), procs })
    } catch {
      /* best-effort */
    }
  }, SAMPLE_INTERVAL_MS)
  sampler.unref?.()
}
