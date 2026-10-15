// src/main/insight/state.ts
import { app } from 'electron'
import { join } from 'path'
import { existsSync, readFileSync, writeFileSync } from 'fs'
import type { InsightSettings } from '../../shared/types'

const DEFAULTS: InsightSettings = {
  notificationStyle: 'omi'
}

function statePath(): string {
  return join(app.getPath('userData'), 'insights.json')
}

let cache: InsightSettings | null = null

export function getInsightSettings(): InsightSettings {
  if (cache) return cache
  try {
    if (existsSync(statePath())) {
      const raw = JSON.parse(readFileSync(statePath(), 'utf8')) as Partial<InsightSettings>
      cache = {
        notificationStyle: raw.notificationStyle === 'native' ? 'native' : 'omi'
      }
      return cache
    }
  } catch {
    /* corrupt → defaults */
  }
  cache = { ...DEFAULTS }
  return cache
}

export function updateInsightSettings(patch: Partial<InsightSettings>): InsightSettings {
  const next = { ...getInsightSettings(), ...patch }
  cache = next
  try {
    writeFileSync(statePath(), JSON.stringify(next, null, 2))
  } catch {
    /* best-effort */
  }
  return next
}
