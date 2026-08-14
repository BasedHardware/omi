// Persist the Google refresh token encrypted at rest via Electron safeStorage
// (DPAPI on Windows). The access token is NOT persisted (kept in oauth.ts memory).
import { app, safeStorage } from 'electron'
import { existsSync, readFileSync, writeFileSync, rmSync } from 'fs'
import { join } from 'path'

type StoredFile = { refreshToken: string; email?: string }

function file(): string {
  return join(app.getPath('userData'), 'google-tokens.json')
}

export function saveRefreshToken(refreshToken: string, email?: string): void {
  if (!safeStorage.isEncryptionAvailable()) {
    throw new Error('Secure storage is unavailable on this system')
  }
  const enc = safeStorage.encryptString(refreshToken).toString('base64')
  writeFileSync(file(), JSON.stringify({ refreshToken: enc, email } satisfies StoredFile), 'utf8')
}

export function loadRefreshToken(): { refreshToken: string; email?: string } | null {
  const f = file()
  if (!existsSync(f)) return null
  try {
    const raw = JSON.parse(readFileSync(f, 'utf8')) as StoredFile
    if (!raw.refreshToken) return null
    const dec = safeStorage.decryptString(Buffer.from(raw.refreshToken, 'base64'))
    return { refreshToken: dec, email: raw.email }
  } catch {
    return null
  }
}

export function clearRefreshToken(): void {
  try {
    rmSync(file(), { force: true })
  } catch {
    /* best-effort */
  }
}
