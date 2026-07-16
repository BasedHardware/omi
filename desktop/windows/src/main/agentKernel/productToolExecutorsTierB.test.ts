// Unit tests for the Tier-B product-tool executors (PR-4..7): execute_sql (the
// security-sensitive one — an injection battery), the backend-backed memories /
// conversations tools (injected BackendToolCaller), the get_work_context /
// get_daily_recap composition tools, and save_knowledge_graph. Every executor is
// built with INJECTED fakes, so nothing here touches better-sqlite3, electron, or
// the network. The pure SQL safety layers (isReadOnlySql / tablesAllowed) run
// BEFORE the injected runQuery, so the injection assertions are exhaustive without
// a real DB.

import { describe, it, expect, vi } from 'vitest'
import type {
  ActionItemRecord,
  FocusSessionRecord,
  InsightRecord,
  LocalConversation,
  RewindFrame
} from '../../shared/types'
import type { BackendToolRequest } from './backendTools'
import {
  AGENT_SQL_TABLE_ALLOWLIST,
  createExecuteSqlExecutor,
  createGetMemoriesExecutor,
  createSearchMemoriesExecutor,
  createGetConversationsExecutor,
  createSearchConversationsExecutor,
  createGetWorkContextExecutor,
  createGetDailyRecapExecutor,
  createSaveKnowledgeGraphExecutor
} from './productToolExecutors'
import { defaultProductToolExecutors, WINDOWS_SERVICEABLE_PRODUCT_TOOLS } from './toolRelayBridge'

const ctx = (signal?: AbortSignal) => ({
  sessionId: 's1',
  adapterId: 'pi-mono',
  signal: signal ?? new AbortController().signal
})

// --- execute_sql (SECURITY) --------------------------------------------------

