import { app, safeStorage } from 'electron'
import { randomBytes } from 'crypto'
import { existsSync, readFileSync, rmSync, writeFileSync } from 'fs'
import { join } from 'path'

type StoredLocalAgentTokenFile = {
  token: string
}

function file(): string {
  return join(app.getPath('userData'), 'local-agent-token.json')
}

function createToken(): string {
  return randomBytes(32).toString('base64url')
}

export function saveLocalAgentToken(token: string): void {
  if (!token) throw new Error('Invalid local agent token')
  if (!safeStorage.isEncryptionAvailable()) {
    throw new Error('Secure storage is unavailable on this system')
  }
  const enc = safeStorage.encryptString(token).toString('base64')
  writeFileSync(file(), JSON.stringify({ token: enc } satisfies StoredLocalAgentTokenFile), 'utf8')
}

export function loadLocalAgentToken(): string | null {
  const f = file()
  if (!existsSync(f)) return null
  try {
    const raw = JSON.parse(readFileSync(f, 'utf8')) as StoredLocalAgentTokenFile
    if (!raw.token) return null
    return safeStorage.decryptString(Buffer.from(raw.token, 'base64'))
  } catch {
    return null
  }
}

export function ensureLocalAgentToken(): string {
  const existing = loadLocalAgentToken()
  if (existing) return existing

  const token = createToken()
  saveLocalAgentToken(token)
  return token
}

export function rotateLocalAgentToken(): string {
  const token = createToken()
  saveLocalAgentToken(token)
  return token
}

export function clearLocalAgentToken(): void {
  try {
    rmSync(file(), { force: true })
  } catch {
    /* best-effort */
  }
}
