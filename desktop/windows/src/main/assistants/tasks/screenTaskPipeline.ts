// Bounded screen-task path: local OCR → JEV admission → one reserved-capacity extraction.
// The extraction uses the Gemini-compatible desktop gateway envelope, while
// requesting the screen extractor alias. The BFF selects reserved Gemini or Luna.
import { net } from 'electron'
import { getLatestProfileText } from '../aiUserProfile/service'
import { helperProcess } from '../../ocr/helperProcess'
import { recordFallback } from '../../observability/fallback'
import { GeminiLane } from '../../../shared/geminiAttribution'
import { geminiClientPlatform, geminiProxyFetch } from '../../../shared/geminiProxy'
import type { BackendSession } from '../core/session'
import { getAbortSignal, getSessionEpoch } from '../core/session'
import type { TaskSearchResult } from './toolBackends'
import { executeKeywordSearch } from './toolBackends'
import { parseStructuredTask, type ExtractedTask } from './models'

export const TASK_MODEL = 'gemini-3.8-flash'

const GATE_TIMEOUT_MS = 4_000
const EXTRACTION_TIMEOUT_MS = 60_000
const GATE_MAX_OCR_CHARS = 12_000
const EXTRACTION_OCR_CHARS = 3_000
const RELATED_TASKS_LIMIT = 8
const RELATED_TASKS_FOR_GATE = 4
const MAX_TASKS = 8
const MAX_OUTPUT_TOKENS = 2_048

export type ScreenTaskGateResult = {
  shouldExtract: boolean
  gateOutcome: 'passed' | 'rejected' | 'fail_open'
  auditSample: boolean
}

export type ScreenTaskPipelineResult = {
  results: ExtractedTask[]
  gateOutcome: ScreenTaskGateResult['gateOutcome']
  auditSample: boolean
}

type GateRequest = {
  app_name: string
  ocr_text: string
  related_tasks: string[]
  user_context: string
}

type PipelineParams = {
  session: BackendSession
  sessionEpoch: number
  app: string
  today: string
  imageBase64: string
  validateWork: () => void
}

type ScreenTaskPipelineDeps = {
  ocr: (jpeg: Buffer) => Promise<{ ok: true; fullText: string } | { ok: false }>
  profile: () => string | null
  search: (query: string) => Promise<TaskSearchResult[]>
  gate: (session: BackendSession, body: GateRequest, signal?: AbortSignal) => Promise<ScreenTaskGateResult>
  extract: (
    session: BackendSession,
    params: {
      app: string
      today: string
      profile: string
      related: TaskSearchResult[]
      imageBase64: string
      gateOutcome: ScreenTaskGateResult['gateOutcome']
      auditSample: boolean
      clientBypass: boolean
    },
    signal?: AbortSignal
  ) => Promise<ExtractedTask[]>
  fallback: (reason: string) => void
}

export class ScreenTaskGateDeniedError extends Error {
  constructor(readonly status: number) {
    super(`screen task gate denied (${status})`)
    this.name = 'ScreenTaskGateDeniedError'
  }
}

class ScreenTaskGateInvalidResponseError extends Error {
  constructor() {
    super('screen task gate returned an invalid response')
    this.name = 'ScreenTaskGateInvalidResponseError'
  }
}

class ScreenTaskGatewayHttpError extends Error {
  constructor(readonly status: number) {
    super(`screen task extraction HTTP ${status}`)
    this.name = 'ScreenTaskGatewayHttpError'
  }
}

const SYSTEM_PROMPT = `You find tasks for the user from what is on their screen. Return JSON only.

A task exists only when another person asked the user to do something and the user agreed or committed; another person directly asked the user to act or answer and they have not done or declined it; or the user wrote an explicit reminder for themselves.

Skip conversation sidebars, inboxes, lists, overviews, public/group requests not directed to the user, things someone else will do, requests already fulfilled or declined, automated messages, newsletters, articles, code, terminals, dashboards, project boards, calendars, media, small talk, jokes, and hypotheticals. In chat, right-side or colored messages are from the user and left-side messages are from others. A frame may contain several distinct tasks; return each separately.

Existing tasks are supplied with the screen context. For a new task, set relation=new and related_id to an empty string. If it is an unchanged duplicate, set relation=duplicate and its active task ID. For a meaningful change to an active task, set relation=refines and its active task ID. If the screen proves an active task is done, set relation=completes, its active task ID, and capture_kind=already_done. Never invent IDs. Staged tasks count as duplicates and have no relation ID. The application will only stage genuinely new tasks.

Use a verb-first English title of 6–15 words naming a person, project, or concrete deliverable. Set deadline to yyyy-MM-dd only when stated or clearly implied, resolved from today's date, never in the past; otherwise use an empty string. Return at most eight tasks. Keep description under 64 characters, evidence empty, and both summaries under 96 characters. Report owner, concrete_deliverable, public_broadcast, direct_mention, ownership_confidence, tags, source_category, and source_subcategory from visible evidence. Do not infer facts hidden by the screenshot.`

