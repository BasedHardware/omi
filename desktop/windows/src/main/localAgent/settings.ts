import { app } from 'electron'
import { readFileSync, writeFileSync } from 'fs'
import { join } from 'path'

export type LocalAgentSettings = {
  enabled: boolean
  port: number
}

export const LOCAL_AGENT_DEFAULT_PORT = 47778

const DEFAULTS: LocalAgentSettings = {
  enabled: false,
  port: LOCAL_AGENT_DEFAULT_PORT
}

function file(): string {
  return join(app.getPath('userData'), 'local-agent-settings.json')
}

function sanitize(raw: Partial<LocalAgentSettings>): LocalAgentSettings {
  const port =
    typeof raw.port === 'number' &&
    Number.isInteger(raw.port) &&
    raw.port >= 1024 &&
    raw.port <= 65535
      ? raw.port
      : DEFAULTS.port

  return {
    enabled: raw.enabled === true,
    port
  }
}

export function getLocalAgentSettings(): LocalAgentSettings {
  try {
    return sanitize(JSON.parse(readFileSync(file(), 'utf-8')) as Partial<LocalAgentSettings>)
  } catch {
    return { ...DEFAULTS }
  }
}

export function setLocalAgentSettings(next: LocalAgentSettings): LocalAgentSettings {
  const value = sanitize(next)
  try {
    writeFileSync(file(), JSON.stringify(value), 'utf-8')
  } catch (e) {
    console.warn('[local-agent] failed to persist settings:', e)
  }
  return value
}
