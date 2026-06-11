// src/main/screenSynth/state.ts
import { app } from 'electron'
import { join } from 'path'
import { existsSync, readFileSync, writeFileSync } from 'fs'
import type { ScreenSynthState } from '../../shared/types'

const DEFAULTS: ScreenSynthState = {
  enabled: false, // opt-in: writes screen-derived content to the cloud account
  watermarkTs: 0,
  lastRunAt: null,
  lastCount: 0,
  denylist: []
}

function statePath(): string {
  return join(app.getPath('userData'), 'screen-synth.json')
}

let cache: ScreenSynthState | null = null

export function getScreenSynthState(): ScreenSynthState {
  if (cache) return cache
  try {
    if (existsSync(statePath())) {
      const raw = JSON.parse(readFileSync(statePath(), 'utf8')) as Partial<ScreenSynthState>
      cache = { ...DEFAULTS, ...raw }
      return cache
    }
  } catch {
    /* corrupt file → fall back to defaults */
  }
  cache = { ...DEFAULTS }
  return cache
}

function persist(next: ScreenSynthState): ScreenSynthState {
  cache = next
  try {
    writeFileSync(statePath(), JSON.stringify(next, null, 2))
  } catch {
    /* best-effort; in-memory cache still holds for this session */
  }
  return next
}

export function updateScreenSynthState(patch: Partial<ScreenSynthState>): ScreenSynthState {
  return persist({ ...getScreenSynthState(), ...patch })
}

export function advanceWatermark(ts: number): void {
  const cur = getScreenSynthState()
  if (ts > cur.watermarkTs) persist({ ...cur, watermarkTs: ts })
}

export function recordRun(lastRunAt: number, lastCount: number): void {
  persist({ ...getScreenSynthState(), lastRunAt, lastCount })
}