const RESPONSE_SCHEMA = {
  type: 'OBJECT',
  properties: {
    screen_kind: { type: 'STRING', enum: ['open_conversation', 'open_email_or_document', 'list_or_overview', 'other'] },
    tasks: {
      type: 'ARRAY',
      maxItems: MAX_TASKS,
      items: {
        type: 'OBJECT',
        properties: {
          title: { type: 'STRING', maxLength: 96 },
          description: { type: 'STRING', maxLength: 64 },
          deadline: { type: 'STRING', maxLength: 10 },
          priority: { type: 'STRING', enum: ['high', 'medium', 'low'] },
          confidence: { type: 'NUMBER' },
          relation: { type: 'STRING', enum: ['new', 'duplicate', 'refines', 'completes'] },
          related_id: { type: 'STRING', maxLength: 128 },
          evidence: { type: 'STRING', maxLength: 0 },
          capture_kind: {
            type: 'STRING',
            enum: ['explicit_command', 'clear_commitment', 'direct_request', 'inferred_next_step', 'already_done']
          },
          owner: { type: 'STRING', enum: ['user', 'other', 'unknown'] },
          concrete_deliverable: { type: 'BOOLEAN' },
          public_broadcast: { type: 'BOOLEAN' },
          direct_mention: { type: 'BOOLEAN' },
          ownership_confidence: { type: 'NUMBER' },
          tags: { type: 'ARRAY', maxItems: 3, items: { type: 'STRING', maxLength: 16 } },
          source_category: {
            type: 'STRING',
            enum: ['direct_request', 'self_generated', 'calendar_driven', 'reactive', 'external_system', 'other']
          },
          source_subcategory: {
            type: 'STRING',
            enum: [
              'message', 'meeting', 'mention', 'commitment', 'idea', 'reminder', 'goal_subtask', 'event_prep',
              'recurring', 'deadline', 'error', 'notification', 'observation', 'project_tool', 'alert',
              'documentation', 'other'
            ]
          }
        },
        required: [
          'title', 'description', 'deadline', 'priority', 'confidence', 'relation', 'related_id', 'evidence',
          'capture_kind', 'owner', 'concrete_deliverable', 'public_broadcast', 'direct_mention',
          'ownership_confidence', 'tags', 'source_category', 'source_subcategory'
        ]
      }
    },
    context_summary: { type: 'STRING', maxLength: 96 },
    current_activity: { type: 'STRING', maxLength: 96 }
  },
  required: ['screen_kind', 'tasks', 'context_summary', 'current_activity']
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function withTimeout<T>(
  ms: number,
  fn: (signal: AbortSignal) => Promise<T>,
  external?: AbortSignal
): Promise<T> {
  const controller = new AbortController()
  let timedOut = false
  const onAbort = (): void => controller.abort(external?.reason)
  const timer = setTimeout(() => {
    timedOut = true
    controller.abort(new DOMException('request timed out', 'TimeoutError'))
  }, ms)
  if (external?.aborted) controller.abort(external.reason)
  else external?.addEventListener('abort', onAbort, { once: true })
  return fn(controller.signal).catch((error: unknown) => {
    if (timedOut) throw new DOMException('request timed out', 'TimeoutError')
    throw error
  }).finally(() => {
    clearTimeout(timer)
    external?.removeEventListener('abort', onAbort)
  })
}

function parseGate(value: unknown): ScreenTaskGateResult {
  if (!isRecord(value)) throw new ScreenTaskGateInvalidResponseError()
  const gateOutcome = value.gate_outcome
  const shouldExtract = value.should_extract
  const auditSample = value.audit_sample
  if (
    !['passed', 'rejected', 'fail_open'].includes(String(gateOutcome)) ||
    typeof shouldExtract !== 'boolean' || typeof auditSample !== 'boolean' ||
    shouldExtract !== (gateOutcome !== 'rejected' || auditSample) ||
    (auditSample && gateOutcome !== 'rejected')
  ) throw new ScreenTaskGateInvalidResponseError()
  return { gateOutcome: gateOutcome as ScreenTaskGateResult['gateOutcome'], shouldExtract, auditSample }
}

async function requestGate(
  session: BackendSession,
  body: GateRequest,
  signal?: AbortSignal
): Promise<ScreenTaskGateResult> {
  return withTimeout(GATE_TIMEOUT_MS, async (requestSignal) => {
    const response = await net.fetch(`${session.apiBase}/v1/screen-task/gate`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${session.token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: requestSignal
    })
    if (!response.ok) {
      const retryable = response.headers.get('x-omi-retryable')
      if (retryable === 'false' || (response.status >= 400 && response.status < 500)) {
        throw new ScreenTaskGateDeniedError(response.status)
      }
      throw new ScreenTaskGatewayHttpError(response.status)
    }
    return parseGate(await response.json())
  }, signal)
}

export { requestGate, requestScreenExtraction }

function taskTokens(text: string): Set<string> {
  return new Set(text.toLowerCase().split(/[^\p{L}\p{N}]+/u).filter((token) => token.length >= 3))
}

function selectRelatedTasks(results: TaskSearchResult[], query: string): TaskSearchResult[] {
  const queryTerms = taskTokens(query)
  const ranked = results.map((row, index) => ({
    row,
    index,
    score: [...taskTokens(row.description)].filter((token) => queryTerms.has(token)).length
  })).sort((a, b) => b.score - a.score || a.index - b.index)
  const seen = new Set<string>()
  return ranked.filter(({ row }) => {
    const key = `${row.source ?? 'unknown'}:${row.status}:${row.id}:${row.description}`
    return seen.has(key) ? false : (seen.add(key), true)
  }).slice(0, RELATED_TASKS_LIMIT).map(({ row }) => row)
}

function relatedTaskPrompt(task: TaskSearchResult): string {
  const status = task.source === 'staged_task' ? 'staged' : task.status
  const id = task.source === 'action_item' && status === 'active' ? ` id:${task.id}` : ''
  return `- [${status}${id}] ${task.description.slice(0, 512)}`
}

function isIsoDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false
  const parsed = new Date(`${value}T00:00:00.000Z`)
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value
}

