import {
  execSafeSelect,
  getFileIndexStats,
  getLocalKGStatus,
  getRewindFrame,
  listLocalConversations,
  listRewindFrames,
  recentInsights,
  rewindStatusStats,
  searchLocalTasks,
  searchRewindFrames
} from '../ipc/db'
import { readRewindFrameImage } from '../rewind/frameImage'
import { rewindRoot } from '../rewind/paths'
import { groupFrames } from '../rewind/rewindGrouping'
import { guardSelect } from '../../shared/sqlGuard'
import type {
  InsightRecord,
  LocalConversation,
  RewindFrame,
  RewindFrameImageOk,
  RewindSearchGroup
} from '../../shared/types'

const MAX_SQL_ROWS = 200
const MAX_SEARCH_LIMIT = 50
const DEFAULT_SCREEN_LIMIT = 15
const DAY_MS = 86_400_000
const TASK_MUTATION_UNAVAILABLE =
  'Windows local task mutation is unavailable because tasks are currently backed by the hosted action-items API, not reliable main-process local storage.'

type JsonObject = Record<string, unknown>

type JsonSchemaObject = {
  type: 'object'
  properties: Record<string, unknown>
  required?: string[]
  additionalProperties?: boolean
}

export type LocalAgentRuntimeContext = {
  localUrl: string
  toolEndpoint: string
  app: {
    name: string
    version: string
    appId: string
  }
}

export type LocalAgentToolDefinition = {
  name: string
  description: string
  inputSchema: JsonSchemaObject
  annotations: Record<string, unknown>
}

export type LocalAgentToolResponse = {
  ok: true
  name: string
  content_type: string
  result: unknown
}

export class LocalAgentToolError extends Error {
  readonly code: string
  readonly status: number
  readonly details?: unknown

  constructor(code: string, message: string, status = 400, details?: unknown) {
    super(message)
    this.name = 'LocalAgentToolError'
    this.code = code
    this.status = status
    this.details = details
  }
}

function schema(
  properties: Record<string, unknown>,
  required: string[] = [],
  additionalProperties = false
): JsonSchemaObject {
  return {
    type: 'object',
    properties,
    required,
    additionalProperties
  }
}

function annotations(
  overrides: Partial<LocalAgentToolDefinition['annotations']> = {}
): LocalAgentToolDefinition['annotations'] {
  return {
    readOnlyHint: true,
    destructiveHint: false,
    openWorldHint: false,
    ...overrides
  }
}

