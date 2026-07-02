import { app, safeStorage } from 'electron'
import { readFileSync, writeFileSync, renameSync, mkdirSync, rmSync } from 'fs'
import { join } from 'path'
import { settings } from './settings'

// Encrypted-at-rest store for BYOK provider API keys. These are long-lived,
// billable secrets, so unlike general settings they are kept out of the plaintext
// settings.json and encrypted with the OS keystore (DPAPI on Windows), the same
// protection auth tokens get. They are never returned to the renderer in cleartext;
// the settings IPC layer strips them on read.

export type ByokProvider = 'openai' | 'anthropic' | 'gemini' | 'deepgram'

export interface ByokKeys {
  openai: string
  anthropic: string
  gemini: string
  deepgram: string
}

const EMPTY: ByokKeys = { openai: '', anthropic: '', gemini: '', deepgram: '' }
let cache: ByokKeys | null = null

const secretsFile = (): string => join(app.getPath('userData'), 'byok.bin')

function load(): ByokKeys {
  if (cache) return cache
  let result: ByokKeys
  try {
    const raw = readFileSync(secretsFile())
    result = safeStorage.isEncryptionAvailable()
      ? { ...EMPTY, ...JSON.parse(safeStorage.decryptString(raw)) }
      : { ...EMPTY }
  } catch {
    result = { ...EMPTY }
  }
  cache = result
  return result
}

/** Decrypted keys for main-process use only (apiProxy headers, BYOK enrollment). */
export function getByokKeys(): ByokKeys {
  return { ...load() }
}

/** Set or clear provider keys. An empty string clears that provider. */
export function setByokKeys(partial: Partial<ByokKeys>): void {
  const next: ByokKeys = { ...load() }
  for (const k of Object.keys(partial) as ByokProvider[]) {
    const v = partial[k]
    if (typeof v === 'string') next[k] = v.trim()
  }
  cache = next

  try {
    mkdirSync(app.getPath('userData'), { recursive: true })
    const hasAny = Object.values(next).some((v) => v)
    if (!hasAny) {
      rmSync(secretsFile(), { force: true })
      return
    }
    if (!safeStorage.isEncryptionAvailable()) {
      // Fail closed: never write provider secrets to disk unencrypted.
      console.warn('secrets: OS encryption unavailable, BYOK keys kept in memory only this session')
      return
    }
    const tmp = secretsFile() + '.tmp'
    writeFileSync(tmp, safeStorage.encryptString(JSON.stringify(next)))
    renameSync(tmp, secretsFile())
  } catch (e) {
    console.error('secrets: persist failed', e)
  }
}

/** Which providers have a key configured (for the renderer, no values). */
export function byokStatus(): Record<ByokProvider, boolean> {
  const k = load()
  return { openai: !!k.openai, anthropic: !!k.anthropic, gemini: !!k.gemini, deepgram: !!k.deepgram }
}

/** Drop the decrypted keys from memory (e.g. on sign-out). Re-read from the
 *  encrypted file on next use. */
export function clearByokCache(): void {
  cache = null
}

/** One-time migration: older builds stored BYOK keys as plaintext in settings.json.
 *  Move any such keys into the encrypted store and purge them from settings. */
export function migrateLegacyByokKeys(): void {
  const s = settings.get()
  const legacy: Partial<ByokKeys> = {
    openai: s.byokOpenAI,
    anthropic: s.byokAnthropic,
    gemini: s.byokGemini,
    deepgram: s.byokDeepgram
  }
  if (Object.values(legacy).some((v) => typeof v === 'string' && v)) {
    // Fail closed: if we can't encrypt, leave the plaintext keys in place rather than
    // clearing settings.json and losing them (setByokKeys would not have persisted).
    if (!safeStorage.isEncryptionAvailable()) return
    setByokKeys(legacy)
    settings.set({ byokOpenAI: '', byokAnthropic: '', byokGemini: '', byokDeepgram: '' })
  }
}
