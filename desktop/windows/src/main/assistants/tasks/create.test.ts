// The staged-task write lifecycle: the confidence gate, the exact
// `POST /v1/staged-tasks` body (backend `CreateStagedTaskRequest`), the
// markSynced/embed success path, fail-open on a sync error, the mid-flight epoch
// guard, and the promotion debounce (spec §5 / §5b). Hermetic — fake net.fetch +
// injected storage/embedding/session.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { RewindFrame } from '../../../shared/types'
import type { ExtractedTask } from './models'
import type { TaskExtractionContext } from './create'

const h = vi.hoisted(() => ({
  epoch: 5,
  getSessionEpoch: vi.fn(() => h.epoch),
  getBackendSession: vi.fn(() => ({
    apiBase: 'https://api',
    desktopApiBase: 'https://d',
    token: 't'
  })),
  getAbortSignal: vi.fn(() => undefined),
  insertLocalStagedTask: vi.fn((_input: Record<string, unknown>) => ({ id: 1 })),
  markSyncedStagedTask: vi.fn(),
  syncTaskActionItems: vi.fn((_items: unknown[], _opts?: unknown) => ({
    skipped: 0,
    adopted: 0,
    inserted: 1,
    updated: 0
  })),
  generateEmbeddingForTask: vi.fn(async () => {}),
  fetch: vi.fn()
}))

vi.mock('../core/session', () => ({
  getSessionEpoch: h.getSessionEpoch,
  getBackendSession: h.getBackendSession,
  getAbortSignal: h.getAbortSignal
}))
vi.mock('../../ipc/db', () => ({
  insertLocalStagedTask: h.insertLocalStagedTask,
  markSyncedStagedTask: h.markSyncedStagedTask,
  syncTaskActionItems: h.syncTaskActionItems
}))
vi.mock('../../tasks/taskEmbeddingService', () => ({
  generateEmbeddingForTask: h.generateEmbeddingForTask
}))
vi.mock('electron', () => ({
  net: { fetch: h.fetch },
  BrowserWindow: { getAllWindows: () => [] }
}))

import {
  createStagedTaskFromExtraction,
  promoteIfNeeded,
  __resetPromotionStateForTests
} from './create'

// A high-confidence, fully-populated extraction (passes the 0.75 gate).
const task: ExtractedTask = {
  title: 'Send Acme onboarding deck to Priya by Friday',
  description: 'Priya asked for the deck',
  priority: 'high',
  sourceApp: 'Slack',
  inferredDeadline: '2099-12-31T00:00:00.000Z',
  confidence: 0.9,
  tags: ['work', 'deck'],
  sourceCategory: 'direct_request',
  sourceSubcategory: 'message',
  captureKind: 'clear_commitment',
  owner: 'user',
  concreteDeliverable: true,
  publicBroadcast: false,
  directMention: true,
  alreadyDone: false,
  duplicateOf: null,
  refinesTask: null,
  ownershipConfidence: 0.85,
  contextSummary: 'Viewing a Slack DM',
  currentActivity: 'Reading a message from Priya'
}

const frame: RewindFrame = {
  id: 7,
  ts: 1000,
  app: 'Slack',
  windowTitle: 'Acme — general',
  processName: 'slack',
  ocrText: '',
  imagePath: '',
  width: 0,
  height: 0,
  indexed: 1
}

const context: TaskExtractionContext = {
  contextSummary: 'Viewing a Slack DM',
  currentActivity: 'Reading a message from Priya'
}

// The backend `metadata` dict Mac sends on the legacy path (TA:497–517), built in
// the SAME key order create.ts uses so JSON.stringify matches byte-for-byte.
const expectedBackendMetadata = {
  source_app: 'Slack',
  confidence: 0.9,
  context_summary: 'Viewing a Slack DM',
  current_activity: 'Reading a message from Priya',
  tags: ['work', 'deck'],
  source_category: 'direct_request',
  source_subcategory: 'message',
  category: 'work',
  reasoning: 'Priya asked for the deck',
  inferred_deadline: '2099-12-31T00:00:00.000Z',
  window_title: 'Acme — general'
}

/** Route fetch by URL: the create POST returns a backend id; the follow-on promote
 *  no-ops (promoted:false) so create's own promote call stays inert in create tests. */
