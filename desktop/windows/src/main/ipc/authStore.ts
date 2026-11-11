// Persist the Firebase auth session (ID + refresh tokens) encrypted at rest via
// Electron safeStorage (DPAPI on Windows). Mirrors `agentKernel/byokStore.ts` and
// `integrations/tokenStore.ts`: one JSON file under userData, per-key base64
// ciphertext, synchronous file I/O. Token material is NEVER logged.
//
// This is the main-process half of a custom Firebase Persistence. The renderer's
// `lib/encryptedAuthPersistence.ts` calls these IPC channels; Firebase's own
// PersistenceUserManager drives the read/write/migrate lifecycle. The stored
// value is whatever Firebase hands the persistence (a JSON string), so this store
// is key-agnostic — it never parses or inspects the plaintext.
//
// Storage shape: { "<firebase key>": "<base64 safeStorage ciphertext>", ... }

import { app, ipcMain, webContents, safeStorage } from 'electron'
import { existsSync, readFileSync, writeFileSync, rmSync } from 'fs'
import { join } from 'path'

/** On-disk shape: firebase key → base64-encoded safeStorage ciphertext. */
type StoredFile = Record<string, string>

/**
 * Encrypted-at-rest store for Firebase auth persistence entries. Reads/writes are
 * synchronous, matching the BYOK/Google token stores. Construct with no args for
 * the real userData path, or pass an explicit path in tests.
 */
export class AuthTokenStore {
  private readonly filePath: string

  constructor(filePath?: string) {
    this.filePath = filePath ?? join(app.getPath('userData'), 'firebase-auth.json')
  }

  /** True when OS-backed encryption (DPAPI) is available on this machine. */
  isAvailable(): boolean {
    return safeStorage.isEncryptionAvailable()
  }

  private readFile(): StoredFile {
    if (!existsSync(this.filePath)) return {}
    try {
      const raw = JSON.parse(readFileSync(this.filePath, 'utf8')) as StoredFile
      return raw && typeof raw === 'object' ? raw : {}
    } catch {
      return {}
    }
  }

  private writeFile(data: StoredFile): void {
    writeFileSync(this.filePath, JSON.stringify(data), 'utf8')
  }

  /** Decrypt and return one entry's value, or null if unset/undecryptable. */
  get(key: string): string | null {
    const enc = this.readFile()[key]
    if (!enc) return null
    try {
      if (!this.isAvailable()) return null
      return safeStorage.decryptString(Buffer.from(enc, 'base64'))
    } catch {
      return null
    }
  }

  /** Encrypt and persist one entry's value. */
  set(key: string, value: string): void {
    if (!this.isAvailable()) {
      throw new Error('Secure storage is unavailable on this system')
    }
    const data = this.readFile()
    data[key] = safeStorage.encryptString(value).toString('base64')
    this.writeFile(data)
  }

  /** Remove one entry. Deletes the backing file once it holds no entries. */
  remove(key: string): void {
    const data = this.readFile()
    if (!(key in data)) return
    delete data[key]
    if (Object.keys(data).length === 0) {
      try {
        rmSync(this.filePath, { force: true })
      } catch {
        /* best-effort */
      }
      return
    }
    this.writeFile(data)
  }
}

let store: AuthTokenStore | null = null

// Lazily construct on first use so the module stays import-pure (no app.getPath
// at import time — userData isn't ready until the app is).
function getStore(): AuthTokenStore {
  if (!store) store = new AuthTokenStore()
  return store
}

// Notify every window that a persistence entry changed, so a second window's
// Firebase instance can re-read (mirrors browserLocalPersistence's storage-event
// cross-tab sync). The key travels; the value never does.
function broadcastChanged(key: string): void {
  for (const wc of webContents.getAllWebContents()) {
    if (!wc.isDestroyed()) wc.send('authStore:changed', { key })
  }
}

/** Registers the `authStore:*` IPC handlers backing the AuthTokenStore. */
export function registerAuthStoreHandlers(): void {
  ipcMain.handle('authStore:isAvailable', (): boolean => getStore().isAvailable())
  ipcMain.handle('authStore:get', (_e, key: string): string | null => getStore().get(key))
  ipcMain.handle('authStore:set', (_e, key: string, value: string): void => {
    getStore().set(key, value)
    broadcastChanged(key)
  })
  ipcMain.handle('authStore:remove', (_e, key: string): void => {
    getStore().remove(key)
    broadcastChanged(key)
  })
}
