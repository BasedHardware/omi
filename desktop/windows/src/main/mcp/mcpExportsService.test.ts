import { describe, it, expect, vi } from 'vitest'
import { McpExportsService, type McpKeyStoreLike } from './mcpExportsService'
import type { McpKeyRecord } from './mcpKeyStore'

const API = 'https://api.omi.me'
const TOKEN = 'tok'

// An in-memory stand-in for McpKeyStore that enforces the same owner-uid guard.
function fakeStore(): McpKeyStoreLike & { _rec: { uid: string; rec: McpKeyRecord } | null } {
  return {
    _rec: null as { uid: string; rec: McpKeyRecord } | null,
    read(uid) {
      // Structural guard: serve only when the owner matches; a mismatch returns
      // null WITHOUT destroying the record (matches the real store).
      return this._rec && this._rec.uid === uid ? this._rec.rec : null
    },
    write(uid, rec) {
      this._rec = { uid, rec }
    },
    storedId() {
      return this._rec?.rec.id ?? null
    },
    clearAll() {
      this._rec = null
    }
  }
}

function mintResponse(id: string, key: string): Response {
  return {
    ok: true,
    status: 200,
    json: async () => ({ id, name: 'Omi Desktop', key }),
    text: async () => ''
  } as unknown as Response
}

describe('McpExportsService.ensureKey', () => {
  it('mints once, then reuses the stored key (lazy, no re-mint)', async () => {
    const store = fakeStore()
    const fetchImpl = vi.fn(async () => mintResponse('k1', 'secret1'))
    const svc = new McpExportsService(store, fetchImpl as unknown as typeof fetch)

    const first = await svc.ensureKey('uid-A', TOKEN, API)
    expect(first).toEqual({ id: 'k1', name: 'Omi Desktop', key: 'secret1' })
    const second = await svc.ensureKey('uid-A', TOKEN, API)
    expect(second).toEqual(first)
    expect(fetchImpl).toHaveBeenCalledTimes(1) // reused, not re-minted
  })

  it('mints a distinct key for a different account (owner-uid guard)', async () => {
    const store = fakeStore()
    const fetchImpl = vi
      .fn()
      .mockResolvedValueOnce(mintResponse('kA', 'secretA'))
      .mockResolvedValueOnce(mintResponse('kB', 'secretB'))
    const svc = new McpExportsService(store, fetchImpl as unknown as typeof fetch)

    await svc.ensureKey('uid-A', TOKEN, API)
    const b = await svc.ensureKey('uid-B', TOKEN, API)
    expect(b.key).toBe('secretB')
    expect(fetchImpl).toHaveBeenCalledTimes(2)
    // uid-A's key was cleared by the guard when uid-B read; hasKey reflects that.
    expect(svc.hasKey('uid-B')).toBe(true)
  })
})

describe('McpExportsService.rotateKey', () => {
  it('mints a new key and revokes the old one', async () => {
    const store = fakeStore()
    store.write('uid-A', { id: 'old', name: 'Omi Desktop', key: 'oldsecret' })
    const calls: Array<{ method: string; url: string }> = []
    const fetchImpl = vi.fn(async (url: string, init: { method: string }) => {
      calls.push({ method: init.method, url })
      if (init.method === 'POST') return mintResponse('new', 'newsecret')
      return {
        ok: true,
        status: 204,
        json: async () => ({}),
        text: async () => ''
      } as unknown as Response
    })
    const svc = new McpExportsService(store, fetchImpl as unknown as typeof fetch)

    const rotated = await svc.rotateKey('uid-A', TOKEN, API)
    expect(rotated.key).toBe('newsecret')
    expect(store.read('uid-A')?.id).toBe('new')
    // The old key id was revoked via DELETE.
    expect(calls).toContainEqual({ method: 'DELETE', url: 'https://api.omi.me/v1/mcp/keys/old' })
  })

  it('keeps the existing key when the mint fails (mint-first safety)', async () => {
    const store = fakeStore()
    store.write('uid-A', { id: 'old', name: 'Omi Desktop', key: 'oldsecret' })
    const fetchImpl = vi.fn(
      async () =>
        ({
          ok: false,
          status: 500,
          json: async () => ({}),
          text: async () => 'boom'
        }) as unknown as Response
    )
    const svc = new McpExportsService(store, fetchImpl as unknown as typeof fetch)

    await expect(svc.rotateKey('uid-A', TOKEN, API)).rejects.toThrow('500')
    expect(store.read('uid-A')?.key).toBe('oldsecret') // untouched
  })
})
