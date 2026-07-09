import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { mkdtempSync, rmSync, writeFileSync, readFileSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'
import { AiCloneStore, type AiCloneStoreDeps } from './store'
import type { AiCloneDraft } from '../../shared/types'

// Reversible stand-in for safeStorage so tests don't need electron.
const deps = (file: string): AiCloneStoreDeps => ({
  file,
  encrypt: (s) => `enc:${Buffer.from(s).toString('base64')}`,
  decrypt: (s) => {
    if (!s.startsWith('enc:')) throw new Error('bad ciphertext')
    return Buffer.from(s.slice(4), 'base64').toString()
  }
})

const draft = (id: string, chatId: string): AiCloneDraft => ({
  id,
  chatId,
  chatTitle: 'Alice',
  network: 'WhatsApp',
  senderName: 'Alice',
  incomingText: 'hey, where are you from?',
  replyText: 'Born in India, living in the US now!',
  createdAt: Date.now()
})

describe('AiCloneStore', () => {
  let dir: string
  let file: string

  beforeEach(() => {
    dir = mkdtempSync(join(tmpdir(), 'ai-clone-store-'))
    file = join(dir, 'ai-clone.json')
  })

  afterEach(() => rmSync(dir, { recursive: true, force: true }))

  it('roundtrips token, enabled, chat modes, drafts, activity across reloads', () => {
    const a = new AiCloneStore(deps(file))
    a.setBeeperToken('beeper-secret')
    a.setEnabled(true)
    a.setChatMode('chat1', 'auto')
    a.upsertDraft(draft('d1', 'chat1'))
    a.addActivity({ id: 'a1', at: 1, kind: 'auto_sent', chatTitle: 'Alice', text: 'hi' })

    const b = new AiCloneStore(deps(file))
    expect(b.getBeeperToken()).toBe('beeper-secret')
    expect(b.getEnabled()).toBe(true)
    expect(b.getChatMode('chat1')).toBe('auto')
    expect(b.getChatMode('unknown')).toBe('off')
    expect(b.getDrafts()).toHaveLength(1)
    expect(b.getActivity()[0].id).toBe('a1')
  })

  it('never writes the plaintext token to disk', () => {
    const s = new AiCloneStore(deps(file))
    s.setBeeperToken('beeper-secret')
    const raw = readFileSync(file, 'utf8')
    expect(raw).not.toContain('beeper-secret')
  })

  it('keeps one pending draft per chat (a newer draft replaces the older)', () => {
    const s = new AiCloneStore(deps(file))
    s.upsertDraft(draft('d1', 'chat1'))
    s.upsertDraft(draft('d2', 'chat1'))
    s.upsertDraft(draft('d3', 'chat2'))
    const drafts = s.getDrafts()
    expect(drafts.map((d) => d.id).sort()).toEqual(['d2', 'd3'])
  })

  it('removeDraft returns the draft and drops it; unknown id is a no-op null', () => {
    const s = new AiCloneStore(deps(file))
    s.upsertDraft(draft('d1', 'chat1'))
    expect(s.removeDraft('nope')).toBeNull()
    expect(s.removeDraft('d1')?.id).toBe('d1')
    expect(s.getDrafts()).toHaveLength(0)
  })

  it('survives a corrupted file and an undecryptable token', () => {
    writeFileSync(file, '{not json', 'utf8')
    const s = new AiCloneStore(deps(file))
    expect(s.getEnabled()).toBe(false)
    expect(s.getBeeperToken()).toBeNull()

    // Token encrypted under a different key: decrypt throws → treated as absent.
    writeFileSync(file, JSON.stringify({ beeperToken: 'garbage' }), 'utf8')
    const t = new AiCloneStore(deps(file))
    expect(t.getBeeperToken()).toBeNull()
  })

  it('caps the activity feed at 100 entries, newest first', () => {
    const s = new AiCloneStore(deps(file))
    for (let i = 0; i < 105; i++) {
      s.addActivity({ id: `a${i}`, at: i, kind: 'error', chatTitle: 'x', text: 'e' })
    }
    const activity = s.getActivity()
    expect(activity).toHaveLength(100)
    expect(activity[0].id).toBe('a104')
  })
})
