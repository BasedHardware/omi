// Persist the hosted MCP key encrypted at rest via Electron safeStorage
// (DPAPI on Windows). The raw key is only returned to explicit IPC callers.
import { app, safeStorage } from 'electron'
import { existsSync, readFileSync, writeFileSync, rmSync } from 'fs'
import { join } from 'path'
import type { McpKeyRecord } from '../../shared/types'

type StoredMcpKeyFile = {
  id: string
  name: string
  key: string
}

function file(): string {
  return join(app.getPath('userData'), 'mcp-key.json')
}

function isMcpKeyRecord(value: unknown): value is McpKeyRecord {
  if (!value || typeof value !== 'object') return false
  const candidate = value as Partial<McpKeyRecord>
  return (
    typeof candidate.id === 'string' &&
    candidate.id.length > 0 &&
    typeof candidate.name === 'string' &&
    candidate.name.length > 0 &&
    typeof candidate.key === 'string' &&
    candidate.key.length > 0
  )
}

export function saveMcpKey(record: McpKeyRecord): void {
  if (!isMcpKeyRecord(record)) {
    throw new Error('Invalid MCP key record')
  }
  if (!safeStorage.isEncryptionAvailable()) {
    throw new Error('Secure storage is unavailable on this system')
  }
  const enc = safeStorage.encryptString(record.key).toString('base64')
  writeFileSync(
    file(),
    JSON.stringify({ id: record.id, name: record.name, key: enc } satisfies StoredMcpKeyFile),
    'utf8'
  )
}

export function loadMcpKey(): McpKeyRecord | null {
  const f = file()
  if (!existsSync(f)) return null
  try {
    const raw = JSON.parse(readFileSync(f, 'utf8')) as StoredMcpKeyFile
    if (!raw.id || !raw.name || !raw.key) return null
    const key = safeStorage.decryptString(Buffer.from(raw.key, 'base64'))
    return { id: raw.id, name: raw.name, key }
  } catch {
    return null
  }
}

export function clearMcpKey(): void {
  try {
    rmSync(file(), { force: true })
  } catch {
    /* best-effort */
  }
}
