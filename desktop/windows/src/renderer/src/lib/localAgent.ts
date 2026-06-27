import { desktopApi } from './apiClient'
import { trackEvent } from './analytics'
import {
  LOCAL_DB_SCHEMA,
  formatContextBlock,
  parseAction,
  raceWithBudget,
  type ContextSection
} from './localAgentProtocol'
import { orderFloorSections, relationshipItems, type KindedSection } from './floorContext'
import type {
  LocalAgentChatToolName,
  LocalAgentChatToolResponse,
  LocalAgentToolArguments
} from '../../../shared/types'

const AGENT_MODEL = 'claude-haiku-4-5-20251001'
const MAX_ITERS = 3 // bounded: each iter is a non-streaming LLM call plus one local tool call
const AGENT_CALL_TIMEOUT_MS = 2_500
// Hard cap on how long chat waits for question-specific enrichment. Deterministic
// local tools still run first and are fast; the model-driven loop is best-effort.
const ENRICH_BUDGET_MS = 4_000
const MAX_SQL_ROWS = 30
const MAX_CELL_CHARS = 360
const MAX_SCREEN_RESULTS = 5
const MAX_STATUS_ITEMS = 5

type MsgRole = 'system' | 'user' | 'assistant'
type ChatCompletion = { choices?: { message?: { content?: string } }[] }
type JsonRecord = Record<string, unknown>

const SYSTEM_PROMPT = [
  'You gather local context to help answer a question about the user’s Windows Omi app.',
  'Each turn, output ONLY a single raw JSON object — no prose, no markdown fences,',
  'no <function_calls> tag, NOT in an array. One of:',
  '  {"action":"get_local_status","input":{}}',
  '  {"action":"search_screen_history","input":{"query":"<keywords>","days":7,"limit":5}}',
  '  {"action":"execute_sql","input":{"query":"<single read-only SELECT/WITH>"}}',
  '  {"action":"get_screenshot","input":{"screenshot_id":123}}',
  '  {"action":"final"}',
  '',
  'Only those four local tools exist in chat. Destructive/update tools are unavailable.',
  'For "what was I looking at earlier" or similarly vague screen-history questions,',
  'use execute_sql over rewind_frames ordered by ts DESC. For keyword screen-history',
  'questions, use search_screen_history. If a screenshot_id matters, call get_screenshot;',
  'only metadata/OCR preview will be used as text context. For count questions, use',
  'COUNT(*) SQL. Prefer substr(...) previews over selecting full OCR/transcripts.',
  '',
  LOCAL_DB_SCHEMA,
  '',
  'Do not answer the question yourself. Gather concise context, then emit final.'
].join('\n')

const clip = (s: string, max = MAX_CELL_CHARS): string =>
  s.length > max ? `${s.slice(0, max).trimEnd()}...` : s

function isRecord(value: unknown): value is JsonRecord {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}