function asTaskList(
  value: unknown,
  app: string,
  today: string,
  related: TaskSearchResult[]
): ExtractedTask[] {
  if (!isRecord(value) || !Array.isArray(value.tasks) || value.tasks.length > MAX_TASKS) {
    throw new Error('invalid screen task extraction')
  }
  if (
    !['open_conversation', 'open_email_or_document', 'list_or_overview', 'other'].includes(String(value.screen_kind)) ||
    typeof value.context_summary !== 'string' || value.context_summary.length > 96 ||
    typeof value.current_activity !== 'string' || value.current_activity.length > 96
  ) throw new Error('invalid screen task extraction')

  const allowedActiveIds = new Set(
    related.filter((row) => row.source === 'action_item' && row.status === 'active').map((row) => String(row.id))
  )
  const output: ExtractedTask[] = []
  for (const raw of value.tasks) {
    if (!isRecord(raw)) continue
    const relation = raw.relation
    const relatedId = typeof raw.related_id === 'string' ? raw.related_id : ''
    if (!['new', 'duplicate', 'refines', 'completes'].includes(String(relation))) continue
    if (relation === 'new') {
      if (relatedId !== '') continue
    } else if (!allowedActiveIds.has(relatedId)) {
      continue
    }
    // Windows' existing staged-task sink has no relation mutation API. Suppress
    // existing duplicates and updates instead of creating a second staged row.
    if (relation !== 'new') continue
    if (
      typeof raw.title !== 'string' || raw.title.length > 96 ||
      typeof raw.description !== 'string' || raw.description.length > 64 ||
      typeof raw.deadline !== 'string' || raw.deadline.length > 10 ||
      !['high', 'medium', 'low'].includes(String(raw.priority)) ||
      typeof raw.confidence !== 'number' || !Number.isFinite(raw.confidence) || raw.confidence < 0 || raw.confidence > 1 ||
      raw.evidence !== '' || !Array.isArray(raw.tags) || raw.tags.length > 3 ||
      !raw.tags.every((tag) => typeof tag === 'string' && tag.length <= 16) ||
      typeof raw.ownership_confidence !== 'number' || !Number.isFinite(raw.ownership_confidence) ||
      raw.ownership_confidence < 0 || raw.ownership_confidence > 1 ||
      typeof raw.concrete_deliverable !== 'boolean' || typeof raw.public_broadcast !== 'boolean' ||
      typeof raw.direct_mention !== 'boolean' ||
      !['explicit_command', 'clear_commitment', 'direct_request', 'inferred_next_step', 'already_done'].includes(String(raw.capture_kind)) ||
      !['user', 'other', 'unknown'].includes(String(raw.owner)) ||
      !['direct_request', 'self_generated', 'calendar_driven', 'reactive', 'external_system', 'other'].includes(String(raw.source_category)) ||
      !['message', 'meeting', 'mention', 'commitment', 'idea', 'reminder', 'goal_subtask', 'event_prep', 'recurring', 'deadline', 'error', 'notification', 'observation', 'project_tool', 'alert', 'documentation', 'other'].includes(String(raw.source_subcategory))
    ) continue
    if (
      raw.owner !== 'user' || raw.concrete_deliverable !== true ||
      (raw.public_broadcast === true && raw.direct_mention !== true) ||
      raw.capture_kind === 'already_done' || raw.capture_kind === 'inferred_next_step'
    ) continue

    const deadline = raw.deadline
    const validDeadline = deadline === '' || (isIsoDate(deadline) && deadline >= today)
    const task = parseStructuredTask({
      title: raw.title,
      description: raw.description,
      priority: raw.priority,
      source_app: app,
      inferred_deadline: validDeadline ? deadline : '',
      confidence: raw.confidence,
      tags: raw.tags,
      source_category: raw.source_category,
      source_subcategory: raw.source_subcategory,
      capture_kind: raw.capture_kind,
      owner: raw.owner,
      concrete_deliverable: raw.concrete_deliverable,
      public_broadcast: raw.public_broadcast,
      direct_mention: raw.direct_mention,
      ownership_confidence: raw.ownership_confidence,
      context_summary: value.context_summary,
      current_activity: value.current_activity
    })
    if (task) output.push(task)
  }
  return output
}