const TOOL_DEFINITIONS: LocalAgentToolDefinition[] = [
  {
    name: 'get_local_status',
    description:
      'Report local Omi Desktop availability, including Rewind screen-history counts, latest capture time, local knowledge graph status, and unavailable local affordances.',
    inputSchema: schema({}),
    annotations: annotations()
  },
  {
    name: 'execute_sql',
    description:
      'Run one read-only SELECT or WITH query against the local Omi Windows SQLite database. Mutations and multi-statement SQL are rejected; returned rows are capped.',
    inputSchema: schema(
      {
        query: {
          type: 'string',
          description: 'Single read-only SELECT or WITH query to execute.'
        }
      },
      ['query']
    ),
    annotations: annotations({
      readOnlyEnforced: true,
      maxRows: MAX_SQL_ROWS,
      mutationStatementsRejected: true
    })
  },
  {
    name: 'search_screen_history',
    description:
      'Search local Rewind screen history using OCR text, app name, and window title. Results include screenshot IDs that can be opened with get_screenshot.',
    inputSchema: schema(
      {
        query: { type: 'string', description: 'Natural-language or keyword screen-history query.' },
        days: { type: 'number', description: 'Days to search back. Defaults to 7.' },
        app_filter: { type: 'string', description: 'Optional app/process/window filter.' },
        limit: {
          type: 'number',
          description: `Maximum result groups to return, capped at ${MAX_SEARCH_LIMIT}. Defaults to ${DEFAULT_SCREEN_LIMIT}.`
        }
      },
      ['query']
    ),
    annotations: annotations()
  },
  {
    name: 'semantic_search',
    description:
      'Compatibility alias for search_screen_history. On Windows this uses local Rewind OCR/app/window search.',
    inputSchema: schema(
      {
        query: { type: 'string', description: 'Natural-language or keyword screen-history query.' },
        days: { type: 'number', description: 'Days to search back. Defaults to 7.' },
        app_filter: { type: 'string', description: 'Optional app/process/window filter.' },
        limit: {
          type: 'number',
          description: `Maximum result groups to return, capped at ${MAX_SEARCH_LIMIT}. Defaults to ${DEFAULT_SCREEN_LIMIT}.`
        }
      },
      ['query']
    ),
    annotations: annotations()
  },
  {
    name: 'get_screenshot',
    description:
      'Fetch a local Rewind screenshot image by screenshot_id. Use IDs returned by search_screen_history or execute_sql over rewind_frames.',
    inputSchema: schema(
      {
        screenshot_id: {
          type: 'number',
          description: 'Rewind frame ID returned as screenshot_id.'
        },
        id: {
          type: 'number',
          description: 'Alias for screenshot_id.'
        }
      },
      ['screenshot_id']
    ),
    annotations: annotations()
  },
  {
    name: 'get_daily_recap',
    description:
      'Get a structured local activity recap for today, yesterday, or a recent range using Rewind frames, local conversations, insights, and locally available tasks.',
    inputSchema: schema({
      days_ago: {
        type: 'number',
        description: '0=today, 1=yesterday, 7=past week. Defaults to 0.'
      }
    }),
    annotations: annotations()
  },
  {
    name: 'search_tasks',
    description:
      'Best-effort search over local task tables if this Windows build has them. Returns an unavailable result when no reliable local task storage exists.',
    inputSchema: schema(
      {
        query: { type: 'string', description: 'Task search query.' },
        include_completed: {
          type: 'boolean',
          description: 'Include completed tasks. Defaults to false.'
        },
        limit: {
          type: 'number',
          description: `Maximum tasks to return, capped at ${MAX_SEARCH_LIMIT}. Defaults to 10.`
        }
      },
      ['query']
    ),
    annotations: annotations({
      availability: 'best_effort_local_tables'
    })
  },
  {
    name: 'complete_task',
    description:
      'Unavailable on Windows local API until task completion can be backed by reliable local storage and sync semantics.',
    inputSchema: schema(
      {
        task_id: { type: 'string', description: 'Hosted/backend task ID.' }
      },
      ['task_id']
    ),
    annotations: annotations({
      readOnlyHint: false,
      gated: true,
      unavailable: true,
      unavailableReason: TASK_MUTATION_UNAVAILABLE
    })
  },
  {
    name: 'delete_task',
    description:
      'Unavailable on Windows local API until destructive task deletion can be backed by reliable local storage and sync semantics.',
    inputSchema: schema(
      {
        task_id: { type: 'string', description: 'Hosted/backend task ID.' }
      },
      ['task_id']
    ),
    annotations: annotations({
      readOnlyHint: false,
      destructiveHint: true,
      gated: true,
      unavailable: true,
      unavailableReason: TASK_MUTATION_UNAVAILABLE
    })
  }
]

const TOOL_NAMES = new Set(TOOL_DEFINITIONS.map((tool) => tool.name))

export function listLocalAgentTools(): LocalAgentToolDefinition[] {
  return TOOL_DEFINITIONS.map((tool) => ({
    ...tool,
    inputSchema: {
      ...tool.inputSchema,
      properties: { ...tool.inputSchema.properties },
      required: [...(tool.inputSchema.required ?? [])]
    },
    annotations: { ...tool.annotations }
  }))
}

export async function runLocalAgentTool(
  name: string,
  rawArguments: unknown,
  context: LocalAgentRuntimeContext
): Promise<LocalAgentToolResponse> {
  if (!TOOL_NAMES.has(name)) {
    throw new LocalAgentToolError('unknown_tool', `Unknown local tool: ${name}`, 404, { name })
  }
  const args = argumentObject(rawArguments)

  switch (name) {
    case 'get_local_status':
      return ok(name, getLocalStatus(context))
    case 'execute_sql':
      return ok(name, executeSql(args))
    case 'search_screen_history':
    case 'semantic_search':
      return ok(name, searchScreenHistory(args))
    case 'get_screenshot':
      return screenshotResponse(name, args)
    case 'get_daily_recap':
      return ok(name, getDailyRecap(args))
    case 'search_tasks':
      return ok(name, searchTasks(args))
    case 'complete_task':
    case 'delete_task':
      throw new LocalAgentToolError('tool_unavailable', TASK_MUTATION_UNAVAILABLE, 501, { name })
    default:
      throw new LocalAgentToolError('unknown_tool', `Unknown local tool: ${name}`, 404, { name })
  }
}

