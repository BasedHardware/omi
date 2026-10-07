import { beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({
  epoch: 7,
  fetch: vi.fn(),
  recordFallback: vi.fn()
}))

vi.mock('electron', () => ({ net: { fetch: h.fetch } }))
vi.mock('../core/session', () => ({ getAbortSignal: () => undefined, getSessionEpoch: () => h.epoch }))
vi.mock('../aiUserProfile/service', () => ({ getLatestProfileText: () => 'Profile' }))
vi.mock('../../ocr/helperProcess', () => ({ helperProcess: { ocr: vi.fn() } }))
vi.mock('../../observability/fallback', () => ({ recordFallback: h.recordFallback }))
vi.mock('./toolBackends', () => ({ executeKeywordSearch: vi.fn(async () => []) }))

import {
  requestGate,
  requestLunaExtraction,
  runScreenTaskPipeline,
  ScreenTaskGateDeniedError,
  type ScreenTaskGateResult
} from './screenTaskPipeline'
import type { BackendSession } from '../core/session'
import type { TaskSearchResult } from './toolBackends'

const session = (): BackendSession => ({ apiBase: 'https://api.test', desktopApiBase: 'https://desktop.test', token: 'token' })
const activeTask: TaskSearchResult = {
  id: 5,
  description: 'Send Sarah the Q4 budget spreadsheet',
  status: 'active',
  similarity: null,
  match_type: 'fts',
  relevance_score: null,
  source: 'action_item'
}

function pipelineDeps(overrides: Record<string, unknown> = {}) {
  return {
    ocr: vi.fn(async () => ({ ok: true as const, fullText: 'Sarah asked for the budget deck.' })),
    profile: vi.fn(() => 'Profile'),
    search: vi.fn(async () => [activeTask]),
    gate: vi.fn(async () => ({ shouldExtract: true, gateOutcome: 'passed', auditSample: false } as ScreenTaskGateResult)),
    extract: vi.fn(async (_session: BackendSession, _params: Parameters<typeof requestLunaExtraction>[1]) => []),
    fallback: vi.fn(),
    ...overrides
  }
}

const pipelineParams = {
  session: session(),
  sessionEpoch: 7,
  app: 'Slack',
  today: '2026-10-07',
  imageBase64: 'jpeg-base64',
  validateWork: () => {}
}

function taskJson(relation = 'new', relatedId = '', captureKind = 'direct_request'): Record<string, unknown> {
  return {
    title: relation === 'new' ? 'Send Sarah the Q4 budget spreadsheet today' : 'Send Sarah the Q4 budget spreadsheet',
    description: 'Sarah asked for the budget deck',
    deadline: '',
    priority: 'medium',
    confidence: 0.9,
    relation,
    related_id: relatedId,
    evidence: '',
    capture_kind: captureKind,
    owner: 'user',
    concrete_deliverable: true,
    public_broadcast: false,
    direct_mention: true,
    ownership_confidence: 0.9,
    tags: ['finance'],
    source_category: 'direct_request',
    source_subcategory: 'message'
  }
}

function modelResponse(tasks: Record<string, unknown>[]): Response {
  return new Response(JSON.stringify({
    candidates: [{
      finishReason: 'STOP',
      content: { parts: [{ text: JSON.stringify({
        screen_kind: 'open_conversation',
        context_summary: 'A request in Slack',
        current_activity: 'Reading Sarah’s request',
        tasks
      }) }] }
    }]
  }), { status: 200 })
}

beforeEach(() => {
  vi.clearAllMocks()
  h.epoch = 7
})