function extractCandidateText(value: unknown): string {
  if (!isRecord(value) || !Array.isArray(value.candidates) || !isRecord(value.candidates[0])) {
    throw new Error('invalid screen task gateway response')
  }
  const candidate = value.candidates[0]
  const finishReason = candidate.finishReason
  if (finishReason !== undefined && !['STOP', 'MAX_TOKENS'].includes(String(finishReason))) {
    throw new Error('screen task extraction did not finish')
  }
  if (!isRecord(candidate.content) || !Array.isArray(candidate.content.parts)) {
    throw new Error('invalid screen task gateway response')
  }
  const text = candidate.content.parts
    .filter((part): part is Record<string, unknown> => isRecord(part))
    .map((part) => typeof part.text === 'string' ? part.text : '')
    .join('')
  if (!text) throw new Error('empty screen task extraction')
  return text
}

async function requestScreenExtraction(
  session: BackendSession,
  params: {
    app: string
    today: string
    profile: string
    related: TaskSearchResult[]
    imageBase64: string
    gateOutcome: ScreenTaskGateResult['gateOutcome']
    auditSample: boolean
    clientBypass: boolean
  },
  signal?: AbortSignal
): Promise<ExtractedTask[]> {
  const related = params.related.map(relatedTaskPrompt).join('\n')
  const prompt = [
    `App: ${params.app}. Today: ${params.today}.`,
    `User profile: ${params.profile.slice(0, 1024)}`,
    `EXISTING TASKS:\n${related || '(none)'}`
  ].join('\n')
  const body = {
    contents: [{ role: 'user', parts: [{ text: prompt }, { inlineData: { mimeType: 'image/jpeg', data: params.imageBase64 } }] }],
    systemInstruction: { parts: [{ text: SYSTEM_PROMPT }] },
    generationConfig: {
      responseMimeType: 'application/json',
      responseSchema: RESPONSE_SCHEMA,
      maxOutputTokens: MAX_OUTPUT_TOKENS
    }
  }
  return withTimeout(EXTRACTION_TIMEOUT_MS, async (requestSignal) => {
    const response = await geminiProxyFetch(net.fetch, {
      baseURL: session.desktopApiBase,
      model: TASK_MODEL,
      action: 'generateContent',
      token: session.token,
      lane: GeminiLane.taskExtraction,
      workload: 'extraction',
      platform: geminiClientPlatform(process.platform),
      extraHeaders: {
        'X-Omi-Screen-Task-Gate': params.gateOutcome,
        'X-Omi-Screen-Task-Audit': params.auditSample ? 'true' : 'false',
        'X-Omi-Screen-Task-Client-Bypass': params.clientBypass ? 'true' : 'false'
      },
      signal: requestSignal,
      body: JSON.stringify(body)
    })
    if (!response.ok) throw new ScreenTaskGatewayHttpError(response.status)
    const text = extractCandidateText(await response.json())
    return asTaskList(JSON.parse(text), params.app, params.today, params.related)
  }, signal)
}