export function errorResponseBody(error: unknown): {
  status: number
  body: { ok: false; error: { code: string; message: string; details?: unknown } }
} {
  if (error instanceof LocalAgentToolError) {
    return {
      status: error.status,
      body: {
        ok: false,
        error: {
          code: error.code,
          message: error.message,
          ...(error.details === undefined ? {} : { details: error.details })
        }
      }
    }
  }
  return {
    status: 500,
    body: {
      ok: false,
      error: {
        code: 'tool_execution_failed',
        message: error instanceof Error ? error.message : 'Local tool execution failed'
      }
    }
  }
}

function ok(
  name: string,
  result: unknown,
  contentType = 'application/json'
): LocalAgentToolResponse {
  return {
    ok: true,
    name,
    content_type: contentType,
    result
  }
}

function argumentObject(rawArguments: unknown): JsonObject {
  if (rawArguments == null) return {}
  if (typeof rawArguments === 'object' && !Array.isArray(rawArguments)) {
    return rawArguments as JsonObject
  }
  throw new LocalAgentToolError('invalid_arguments', 'arguments must be a JSON object')
}

function requiredString(args: JsonObject, key: string, aliases: string[] = []): string {
  for (const candidate of [key, ...aliases]) {
    const value = args[candidate]
    if (typeof value === 'string' && value.trim()) return value.trim()
  }
  throw new LocalAgentToolError('invalid_arguments', `${key} is required`, 400, { key })
}

function optionalString(args: JsonObject, key: string): string | undefined {
  const value = args[key]
  return typeof value === 'string' && value.trim() ? value.trim() : undefined
}

function numberArg(
  args: JsonObject,
  key: string,
  fallback: number,
  min: number,
  max: number
): number {
  const value = args[key]
  const parsed =
    typeof value === 'number'
      ? value
      : typeof value === 'string' && value.trim()
        ? Number(value.trim())
        : fallback
  const safe = Number.isFinite(parsed) ? Math.trunc(parsed) : fallback
  return Math.min(max, Math.max(min, safe))
}

function booleanArg(args: JsonObject, key: string, fallback: boolean): boolean {
  const value = args[key]
  if (typeof value === 'boolean') return value
  if (typeof value === 'string') {
    const normalized = value.trim().toLowerCase()
    if (normalized === 'true') return true
    if (normalized === 'false') return false
  }
  return fallback
}

function screenshotId(args: JsonObject): number {
  const value = args.screenshot_id ?? args.id
  const parsed =
    typeof value === 'number'
      ? value
      : typeof value === 'string' && value.trim()
        ? Number(value.trim())
        : NaN
  if (Number.isSafeInteger(parsed) && parsed > 0) return parsed
  throw new LocalAgentToolError('invalid_arguments', 'screenshot_id is required', 400, {
    key: 'screenshot_id'
  })
}

