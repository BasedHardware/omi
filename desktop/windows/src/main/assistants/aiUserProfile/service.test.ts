// Orchestrator-core tests for the AI User Profile generate flow. These exercise
// service.ts's real orchestration logic through the injectable seams it wires to
// (orchestrate.generateProfile) WITHOUT importing electron or better-sqlite3, so
// they run hermetically under plain-node vitest. service.ts itself is a thin
// wiring layer over this core (net.fetch + the db.ts writers).
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  AuthExpiredError,
  HttpError,
  SessionChangedError,
  generateProfile,
  type OrchestratorDeps,
  type SourceFetchers
} from './orchestrate'
import type { ChatMessage } from './synthesis'

// A fetcher set that returns nothing anywhere (the "no data" case).
function emptyFetchers(): SourceFetchers {
  return {
    memories: vi.fn(async () => []),
    tasks: vi.fn(async () => []),
    goals: vi.fn(async () => []),
    conversations: vi.fn(async () => []),
    messages: vi.fn(async () => [])
  }
}

function makeDeps(over: Partial<OrchestratorDeps> = {}): {
  deps: OrchestratorDeps
  chat: ReturnType<typeof vi.fn>
  insertProfile: ReturnType<typeof vi.fn>
  syncProfile: ReturnType<typeof vi.fn>
} {
  const chat = vi.fn(async (_messages: ChatMessage[]) => '- User is an engineer')
  const insertProfile = vi.fn(() => 42)
  const syncProfile = vi.fn(async () => undefined)
  const deps: OrchestratorDeps = {
    fetchers: emptyFetchers(),
    chat,
    listPastProfiles: vi.fn(() => []),
    insertProfile,
    syncProfile,
    now: () => 1_700_000_000_000,
    ...over
  }
  return { deps, chat, insertProfile, syncProfile }
}

// Let the fire-and-forget syncProfile().catch() microtasks settle.
const flush = (): Promise<void> => new Promise((r) => setTimeout(r, 0))

afterEach(() => vi.restoreAllMocks())

