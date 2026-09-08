// Standalone system-responsiveness probe. Runs a high-frequency timer and records
// how much later than scheduled it actually fires — a proxy for whole-system
// saturation (all-core CPU / GPU-scheduler starvation), which is what makes the OS
// mouse cursor feel slow/glitchy. Run this in its OWN process, start it a second
// before launching the app under test, and watch for jitter spikes during the
// app's first seconds.
//
// Usage:  node tools/jitter-probe.mjs [durationSec] [tag]
// Output: JSONL to stdout, one line per 250ms bucket: {t, tag, maxLag, avgLag, n}
//         plus a final {summary:...} line with the worst bucket.
const durationSec = Number(process.argv[2] ?? 25)
const tag = process.argv[3] ?? 'probe'
const TICK_MS = 8 // ~125 Hz — fine enough to catch sub-frame stalls
const BUCKET_MS = 250

const t0 = performance.now()
let last = t0
let bucketStart = t0
let bucketMax = 0
let bucketSum = 0
let bucketN = 0
let worst = { t: 0, maxLag: 0 }

function tick() {
  const now = performance.now()
  const lag = now - last - TICK_MS
  last = now
  if (lag > 0) {
    bucketMax = Math.max(bucketMax, lag)
    bucketSum += lag
    bucketN++
  }
  if (now - bucketStart >= BUCKET_MS) {
    const t = Math.round(now - t0)
    const line = {
      t,
      tag,
      maxLag: Math.round(bucketMax * 10) / 10,
      avgLag: bucketN ? Math.round((bucketSum / bucketN) * 10) / 10 : 0,
      n: bucketN
    }
    process.stdout.write(JSON.stringify(line) + '\n')
    if (bucketMax > worst.maxLag) worst = { t, maxLag: Math.round(bucketMax * 10) / 10 }
    bucketStart = now
    bucketMax = 0
    bucketSum = 0
    bucketN = 0
  }
  if (now - t0 < durationSec * 1000) setTimeout(tick, TICK_MS)
  else process.stdout.write(JSON.stringify({ summary: true, tag, worst }) + '\n')
}
setTimeout(tick, TICK_MS)