function getLocalStatus(context: LocalAgentRuntimeContext): JsonObject {
  try {
    const rewind = rewindStatusStats()
    const kg = getLocalKGStatus()
    const fileIndex = getFileIndexStats()
    return {
      ok: true,
      mode: 'local_omi_windows',
      app: context.app,
      local_api: context.localUrl,
      tool_endpoint: context.toolEndpoint,
      database_available: true,
      screen_history_available: rewind.totalFrameCount > 0,
      screenshot_count: rewind.totalFrameCount,
      indexed_screenshot_count: rewind.indexedFrameCount,
      ocr_backlog_count: rewind.ocrBacklogCount,
      oldest_capture_at: iso(rewind.oldestFrameTs),
      latest_capture_at: iso(rewind.latestFrameTs),
      knowledge_graph: kg,
      file_index: fileIndex,
      local_affordances: [
        'Rewind screen history and OCR search',
        'raw screenshot image retrieval by screenshot_id',
        'local transcription and conversation tables',
        'read-only SQL over the local Omi Windows database',
        'daily local activity recaps',
        'indexed files and local knowledge graph data',
        'best-effort local task search when task tables exist'
      ],
      unavailable_affordances: [
        {
          tool: 'complete_task',
          reason: TASK_MUTATION_UNAVAILABLE
        },
        {
          tool: 'delete_task',
          reason: TASK_MUTATION_UNAVAILABLE
        }
      ],
      recommended_first_tools: [
        'search_screen_history for Rewind/OCR questions',
        'get_screenshot after a search result returns a screenshot_id',
        'get_daily_recap for today/yesterday/this week',
        'execute_sql for exact read-only local database questions'
      ]
    }
  } catch (error) {
    return {
      ok: false,
      mode: 'local_omi_windows',
      app: context.app,
      local_api: context.localUrl,
      tool_endpoint: context.toolEndpoint,
      database_available: false,
      screen_history_available: false,
      message: error instanceof Error ? error.message : 'Failed to read local Omi status',
      unavailable_affordances: [
        {
          tool: 'complete_task',
          reason: TASK_MUTATION_UNAVAILABLE
        },
        {
          tool: 'delete_task',
          reason: TASK_MUTATION_UNAVAILABLE
        }
      ]
    }
  }
}

function executeSql(args: JsonObject): JsonObject {
  const query = requiredString(args, 'query', ['sql'])
  try {
    const guarded = guardSelect(query)
    const result = execSafeSelect(guarded)
    const rows = result.rows.slice(0, MAX_SQL_ROWS).map(sanitizeRow)
    return {
      columns: result.columns,
      rows,
      row_count: rows.length,
      truncated: result.rows.length > rows.length,
      read_only: true,
      max_rows: MAX_SQL_ROWS,
      executed_query: guarded
    }
  } catch (error) {
    throw new LocalAgentToolError(
      'sql_rejected_or_failed',
      error instanceof Error ? error.message : 'SQL query failed',
      400
    )
  }
}

function searchScreenHistory(args: JsonObject): JsonObject {
  const query = requiredString(args, 'query')
  const days = numberArg(args, 'days', 7, 1, 365)
  const limit = numberArg(args, 'limit', DEFAULT_SCREEN_LIMIT, 1, MAX_SEARCH_LIMIT)
  const appFilter = optionalString(args, 'app_filter')
  const since = Date.now() - days * DAY_MS
  const candidateLimit = Math.max(limit * 8, 100)
  const frames = searchRewindFrames(query, candidateLimit)
    .filter((frame) => frame.ts >= since)
    .filter((frame) => matchesAppFilter(frame, appFilter))
  const groups = groupFrames(frames, query).slice(0, limit)
  const results = groups.map(mapSearchGroup)

  return {
    query,
    days,
    app_filter: appFilter ?? null,
    limit,
    result_count: results.length,
    searched_frame_count: frames.length,
    source: 'rewind_frames_ocr',
    results,
    suggestions:
      results.length === 0
        ? [
            'Try a broader query',
            'Increase the days window',
            'Use execute_sql for exact app/window/OCR filters over rewind_frames'
          ]
        : []
  }
}

async function screenshotResponse(name: string, args: JsonObject): Promise<LocalAgentToolResponse> {
  const id = screenshotId(args)
  const result = await readRewindFrameImage(getRewindFrame(id), rewindRoot())
  if (!result.ok) {
    throw new LocalAgentToolError('screenshot_not_found', result.message, 404, {
      screenshot_id: id
    })
  }

  return ok(name, mapScreenshot(result), result.imageMimeType)
}

