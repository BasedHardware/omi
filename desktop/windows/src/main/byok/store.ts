import { app, safeStorage } from 'electron'
import { existsSync, mkdirSync, readFileSync, renameSync, rmSync, writeFileSync } from 'fs'
import { dirname, join } from 'path'
import type {
  ByokChatProvider,
  ByokProvider,
  ByokProviderStatus,
  ByokStatus,
  ByokValidationResult
} from '../../shared/types'

export const BYOK_PROVIDERS = [
  'openai',
  'anthropic',
  'gemini',
  'deepgram',
  'openrouter',
  'elevenlabs'
] as const
export const BYOK_CHAT_PROVIDERS = ['openai', 'anthropic', 'gemini', 'openrouter'] as const

type StoredByokProvider = {
  key: string
  updatedAt: number
  lastValidatedAt?: number
  lastValidationOk?: boolean
  lastValidationError?: string
}

type StoredByokFile = {
  version: 1
  activeChatProvider?: ByokChatProvider | null
  providers?: Partial<Record<ByokProvider, StoredByokProvider>>
}

type LoadedByokSettings = {
  activeChatProvider: ByokChatProvider | null
  providers: Partial<Record<ByokProvider, StoredByokProvider & { rawKey: string }>>
}

function file(): string {
  return join(app.getPath('userData'), 'byok-keys.json')
}

export function isByokProvider(value: unknown): value is ByokProvider {
  return typeof value === 'string' && BYOK_PROVIDERS.includes(value as ByokProvider)
}

export function isByokChatProvider(value: unknown): value is ByokChatProvider {
  return typeof value === 'string' && BYOK_CHAT_PROVIDERS.includes(value as ByokChatProvider)
}

export function maskByokKey(key: string): string {
  const trimmed = key.trim()
  if (trimmed.length <= 8) return '****'
  return `${trimmed.slice(0, 4)}...${trimmed.slice(-4)}`
}

function emptySettings(): LoadedByokSettings {
  return { activeChatProvider: null, providers: {} }
}

function encryptionRequired(): void {
  if (!safeStorage.isEncryptionAvailable()) {
    throw new Error('Secure storage is unavailable on this system')
  }
}

function readStoredFile(): StoredByokFile | null {
  const f = file()
  if (!existsSync(f)) return null
  try {
    const raw = JSON.parse(readFileSync(f, 'utf8')) as StoredByokFile
    if (raw.version !== 1 || !raw.providers || typeof raw.providers !== 'object') return null
    return raw
  } catch {
    return null
  }
}

function decryptProvider(provider: StoredByokProvider): string | null {
  try {
    return safeStorage.decryptString(Buffer.from(provider.key, 'base64'))
  } catch {
    return null
  }
}

function loadSettings(): LoadedByokSettings {
  const stored = readStoredFile()
  if (!stored) return emptySettings()

  const providers: LoadedByokSettings['providers'] = {}
  for (const provider of BYOK_PROVIDERS) {
    const entry = stored.providers?.[provider]
    if (!entry?.key || typeof entry.updatedAt !== 'number') continue
    const rawKey = decryptProvider(entry)
    if (!rawKey) continue
    providers[provider] = { ...entry, rawKey }
  }

  const activeChatProvider =
    stored.activeChatProvider &&
    isByokChatProvider(stored.activeChatProvider) &&
    providers[stored.activeChatProvider]
      ? stored.activeChatProvider
      : null

  return { activeChatProvider, providers }
}

function serialize(settings: LoadedByokSettings): StoredByokFile {
  const providers: StoredByokFile['providers'] = {}
  for (const provider of BYOK_PROVIDERS) {
    const entry = settings.providers[provider]
    if (!entry?.rawKey) continue
    providers[provider] = {
      key: safeStorage.encryptString(entry.rawKey).toString('base64'),
      updatedAt: entry.updatedAt,
      lastValidatedAt: entry.lastValidatedAt,
      lastValidationOk: entry.lastValidationOk,
      lastValidationError: entry.lastValidationError
    }
  }
  return {
    version: 1,
    activeChatProvider: settings.activeChatProvider,
    providers
  }
}

function writeSettings(settings: LoadedByokSettings): void {
  encryptionRequired()
  const target = file()
  const tmp = `${target}.${process.pid}.${Date.now()}.tmp`
  mkdirSync(dirname(target), { recursive: true })
  try {
    writeFileSync(tmp, JSON.stringify(serialize(settings)), 'utf8')
    renameSync(tmp, target)
  } catch (error) {
    try {
      rmSync(tmp, { force: true })
    } catch {
      /* best-effort */
    }
    throw error
  }
}

function providerStatus(
  provider: ByokProvider,
  entry: LoadedByokSettings['providers'][ByokProvider]
): ByokProviderStatus {
  if (!entry?.rawKey) {
    return { provider, configured: false }
  }
  return {
    provider,
    configured: true,
    maskedKey: maskByokKey(entry.rawKey),
    updatedAt: entry.updatedAt,
    lastValidatedAt: entry.lastValidatedAt,
    lastValidationOk: entry.lastValidationOk,
    lastValidationError: entry.lastValidationError
  }
}

export function getByokStatus(): ByokStatus {
  const settings = loadSettings()
  const providers = Object.fromEntries(
    BYOK_PROVIDERS.map((provider) => [
      provider,
      providerStatus(provider, settings.providers[provider])
    ])
  ) as Record<ByokProvider, ByokProviderStatus>

  return {
    activeChatProvider: settings.activeChatProvider,
    providers
  }
}

export function saveByokKey(provider: ByokProvider, key: string): ByokStatus {
  const trimmed = key.trim()
  if (!trimmed) throw new Error('BYOK key is required')
  const settings = loadSettings()
  settings.providers[provider] = {
    rawKey: trimmed,
    key: '',
    updatedAt: Date.now()
  }
  writeSettings(settings)
  return getByokStatus()
}

export function deleteByokKey(provider: ByokProvider): ByokStatus {
  const settings = loadSettings()
  delete settings.providers[provider]
  if (settings.activeChatProvider === provider) {
    settings.activeChatProvider = null
  }
  writeSettings(settings)
  return getByokStatus()
}

export function clearByokSettings(): void {
  try {
    rmSync(file(), { force: true })
  } catch {
    /* best-effort */
  }
}

export function setActiveByokChatProvider(provider: ByokChatProvider | null): ByokStatus {
  const settings = loadSettings()
  if (provider && !settings.providers[provider]?.rawKey) {
    throw new Error('Save this provider key before using it for chat')
  }
  settings.activeChatProvider = provider
  writeSettings(settings)
  return getByokStatus()
}

export function loadByokKey(provider: ByokProvider): string | null {
  return loadSettings().providers[provider]?.rawKey ?? null
}

export function loadActiveByokChatKey(): { provider: ByokChatProvider; key: string } | null {
  const settings = loadSettings()
  const provider = settings.activeChatProvider
  if (!provider) return null
  const key = settings.providers[provider]?.rawKey
  return key ? { provider, key } : null
}

export function recordByokValidation(
  provider: ByokProvider,
  result: ByokValidationResult
): ByokStatus {
  const settings = loadSettings()
  const entry = settings.providers[provider]
  if (!entry) return getByokStatus()
  entry.lastValidatedAt = Date.now()
  entry.lastValidationOk = result.ok
  entry.lastValidationError = result.ok ? undefined : result.error
  writeSettings(settings)
  return getByokStatus()
}
