// Persist the Beeper Desktop API token encrypted at rest via Electron safeStorage
// (DPAPI on Windows). Never log the token.
import { app, safeStorage } from 'electron'
import { existsSync, readFileSync, writeFileSync, rmSync } from 'fs'
import { join } from 'path'

type StoredFile = { token: string }

function file(): string {
  return join(app.getPath('userData'), 'beeper-token.json')
}

export function saveBeeperToken(token: string): void {
  if (!safeStorage.isEncryptionAvailable()) {
    throw new Error('Secure storage is unavailable on this system')
  }
  const enc = safeStorage.encryptString(token).toString('base64')
  writeFileSync(file(), JSON.stringify({ token: enc } satisfies StoredFile), 'utf8')
}

export function loadBeeperToken(): string | null {
  const f = file()
  if (!existsSync(f)) return null
  try {
    const raw = JSON.parse(readFileSync(f, 'utf8')) as StoredFile
    if (!raw.token) return null
    return safeStorage.decryptString(Buffer.from(raw.token, 'base64'))
  } catch (error) {
    console.warn('[beeper] failed to load token from secure storage:', error)
    return null
  }
}

export function clearBeeperToken(): void {
  try {
    rmSync(file(), { force: true })
  } catch {
    /* best-effort */
  }
}