function getDailyRecap(args: JsonObject): JsonObject {
  const daysAgo = numberArg(args, 'days_ago', 0, 0, 365)
  const range = recapRange(daysAgo)
  const frames = listRewindFrames(range.startTs, range.endTs)
  const apps = summarizeApps(frames)
  const conversations = listLocalConversations()
    .filter(
      (conversation) =>
        conversation.startedAt < range.endTs && conversation.endedAt >= range.startTs
    )
    .slice(0, 20)
    .map(mapConversation)
  const insights = recentInsights(100)
    .filter((insight) => insight.ts >= range.startTs && insight.ts < range.endTs)
    .slice(0, 20)
    .map(mapInsight)
  const taskSearch = searchLocalTasks('', true, 20)
  const tasks = taskSearch.tasks.filter((task) => timestampInRange(task.createdAt, range))
  const text = formatDailyRecap(
    range.label,
    apps,
    conversations,
    tasks,
    insights,
    taskSearch.available
  )

  return {
    label: range.label,
    range: {
      start_ts: range.startTs,
      end_ts: range.endTs,
      start_at: iso(range.startTs),
      end_at: iso(range.endTs)
    },
    apps,
    conversations,
    insights,
    tasks,
    task_search_available: taskSearch.available,
    task_search_reason: taskSearch.reason ?? null,
    text
  }
}

function searchTasks(args: JsonObject): JsonObject {
  const query = requiredString(args, 'query')
  const includeCompleted = booleanArg(args, 'include_completed', false)
  const limit = numberArg(args, 'limit', 10, 1, MAX_SEARCH_LIMIT)
  const result = searchLocalTasks(query, includeCompleted, limit)
  return {
    query,
    include_completed: includeCompleted,
    limit,
    available: result.available,
    reason: result.reason ?? null,
    sources: result.sources,
    result_count: result.tasks.length,
    tasks: result.tasks
  }
}

function sanitizeRow(row: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(row)) {
    if (Buffer.isBuffer(value)) out[key] = `<${value.length} bytes>`
    else if (typeof value === 'bigint') out[key] = value.toString()
    else out[key] = value
  }
  return out
}

function matchesAppFilter(frame: RewindFrame, appFilter?: string): boolean {
  if (!appFilter) return true
  const needle = appFilter.toLowerCase()
  return [frame.app, frame.processName, frame.windowTitle].some((value) =>
    value.toLowerCase().includes(needle)
  )
}

function mapSearchGroup(group: RewindSearchGroup): JsonObject {
  return {
    group_id: group.id,
    app: group.app,
    window_title: group.windowTitle,
    start_ts: group.startTs,
    end_ts: group.endTs,
    start_at: iso(group.startTs),
    end_at: iso(group.endTs),
    match_snippet: group.matchSnippet,
    representative: mapFrame(group.representative),
    screenshots: group.frames
      .filter((frame) => frame.id != null)
      .slice(0, 10)
      .map(mapFrame)
  }
}

function mapFrame(frame: RewindFrame): JsonObject {
  return {
    screenshot_id: frame.id ?? null,
    ts: frame.ts,
    timestamp: iso(frame.ts),
    app: frame.app,
    window_title: frame.windowTitle,
    process_name: frame.processName,
    width: frame.width,
    height: frame.height,
    indexed: frame.indexed === 1,
    ocr_preview: preview(frame.ocrText, 500)
  }
}

function mapScreenshot(result: RewindFrameImageOk): JsonObject {
  const imageBytes = Buffer.byteLength(result.imageBase64, 'base64')
  return {
    screenshot_id: result.id,
    image_base64: result.imageBase64,
    image_mime_type: result.imageMimeType,
    metadata: {
      screenshot_id: result.id,
      ts: result.ts,
      timestamp: iso(result.ts),
      app: result.app,
      window_title: result.windowTitle,
      has_ocr: result.ocrPreview.length > 0,
      ocr_preview: result.ocrPreview,
      image_mime_type: result.imageMimeType,
      image_bytes: imageBytes
    }
  }
}

function recapRange(daysAgo: number): { label: string; startTs: number; endTs: number } {
  const now = Date.now()
  const today = new Date(now)
  today.setHours(0, 0, 0, 0)
  const startToday = today.getTime()

  if (daysAgo === 0) {
    return { label: 'Today', startTs: startToday, endTs: now }
  }
  if (daysAgo === 1) {
    return { label: 'Yesterday', startTs: startToday - DAY_MS, endTs: startToday }
  }
  return {
    label: `Past ${daysAgo} days`,
    startTs: startToday - daysAgo * DAY_MS,
    endTs: now
  }
}