describe('execute_sql', () => {
  const runner = () => vi.fn(() => ({ columns: ['n'], rows: [[1]] }))

  it('requires a query', async () => {
    const runQuery = runner()
    const exec = createExecuteSqlExecutor({ runQuery })
    expect(await exec({}, ctx())).toBe('Error: query is required')
    expect(runQuery).not.toHaveBeenCalled()
  })

  it.each([
    ['INSERT', "INSERT INTO memories (content) VALUES ('x')"],
    ['UPDATE', 'UPDATE action_items SET completed = 1 WHERE id = 1'],
    ['DELETE', 'DELETE FROM rewind_frames WHERE id = 1'],
    ['DROP', 'DROP TABLE rewind_frames'],
    ['ALTER', 'ALTER TABLE memories ADD COLUMN x TEXT'],
    ['CREATE', 'CREATE TABLE evil (x TEXT)'],
    ['PRAGMA', 'PRAGMA table_info(memories)'],
    ['ATTACH', "ATTACH DATABASE 'other.db' AS other"],
    ['REPLACE', "REPLACE INTO memories (content) VALUES ('x')"]
  ])('rejects a %s write/DDL statement (read-only), never runs it', async (_kind, sql) => {
    const runQuery = runner()
    const exec = createExecuteSqlExecutor({ runQuery })
    const out = await exec({ query: sql }, ctx())
    expect(out).toContain('read-only')
    expect(runQuery).not.toHaveBeenCalled()
  })

  it('rejects a multi-statement query, never runs it', async () => {
    const runQuery = runner()
    const exec = createExecuteSqlExecutor({ runQuery })
    const out = await exec({ query: 'SELECT 1; DROP TABLE rewind_frames' }, ctx())
    expect(out).toContain('multi-statement')
    expect(runQuery).not.toHaveBeenCalled()
  })

  it('rejects a SELECT from a non-allowlisted table', async () => {
    const runQuery = runner()
    const exec = createExecuteSqlExecutor({ runQuery })
    const out = await exec({ query: 'SELECT * FROM app_meta' }, ctx())
    expect(out).toContain('not queryable')
    expect(runQuery).not.toHaveBeenCalled()
  })

  it('rejects a SELECT that JOINs an allowlisted and a non-allowlisted table', async () => {
    const runQuery = runner()
    const exec = createExecuteSqlExecutor({ runQuery })
    const out = await exec({ query: 'SELECT * FROM memories JOIN app_meta ON 1=1' }, ctx())
    expect(out).toContain('not queryable')
    expect(runQuery).not.toHaveBeenCalled()
  })

  it('runs a valid SELECT over an allowlisted table and wraps it in an unsuppressible outer LIMIT', async () => {
    const runQuery = vi.fn((_sql: string) => ({ columns: ['app', 'n'], rows: [['Chrome', 12]] }))
    const exec = createExecuteSqlExecutor({ runQuery })
    const out = await exec(
      { query: 'SELECT app, COUNT(*) n FROM rewind_frames GROUP BY app' },
      ctx()
    )
    expect(runQuery).toHaveBeenCalledTimes(1)
    expect(runQuery.mock.calls[0][0]).toMatch(/^SELECT \* FROM \(.*\) LIMIT 201\s*$/s)
    expect(out).toContain('app | n')
    expect(out).toContain('Chrome | 12')
    expect(out).toContain('1 row(s)')
  })

  it('keeps an inner explicit LIMIT AND applies the outer cap, caps rendered rows at 200', async () => {
    const rows = Array.from({ length: 250 }, (_, i) => [i])
    const runQuery = vi.fn((_sql: string) => ({ columns: ['id'], rows }))
    const exec = createExecuteSqlExecutor({ runQuery })
    const out = await exec({ query: 'SELECT id FROM memories LIMIT 500' }, ctx())
    expect(runQuery.mock.calls[0][0]).toContain('LIMIT 500') // inner preserved
    expect(runQuery.mock.calls[0][0]).toMatch(/\) LIMIT 201\s*$/) // outer cap unsuppressed
    expect(out).toContain('200 row(s)')
  })

  it('allowlist excludes meta/kv/embedding/outbox tables', () => {
    for (const t of [
      'app_meta',
      'file_index_meta',
      'indexed_files',
      'caption_event',
      'rewind_embeddings',
      'rewind_embedding_vectors',
      'voice_turn_outbox'
    ]) {
      expect(AGENT_SQL_TABLE_ALLOWLIST.has(t)).toBe(false)
    }
    for (const t of ['rewind_frames', 'action_items', 'local_conversation', 'memories']) {
      expect(AGENT_SQL_TABLE_ALLOWLIST.has(t)).toBe(true)
    }
  })
})

// --- memories + conversations (backend caller injected) ----------------------

describe('get_memories', () => {
  it('calls the memories endpoint with clamped paging + date passthrough', async () => {
    const call = vi.fn(async (_req: BackendToolRequest) => 'MEMORIES')
    const exec = createGetMemoriesExecutor(call)
    const out = await exec({ limit: 999999, offset: 3 }, ctx())
    expect(out).toBe('MEMORIES')
    const req = call.mock.calls[0][0]
    expect(req.method).toBe('GET')
    expect(req.path).toBe('/v1/tools/memories')
    expect(req.query!.limit).toBe(5000) // clamped to max
    expect(req.query!.offset).toBe(3)
  })

  it('rejects a malformed start_date before calling', async () => {
    const call = vi.fn(async (_req: BackendToolRequest) => 'X')
    const exec = createGetMemoriesExecutor(call)
    const out = await exec({ start_date: 'not-a-date' }, ctx())
    expect(out).toContain('Error: start_date must be ISO format')
    expect(call).not.toHaveBeenCalled()
  })
})

