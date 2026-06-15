import { desktopApi, omiApi } from './apiClient'
import {
  LOCAL_DB_SCHEMA,
  formatContextBlock,
  parseAction,
  raceWithBudget,
  type ContextSection
} from './localAgentProtocol'
import { orderFloorSections, relationshipItems, type KindedSection } from './floorContext'
import { rankMemories } from './memoryRank'
import type { Memory } from '../hooks/useMemories'

const AGENT_MODEL = 'claude-haiku-4-5-20251001'
const MAX_ITERS = 2 // capped tight: each iter is a full non-streaming LLM call
const AGENT_CALL_TIMEOUT_MS = 2_500 // per-iteration LLM timeout
// Hard cap on how long the chat WAITS for question-specific enrichment before
// sending. The deterministic floor (apps/folders/projects/tech) already grounds
// the chat instantly, so we keep this snappy: enrichment is a fast best-effort
// bonus, not something worth stalling the user's message for seconds.
const ENRICH_BUDGET_MS = 2_500
const MAX_SQL_ROWS = 30 // rows rendered into context per query
const MAX_MEMORY_CHARS = 220

// Floor-only mode. The deterministic snapshot (snapshotSections) already grounds
// the chat instantly and cleanly. The execute_sql agent enrichment added up to
// ENRICH_BUDGET_MS of dead time before every message and, within that budget,
// usually got cut off mid-loop — frequently contributing nothing or a raw
// row-dump that muddied the hosted answer. So enrichment is OFF: faster AND
// cleaner context. Flip to true to restore the macOS-faithful agentic pre-step.
const ENRICH_ENABLED = false

type MsgRole = 'system' | 'user' | 'assistant'
type ChatCompletion = { choices?: { message?: { content?: string } }[] }

const clip = (s: string): string =>
  s.length > MAX_MEMORY_CHARS ? `${s.slice(0, MAX_MEMORY_CHARS).trimEnd()}…` : s

// Memories are the MEANING source; fetched once per session and reused.
let memoryCache: Memory[] | null = null
async function loadMemories(): Promise<Memory[]> {
  if (memoryCache) return memoryCache
  try {
    const r = await omiApi.get('/v3/memories', { params: { limit: 100, offset: 0 } })
    const data = r.data as { memories?: Memory[] } | Memory[]
    memoryCache = Array.isArray(data) ? data : (data.memories ?? [])
  } catch {
    memoryCache = []
  }
  return memoryCache
}

const SYSTEM_PROMPT = [
  'You gather local context to help answer a question about the user’s machine and work.',
  'You can query the local database directly. Each turn, output ONLY a single raw JSON',
  'object — no prose, no markdown fences, no <function_calls> tag, NOT in an array. One of:',
  '  {"action":"execute_sql","input":"<a single read-only SELECT>"}   - query the local DB',
  '  {"action":"search_memories","input":"<topic/project name>"}   - find what the user saved',
  '  {"action":"final"}   - stop; you have enough context',
  '',
  LOCAL_DB_SCHEMA,
  '',
  'Notes: programming languages/technologies are rows in local_kg_nodes WHERE',
  "node_type='technology'. Projects/people/orgs are other node_type values. Keep",
  'queries simple and specific. Usually 1-3 queries is enough, then emit final. Do',
  'not answer the question yourself — only gather context.'
].join('\n')

// Render SQL rows into compact "col | col" lines with a header.
function formatRows(columns: string[], rows: Record<string, unknown>[]): string[] {
  if (rows.length === 0) return []
  const header = columns.join(' | ')
  const lines = rows
    .slice(0, MAX_SQL_ROWS)
    .map((r) => columns.map((c) => String(r[c] ?? '')).join(' | '))
  // Tell the model when the result was truncated so it doesn't treat a partial
  // result set as the whole thing.
  if (rows.length > MAX_SQL_ROWS) lines.push(`… (${rows.length - MAX_SQL_ROWS} more rows)`)
  return [header, ...lines]
}

