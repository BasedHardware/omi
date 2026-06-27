import { describe, it, expect, vi } from 'vitest'
import { resolveChatId, mergeChatMessages, type StoredId } from './chatConversation'
import type { ChatMsg } from '../hooks/useChat'

const msg = (id: string, role: ChatMsg['role'], content: string): ChatMsg => ({ id, role, content })

function memStore(initial: string | null = null): StoredId {
  let v = initial
  return { get: () => v, set: (id) => { v = id } }
}

describe('resolveChatId', () => {
  it('per-launch mints a fresh id every call', () => {
    const mint = vi.fn().mockReturnValueOnce('a').mockReturnValueOnce('b')
    const store = memStore()
    expect(resolveChatId('per-launch', store, mint)).toBe('a')
    expect(resolveChatId('per-launch', store, mint)).toBe('b')
    expect(mint).toHaveBeenCalledTimes(2)
  })

  it('infinite mints + stores once, then returns the stored id', () => {
    const mint = vi.fn().mockReturnValue('inf-1')
    const store = memStore()
    expect(resolveChatId('infinite', store, mint)).toBe('inf-1')
    expect(resolveChatId('infinite', store, mint)).toBe('inf-1')
    expect(mint).toHaveBeenCalledTimes(1)
  })

  it('infinite returns an already-stored id without minting', () => {
    const mint = vi.fn().mockReturnValue('new')
    const store = memStore('existing')
    expect(resolveChatId('infinite', store, mint)).toBe('existing')
    expect(mint).not.toHaveBeenCalled()
  })
})

describe('mergeChatMessages', () => {
  it('returns incoming when stored is empty', () => {
    const incoming = [msg('1', 'user', 'hi')]
    expect(mergeChatMessages([], incoming)).toEqual(incoming)
  })

  it('appends incoming messages with new ids, preserving stored order', () => {
    const stored = [msg('1', 'user', 'a'), msg('2', 'assistant', 'b')]
    const incoming = [msg('3', 'user', 'c')]
    expect(mergeChatMessages(stored, incoming).map((m) => m.id)).toEqual(['1', '2', '3'])
  })

  it('replaces a stored message in place when an incoming id matches (streaming update)', () => {
    const stored = [msg('1', 'user', 'a'), msg('2', 'assistant', 'partial')]
    const incoming = [msg('2', 'assistant', 'partial complete')]
    const out = mergeChatMessages(stored, incoming)
    expect(out).toHaveLength(2)
    expect(out[1].content).toBe('partial complete')
  })

  it('preserves stored messages the incoming side never loaded (the other writer)', () => {
    const stored = [msg('1', 'user', 'main-msg')]
    const incoming = [msg('9', 'user', 'overlay-msg')]
    expect(mergeChatMessages(stored, incoming).map((m) => m.id)).toEqual(['1', '9'])
  })

  it('appends incoming messages that have no id (legacy/edge)', () => {
    const stored = [msg('1', 'user', 'a')]
    const incoming = [{ role: 'assistant', content: 'no-id' } as ChatMsg]
    const out = mergeChatMessages(stored, incoming)
    expect(out).toHaveLength(2)
    expect(out[1].content).toBe('no-id')
  })
})