describe('search_memories', () => {
  it('requires a query', async () => {
    const call = vi.fn(async (_req: BackendToolRequest) => 'X')
    const exec = createSearchMemoriesExecutor(call)
    expect(await exec({}, ctx())).toBe('Error: query is required')
    expect(call).not.toHaveBeenCalled()
  })

  it('POSTs the query with a clamped limit', async () => {
    const call = vi.fn(async (_req: BackendToolRequest) => 'HITS')
    const exec = createSearchMemoriesExecutor(call)
    await exec({ query: 'dog name', limit: 99 }, ctx())
    const req = call.mock.calls[0][0]
    expect(req.method).toBe('POST')
    expect(req.path).toBe('/v1/tools/memories/search')
    expect(req.body).toEqual({ query: 'dog name', limit: 20 })
  })
})

describe('get_conversations', () => {
  it('passes date range + include_transcript through', async () => {
    const call = vi.fn(async (_req: BackendToolRequest) => 'CONVOS')
    const exec = createGetConversationsExecutor(call)
    await exec({ start_date: '2026-02-01T00:00:00Z', limit: 3, include_transcript: false }, ctx())
    const req = call.mock.calls[0][0]
    expect(req.method).toBe('GET')
    expect(req.path).toBe('/v1/tools/conversations')
    expect(req.query!.start_date).toBe('2026-02-01T00:00:00Z')
    expect(req.query!.limit).toBe(3)
    expect(req.query!.include_transcript).toBe(false)
  })
})

describe('search_conversations', () => {
  it('requires a query', async () => {
    const call = vi.fn(async (_req: BackendToolRequest) => 'X')
    const exec = createSearchConversationsExecutor(call)
    expect(await exec({}, ctx())).toBe('Error: query is required')
    expect(call).not.toHaveBeenCalled()
  })

  it('POSTs query + optional date range', async () => {
    const call = vi.fn(async (_req: BackendToolRequest) => 'RESULTS')
    const exec = createSearchConversationsExecutor(call)
    await exec({ query: 'the offsite', end_date: '2026-03-01T00:00:00Z' }, ctx())
    const req = call.mock.calls[0][0]
    expect(req.method).toBe('POST')
    expect(req.body!.query).toBe('the offsite')
    expect(req.body!.limit).toBe(5)
    expect(req.body!.end_date).toBe('2026-03-01T00:00:00Z')
  })
})

// --- get_work_context --------------------------------------------------------

function frame(over: Partial<RewindFrame>): RewindFrame {
  return {
    id: 1,
    ts: Date.now(),
    app: 'Chrome',
    windowTitle: 'Docs',
    processName: 'chrome.exe',
    ocrText: '',
    imagePath: '/x.jpg',
    width: 100,
    height: 100,
    indexed: 1,
    ...over
  }
}