// Snapshot fallback: partition recent nodes with technologies first, so even if
// the agent loop yields nothing the chat is grounded (and never blind to
// languages). Best-effort.
async function snapshotSections(): Promise<KindedSection[]> {
  const graph = await window.omi.kgQueryNodes('', 80)
  const nodes = graph.nodes
  const pick = (t: string): string[] => nodes.filter((n) => n.nodeType === t).map((n) => n.summary)
  const out: KindedSection[] = []
  // Background-synthesized overview card (natural-language summary) leads the floor.
  const cards = nodes.filter((n) => n.nodeType === 'card').map((n) => n.summary)
  if (cards.length) out.push({ kind: 'overview', heading: 'Overview', items: cards })
  const tech = pick('technology')
  if (tech.length) out.push({ kind: 'tech', heading: 'Programming languages & technologies', items: tech })
  const ent = nodes
    .filter((n) => ['project', 'person', 'org', 'interest'].includes(n.nodeType))
    .map((n) => `${n.label} (${n.nodeType}): ${n.summary}`)
  if (ent.length) out.push({ kind: 'entities', heading: 'Projects, people & interests', items: ent })
  // Tier 1: surface the labeled relationships synthesis built (macOS's signature).
  const rels = relationshipItems(nodes, graph.edges)
  if (rels.length) out.push({ kind: 'relationships', heading: 'How they relate', items: rels })
  const folders = pick('file_group')
  if (folders.length)
    out.push({ kind: 'folders', heading: 'Recently active working folders', items: folders })
  const apps = pick('app')
  if (apps.length) out.push({ kind: 'apps', heading: 'Installed apps', items: apps })
  return out
}

// The bounded agent loop: the model drives execute_sql / search_memories over
// local data and we accumulate the results as context sections. Capped at
// MAX_ITERS, each LLM call bounded by AGENT_CALL_TIMEOUT_MS. Returns whatever
// sections it gathered (possibly empty). Network-bound; callers race it against
// a budget and merge the result onto the deterministic floor.
async function runAgentLoop(userText: string): Promise<ContextSection[]> {
  const sections: ContextSection[] = []
  const messages: { role: MsgRole; content: string }[] = [
    { role: 'system', content: SYSTEM_PROMPT },
    { role: 'user', content: `User question: ${userText}` }
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

    let observation = 'No matches.'
    if (action.action === 'execute_sql') {
      try {
        const { columns, rows } = await window.omi.kgExecuteSql(action.input)
        const items = formatRows(columns, rows)
        if (items.length) {
          sections.push({ heading: `Query: ${action.input}`, items })
          observation = items.join('\n')
        } else {
          observation = '0 rows.'
        }
      } catch (e) {
        // Rejected by sqlGuard or a SQL error — tell the model so it can fix it.
        observation = `Query rejected: ${(e as Error).message}`
      }
    } else if (action.action === 'search_memories') {
      const items = rankMemories(await loadMemories(), action.input, 6).map(clip)
      if (items.length) {
        sections.push({ heading: `Memories about "${action.input}"`, items })
        observation = items.join('\n')
      }
    } else {
      // query_kg / search_files are legacy actions; treat as no-op observation.
      observation = 'Use execute_sql instead.'
    }
    messages.push({ role: 'user', content: `Observation:\n${observation}` })
  }
  return sections
}

// Chat pre-step: instant deterministic floor + raced agent enrichment. The floor
// (a single local SQL read, no LLM) is always computed so the chat is ALWAYS
// grounded. The bounded agent loop runs concurrently, raced against a hard budget;
// whatever it gathered when the budget expires is merged on top. Best-effort —
// ANY failure returns '' so the chat sends the raw message and never regresses.
export async function gatherLocalContext(userText: string): Promise<string> {
  try {
    const status = await window.omi.kgStatus()
    if (status.nodeCount === 0) {
      const digest = await window.omi.kgFileIndexDigest()
      if (digest.totalFiles === 0) return ''
    }

    // Floor: the deterministic snapshot (a single local SQL read, no LLM) is
    // computed unconditionally so the chat is ALWAYS grounded. Enrichment: the
    // bounded agent loop runs concurrently and is raced against a hard budget —
    // whatever it has gathered when the budget expires is merged on top. A
    // floor failure degrades to an empty floor (the agent result still counts);
    // an enrichment failure/timeout degrades to floor-only.
    const floorP = snapshotSections().catch(() => [] as KindedSection[])
    const agentSections = ENRICH_ENABLED
      ? await raceWithBudget<ContextSection[]>(runAgentLoop(userText), ENRICH_BUDGET_MS, [])
      : []
    const floor = await floorP

    // The overview card always leads (a coherent summary grounds every answer);
    // the remaining sections are intent-routed so the question-relevant one comes
    // next and survives formatContextBlock's end-trimming. Agent enrichment, when
    // enabled, is appended last.
    const overview = floor.filter((s) => s.kind === 'overview').map(({ heading, items }) => ({ heading, items }))
    const rest = floor.filter((s) => s.kind !== 'overview')
    return formatContextBlock([...overview, ...orderFloorSections(rest, userText), ...agentSections])
  } catch {
    return ''
  }
}
