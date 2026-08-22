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
import type { ProfileSources } from './synthesis'

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
  synthesize: ReturnType<typeof vi.fn>
  insertProfile: ReturnType<typeof vi.fn>
  syncProfile: ReturnType<typeof vi.fn>
} {
  const synthesize = vi.fn(
    async (_sources: ProfileSources, _past: string[]) => '- User is an engineer'
  )
  const insertProfile = vi.fn(() => 42)
  const syncProfile = vi.fn(async () => undefined)
  const deps: OrchestratorDeps = {
    fetchers: emptyFetchers(),
    synthesize,
    listPastProfiles: vi.fn(() => []),
    insertProfile,
    syncProfile,
    now: () => 1_700_000_000_000,
    ...over
  }
  return { deps, synthesize, insertProfile, syncProfile }
}

// Let the fire-and-forget syncProfile().catch() microtasks settle.
const flush = (): Promise<void> => new Promise((r) => setTimeout(r, 0))

afterEach(() => vi.restoreAllMocks())

describe('generateProfile (orchestrator core)', () => {
  it('(a) throws "not enough data" and never calls the LLM when every source is empty', async () => {
    const { deps, synthesize, insertProfile, syncProfile } = makeDeps()
    await expect(generateProfile(deps)).rejects.toThrow(/not enough data/)
    expect(synthesize).not.toHaveBeenCalled()
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
    const { deps, synthesize, insertProfile } = makeDeps({ fetchers })

    const record = await generateProfile(deps)

    // Generation proceeded on the surviving source.
    expect(synthesize).toHaveBeenCalledTimes(1)
    expect(insertProfile).toHaveBeenCalledTimes(1)
    expect(record.id).toBe(42)
    // The failed source was named as a degraded (not silent) outcome.
    expect(warn).toHaveBeenCalledWith(
      '[fallback]',
      expect.objectContaining({
        component: 'backend_fetch',
        outcome: 'degraded',
        reason: 'source_fetch_failed',
        source: 'memories',
        error: 'HTTP 500'
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
      '[fallback]',
      expect.objectContaining({
        component: 'sync_dispatch',
        outcome: 'degraded',
        reason: 'backend_sync_failed',
        op: 'generate'
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
    const { deps, synthesize, insertProfile } = makeDeps({ fetchers })

    await expect(generateProfile(deps)).rejects.toBeInstanceOf(AuthExpiredError)
    await expect(generateProfile(deps)).rejects.toThrow(/auth expired/)
    expect(synthesize).not.toHaveBeenCalled()
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
    const synthesize = vi.fn(async (_sources: ProfileSources, _past: string[]) => {
      stale = true // the user signs out during synthesis
      return '- User is an engineer'
    })
    const { deps, insertProfile, syncProfile } = makeDeps({
      fetchers,
      synthesize,
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

  it('hands the backend its sources plus past profiles oldest→newest', async () => {
    const fetchers: SourceFetchers = {
      ...emptyFetchers(),
      memories: vi.fn(async () => ['[work] engineer'])
    }
    const synthesize = vi
      .fn<(s: ProfileSources, past: string[]) => Promise<string>>()
      .mockResolvedValue('- consolidated fact')
    const listPastProfiles = vi.fn(() => ['- newest past', '- oldest past'])
    const { deps } = makeDeps({ fetchers, synthesize, listPastProfiles })

    const record = await generateProfile(deps)

    expect(synthesize).toHaveBeenCalledTimes(1)
    const [sources, past] = synthesize.mock.calls[0]
    expect(sources.memories).toEqual(['[work] engineer'])
    // The stored list is newest-first; the core reverses it for the backend's
    // consolidation stage.
    expect(past).toEqual(['- oldest past', '- newest past'])
    expect(record.profileText).toBe('- consolidated fact')
  })
})
