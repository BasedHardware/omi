// Live verification probe for the meeting-detection native layer, run OUTSIDE
// Electron against the REAL machine:
//
//   pnpm exec vite-node scripts/meeting-native-probe.ts            # one-shot
//   pnpm exec vite-node scripts/meeting-native-probe.ts --watch    # + watcher
//   pnpm exec vite-node scripts/meeting-native-probe.ts --soak-min 10
//
// One-shot: Toolhelp32 process snapshot + Tier 1 pattern matches + ConsentStore
// read (packaged + NonPackaged, active-now entries). The watcher check is
// SELF-CONTAINED: it plants a fake in-use leaf under NonPackaged (HKCU is
// user-writable), asserts the event fires and the reader sees it active, then
// deletes it and asserts it disappears.
//
// Soak mode: arms the watcher and samples process.cpuUsage() every 30s for N
// minutes to prove the event-driven wait burns no CPU (no-polling requirement).
import { execFileSync } from 'node:child_process'
import { listProcessNames } from '../src/main/meeting/processSnapshot'
import { readMicCaptureEntries, watchMicConsentStore } from '../src/main/meeting/micConsentStore'
import { bundledPatterns, matchTier1, pickAgreedMatch } from '../src/main/meeting/patterns'

const MIC_KEY =
  'HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\CapabilityAccessManager\\ConsentStore\\microphone'
const PROBE_KEY = `${MIC_KEY}\\NonPackaged\\C:#OmiMeetingProbe#fake-probe.exe`

function reg(args: string[]): void {
  execFileSync('reg', args, { stdio: 'pipe' })
}

function oneShot(): void {
  const t0 = Date.now()
  const procs = listProcessNames()
  const snapMs = Date.now() - t0
  console.log(`[snapshot] ${procs.length} processes in ${snapMs}ms`)
  if (procs.length === 0) throw new Error('snapshot returned 0 processes — koffi binding broken')
  for (const known of ['explorer.exe', 'svchost.exe']) {
    console.log(`[snapshot] contains ${known}: ${procs.includes(known)}`)
  }

  const patterns = bundledPatterns()
  const matches = matchTier1(procs, { exePath: null, title: null }, patterns)
  console.log(`[tier1] conferencing processes running now:`, matches)

  const t1 = Date.now()
  const active = readMicCaptureEntries()
  console.log(`[tier2] ConsentStore read in ${Date.now() - t1}ms — active mic captures:`, active)
  console.log(
    `[gate] agreed match right now:`,
    pickAgreedMatch(
      matches,
      active.map((e) => e.id),
      patterns
    )
  )
}

async function watcherCheck(): Promise<void> {
  console.log('\n[watch] arming RegNotifyChangeKeyValue watcher…')
  let events = 0
  const watcher = watchMicConsentStore(() => {
    events++
    console.log(`[watch] change event #${events}`)
  })
  if (!watcher) throw new Error('watcher failed to arm')

  // Plant a fake "capturing right now" leaf (LastUsedTimeStop == 0).
  console.log('[watch] planting fake in-use entry under NonPackaged…')
  reg(['add', PROBE_KEY, '/v', 'LastUsedTimeStart', '/t', 'REG_QWORD', '/d', '133600000000000000', '/f'])
  reg(['add', PROBE_KEY, '/v', 'LastUsedTimeStop', '/t', 'REG_QWORD', '/d', '0', '/f'])
  await new Promise((r) => setTimeout(r, 500))
  const during = readMicCaptureEntries()
  const seen = during.some((e) => e.id === 'fake-probe.exe')
  console.log(`[watch] reader sees planted entry active: ${seen}`)

  console.log('[watch] deleting the planted entry…')
  reg(['delete', PROBE_KEY, '/f'])
  await new Promise((r) => setTimeout(r, 500))
  const after = readMicCaptureEntries()
  const gone = !after.some((e) => e.id === 'fake-probe.exe')
  console.log(`[watch] entry gone after delete: ${gone}`)

  watcher.stop()
  await new Promise((r) => setTimeout(r, 300))
  if (events === 0) throw new Error('watcher never fired — RegNotifyChangeKeyValue path broken')
  if (!seen || !gone) throw new Error('ConsentStore reader did not track the planted entry')
  console.log(`[watch] PASS — ${events} events, plant+delete both observed`)
}

async function soak(minutes: number): Promise<void> {
  console.log(`\n[soak] watcher armed for ${minutes} min; sampling CPU every 30s…`)
  let events = 0
  const watcher = watchMicConsentStore(() => events++)
  if (!watcher) throw new Error('watcher failed to arm')
  const samples: { t: number; userMs: number; sysMs: number }[] = []
  let last = process.cpuUsage()
  const started = Date.now()
  await new Promise<void>((resolve) => {
    const timer = setInterval(() => {
      const next = process.cpuUsage()
      const d = { user: next.user - last.user, system: next.system - last.system }
      last = next
      const t = Math.round((Date.now() - started) / 1000)
      samples.push({ t, userMs: d.user / 1000, sysMs: d.system / 1000 })
      console.log(
        `[soak] t=${t}s cpu-delta user=${(d.user / 1000).toFixed(1)}ms sys=${(d.system / 1000).toFixed(1)}ms events=${events}`
      )
      if (Date.now() - started >= minutes * 60_000) {
        clearInterval(timer)
        resolve()
      }
    }, 30_000)
  })
  watcher.stop()
  // Drop the first sample (vite-node/module warmup can bleed in), then assert
  // no drift: every steady-state 30s window stays under 50ms of CPU.
  const steady = samples.slice(1)
  const worst = Math.max(...steady.map((s) => s.userMs + s.sysMs))
  console.log(`[soak] worst steady-state 30s CPU delta: ${worst.toFixed(1)}ms (${events} events)`)
  if (worst > 50) throw new Error(`CPU drift detected: ${worst.toFixed(1)}ms per 30s window`)
  console.log('[soak] PASS — no CPU drift; the wait is genuinely event-driven')
}

async function main(): Promise<void> {
  if (process.platform !== 'win32') throw new Error('windows-only probe')
  const soakIdx = process.argv.indexOf('--soak-min')
  oneShot()
  if (process.argv.includes('--watch')) await watcherCheck()
  if (soakIdx >= 0) await soak(Number(process.argv[soakIdx + 1] || '10'))
  console.log('\n[probe] done')
  process.exit(0)
}

main().catch((e) => {
  console.error('[probe] FAIL:', e)
  process.exit(1)
})
