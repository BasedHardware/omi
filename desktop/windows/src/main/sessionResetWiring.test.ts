// Verifies the actual wiring main/index.ts sets up: AI Clone teardown
// (clearAiCloneUserData) is registered against session.ts's onSessionReset —
// the hook that fires on every ordinary sign-out — not only against the
// heavier, explicit main/ipc/db.ts wipeUserData path, which does not fire
// automatically on a plain sign-out.
//
// index.ts itself is app-bootstrap code (window creation, tray icons, etc.)
// and isn't practical to unit test directly. This test instead reproduces
// the exact registration index.ts performs — onSessionReset(() =>
// clearAiCloneUserData()) — and drives it through session.ts's real
// setBackendSession(), the same function the renderer actually calls on
// sign-out. That's as close to an end-to-end proof as a unit test gets
// without booting Electron.

import { afterAll, afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mkdtempSync, rmSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'

const dir = mkdtempSync(join(tmpdir(), 'session-reset-wiring-test-'))

vi.mock('electron', () => ({
  app: { getPath: (): string => dir },
  safeStorage: {
    isEncryptionAvailable: (): boolean => true,
    encryptString: (s: string): Buffer => Buffer.from(s, 'utf8'),
    decryptString: (b: Buffer): string => b.toString('utf8')
  },
  ipcMain: { handle: (): void => {} },
  BrowserWindow: { getAllWindows: (): unknown[] => [] }
}))

vi.mock('./aiClone/beeperClient', () => ({
  createBeeperClient: vi.fn()
}))

// AI-profile grounding isn't relevant to this test and drags in more of the
// backend-session-consuming surface than needed.
vi.mock('./assistants/aiUserProfile/service', () => ({
  getLatestProfileText: (): string | null => null
}))

import { onSessionReset, setBackendSession } from './assistants/core/session'
import { clearAiCloneUserData } from './ipc/aiClone'
import { BeeperTokenStore } from './aiClone/beeperTokenStore'
import { ChatSettingsStore } from './aiClone/chatSettingsStore'
import { DraftStore } from './aiClone/draftStore'

afterAll(() => rmSync(dir, { recursive: true, force: true }))

const testSession = (
  token: string
): { apiBase: string; desktopApiBase: string; token: string } => ({
  apiBase: 'https://api.example',
  desktopApiBase: 'https://desktop.example',
  token
})

beforeEach(() => {
  vi.spyOn(console, 'warn').mockImplementation(() => {})
  // Reproduce index.ts's actual registration — this is the line under test.
  onSessionReset(() => clearAiCloneUserData())
})

afterEach(() => {
  // Leave the shared session.ts module state clean for the next test in
  // this file (module-level, not reset automatically between tests).
  setBackendSession(null)
})

describe('AI Clone sign-out wiring', () => {
  it('clears AI Clone state when the real sign-out event (setBackendSession(null)) fires', () => {
    new BeeperTokenStore().set('beeper-token-for-user-a')
    new ChatSettingsStore().upsert({ chatID: 'chat-1', displayName: 'Jordan', mode: 'auto_send' })
    new DraftStore().add({
      chatID: 'chat-1',
      chatDisplayName: 'Jordan',
      incomingMessageText: 'hi',
      draftText: 'hey!',
      sessionGeneration: 0
    })
    expect(new BeeperTokenStore().has()).toBe(true)

    // The actual event: renderer relays sign-in, then sign-out. Sign-out is
    // exactly setBackendSession(null) — nothing AI-Clone-specific about it.
    setBackendSession(testSession('h.e30.s'))
    setBackendSession(null)

    expect(new BeeperTokenStore().has()).toBe(false)
    expect(new ChatSettingsStore().list()).toEqual([])
    expect(new DraftStore().list()).toEqual([])
  })

  it('does NOT clear AI Clone state on a session change that is not a sign-out', () => {
    new BeeperTokenStore().set('beeper-token-for-user-a')

    setBackendSession(testSession('h.e30.s'))
    // A second non-null session relay (e.g. a token refresh) — session.ts's
    // own contract is that only a transition TO null fires reset listeners
    // (see session.test.ts's onSessionReset suite). AI Clone shouldn't be
    // wiped just because a session value was relayed again.
    setBackendSession(testSession('h.e30.s2'))

    expect(new BeeperTokenStore().has()).toBe(true)
  })
})
