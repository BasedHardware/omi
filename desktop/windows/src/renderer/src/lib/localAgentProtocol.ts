import type { LocalAgentChatToolName, LocalAgentToolArguments } from '../../../shared/types'

// One JSON object the model emits per turn of the bounded tool loop.
export type ToolAction =
  | { action: LocalAgentChatToolName; input: LocalAgentToolArguments }
  | { action: 'final' }

export const CHAT_LOCAL_TOOL_NAMES = [
  'get_local_status',
  'search_screen_history',
  'execute_sql',
  'get_screenshot'
] as const satisfies readonly LocalAgentChatToolName[]

const CHAT_LOCAL_TOOL_SET = new Set<string>(CHAT_LOCAL_TOOL_NAMES)

// Compact schema description handed to the chat agent so it can write its own
// read-only SELECTs (mirrors macOS's execute_sql tool). Kept terse on purpose.
export const LOCAL_DB_SCHEMA = [
  'Tables you can SELECT from (read-only):',
  '- rewind_frames(id, ts, app, window_title, process_name, ocr_text, image_path, width, height, indexed)',
  '  — local Rewind screen-history frames; ts is epoch ms; use substr(ocr_text, 1, 500)',
  '  for previews and COUNT(*) for counts instead of selecting full OCR bodies.',
  '- local_kg_nodes(id, label, node_type, summary, source, created_at) — node_type in',
  '  (card, project, person, org, interest, technology, app, file_group)',
  '- local_kg_edges(id, source_id, target_id, label) — relationships between node ids',
  '- indexed_files(filename, folder, file_type, extension, modified_at) — file_type in',
  '  (code, document, image, media, archive, application)',
  '- local_conversation(id, transcript, started_at, ended_at, kind, title) — past chats/recordings;',
  '  use COUNT(*) for count questions and substr(transcript, 1, 500) for previews.'
].join('\n')

// Extract the first balanced JSON object from arbitrary model text. Tolerates
// prose before/after, code fences, and wrappers like Claude's native
// `<function_calls>\n[{...}]` (array, trailing chars) — we scan from the first
// `{` and brace-match to its close, ignoring everything outside. Strings are
// respected so braces inside values don't throw off the depth count.
function firstJsonObject(text: string): string | null {
  const start = text.indexOf('{')
  if (start === -1) return null
  let depth = 0
  let inStr = false
  let esc = false
  for (let i = start; i < text.length; i++) {
    const ch = text[i]
    if (inStr) {
      if (esc) esc = false
      else if (ch === '\\') esc = true
      else if (ch === '"') inStr = false
      continue
    }
    if (ch === '"') inStr = true
    else if (ch === '{') depth++
    else if (ch === '}') {
      depth--
      if (depth === 0) return text.slice(start, i + 1)
    }
  }
  return null
}

export function parseAction(text: string): ToolAction | null {
  const json = firstJsonObject(text)
  if (!json) return null
  let obj: unknown
  try {
    obj = JSON.parse(json)
  } catch {
    return null
  }
  const o = obj as { action?: unknown; input?: unknown; fileType?: unknown }
  if (o.action === 'final') return { action: 'final' }
  if (typeof o.action !== 'string' || !CHAT_LOCAL_TOOL_SET.has(o.action)) return null
  const action = o.action as LocalAgentChatToolName
  const input = normalizeToolInput(action, o.input)
  if (!input) return null
  return { action, input }
}

function normalizeToolInput(
  action: LocalAgentChatToolName,
  input: unknown
): LocalAgentToolArguments | null {
  if (action === 'get_local_status') return {}
  if (input && typeof input === 'object' && !Array.isArray(input)) {
    const args = input as LocalAgentToolArguments
    if (action === 'execute_sql') {
      return typeof args.query === 'string' && args.query.trim()
        ? { ...args, query: args.query.trim() }
        : null
    }
    if (action === 'search_screen_history') {
      return typeof args.query === 'string' && args.query.trim()
        ? { ...args, query: args.query.trim() }
        : null
    }
    if (action === 'get_screenshot') {
      const id = numericId(args.screenshot_id ?? args.id)
      return id == null ? null : { ...args, screenshot_id: id }
    }
  }
  if (action === 'execute_sql' && typeof input === 'string' && input.trim()) {
    return { query: input.trim() }
  }
  if (action === 'search_screen_history' && typeof input === 'string' && input.trim()) {
    return { query: input.trim() }
  }
  if (action === 'get_screenshot') {
    const id = numericId(input)
    if (id != null) return { screenshot_id: id }
  }
  return null
}

function numericId(value: unknown): number | null {
  const parsed =
    typeof value === 'number'
      ? value
      : typeof value === 'string' && value.trim()
        ? Number(value.trim())
        : NaN
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null
}

export type ContextSection = { heading: string; items: string[] }

export const GUARD_LINE =
  'The Local context above is background reference about this machine, provided only to keep you accurate. ' +
  'Use it solely when it is relevant to the question. Do NOT recite or list these facts ' +
  '(especially programming languages or file counts) unless the user actually asks about them, ' +
  'and do NOT infer relationships between them — e.g. that all projects live in one folder/workspace. ' +
  'Answer the question naturally, and never introduce technologies, frameworks, or projects that are not listed above.'

// Max chars for the context body (before the guard line). Large enough to hold
// the deterministic snapshot (languages + recent folders + related memories +
// a short app list) while still staying modest relative to the conversation.
// Sections are ordered most-valuable-first, so trimming from the end drops the
// app list before it touches the languages/folders/memories.
export const CONTEXT_BUDGET = 2800

// Build the compact "Local context" block from accumulated tool results. Empty
// sections are dropped; if nothing remains, returns '' so the caller sends the
// raw message (today's behavior). The guard line is always appended when there
// IS context.
export function formatContextBlock(sections: ContextSection[]): string {
  const nonEmpty = sections.filter((s) => s.items.length > 0)
  if (nonEmpty.length === 0) return ''
  const lines: string[] = ['Local context:']
  for (const s of nonEmpty) {
    lines.push(`${s.heading}:`)
    for (const item of s.items) lines.push(`- ${item}`)
  }
  let body = lines.join('\n')
  if (body.length > CONTEXT_BUDGET) {
    // Trim to budget on a line boundary so we never emit a half line.
    body = body.slice(0, CONTEXT_BUDGET).replace(/\n[^\n]*$/, '')
  }
  return `${body}\n\n${GUARD_LINE}`
}

// Resolve with p's value if it settles within `ms`; otherwise resolve with
// `fallback`. A rejection ALSO resolves with `fallback` — this never rejects, so
// callers don't need a try/catch. Used to cap the chat pre-step's agent loop at
// a hard latency budget while always yielding a usable value.
export function raceWithBudget<T>(p: Promise<T>, ms: number, fallback: T): Promise<T> {
  return new Promise<T>((resolve) => {
    let settled = false
    const done = (v: T): void => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      resolve(v)
    }
    const timer = setTimeout(() => done(fallback), ms)
    void p.then(
      (v) => done(v),
      () => done(fallback)
    )
  })
}