function routeFetch(createResponse: unknown): void {
  h.fetch.mockImplementation(async (url: string) => {
    if (url.endsWith('/v1/staged-tasks/promote')) {
      return {
        ok: true,
        json: async () => ({ promoted: false, reason: 'none', promoted_task: null })
      }
    }
    if (url.endsWith('/v1/staged-tasks')) return createResponse
    return { ok: false, status: 404, json: async () => ({}) }
  })
}

const createCall = (): [string, { body: string }] =>
  h.fetch.mock.calls.find(([u]) => (u as string).endsWith('/v1/staged-tasks')) as [
    string,
    { body: string }
  ]

beforeEach(() => {
  vi.clearAllMocks()
  vi.spyOn(console, 'warn').mockImplementation(() => {})
  h.epoch = 5
  h.getSessionEpoch.mockImplementation(() => h.epoch)
  h.getBackendSession.mockReturnValue({
    apiBase: 'https://api',
    desktopApiBase: 'https://d',
    token: 't'
  })
  h.getAbortSignal.mockReturnValue(undefined)
  h.insertLocalStagedTask.mockReturnValue({ id: 1 })
  __resetPromotionStateForTests()
})

afterEach(() => vi.restoreAllMocks())

describe('createStagedTaskFromExtraction — confidence gate (§5 step 1)', () => {
  it('drops a sub-threshold task with NO write and NO network', async () => {
    await createStagedTaskFromExtraction({ ...task, confidence: 0.74 }, frame, 5, context)
    expect(h.insertLocalStagedTask).not.toHaveBeenCalled()
    expect(h.fetch).not.toHaveBeenCalled()
  })

  it('lets a task exactly at the threshold (0.75) through', async () => {
    routeFetch({ ok: true, json: async () => ({ id: 'st-1' }) })
    await createStagedTaskFromExtraction({ ...task, confidence: 0.75 }, frame, 5, context)
    expect(h.insertLocalStagedTask).toHaveBeenCalledTimes(1)
  })
})

describe('createStagedTaskFromExtraction — local row + POST body', () => {
  beforeEach(() => routeFetch({ ok: true, json: async () => ({ id: 'st-1' }) }))

  it('inserts the local staged row born unsynced with source "screenshot"', async () => {
    await createStagedTaskFromExtraction(task, frame, 5, context)
    expect(h.insertLocalStagedTask).toHaveBeenCalledWith(
      expect.objectContaining({
        description: 'Send Acme onboarding deck to Priya by Friday',
        source: 'screenshot',
        priority: 'high',
        category: 'work',
        tags: ['work', 'deck'],
        screenshotId: 7,
        confidence: 0.9,
        sourceApp: 'Slack',
        windowTitle: 'Acme — general',
        contextSummary: 'Viewing a Slack DM',
        currentActivity: 'Reading a message from Priya',
        relevanceScore: null,
        backendSynced: false
      })
    )
    // Local metadata is the JSON-stringified Mac dict (TA:427–441).
    const insertArg = h.insertLocalStagedTask.mock.calls[0][0] as unknown as {
      metadataJson: string
    }
    expect(JSON.parse(insertArg.metadataJson)).toEqual({
      tags: ['work', 'deck'],
      context_summary: 'Viewing a Slack DM',
      source_category: 'direct_request',
      source_subcategory: 'message',
      category: 'work',
      inferred_deadline: '2099-12-31T00:00:00.000Z',
      window_title: 'Acme — general'
    })
  })

  it('POSTs /v1/staged-tasks with the EXACT backend body (metadata stringified, due_at ISO, relevance_score null)', async () => {
    await createStagedTaskFromExtraction(task, frame, 5, context)
    const [url, opts] = createCall()
    expect(url).toBe('https://api/v1/staged-tasks')
    const body = JSON.parse(opts.body)
    expect(body).toEqual({
      description: 'Send Acme onboarding deck to Priya by Friday',
      due_at: '2099-12-31T00:00:00.000Z',
      source: 'screenshot',
      priority: 'high',
      category: 'work',
      metadata: JSON.stringify(expectedBackendMetadata),
      relevance_score: null
    })
  })

  it('sends the Bearer token', async () => {
    await createStagedTaskFromExtraction(task, frame, 5, context)
    const [, opts] = createCall() as unknown as [string, { headers: Record<string, string> }]
    expect(opts.headers.Authorization).toBe('Bearer t')
  })

  it('derives context from the task when no explicit context is passed', async () => {
    // The metadata-gap fix: context_summary/current_activity now live on the task,
    // so a 3-arg call (the assistant's call shape) carries them into the metadata.
    const t = { ...task, contextSummary: 'On task ctx', currentActivity: 'On task activity' }
    await createStagedTaskFromExtraction(t, frame, 5)
    const [, opts] = createCall()
    const meta = JSON.parse(JSON.parse(opts.body).metadata)
    expect(meta.context_summary).toBe('On task ctx')
    expect(meta.current_activity).toBe('On task activity')
  })
})