describe('generateProfile (orchestrator core)', () => {
  it('(a) throws "not enough data" and never calls the LLM when every source is empty', async () => {
    const { deps, chat, insertProfile, syncProfile } = makeDeps()
    await expect(generateProfile(deps)).rejects.toThrow(/not enough data/)
    expect(chat).not.toHaveBeenCalled()
    expect(insertProfile).not.toHaveBeenCalled()
    expect(syncProfile).not.toHaveBeenCalled()
  })

  it('(b) still generates when one source fails but others return data (per-source failure does not abort)', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const fetchers: SourceFetchers = {
      ...emptyFetchers(),
      // One source throws a transient (non-auth) error…
      memories: vi.fn(async () => {
        throw new HttpError(500)
      }),
      // …another returns real data.
      tasks: vi.fn(async () => ['[todo] Ship the Windows profile feature'])
    }
    const { deps, chat, insertProfile } = makeDeps({ fetchers })

    const record = await generateProfile(deps)

    // Generation proceeded on the surviving source.
    expect(chat).toHaveBeenCalledTimes(1)
    expect(insertProfile).toHaveBeenCalledTimes(1)
    expect(record.id).toBe(42)
    // The failed source was named as a degraded (not silent) outcome.
    expect(warn).toHaveBeenCalledWith(
      'omi_fallback_event',
      expect.objectContaining({
        event: 'fallback',
        component: 'ai_profile',
        outcome: 'degraded',
        reason: 'source_fetch_failed',
        detail: expect.objectContaining({ source: 'memories', error: 'HTTP 500' })
      })
    )
  })

  it('(c) returns the inserted local row even when the backend sync fails (sync loss never loses the profile)', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const fetchers: SourceFetchers = {
      ...emptyFetchers(),
      goals: vi.fn(async () => ['Ship 2 features per week (50% complete)'])
    }
    const syncProfile = vi.fn(async () => {
      throw new HttpError(503)
    })
    const { deps, insertProfile } = makeDeps({ fetchers, syncProfile })

    const record = await generateProfile(deps)

    // Local row was inserted and returned regardless of the sync outcome.
    expect(insertProfile).toHaveBeenCalledTimes(1)
    expect(record).toMatchObject({ id: 42, backendSynced: false })
    expect(syncProfile).toHaveBeenCalledTimes(1)

    await flush()
    // The sync failure surfaced as a degraded (not silent) outcome.
    expect(warn).toHaveBeenCalledWith(
      'omi_fallback_event',
      expect.objectContaining({
        event: 'fallback',
        component: 'ai_profile',
        outcome: 'degraded',
        reason: 'backend_sync_failed',
        detail: expect.objectContaining({ op: 'generate' })
      })
    )
  })

  it('(m4) aborts with AuthExpiredError (not "not enough data") and never calls the LLM when a source session is expired', async () => {
    const fetchers: SourceFetchers = {
      ...emptyFetchers(),
      // Data present elsewhere would otherwise generate — but auth expiry wins.
      messages: vi.fn(async () => ['[human] hi']),
      memories: vi.fn(async () => {
        throw new AuthExpiredError()
      })
    }
    const { deps, chat, insertProfile } = makeDeps({ fetchers })

    await expect(generateProfile(deps)).rejects.toBeInstanceOf(AuthExpiredError)
    await expect(generateProfile(deps)).rejects.toThrow(/auth expired/)
    expect(chat).not.toHaveBeenCalled()
    expect(insertProfile).not.toHaveBeenCalled()
  })

  // C1 (sign-out privacy). signOutUser() is wipe-then-signout, and a generation
  // takes 10–90s. Without this guard an in-flight run completes AFTER the wipe
  // and re-inserts the signed-out user's synthesized dossier into the DB that was
  // just cleared to erase it (and PATCHes it to the backend with their token) —
  // and if a second user has signed in by then, it lands in THEIR database.
  it('(C1) discards the result — no insert, no sync — when the session changes mid-generation', async () => {
    const fetchers: SourceFetchers = {
      ...emptyFetchers(),
      memories: vi.fn(async () => ['[work] engineer'])
    }
    // Session is live while the sources/LLM run, gone by the time we would write.
    let stale = false
    const chat = vi.fn(async (_messages: ChatMessage[]) => {
      stale = true // the user signs out during synthesis
      return '- User is an engineer'
    })
    const { deps, insertProfile, syncProfile } = makeDeps({
      fetchers,
      chat,
      isStale: () => stale
    })

    await expect(generateProfile(deps)).rejects.toBeInstanceOf(SessionChangedError)

    // The whole point: nothing was written anywhere.
    expect(insertProfile).not.toHaveBeenCalled()
    expect(syncProfile).not.toHaveBeenCalled()
  })

  it('(C1) writes normally while the session is unchanged (guard does not misfire)', async () => {
    const fetchers: SourceFetchers = {
      ...emptyFetchers(),
      memories: vi.fn(async () => ['[work] engineer'])
    }
    const { deps, insertProfile, syncProfile } = makeDeps({ fetchers, isStale: () => false })

    const record = await generateProfile(deps)

    expect(record.id).toBe(42)
    expect(insertProfile).toHaveBeenCalledTimes(1)
    expect(syncProfile).toHaveBeenCalledTimes(1)
  })

  it('runs stage-2 consolidation when past profiles exist (oldest→newest)', async () => {
    const fetchers: SourceFetchers = {
      ...emptyFetchers(),
      memories: vi.fn(async () => ['[work] engineer'])
    }
    const chat = vi
      .fn<(m: ChatMessage[]) => Promise<string>>()
      .mockResolvedValueOnce('- stage1 fact')
      .mockResolvedValueOnce('- consolidated fact')
    const listPastProfiles = vi.fn(() => ['- newest past', '- oldest past'])
    const { deps } = makeDeps({ fetchers, chat, listPastProfiles })

    const record = await generateProfile(deps)

    expect(chat).toHaveBeenCalledTimes(2)
    // Stage 2 prompt renders past profiles oldest→newest (list is newest-first,
    // reversed by the core).
    const stage2User = chat.mock.calls[1][0][1].content
    expect(stage2User.indexOf('- oldest past')).toBeLessThan(stage2User.indexOf('- newest past'))
    expect(record.profileText).toBe('- consolidated fact')
  })
})