describe('get_work_context', () => {
  it('reports capture_disabled when Screen History is off', async () => {
    const exec = createGetWorkContextExecutor({ captureEnabled: () => false })
    const payload = JSON.parse(await exec({}, ctx()))
    expect(payload.ok).toBe(false)
    expect(payload.failure_code).toBe('capture_disabled')
    expect(payload.screen_now.available).toBe(false)
  })

  it('reports no_recent_capture when nothing has been captured', async () => {
    const exec = createGetWorkContextExecutor({
      captureEnabled: () => true,
      latestFrame: () => null
    })
    const payload = JSON.parse(await exec({}, ctx()))
    expect(payload.ok).toBe(false)
    expect(payload.failure_code).toBe('no_recent_capture')
  })

  it('builds screen_now + a collapsed timeline from the latest + sampled frames', async () => {
    const now = 1_000_000_000_000
    const exec = createGetWorkContextExecutor({
      captureEnabled: () => true,
      now: () => now,
      latestFrame: () =>
        frame({ id: 7, ts: now - 5000, app: 'Safari', windowTitle: 'Gmail', ocrText: 'inbox 3' }),
      sampledFrames: () => [
        frame({ id: 1, ts: now - 300_000, app: 'Safari', windowTitle: 'Gmail' }),
        frame({ id: 2, ts: now - 240_000, app: 'Safari', windowTitle: 'Gmail' }),
        frame({ id: 3, ts: now - 120_000, app: 'Code', windowTitle: 'main.ts' })
      ]
    })
    const payload = JSON.parse(await exec({ minutes: 30 }, ctx()))
    expect(payload.ok).toBe(true)
    expect(payload.window_minutes).toBe(30)
    expect(payload.screen_now.available).toBe(true)
    expect(payload.screen_now.screenshot_id).toBe(7)
    expect(payload.screen_now.app_name).toBe('Safari')
    expect(payload.screen_now.ocr_preview).toBe('inbox 3')
    // Two Safari/Gmail frames collapse into one run; Code is a second run.
    expect(payload.timeline).toHaveLength(2)
    // Most-recent-first.
    expect(payload.timeline[0].app).toBe('Code')
    expect(payload.timeline[1].app).toBe('Safari')
    expect(payload.timeline[1].frames).toBe(2)
  })

  it('clamps minutes to [1,120]', async () => {
    const exec = createGetWorkContextExecutor({
      captureEnabled: () => true,
      latestFrame: () => frame({}),
      sampledFrames: () => []
    })
    const payload = JSON.parse(await exec({ minutes: 9999 }, ctx()))
    expect(payload.window_minutes).toBe(120)
  })
})

// --- get_daily_recap ---------------------------------------------------------

function actionItem(over: Partial<ActionItemRecord>): ActionItemRecord {
  return {
    id: 1,
    backendId: 'b1',
    backendSynced: true,
    description: 'Task',
    completed: false,
    deleted: false,
    deletedBy: null,
    source: 'omi',
    conversationId: null,
    priority: null,
    category: null,
    tags: [],
    dueAt: null,
    screenshotId: null,
    confidence: null,
    sourceApp: null,
    windowTitle: null,
    contextSummary: null,
    currentActivity: null,
    metadataJson: null,
    relevanceScore: null,
    scoredAt: null,
    fromStaged: false,
    sortOrder: null,
    indentLevel: null,
    createdAt: 0,
    updatedAt: 0,
    ...over
  }
}

describe('get_daily_recap', () => {
  // Fix "now" to local noon so the day window is unambiguous.
  const now = new Date(2026, 5, 15, 12, 0, 0, 0).getTime()
  const startToday = new Date(2026, 5, 15, 0, 0, 0, 0).getTime()
  const yesterdayMorning = startToday - 12 * 60 * 60 * 1000

  const deps = () => ({
    now: () => now,
    appActivity: vi.fn((_from: number, _to: number) => [
      { app: 'Chrome', windowTitle: 'A', count: 120, firstSeen: startToday, lastSeen: now },
      { app: 'Chrome', windowTitle: 'B', count: 60, firstSeen: startToday, lastSeen: now },
      { app: 'Code', windowTitle: 'x', count: 30, firstSeen: startToday, lastSeen: now }
    ]),
    conversations: vi.fn(() => [
      {
        id: 'c1',
        startedAt: now - 600_000,
        endedAt: now,
        transcript: 'hello world',
        createdAt: now - 600_000
      } as LocalConversation,
      {
        id: 'old',
        startedAt: 0,
        endedAt: 0,
        transcript: 'nope',
        createdAt: 100
      } as LocalConversation
    ]),
    actionItems: vi.fn(() => [
      actionItem({ description: 'today task', createdAt: now - 1000 }),
      actionItem({ description: 'old task', createdAt: 100 })
    ]),
    focusSessions: vi.fn(() => [] as FocusSessionRecord[]),
    memories: vi.fn(() => [{ content: 'likes tea', category: 'preference' }]),
    insights: vi.fn(() => [] as InsightRecord[])
  })

  it('renders a Today recap and windows out old rows', async () => {
    const exec = createGetDailyRecapExecutor(deps())
    const out = await exec({ days_ago: 0 }, ctx())
    expect(out).toContain('# Today Recap')
    // Chrome A+B counts merge → 180 captures ≈ 3 min.
    expect(out).toContain('**Chrome**: 3 min (180 captures')
    expect(out).toContain('## Conversations (1)')
    expect(out).toContain('hello world')
    expect(out).not.toContain('nope')
    expect(out).toContain('## Tasks (1)')
    expect(out).toContain('today task')
    expect(out).not.toContain('old task')
    expect(out).toContain('## Memories (1 recent)')
  })

  it('labels Yesterday and passes the day window to appActivity', async () => {
    const d = deps()
    const exec = createGetDailyRecapExecutor(d)
    const out = await exec({ days_ago: 1 }, ctx())
    expect(out).toContain('# Yesterday Recap')
    const [from, to] = d.appActivity.mock.calls[0]
    expect(from).toBe(startToday - 24 * 60 * 60 * 1000)
    expect(to).toBe(startToday)
    // sanity: yesterdayMorning is inside [from,to)
    expect(yesterdayMorning >= from && yesterdayMorning < to).toBe(true)
  })
})