describe('createStagedTaskFromExtraction — sync outcomes', () => {
  it('on success marks synced with the returned id, then embeds the TITLE', async () => {
    routeFetch({ ok: true, json: async () => ({ id: 'st-1' }) })
    await createStagedTaskFromExtraction(task, frame, 5, context)
    expect(h.markSyncedStagedTask).toHaveBeenCalledWith(1, 'st-1', expect.any(Number))
    expect(h.generateEmbeddingForTask).toHaveBeenCalledWith(
      'staged_task',
      1,
      'Send Acme onboarding deck to Priya by Friday'
    )
  })

  it('on a POST 500 keeps the local row unsynced and does not throw or embed', async () => {
    routeFetch({ ok: false, status: 500, json: async () => ({}) })
    await expect(createStagedTaskFromExtraction(task, frame, 5, context)).resolves.toBeUndefined()
    expect(h.insertLocalStagedTask).toHaveBeenCalledTimes(1) // row still written
    expect(h.markSyncedStagedTask).not.toHaveBeenCalled()
    expect(h.generateEmbeddingForTask).not.toHaveBeenCalled()
  })

  it('skips markSynced when the session epoch advances while the POST is in flight', async () => {
    let resolvePost!: (v: unknown) => void
    h.fetch.mockImplementation((url: string) => {
      if (url.endsWith('/v1/staged-tasks')) return new Promise((r) => (resolvePost = r))
      return Promise.resolve({
        ok: true,
        json: async () => ({ promoted: false, promoted_task: null })
      })
    })
    const p = createStagedTaskFromExtraction(task, frame, 5, context)
    h.epoch = 6 // sign-out / user switch mid-POST
    resolvePost({ ok: true, json: async () => ({ id: 'st-1' }) })
    await p
    expect(h.insertLocalStagedTask).toHaveBeenCalledTimes(1) // insert happened pre-await
    expect(h.markSyncedStagedTask).not.toHaveBeenCalled() // post-await write dropped
    expect(h.generateEmbeddingForTask).not.toHaveBeenCalled()
  })
})

describe('promoteIfNeeded — §5b', () => {
  it('on promoted:true reflects the action_item locally and broadcasts', async () => {
    h.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        promoted: true,
        reason: null,
        promoted_task: { id: 'ai-9', description: 'Send deck', completed: false }
      })
    })
    await promoteIfNeeded()
    expect(h.syncTaskActionItems).toHaveBeenCalledTimes(1)
    const [items] = h.syncTaskActionItems.mock.calls[0]
    expect(items).toEqual([
      expect.objectContaining({
        backendId: 'ai-9',
        description: 'Send deck',
        completed: false,
        fromStaged: true
      })
    ])
  })

  it('on promoted:false does not touch the local store', async () => {
    h.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        promoted: false,
        reason: 'No staged tasks available',
        promoted_task: null
      })
    })
    await promoteIfNeeded()
    expect(h.syncTaskActionItems).not.toHaveBeenCalled()
  })

  it('debounces a second trigger within 30s to a single promote call', async () => {
    h.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        promoted: true,
        reason: null,
        promoted_task: { id: 'ai-1', description: 'x', completed: false }
      })
    })
    await promoteIfNeeded()
    await promoteIfNeeded() // within the 30s window → debounced, no second POST
    const promoteCalls = h.fetch.mock.calls.filter(([u]) => (u as string).endsWith('/promote'))
    expect(promoteCalls).toHaveLength(1)
    expect(h.syncTaskActionItems).toHaveBeenCalledTimes(1)
  })

  it('a bypassDebounce trigger promotes again even inside the window', async () => {
    h.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        promoted: true,
        reason: null,
        promoted_task: { id: 'ai-1', description: 'x', completed: false }
      })
    })
    await promoteIfNeeded()
    await promoteIfNeeded({ bypassDebounce: true }) // safety-net timer path
    const promoteCalls = h.fetch.mock.calls.filter(([u]) => (u as string).endsWith('/promote'))
    expect(promoteCalls).toHaveLength(2)
  })
})
