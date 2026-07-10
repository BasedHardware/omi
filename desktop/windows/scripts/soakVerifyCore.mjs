// Pure analysis of a soak.jsonl sample series — no fs/electron, so it is unit-
// testable under vitest (scripts/soakVerify.test.mjs). Two acceptance signals:
//
//  1. bytesDuringSilenceB — total listen bytes fed across the run. The soak is an
//     IDLE soak (no speech played), so a correctly gating capture feeds ≈0 bytes;
//     a non-trivial delta means silence is leaking past the VAD gate to the backend.
//  2. rssSlopeMBperHour — least-squares slope of renderer ('Tab') working-set RSS
//     over time. A capture-window leak shows here; the app is otherwise idle.
//
// app.getAppMetrics() reports memory.workingSetSize in KILOBYTES.

/** Sum of bytes across all mode:source counters in one sample. */
function totalListenBytes(sample) {
  const listen = sample.listen ?? {}
  let sum = 0
  for (const k of Object.keys(listen)) sum += listen[k]?.bytes ?? 0
  return sum
}

/** Summed renderer working set (MB) in one sample. Renderer processes are type
 *  'Tab'; the hidden capture window is one of them. Falls back to all processes if
 *  none are typed 'Tab' (defensive against Electron type-label changes). */
function rendererRssMB(sample) {
  const metrics = sample.metrics ?? []
  const tabs = metrics.filter((m) => m.type === 'Tab')
  const pool = tabs.length > 0 ? tabs : metrics
  const kb = pool.reduce((n, m) => n + (m.memory?.workingSetSize ?? 0), 0)
  return kb / 1024
}

/** Least-squares slope of ys vs xs (units: y per x). 0 when fewer than 2 points. */
function slope(xs, ys) {
  const n = xs.length
  if (n < 2) return 0
  const meanX = xs.reduce((a, b) => a + b, 0) / n
  const meanY = ys.reduce((a, b) => a + b, 0) / n
  let num = 0
  let den = 0
  for (let i = 0; i < n; i++) {
    num += (xs[i] - meanX) * (ys[i] - meanY)
    den += (xs[i] - meanX) ** 2
  }
  return den === 0 ? 0 : num / den
}

/**
 * @param {Array} samples parsed soak.jsonl rows ({ ts, metrics, listen }).
 * @param {object} opts thresholds.
 * @returns {{pass:boolean, bytesDuringSilenceB:number, rssSlopeMBperHour:number, samples:number, reasons:string[]}}
 */
export function soakVerifyCore(samples, opts = {}) {
  const bytesEpsilonB = opts.bytesEpsilonB ?? 64 * 1024 // tolerate a few VAD misfires
  const rssSlopeMBperHourMax = opts.rssSlopeMBperHourMax ?? 15
  const minSamples = opts.minSamples ?? 3

  const rows = [...samples].sort((a, b) => a.ts - b.ts)
  const reasons = []

  if (rows.length < minSamples) {
    return {
      pass: false,
      bytesDuringSilenceB: 0,
      rssSlopeMBperHour: 0,
      samples: rows.length,
      reasons: [`only ${rows.length} sample(s); need ≥ ${minSamples}`]
    }
  }

  const bytesDuringSilenceB = totalListenBytes(rows[rows.length - 1]) - totalListenBytes(rows[0])

  const t0 = rows[0].ts
  const hours = rows.map((r) => (r.ts - t0) / 3_600_000)
  const rss = rows.map(rendererRssMB)
  const rssSlopeMBperHour = slope(hours, rss)

  if (bytesDuringSilenceB > bytesEpsilonB) {
    reasons.push(
      `${bytesDuringSilenceB}B fed during silence (> ${bytesEpsilonB}B tolerance) — gate leaking`
    )
  }
  if (rssSlopeMBperHour >= rssSlopeMBperHourMax) {
    reasons.push(
      `renderer RSS slope ${rssSlopeMBperHour.toFixed(1)}MB/h (≥ ${rssSlopeMBperHourMax}) — possible leak`
    )
  }

  return {
    pass: reasons.length === 0,
    bytesDuringSilenceB,
    rssSlopeMBperHour: Number(rssSlopeMBperHour.toFixed(3)),
    samples: rows.length,
    reasons
  }
}
