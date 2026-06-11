import { app } from 'electron'
import { join } from 'path'
import { existsSync, writeFileSync } from 'fs'
import { readUserAssistRaw } from './userAssistRegistry'
import { aggregateUserAssist } from './userAssist'
import { getUsageSettings } from './usageSettings'
import { seedAppUsage } from '../ipc/db'

// Ignore apps with negligible historical focus time — drops sub-minute noise the
// name-join would otherwise let through (e.g. a 12-second Telegram launch, MSI
// "Creator Center"). 1 minute is well below any app the user actually relies on.
const MIN_FOCUS_SECONDS = 60

// One-shot marker so the seed runs exactly once. Absent until a successful seed,
// so if tracking was OFF at first launch we still seed the first time it's ON.
function markerFile(): string {
  return join(app.getPath('userData'), 'userassist-seeded.json')
}

// Seed app_usage from the per-user UserAssist registry history, ONCE. No-op when:
// off-Windows, app-usage tracking is disabled (opt-out), already seeded, or the
// registry can't be read. Never throws. Stamps `now` as last_used so the snapshot
// survives the retention window. Call at startup before the first brain-map build.
export function seedUserAssistOnce(): void {
  try {
    if (process.platform !== 'win32') return
    if (!getUsageSettings().enabled) return
    if (existsSync(markerFile())) return

    const apps = aggregateUserAssist(readUserAssistRaw())
    const now = Date.now()
    let seeded = 0
    for (const a of apps) {
      if (a.focusSeconds < MIN_FOCUS_SECONDS) continue
      seedAppUsage(a.name, a.focusSeconds, now)
      seeded++
    }
    // Only mark done once we've actually read the registry and seeded (or found
    // nothing to seed) — a load failure above throws past this and retries later.
    writeFileSync(markerFile(), JSON.stringify({ at: now, seeded }), 'utf-8')
    console.log(`[usage] UserAssist seed complete: ${seeded} app(s)`)
  } catch (e) {
    console.warn('[usage] UserAssist seed failed:', e)
  }
}