const defaultDeps: ScreenTaskPipelineDeps = {
  ocr: async (jpeg) => {
    const result = await helperProcess.ocr(jpeg)
    return result.ok ? { ok: true, fullText: result.fullText } : { ok: false }
  },
  profile: () => getLatestProfileText(),
  search: executeKeywordSearch,
  gate: requestGate,
  extract: requestScreenExtraction,
  fallback: (reason) => recordFallback({
    component: 'other', from: 'jev_gate', to: 'screen_extraction', reason, outcome: 'degraded'
  })
}

/** Run one local OCR pass, one JEV gate, and at most one reserved-capacity extraction request. */
export async function runScreenTaskPipeline(
  params: PipelineParams,
  deps: Partial<ScreenTaskPipelineDeps> = {}
): Promise<ScreenTaskPipelineResult> {
  const d = { ...defaultDeps, ...deps }
  const signal = getAbortSignal()
  const validateSession = (): void => {
    if (signal?.aborted || getSessionEpoch() !== params.sessionEpoch) {
      throw new DOMException('session changed during screen task extraction', 'AbortError')
    }
  }
  const validateWork = (): void => {
    validateSession()
    params.validateWork()
  }
  validateWork()

  let gateOutcome: ScreenTaskGateResult['gateOutcome'] = 'fail_open'
  let auditSample = false
  let clientBypass = false
  let ocr: Awaited<ReturnType<ScreenTaskPipelineDeps['ocr']>>
  try {
    ocr = await d.ocr(Buffer.from(params.imageBase64, 'base64'))
  } catch {
    validateWork()
    ocr = { ok: false }
  }
  validateWork()
  const usableOcr = ocr.ok && ocr.fullText.trim().length > 0 && ocr.fullText.length <= GATE_MAX_OCR_CHARS
  const ocrText = ocr.ok ? ocr.fullText.slice(0, GATE_MAX_OCR_CHARS) : ''
  const searchResults = await d.search(ocrText.slice(0, EXTRACTION_OCR_CHARS))
  validateWork()
  const related = selectRelatedTasks(searchResults, ocrText)
  const profile = d.profile() ?? ''

  let shouldExtract = true
  if (usableOcr) {
    try {
      const gate = await d.gate(params.session, {
        app_name: params.app.slice(0, 128),
        ocr_text: ocrText,
        related_tasks: related.slice(0, RELATED_TASKS_FOR_GATE).map((task) => task.description.slice(0, 576)),
        user_context: profile.slice(0, 1024)
      }, signal)
      validateWork()
      gateOutcome = gate.gateOutcome
      auditSample = gate.auditSample
      shouldExtract = gate.shouldExtract
      if (gateOutcome === 'fail_open') d.fallback('gate_fail_open')
    } catch (error) {
      validateWork()
      if (error instanceof ScreenTaskGateDeniedError) throw error
      if (error instanceof ScreenTaskGatewayHttpError && error.status >= 400 && error.status < 500) {
        throw new ScreenTaskGateDeniedError(error.status)
      }
      if (error instanceof ScreenTaskGatewayHttpError && error.status >= 500) {
        // The backend's typed terminal responses can carry an X-Omi-Retryable
        // header; requestGate already turns those into ScreenTaskGateDeniedError.
        d.fallback('gate_provider_unavailable')
      } else {
        d.fallback(error instanceof ScreenTaskGateInvalidResponseError ? 'gate_invalid_response' : 'gate_unavailable')
      }
      clientBypass = true
      gateOutcome = 'fail_open'
      auditSample = false
      shouldExtract = true
    }
  } else {
    clientBypass = true
    d.fallback('ocr_unusable')
  }

  if (!shouldExtract) return { results: [], gateOutcome, auditSample }
  validateWork()
  const results = await d.extract(params.session, {
    app: params.app,
    today: params.today,
    profile,
    related,
    imageBase64: params.imageBase64,
    gateOutcome,
    auditSample,
    clientBypass
  }, signal)
  validateWork()
  return { results, gateOutcome, auditSample }
}