// --- save_knowledge_graph ----------------------------------------------------

describe('save_knowledge_graph', () => {
  it('maps nodes, synthesizes edge ids, and drops dangling edges', async () => {
    const upsert = vi.fn()
    const exec = createSaveKnowledgeGraphExecutor({ upsert })
    const out = await exec(
      {
        nodes: [
          { id: 'n1', label: 'Alice', node_type: 'person', aliases: ['Al'] },
          { id: 'n2', label: 'Acme', node_type: 'organization' }
        ],
        edges: [
          { source_id: 'n1', target_id: 'n2', label: 'works at' },
          { source_id: 'n1', target_id: 'ghost', label: 'knows' } // dangling → dropped
        ]
      },
      ctx()
    )
    expect(out).toBe('OK: saved 2 entities and 1 relationships to your knowledge graph')
    const [nodes, edges] = upsert.mock.calls[0]
    expect(nodes).toEqual([
      { id: 'n1', label: 'Alice', nodeType: 'person', aliases: ['Al'] },
      { id: 'n2', label: 'Acme', nodeType: 'organization', aliases: undefined }
    ])
    expect(edges).toHaveLength(1)
    expect(edges[0]).toMatchObject({ sourceId: 'n1', targetId: 'n2', label: 'works at' })
    expect(typeof edges[0].id).toBe('string')
  })

  it('defaults an unknown node_type to thing', async () => {
    const upsert = vi.fn()
    const exec = createSaveKnowledgeGraphExecutor({ upsert })
    await exec({ nodes: [{ id: 'n1', label: 'X', node_type: 'weapon' }], edges: [] }, ctx())
    expect(upsert.mock.calls[0][0][0].nodeType).toBe('thing')
  })

  it('errors when there are no valid nodes', async () => {
    const upsert = vi.fn()
    const exec = createSaveKnowledgeGraphExecutor({ upsert })
    const out = await exec({ nodes: [{ label: 'no id' }], edges: [] }, ctx())
    expect(out).toContain('Error: no valid nodes')
    expect(upsert).not.toHaveBeenCalled()
  })
})

// --- registry wiring ---------------------------------------------------------

describe('Tier-B tools are registered + serviceable', () => {
  const names = [
    'execute_sql',
    'get_memories',
    'search_memories',
    'get_conversations',
    'search_conversations',
    'get_work_context',
    'get_daily_recap',
    'save_knowledge_graph'
  ]

  it('every Tier-B tool is in the default registry and the serviceable allowlist', () => {
    for (const n of names) {
      expect(defaultProductToolExecutors.has(n)).toBe(true)
      expect(WINDOWS_SERVICEABLE_PRODUCT_TOOLS.has(n)).toBe(true)
    }
  })
})