describe('runScreenTaskPipeline', () => {
  it('runs the OCR gate once and skips Luna on a non-audited rejection', async () => {
    const deps = pipelineDeps({
      gate: vi.fn(async () => ({ shouldExtract: false, gateOutcome: 'rejected', auditSample: false }))
    })
    const result = await runScreenTaskPipeline(pipelineParams, deps)
    expect(deps.gate).toHaveBeenCalledWith(session(), {
      app_name: 'Slack',
      ocr_text: 'Sarah asked for the budget deck.',
      related_tasks: ['Send Sarah the Q4 budget spreadsheet'],
      user_context: 'Profile'
    }, undefined)
    expect(deps.extract).not.toHaveBeenCalled()
    expect(result).toMatchObject({ results: [], gateOutcome: 'rejected', auditSample: false })
  })

  it('fails open from an unavailable JEV gate into exactly one Luna request', async () => {
    const deps = pipelineDeps({ gate: vi.fn(async () => { throw new TypeError('offline') }) })
    const result = await runScreenTaskPipeline(pipelineParams, deps)
    expect(deps.extract).toHaveBeenCalledTimes(1)
    expect(deps.extract.mock.calls[0][1]).toMatchObject({
      gateOutcome: 'fail_open', auditSample: false, clientBypass: true
    })
    expect(deps.fallback).toHaveBeenCalledWith('gate_unavailable')
    expect(result.gateOutcome).toBe('fail_open')
  })

  it('keeps typed authorization, quota and stop denials terminal', async () => {
    const deps = pipelineDeps({ gate: vi.fn(async () => { throw new ScreenTaskGateDeniedError(429) }) })
    await expect(runScreenTaskPipeline(pipelineParams, deps)).rejects.toBeInstanceOf(ScreenTaskGateDeniedError)
    expect(deps.extract).not.toHaveBeenCalled()
  })

  it('uses Luna when local OCR is unusable and marks the proxy request as a bypass', async () => {
    const deps = pipelineDeps({ ocr: vi.fn(async () => ({ ok: false as const })) })
    await runScreenTaskPipeline(pipelineParams, deps)
    expect(deps.gate).not.toHaveBeenCalled()
    expect(deps.extract.mock.calls[0][1]).toMatchObject({ gateOutcome: 'fail_open', clientBypass: true })
    expect(deps.fallback).toHaveBeenCalledWith('ocr_unusable')
  })

  it('does not continue when the session or screen-work authorization changes', async () => {
    const deps = pipelineDeps({
      ocr: vi.fn(async () => {
        h.epoch++
        return { ok: true as const, fullText: 'screen text' }
      })
    })
    await expect(runScreenTaskPipeline(pipelineParams, deps)).rejects.toMatchObject({ name: 'AbortError' })
    expect(deps.gate).not.toHaveBeenCalled()
    expect(deps.extract).not.toHaveBeenCalled()
  })
})

describe('screen-task gateway requests', () => {
  it('extracts one structured response through the Luna alias and suppresses related tasks', async () => {
    h.fetch.mockResolvedValueOnce(modelResponse([
      taskJson('duplicate', '5'),
      taskJson('new', '', 'inferred_next_step'),
      taskJson()
    ]))
    const results = await requestLunaExtraction(session(), {
      app: 'Slack', today: '2026-10-07', profile: 'Profile', related: [activeTask], imageBase64: 'image',
      gateOutcome: 'passed', auditSample: false, clientBypass: false
    })
    expect(h.fetch).toHaveBeenCalledTimes(1)
    const [url, init] = h.fetch.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('https://desktop.test/v1/proxy/gemini/models/gpt-6-luna:generateContent')
    expect(init.headers).toMatchObject({
      Authorization: 'Bearer token',
      'X-Omi-Lane': 'task_extraction',
      'X-Omi-Workload': 'extraction',
      'X-Omi-Screen-Task-Gate': 'passed',
      'X-Omi-Screen-Task-Audit': 'false',
      'X-Omi-Screen-Task-Client-Bypass': 'false'
    })
    const body = JSON.parse(init.body as string)
    expect(body.generationConfig.maxOutputTokens).toBe(2048)
    expect(body.generationConfig.thinkingConfig).toBeUndefined()
    expect(body.contents[0].parts[1].inlineData.mimeType).toBe('image/jpeg')
    expect(results).toHaveLength(1)
    expect(results[0]).toMatchObject({ title: 'Send Sarah the Q4 budget spreadsheet today', sourceApp: 'Slack' })
  })

  it('keeps non-retryable stop/quota gate responses terminal', async () => {
    h.fetch.mockResolvedValueOnce(new Response(JSON.stringify({ detail: { error: 'screen_task_stopped' } }), {
      status: 409, headers: { 'X-Omi-Retryable': 'false' }
    }))
    await expect(requestGate(session(), {
      app_name: 'Slack', ocr_text: 'request', related_tasks: [], user_context: ''
    })).rejects.toBeInstanceOf(ScreenTaskGateDeniedError)
  })
})
