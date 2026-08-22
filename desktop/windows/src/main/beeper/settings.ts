// Non-secret Beeper chat-reply preferences. Token stays in tokenStore.
import { app } from 'electron'
import { existsSync, readFileSync, writeFileSync } from 'fs'
import { join } from 'path'
import {
  DEFAULT_BEEPER_NETWORKS,
  DEFAULT_SEND_MODE,
  type BeeperNetwork,
  type BeeperSendMode
} from './replyLogic'

export type BeeperSettings = {
  enabled: boolean
  sendMode: BeeperSendMode
  networks: BeeperNetwork[]
}

const DEFAULTS: BeeperSettings = {
  enabled: false,
  sendMode: DEFAULT_SEND_MODE,
  networks: [...DEFAULT_BEEPER_NETWORKS]
}

function file(): string {
  return join(app.getPath('userData'), 'beeper-settings.json')
}

function isNetwork(v: unknown): v is BeeperNetwork {
  return v === 'whatsapp' || v === 'telegram' || v === 'imessage'
}

export function loadBeeperSettings(): BeeperSettings {
  const f = file()
  if (!existsSync(f)) return { ...DEFAULTS, networks: [...DEFAULTS.networks] }
  try {
    const raw = JSON.parse(readFileSync(f, 'utf8')) as Partial<BeeperSettings>
    const networks = Array.isArray(raw.networks)
      ? raw.networks.filter(isNetwork)
      : DEFAULTS.networks
    return {
      enabled: raw.enabled === true,
      sendMode: raw.sendMode === 'auto' ? 'auto' : 'draft',
      networks: networks.length > 0 ? networks : [...DEFAULTS.networks]
    }
  } catch {
    return { ...DEFAULTS, networks: [...DEFAULTS.networks] }
  }
}

export function saveBeeperSettings(next: BeeperSettings): void {
  writeFileSync(file(), JSON.stringify(next), 'utf8')
}

export function patchBeeperSettings(patch: Partial<BeeperSettings>): BeeperSettings {
  const current = loadBeeperSettings()
  const next: BeeperSettings = {
    enabled: patch.enabled ?? current.enabled,
    sendMode: patch.sendMode ?? current.sendMode,
    networks: patch.networks ?? current.networks
  }
  saveBeeperSettings(next)
  return next
}
