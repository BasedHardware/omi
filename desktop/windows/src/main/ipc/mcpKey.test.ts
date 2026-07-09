import { mkdtempSync, readFileSync, rmSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

type IpcHandler = (event: unknown, ...args: unknown[]) => Promise<unknown>

const electronState = vi.hoisted(() => ({
  userData: '',
  handlers: new Map<string, IpcHandler>(),
  clipboardText: '',
  clipboardWrites: [] as string[],
  clipboardClears: 0,
  // Index of the dialog button to "press": 0 = Copy, 1 = Cancel.
  dialogResponse: 1,
  dialogCalls: [] as Array<Record<string, unknown>>
}))

vi.mock('electron', () => ({
  app: {
    getPath: (name: string): string => {
      if (name !== 'userData') throw new Error(`unexpected app path: ${name}`)
      return electronState.userData
    }
  },
  safeStorage: {
    isEncryptionAvailable: (): boolean => true,
    encryptString: (value: string): Buffer => Buffer.from(`encrypted:${value}`, 'utf8'),
    decryptString: (value: Buffer): string => value.toString('utf8').replace(/^encrypted:/, '')
  },
  ipcMain: {
    handle: (channel: string, handler: IpcHandler): void => {
      electronState.handlers.set(channel, handler)
    }
  },
  clipboard: {
    writeText: (text: string): void => {
      electronState.clipboardText = text
      electronState.clipboardWrites.push(text)
    },
    readText: (): string => electronState.clipboardText,
    clear: (): void => {
      electronState.clipboardText = ''
      electronState.clipboardClears += 1
    }
  },
  dialog: {
    showMessageBox: async (options: Record<string, unknown>): Promise<{ response: number }> => {
      electronState.dialogCalls.push(options)
      return { response: electronState.dialogResponse }
    }
  },
  BrowserWindow: {
    fromWebContents: (): null => null
  }
}))

import { registerMcpKeyHandlers } from './mcpKey'
import type { McpKeyMetadata } from '../../shared/types'

registerMcpKeyHandlers()

const trustedEvent = { sender: {}, senderFrame: { url: 'file:///C:/app/index.html' } }
const untrustedEvent = { sender: {}, senderFrame: { url: 'https://evil.example/index.html' } }

const RAW_KEY = 'omi_live_super_secret_key_1234'
const API_RECORD = { id: 'key_123', name: 'Omi Windows', key: RAW_KEY }
const MASKED = 'omi_li********1234'

function invoke(channel: string, event: unknown, ...args: unknown[]): Promise<unknown> {
  const handler = electronState.handlers.get(channel)
  if (!handler) throw new Error(`no handler registered for ${channel}`)
  return handler(event, ...args)
}

function stubFetchWithKeyRecord(): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({ ...API_RECORD })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

async function createStoredKey(): Promise<McpKeyMetadata> {
  stubFetchWithKeyRecord()
  const metadata = (await invoke(
    'mcpKey:createAndStore',
    trustedEvent,
    'firebase-token'
  )) as McpKeyMetadata
  vi.unstubAllGlobals()
  return metadata
}

describe('mcpKey IPC handlers', () => {
  beforeEach(() => {
    electronState.userData = mkdtempSync(join(tmpdir(), 'omi-mcp-ipc-'))
    electronState.clipboardText = ''
    electronState.clipboardWrites = []
    electronState.clipboardClears = 0
    electronState.dialogResponse = 1
    electronState.dialogCalls = []
  })

  afterEach(() => {
    rmSync(electronState.userData, { recursive: true, force: true })
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  describe('sender validation', () => {
    it.each([
      ['mcpKey:createAndStore', ['firebase-token']],
      ['mcpKey:read', []],
      ['mcpKey:copy', [{ kind: 'key' }]],
      ['mcpKey:test', []],
      ['mcpKey:delete', []]
    ])('rejects untrusted senders on %s', async (channel, args) => {
      await expect(invoke(channel, untrustedEvent, ...args)).rejects.toThrow(
        'MCP key IPC is not available from this renderer'
      )
    })
  })

  describe('mcpKey:createAndStore', () => {
    it('creates the key in main and returns metadata only — never the raw key', async () => {
      const fetchMock = stubFetchWithKeyRecord()

      const result = await invoke('mcpKey:createAndStore', trustedEvent, 'firebase-token')

      expect(result).toEqual({ id: 'key_123', name: 'Omi Windows', maskedKey: MASKED })
      expect(JSON.stringify(result)).not.toContain(RAW_KEY)
      expect(fetchMock).toHaveBeenCalledWith(
        'https://api.omi.me/v1/mcp/keys',
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({ Authorization: 'Bearer firebase-token' }),
          body: JSON.stringify({ name: 'Omi Windows' })
        })
      )
      // Persisted encrypted at rest — the raw key must not appear on disk.
      const storedFile = readFileSync(join(electronState.userData, 'mcp-key.json'), 'utf8')
      expect(storedFile).not.toContain(RAW_KEY)
    })

    it('rejects a missing or empty auth token before any network call', async () => {
      const fetchMock = stubFetchWithKeyRecord()

      await expect(invoke('mcpKey:createAndStore', trustedEvent, '')).rejects.toThrow(
        'Invalid auth token for MCP key creation'
      )
      await expect(invoke('mcpKey:createAndStore', trustedEvent, undefined)).rejects.toThrow(
        'Invalid auth token for MCP key creation'
      )
      expect(fetchMock).not.toHaveBeenCalled()
    })

    it('surfaces HTTP failures without storing anything', async () => {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 401 }))

      await expect(invoke('mcpKey:createAndStore', trustedEvent, 'firebase-token')).rejects.toThrow(
        'MCP key creation returned HTTP 401.'
      )
      expect(await invoke('mcpKey:read', trustedEvent)).toBeNull()
    })

    it('rejects malformed key records from the API', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue({
          ok: true,
          status: 200,
          json: async () => ({ id: 'key_123', name: 'Omi Windows' })
        })
      )

      await expect(invoke('mcpKey:createAndStore', trustedEvent, 'firebase-token')).rejects.toThrow(
        'MCP key creation returned an invalid key record.'
      )
    })
  })

  describe('mcpKey:read', () => {
    it('returns metadata with a masked key and no raw key material', async () => {
      await createStoredKey()

      const result = await invoke('mcpKey:read', trustedEvent)

      expect(result).toEqual({ id: 'key_123', name: 'Omi Windows', maskedKey: MASKED })
      expect(result).not.toHaveProperty('key')
      expect(JSON.stringify(result)).not.toContain(RAW_KEY)
    })

    it('returns null when no key is stored', async () => {
      expect(await invoke('mcpKey:read', trustedEvent)).toBeNull()
    })
  })

  describe('mcpKey:copy confirmation', () => {
    it('does not touch the clipboard when the user cancels', async () => {
      await createStoredKey()
      electronState.dialogResponse = 1

      const result = await invoke('mcpKey:copy', trustedEvent, { kind: 'key' })

      expect(result).toEqual({ copied: false, canceled: true })
      expect(electronState.dialogCalls).toHaveLength(1)
      expect(electronState.clipboardWrites).toHaveLength(0)
    })

    it('copies the raw key only after the user confirms', async () => {
      await createStoredKey()
      electronState.dialogResponse = 0

      const result = await invoke('mcpKey:copy', trustedEvent, { kind: 'key' })

      expect(result).toEqual({ copied: true })
      expect(electronState.clipboardWrites).toEqual([RAW_KEY])
    })

    it('substitutes the placeholder in confirmed setup-text copies', async () => {
      await createStoredKey()
      electronState.dialogResponse = 0

      const result = await invoke('mcpKey:copy', trustedEvent, {
        kind: 'text',
        text: 'Authorization: Bearer YOUR_OMI_MCP_KEY'
      })

      expect(result).toEqual({ copied: true })
      expect(electronState.clipboardWrites).toEqual([`Authorization: Bearer ${RAW_KEY}`])
    })

    it('rejects malformed copy requests', async () => {
      await createStoredKey()

      await expect(invoke('mcpKey:copy', trustedEvent, { kind: 'text' })).rejects.toThrow(
        'Invalid MCP key copy request'
      )
      expect(electronState.dialogCalls).toHaveLength(0)
    })
  })

  describe('clipboard auto-clear', () => {
    it('clears the clipboard after the timeout when it still holds the copied secret', async () => {
      await createStoredKey()
      electronState.dialogResponse = 0
      vi.useFakeTimers()

      await invoke('mcpKey:copy', trustedEvent, { kind: 'key' })
      expect(electronState.clipboardText).toBe(RAW_KEY)

      vi.advanceTimersByTime(60_000)

      expect(electronState.clipboardClears).toBe(1)
      expect(electronState.clipboardText).toBe('')
    })

    it('leaves the clipboard alone when the user has since copied something else', async () => {
      await createStoredKey()
      electronState.dialogResponse = 0
      vi.useFakeTimers()

      await invoke('mcpKey:copy', trustedEvent, { kind: 'key' })
      electronState.clipboardText = 'unrelated user content'

      vi.advanceTimersByTime(60_000)

      expect(electronState.clipboardClears).toBe(0)
      expect(electronState.clipboardText).toBe('unrelated user content')
    })
  })
})