function stringValue(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

function numberValue(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function recordArray(value: unknown): JsonRecord[] {
  return Array.isArray(value) ? value.filter(isRecord) : []
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : []
}

function firstNumber(...values: unknown[]): number | null {
  for (const value of values) {
    const parsed =
      typeof value === 'number'
        ? value
        : typeof value === 'string' && value.trim()
          ? Number(value.trim())
          : NaN
    if (Number.isSafeInteger(parsed) && parsed > 0) return parsed
  }
  return null
}

function telemetryForResult(response: LocalAgentChatToolResponse): Record<string, unknown> {
  const result = isRecord(response.result) ? response.result : {}
  const metrics: Record<string, unknown> = {
    content_type: response.content_type
  }
  for (const key of ['row_count', 'result_count', 'screenshot_count', 'indexed_screenshot_count']) {
    const value = numberValue(result[key])
    if (value != null) metrics[key] = value
  }
  if (response.name === 'get_screenshot') metrics.has_screenshot = true
  return metrics
}

function trackLocalToolUse(
  tool: LocalAgentChatToolName,
  ok: boolean,
  durationMs: number,
  extra: Record<string, unknown> = {}
): void {
  trackEvent('Windows Chat Local Tool Used', {
    tool,
    ok,
    duration_ms: Math.round(durationMs),
    ...extra
  })
}

async function invokeChatTool(
  tool: LocalAgentChatToolName,
  args: LocalAgentToolArguments = {}
): Promise<LocalAgentChatToolResponse> {
  const start = performance.now()
  try {
    const response = await window.omi.localAgentChatTool(tool, args)
    trackLocalToolUse(tool, true, performance.now() - start, telemetryForResult(response))
    return response
  } catch (error) {
    trackLocalToolUse(tool, false, performance.now() - start, {
      error_type: error instanceof Error ? error.name : typeof error
    })
    throw error
  }
}

// Render SQL rows into compact "col | col" lines with a header.
function formatRows(columns: string[], rows: JsonRecord[]): string[] {
  if (rows.length === 0) return []
  const header = columns.join(' | ')
  const lines = rows
    .slice(0, MAX_SQL_ROWS)
    .map((r) => columns.map((c) => clip(String(r[c] ?? ''))).join(' | '))
  if (rows.length > MAX_SQL_ROWS) lines.push(`... (${rows.length - MAX_SQL_ROWS} more rows)`)
  return [header, ...lines]
}

function formatStatus(response: LocalAgentChatToolResponse): ContextSection | null {
  if (!isRecord(response.result)) return null
  const result = response.result
  const kg = isRecord(result.knowledge_graph) ? result.knowledge_graph : {}
  const fileIndex = isRecord(result.file_index) ? result.file_index : {}
  const items = [
    `Rewind screen history: ${numberValue(result.screenshot_count) ?? 0} screenshot(s), ${
      numberValue(result.indexed_screenshot_count) ?? 0
    } indexed, latest capture ${stringValue(result.latest_capture_at) ?? 'none'}.`,
    `Local knowledge graph: ${numberValue(kg.nodeCount) ?? 0} node(s), ${
      numberValue(kg.edgeCount) ?? 0
    } edge(s).`,
    `File index: ${numberValue(fileIndex.filesIndexed) ?? 0} indexed file(s).`
  ]
  const unavailable = recordArray(result.unavailable_affordances)
    .map((item) => stringValue(item.tool))
    .filter((tool): tool is string => tool != null)
  if (unavailable.length) items.push(`Unavailable local tools: ${unavailable.join(', ')}.`)
  return { heading: 'Local Omi status', items: items.slice(0, MAX_STATUS_ITEMS) }
}

function formatScreenGroup(group: JsonRecord): string {
  const representative = isRecord(group.representative) ? group.representative : {}
  const screenshots = recordArray(group.screenshots)
  const ids = [
    firstNumber(representative.screenshot_id),
    ...screenshots.map((frame) => firstNumber(frame.screenshot_id))
  ].filter((id): id is number => id != null)
  const uniqueIds = [...new Set(ids)].slice(0, 5)
  const app = stringValue(group.app) ?? stringValue(representative.app) ?? 'Unknown app'
  const title =
    stringValue(group.window_title) ?? stringValue(representative.window_title) ?? 'Untitled window'
  const time = stringValue(group.start_at) ?? stringValue(representative.timestamp)
  const snippet =
    stringValue(group.match_snippet) ?? stringValue(representative.ocr_preview) ?? 'No OCR preview.'
  const idText = uniqueIds.length ? ` screenshot_id=${uniqueIds.join(',')}` : ''
  return `${time ? `${time} ` : ''}${app} - ${title}${idText}: ${clip(snippet, 280)}`
}

function formatScreenSearch(response: LocalAgentChatToolResponse): ContextSection | null {
  if (!isRecord(response.result)) return null
  const results = recordArray(response.result.results)
  if (results.length === 0) {
    return {
      heading: 'Screen history results',
      items: ['No Rewind OCR matches for that search.']
    }
  }
  return {
    heading: 'Screen history results',
    items: results.slice(0, MAX_SCREEN_RESULTS).map(formatScreenGroup)
  }
}

function formatSql(response: LocalAgentChatToolResponse): ContextSection | null {
  if (!isRecord(response.result)) return null
  const columns = stringArray(response.result.columns)
  const rows = recordArray(response.result.rows)
  const items = formatRows(columns, rows)
  if (items.length === 0) {
    const count = numberValue(response.result.row_count)
    return { heading: 'Local database result (read-only SQL)', items: [`${count ?? 0} rows.`] }
  }
  const truncated = response.result.truncated === true ? ['Result was truncated.'] : []
  return {
    heading: 'Local database result (read-only SQL)',
    items: [...items, ...truncated]
  }
}

function formatScreenshot(response: LocalAgentChatToolResponse): ContextSection | null {
  if (!isRecord(response.result)) return null
  const metadata = isRecord(response.result.metadata) ? response.result.metadata : {}
  const id = firstNumber(response.result.screenshot_id, metadata.screenshot_id)
  const app = stringValue(metadata.app) ?? 'Unknown app'
  const title = stringValue(metadata.window_title) ?? 'Untitled window'
  const timestamp = stringValue(metadata.timestamp) ?? 'unknown time'
  const bytes = numberValue(metadata.image_bytes)
  const mime = stringValue(metadata.image_mime_type) ?? stringValue(response.result.image_mime_type)
  const preview = stringValue(metadata.ocr_preview)
  const items = [
    `Screenshot ${id ?? 'unknown'}: ${timestamp}, ${app} - ${title}${
      mime ? `, ${mime}` : ''
    }${bytes != null ? `, ${bytes} bytes` : ''}.`
  ]
  if (preview) items.push(`OCR preview: ${clip(preview, 280)}`)
  return { heading: 'Screenshot metadata', items }
}

function contextSectionForTool(
  tool: LocalAgentChatToolName,
  response: LocalAgentChatToolResponse
): ContextSection | null {
  switch (tool) {
    case 'get_local_status':
      return formatStatus(response)
    case 'search_screen_history':
      return formatScreenSearch(response)
    case 'execute_sql':
      return formatSql(response)
    case 'get_screenshot':
      return formatScreenshot(response)
  }
}

async function appendToolSection(
  sections: ContextSection[],
  tool: LocalAgentChatToolName,
  args: LocalAgentToolArguments
): Promise<LocalAgentChatToolResponse | null> {
  try {
    const response = await invokeChatTool(tool, args)
    const section = contextSectionForTool(tool, response)
    if (section && section.items.length > 0) sections.push(section)
    return response
  } catch {
    return null
  }
}

function screenHistoryIntent(userText: string): boolean {
  return /\b(looking at|looked at|on (?:my|the) screen|screen history|rewind|screenshot|what.*(?:earlier|previously|before)|what was i.*doing|where was i)\b/i.test(
    userText
  )
}

function vagueRecentScreenIntent(userText: string): boolean {
  return /\b(earlier|previously|previous|before|recent|last|looking at|looked at|doing)\b/i.test(
    userText
  )
}

function countSqlForQuestion(userText: string): string | null {
  if (!/\b(how many|count|number of|total)\b/i.test(userText)) return null
  if (/\b(screenshot|screenshots|rewind|screen|frames?)\b/i.test(userText)) {
    return 'SELECT COUNT(*) AS screenshot_count FROM rewind_frames'
  }
  if (/\b(conversation|conversations|recording|recordings|chat|chats)\b/i.test(userText)) {
    return "SELECT COALESCE(kind, 'recording') AS kind, COUNT(*) AS count FROM local_conversation GROUP BY COALESCE(kind, 'recording') ORDER BY count DESC"
  }
  if (/\b(file|files|indexed|documents?|code)\b/i.test(userText)) {
    return 'SELECT file_type, COUNT(*) AS count FROM indexed_files GROUP BY file_type ORDER BY count DESC'
  }
  if (/\b(knowledge graph|kg|nodes?|entities|technologies|projects?)\b/i.test(userText)) {
    return 'SELECT node_type, COUNT(*) AS count FROM local_kg_nodes GROUP BY node_type ORDER BY count DESC'
  }
  return null
}

function recentRewindSql(): string {
  return [
    'SELECT id AS screenshot_id,',
    "datetime(ts / 1000, 'unixepoch') AS captured_at_utc,",
    'app, window_title, process_name, substr(ocr_text, 1, 500) AS ocr_preview',
    'FROM rewind_frames ORDER BY ts DESC LIMIT 8'
  ].join(' ')
}

function firstScreenshotId(response: LocalAgentChatToolResponse | null): number | null {
  if (!response || !isRecord(response.result)) return null
  const results = recordArray(response.result.results)
  for (const group of results) {
    const representative = isRecord(group.representative) ? group.representative : {}
    const repId = firstNumber(representative.screenshot_id)
    if (repId != null) return repId
    for (const frame of recordArray(group.screenshots)) {
      const id = firstNumber(frame.screenshot_id)
      if (id != null) return id
    }
  }
  return null
}

async function deterministicToolPass(userText: string): Promise<ContextSection[]> {
  const sections: ContextSection[] = []
  await appendToolSection(sections, 'get_local_status', {})

  if (screenHistoryIntent(userText)) {
    const search = await appendToolSection(sections, 'search_screen_history', {
      query: userText,
      days: 7,
      limit: 5
    })
    const screenshotId = firstScreenshotId(search)
    if (screenshotId != null) {
      await appendToolSection(sections, 'get_screenshot', { screenshot_id: screenshotId })
    }
    if (vagueRecentScreenIntent(userText)) {
      await appendToolSection(sections, 'execute_sql', { query: recentRewindSql() })
    }
  }

  const countSql = countSqlForQuestion(userText)
  if (countSql) await appendToolSection(sections, 'execute_sql', { query: countSql })

  return sections
}

// Snapshot fallback: partition recent nodes with technologies first, so even if
// the agent loop yields nothing the chat is grounded (and never blind to
// languages). Best-effort.
async function snapshotSections(): Promise<KindedSection[]> {
  const graph = await window.omi.kgQueryNodes('', 80)
  const nodes = graph.nodes
  const pick = (t: string): string[] => nodes.filter((n) => n.nodeType === t).map((n) => n.summary)
  const out: KindedSection[] = []
  const cards = nodes.filter((n) => n.nodeType === 'card').map((n) => n.summary)
  if (cards.length) out.push({ kind: 'overview', heading: 'Overview', items: cards })
  const tech = pick('technology')
  if (tech.length)
    out.push({ kind: 'tech', heading: 'Programming languages & technologies', items: tech })
  const ent = nodes
    .filter((n) => ['project', 'person', 'org', 'interest'].includes(n.nodeType))
    .map((n) => `${n.label} (${n.nodeType}): ${n.summary}`)
  if (ent.length)
    out.push({ kind: 'entities', heading: 'Projects, people & interests', items: ent })
  const rels = relationshipItems(nodes, graph.edges)
  if (rels.length) out.push({ kind: 'relationships', heading: 'How they relate', items: rels })
  const folders = pick('file_group')
  if (folders.length)
    out.push({ kind: 'folders', heading: 'Recently active working folders', items: folders })
  const apps = pick('app')
  if (apps.length) out.push({ kind: 'apps', heading: 'Installed apps', items: apps })
  return out
}

function observationFor(section: ContextSection | null): string {
  if (!section || section.items.length === 0) return 'No usable local result.'
  return `${section.heading}:\n${section.items.map((item) => `- ${item}`).join('\n')}`
}

// The bounded agent loop: the model drives the read-only local tool allowlist and
// we accumulate the rendered results as context sections. Network-bound and
// best-effort; callers race it against ENRICH_BUDGET_MS.
async function runAgentLoop(
  userText: string,
  sections: ContextSection[]
): Promise<ContextSection[]> {
  const messages: { role: MsgRole; content: string }[] = [
    { role: 'system', content: SYSTEM_PROMPT },
    {
      role: 'user',
      content:
        `User question: ${userText}\n\n` +
        'Deterministic local status and obvious screen/count context may already be collected. ' +
        'Use one additional local tool only if more context is needed.'
    }
  ]

  for (let i = 0; i < MAX_ITERS; i++) {
    const res = await desktopApi.post(
      '/v2/chat/completions',
      { model: AGENT_MODEL, stream: false, messages },
      { timeout: AGENT_CALL_TIMEOUT_MS }
    )
    const content = (res.data as ChatCompletion)?.choices?.[0]?.message?.content ?? ''
    const action = parseAction(content)
    if (!action || action.action === 'final') break
    messages.push({ role: 'assistant', content })

    let observation = 'Tool failed.'
    try {
      const response = await invokeChatTool(action.action, action.input)
      const section = contextSectionForTool(action.action, response)
      if (section && section.items.length > 0) sections.push(section)
      observation = observationFor(section)
    } catch {
      observation = 'Tool failed or was rejected.'
    }
    messages.push({ role: 'user', content: `Observation:\n${observation}` })
  }
  return sections
}

// Chat pre-step: instant deterministic floor + local read-only tools + raced
// agent enrichment. Best-effort — any failure returns '' or partial context so
// the existing /v2/messages chat transport still sends.
export async function gatherLocalContext(userText: string): Promise<string> {
  try {
    const floorP = snapshotSections().catch(() => [] as KindedSection[])
    const deterministicP = deterministicToolPass(userText).catch(() => [] as ContextSection[])
    const agentSections: ContextSection[] = []
    await raceWithBudget<ContextSection[]>(
      runAgentLoop(userText, agentSections),
      ENRICH_BUDGET_MS,
      agentSections
    )

    const [floor, deterministic] = await Promise.all([floorP, deterministicP])
    const overview = floor
      .filter((s) => s.kind === 'overview')
      .map(({ heading, items }) => ({ heading, items }))
    const rest = floor.filter((s) => s.kind !== 'overview')
    return formatContextBlock([
      ...overview,
      ...deterministic,
      ...orderFloorSections(rest, userText),
      ...agentSections
    ])
  } catch {
    return ''
  }
}
