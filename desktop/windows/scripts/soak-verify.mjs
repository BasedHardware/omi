// Read a soak.jsonl produced by src/main/soak.ts and write a soak-report.json
// verdict. Usage:
//   node scripts/soak-verify.mjs --file <soak.jsonl> [--out soak-report.json]
//                                [--max-rss-slope 15] [--bytes-epsilon 65536]
// Exit 0 = pass, 1 = fail, 2 = usage/parse error. Analysis lives in the pure
// soakVerifyCore.mjs (unit-tested by soakVerify.test.mjs).
import fs from 'node:fs'
import path from 'node:path'
import { soakVerifyCore } from './soakVerifyCore.mjs'

function arg(name, fallback) {
  const i = process.argv.indexOf(name)
  return i >= 0 && i + 1 < process.argv.length ? process.argv[i + 1] : fallback
}

const file = arg('--file')
if (!file) {
  console.error('[soak-verify] --file <soak.jsonl> is required')
  process.exit(2)
}
if (!fs.existsSync(file)) {
  console.error(`[soak-verify] not found: ${file}`)
  process.exit(2)
}

const out = arg('--out', path.join(path.dirname(file), 'soak-report.json'))
const opts = {
  rssSlopeMBperHourMax: Number(arg('--max-rss-slope', '15')),
  bytesEpsilonB: Number(arg('--bytes-epsilon', String(64 * 1024)))
}

const samples = []
for (const line of fs.readFileSync(file, 'utf8').split(/\r?\n/)) {
  const t = line.trim()
  if (!t) continue
  try {
    samples.push(JSON.parse(t))
  } catch {
    // Ignore a torn final line (process killed mid-write); every prior line is intact.
  }
}

const report = soakVerifyCore(samples, opts)
fs.writeFileSync(out, JSON.stringify(report, null, 2))
console.log(`[soak-verify] ${report.pass ? 'PASS' : 'FAIL'} — ${report.samples} samples`)
console.log(
  `  bytesDuringSilence=${report.bytesDuringSilenceB}B  rssSlope=${report.rssSlopeMBperHour}MB/h  → ${out}`
)
for (const r of report.reasons) console.log(`  - ${r}`)
process.exit(report.pass ? 0 : 1)
