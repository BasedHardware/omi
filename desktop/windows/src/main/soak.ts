// Long-run soak instrumentation. When OMI_SOAK=1, append a metrics sample to
// userData/soak.jsonl every 60s: per-process memory (app.getAppMetrics) plus the
// per-mode/source byte counters (getListenStats). scripts/soak-verify.mjs reads the
// JSONL and asserts no capture-window RSS creep and no bytes sent during silence.
//
// Off by default — a plain `registerSoak()` call in the main process is inert
// unless OMI_SOAK is set, so this stays wired in with zero production cost.
import { app } from 'electron'
import { appendFile } from 'node:fs/promises'
import { join } from 'node:path'
import { getListenStats } from './ipc/omiListen'

const SAMPLE_INTERVAL_MS = 60_000

let timer: NodeJS.Timeout | null = null

/** Start the soak sampler when OMI_SOAK=1. Idempotent; no-op otherwise. Call once
 *  from the main process after `app` is ready. */
export function registerSoak(): void {
  if (process.env.OMI_SOAK !== '1' || timer) return
  const file = join(app.getPath('userData'), 'soak.jsonl')
  console.log(`[soak] enabled — sampling every ${SAMPLE_INTERVAL_MS / 1000}s → ${file}`)

  const sample = (): void => {
    const line =
      JSON.stringify({ ts: Date.now(), metrics: app.getAppMetrics(), listen: getListenStats() }) +
      '\n'
    void appendFile(file, line).catch((e) =>
      console.warn(`[soak] append failed: ${(e as Error).message}`)
    )
  }

  sample() // baseline sample immediately so a short run still yields ≥1 point
  timer = setInterval(sample, SAMPLE_INTERVAL_MS)
  timer.unref?.() // never keep the process alive just to sample

  app.on('before-quit', () => {
    if (timer) clearInterval(timer)
    timer = null
  })
}