function summarizeApps(frames: RewindFrame[]): JsonObject[] {
  const byApp = new Map<
    string,
    {
      app: string
      captures: number
      firstTs: number
      lastTs: number
      windowTitles: Set<string>
    }
  >()
  for (const frame of frames) {
    const app = frame.app || frame.processName || 'Unknown'
    const current =
      byApp.get(app) ??
      ({
        app,
        captures: 0,
        firstTs: frame.ts,
        lastTs: frame.ts,
        windowTitles: new Set<string>()
      } satisfies {
        app: string
        captures: number
        firstTs: number
        lastTs: number
        windowTitles: Set<string>
      })
    current.captures += 1
    current.firstTs = Math.min(current.firstTs, frame.ts)
    current.lastTs = Math.max(current.lastTs, frame.ts)
    if (frame.windowTitle) current.windowTitles.add(frame.windowTitle)
    byApp.set(app, current)
  }

  return [...byApp.values()]
    .sort((a, b) => b.captures - a.captures)
    .slice(0, 20)
    .map((app) => ({
      app: app.app,
      captures: app.captures,
      first_ts: app.firstTs,
      last_ts: app.lastTs,
      first_seen_at: iso(app.firstTs),
      last_seen_at: iso(app.lastTs),
      sample_window_titles: [...app.windowTitles].slice(0, 5)
    }))
}

function mapConversation(conversation: LocalConversation): JsonObject {
  return {
    id: conversation.id,
    title: conversation.title ?? null,
    kind: conversation.kind ?? 'recording',
    started_at: iso(conversation.startedAt),
    ended_at: iso(conversation.endedAt),
    transcript_preview: preview(conversation.transcript, 500)
  }
}

function mapInsight(insight: InsightRecord): JsonObject {
  return {
    id: insight.id,
    ts: insight.ts,
    timestamp: iso(insight.ts),
    headline: insight.headline,
    advice: insight.advice,
    category: insight.category,
    source_app: insight.sourceApp,
    confidence: insight.confidence
  }
}

function timestampInRange(value: unknown, range: { startTs: number; endTs: number }): boolean {
  if (value == null) return true
  const parsed =
    typeof value === 'number'
      ? value
      : typeof value === 'string' && value.trim()
        ? Number.isFinite(Number(value))
          ? Number(value)
          : Date.parse(value)
        : NaN
  return Number.isFinite(parsed) ? parsed >= range.startTs && parsed < range.endTs : true
}

function formatDailyRecap(
  label: string,
  apps: JsonObject[],
  conversations: JsonObject[],
  tasks: JsonObject[],
  insights: JsonObject[],
  taskSearchAvailable: boolean
): string {
  const lines = [`# ${label} Recap`, '', `## Apps (${apps.length})`]
  if (apps.length === 0) {
    lines.push('No screen activity recorded.')
  } else {
    for (const app of apps.slice(0, 10)) {
      lines.push(`- ${app.app}: ${app.captures} capture(s)`)
    }
  }

  lines.push('', `## Conversations (${conversations.length})`)
  if (conversations.length === 0) {
    lines.push('No local conversations recorded.')
  } else {
    for (const conversation of conversations.slice(0, 10)) {
      lines.push(`- ${conversation.title ?? conversation.id}: ${conversation.transcript_preview}`)
    }
  }

  lines.push('', `## Tasks (${tasks.length})`)
  if (!taskSearchAvailable) {
    lines.push('Local task storage is unavailable on this Windows build.')
  } else if (tasks.length === 0) {
    lines.push('No local tasks found for this range.')
  } else {
    for (const task of tasks.slice(0, 10)) {
      lines.push(`- ${task.completed ? '[x]' : '[ ]'} ${task.description}`)
    }
  }

  lines.push('', `## Insights (${insights.length})`)
  if (insights.length === 0) {
    lines.push('No local insights recorded.')
  } else {
    for (const insight of insights.slice(0, 10)) {
      lines.push(`- ${insight.headline}: ${insight.advice}`)
    }
  }
  return lines.join('\n')
}

function preview(text: string, length: number): string {
  return text.replace(/\s+/g, ' ').trim().slice(0, length)
}

function iso(ts: number | null | undefined): string | null {
  return typeof ts === 'number' && Number.isFinite(ts) ? new Date(ts).toISOString() : null
}
