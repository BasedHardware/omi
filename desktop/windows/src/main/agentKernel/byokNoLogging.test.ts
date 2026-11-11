// Security regression guard: BYOK key material must NEVER be logged. This spies
// on every console method, drives the validator, the enroll orchestrator (both
// the all-ok POST path and the reject DELETE path), and the store's set /
// getAll / corrupt-file failure paths with a sentinel key, then asserts the
// sentinel never appears in any log call. A future `console.log(key)` regression
// anywhere in these paths fails CI.
import { describe, it, expect, beforeEach, afterEach, afterAll, vi } from 'vitest'
import { mkdtempSync, rmSync, writeFileSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'

const dir = mkdtempSync(join(tmpdir(), 'byok-nolog-'))

// Identity-ish safeStorage + temp userData so ByokKeyStore round-trips.
vi.mock('electron', () => ({
  app: { getPath: (): string => dir },
  safeStorage: {
    isEncryptionAvailable: (): boolean => true,
    encryptString: (s: string): Buffer => Buffer.from(s, 'utf8'),
    decryptString: (b: Buffer): string => b.toString('utf8')
  }
}))

import { validateProviderKey, type FetchLike } from './byokValidator'
import { enrollByok, type BackendFetch } from './byokEnroll'
import { ByokKeyStore } from './byokStore'

const SENTINEL = 'sk-SECRET-do-not-log-abcdef1234567890'
const FULL = {
  openai: SENTINEL,
  anthropic: `${SENTINEL}-a`,
  gemini: `${SENTINEL}-g`,
  deepgram: `${SENTINEL}-d`
}

let calls: unknown[][]
let spies: ReturnType<typeof vi.spyOn>[]

beforeEach(() => {
  calls = []
  spies = (['log', 'info', 'warn', 'error', 'debug'] as const).map((m) =>
    vi.spyOn(console, m).mockImplementation((...args: unknown[]) => {
      calls.push(args)
    })
  )
})
afterEach(() => spies.forEach((s) => s.mockRestore()))
afterAll(() => rmSync(dir, { recursive: true, force: true }))

const assertNoSentinel = (): void => {
  expect(JSON.stringify(calls)).not.toContain(SENTINEL)
}

describe('BYOK never logs key material', () => {
  it('validator does not log the key on reject or network paths', async () => {
    const reject: FetchLike = async () => ({ status: 401 })
    await validateProviderKey('openai', SENTINEL, reject)
    // Even a thrown error that itself carries the key must not be logged.
    const boom: FetchLike = async () => {
      throw new Error(`ECONNREFUSED ${SENTINEL}`)
    }
    await validateProviderKey('anthropic', SENTINEL, boom)
    assertNoSentinel()
  })

  it('enroll does not log keys on the all-reject → DELETE path', async () => {
    const reject: FetchLike = async () => ({ status: 401 })
    const backend: BackendFetch = async () => ({ ok: true, status: 200 })
    await enrollByok({
      keys: FULL,
      apiBase: 'https://api.omi.me',
      token: 'tok',
      validateFetch: reject,
      backendFetch: backend
    })
    assertNoSentinel()
  })

  it('enroll does not log keys on the all-ok → POST path', async () => {
    const ok: FetchLike = async () => ({ status: 200 })
    const backend: BackendFetch = async () => ({ ok: true, status: 200 })
    await enrollByok({
      keys: FULL,
      apiBase: 'https://api.omi.me',
      token: 'tok',
      validateFetch: ok,
      backendFetch: backend
    })
    assertNoSentinel()
  })

  it('store does not log keys on set / getAll / corrupt-file failure paths', () => {
    const path = join(dir, 'nolog.json')
    const store = new ByokKeyStore(path)
    store.setKey('openai', SENTINEL)
    store.getAllKeys()
    // Corrupt the backing file so getAllKeys() exercises its silent catch.
    writeFileSync(path, `{not valid json ${SENTINEL}`, 'utf8')
    store.getAllKeys()
    assertNoSentinel()
  })
})
