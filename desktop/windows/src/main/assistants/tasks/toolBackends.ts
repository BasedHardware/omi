// The TaskAssistant's two search-tool backends — `search_similar` (vector) and
// `search_keywords` (FTS5) — the extraction loop dispatches to so Gemini can check
// for existing/duplicate tasks before it emits `extract_task`. Ported 1:1 from
// Mac's `executeVectorSearch` / `executeKeywordSearch`
// (TaskAssistant.swift:1450–1560) and the `TaskSearchResult` Codable shape
// (TaskModels.swift:530).
//
// Structured like `insight/sql.ts`: the impure edges (the embedding call, the
// vector index, the two FTS reads, the action-item resolver) are INJECTED, so the
// whole result-shaping — 0.3 similarity gate, source-aware resolution, FTS
// tokenization, and both-table merge — is pure and hermetically testable with
// fakes. Thin WIRED wrappers (`executeVectorSearch` / `executeKeywordSearch`) bind
// the real PR-A storage + embedding functions and are what the loop calls.
//
// Faithfulness notes (Mac is the reference; verified against the running oracle):
//  - Both backends return `TaskSearchResult[]`; the LOOP JSON-encodes them into the
//    tool functionResponse (Mac dispatch: `JSONEncoder().encode(searchResults)`,
//    `"[]"` on failure). `encodeSearchResults` mirrors that exactly.
//  - The empty / no-session / error outcome is an EMPTY array (encodes to `[]`),
//    NOT a prose "no similar tasks" string — Mac's `catch` returns `[]`.
//  - Keyword search does NOT dedupe across the two tables: `action_items` and
//    `staged_tasks` have independent rowid spaces, so a shared id is two different
//    tasks. Mac appends both lists verbatim; deduping by id would wrongly drop an
//    unrelated staged task. So we append both, no cross-table dedupe (matches Mac).
//  - Windows hard-deletes tasks, so no `deleted=1` rows exist: the action FTS query
//    always excludes deleted (there is no `includeDeleted` param to pass) and the
//    resolver only ever sees active/completed rows. The `deleted → "deleted"` status
//    branch is kept for fidelity but is unreachable on Windows.
// Only TYPES are imported at module scope — every import here is `import type`, so
// nothing pulls in db.ts (better-sqlite3/electron) or the embedding service at load
// time. That keeps this module importable under vitest (the pure cores are tested
// with injected fakes); the WIRED wrappers below defer the real-module loads to
// call-time via dynamic import, exactly so the test never drags in the native DB.
import type { ActionItemRecord, StagedTaskRecord, TaskEmbeddingSource } from '../../../shared/types'
import type { TaskSimilarity } from '../../tasks/taskEmbeddingService'

/** Mac's `TaskSearchResult` (TaskModels.swift:530), ported field-for-field with its
 *  exact Codable JSON keys (`match_type` / `relevance_score` are snake_case). This
 *  is the object the loop JSON-encodes (via `encodeSearchResults`, which emits ONLY
 *  these Mac fields) as each search tool's functionResponse.
 *
 *  `backendId` + `source` are Windows-only enrichment for the `search_tasks` product
 *  tool: `id` is the LOCAL rowid of the source table (staged/action rowid spaces
 *  overlap, so it is NOT a stable cross-tool handle), whereas the product tool must
 *  hand the model an id the mutation tools (update/complete/delete) can resolve. Only
 *  an `action_item` carries a mutatable id (its `backendId`, or `local:<rowid>` before
 *  it syncs); a `staged_task` is an extraction draft with no action-item identity.
 *  These fields are stripped by `encodeSearchResults` so the extraction-loop JSON
 *  stays byte-for-byte Mac-faithful. */
export type TaskSearchResult = {
  id: number
  description: string
  /** "active" | "completed" | "deleted". */
  status: string
  /** Cosine similarity for vector matches; null for FTS-only matches. */
  similarity: number | null
  /** "vector" | "fts". */
  match_type: string
  /** Relevance ranking score (higher = more important); null when unscored. */
  relevance_score: number | null
  /** Source table this row came from. Populated by the vector backend (the only one
   *  the `search_tasks` product tool reads); absent on results the extraction loop
   *  produces that never surface to a mutation tool. */
  source?: TaskEmbeddingSource
  /** The action-item backendId, when the row is a synced `action_item`; null for an
   *  unsynced action item or any staged task. */
  backendId?: string | null
}

/** The projection of a task row the backends read to build a `TaskSearchResult`.
 *  Narrower than the full records so fakes are trivial to construct in tests. */
export type ResolvedTask = {
  description: string
  completed: boolean
  deleted: boolean
  relevanceScore: number | null
  /** The action-item backendId (null for a staged task or an unsynced action item).
   *  Threaded through so `search_tasks` can emit a mutation-resolvable id. */
  backendId: string | null
}

/** One `action_items` FTS row (subset of `searchActionItemsFTS`'s return this
 *  backend reads). */
export type ActionFtsRow = {
  id: number
  description: string
  completed: boolean
  deleted: boolean
  relevanceScore: number | null
}

/** One `staged_tasks` FTS row (subset of `searchStagedTasksFTS`'s return). */
export type StagedFtsRow = {
  id: number
  description: string
  relevanceScore: number | null
}

/** Injected impure edges for the vector backend. */
export type VectorSearchDeps = {
  embedQuery: (text: string) => Promise<Float32Array | null>
  searchSimilar: (queryVec: Float32Array, topK: number) => TaskSimilarity[]
  getStagedTask: (id: number) => ResolvedTask | null
  getActionItem: (id: number) => ResolvedTask | null
}

/** Injected impure edges for the keyword backend. */
export type KeywordSearchDeps = {
  searchActionItemsFTS: (query: string, limit: number, includeCompleted: boolean) => ActionFtsRow[]
  searchStagedTasksFTS: (query: string, limit: number) => StagedFtsRow[]
}

/** Vector search fan-out (Mac `topK: 10`). */
const VECTOR_TOP_K = 10
/** Keep only hits strictly above this cosine similarity (Mac `> 0.3`). */
const SIMILARITY_THRESHOLD = 0.3
/** Per-table FTS row cap (Mac `limit: 10`). */
const KEYWORD_LIMIT = 10
/** Drop tokens shorter than this after stripping non-alphanumerics (Mac `count >= 3`). */
const MIN_TOKEN_LEN = 3

/** Mac's status derivation: deleted wins, then completed, else active. */
function statusOf(t: { deleted: boolean; completed: boolean }): string {
  if (t.deleted) return 'deleted'
  if (t.completed) return 'completed'
  return 'active'
}

/**
 * `search_similar` backend. Embeds `query`, ranks the in-memory index, keeps hits
 * strictly above the 0.3 similarity gate, resolves each against the EXACT table its
 * vector came from (`source`, so a shared rowid can't surface an unrelated task),
 * and returns the results sorted by similarity (strongest first).
 *
 * Never throws (Mac's `catch` → return what has accumulated): a missing session or
 * empty text yields `[]` (embed returns null); a resolver/index error stops early
 * and returns the partial list.
 */
export async function executeVectorSearchWith(
  deps: VectorSearchDeps,
  query: string
): Promise<TaskSearchResult[]> {
  const out: TaskSearchResult[] = []
  try {
    const queryVec = await deps.embedQuery(query)
    if (!queryVec) return out // no session / empty text / backend error → no similar tasks
    for (const hit of deps.searchSimilar(queryVec, VECTOR_TOP_K)) {
      if (!(hit.similarity > SIMILARITY_THRESHOLD)) continue
      const rec =
        hit.source === 'staged_task' ? deps.getStagedTask(hit.id) : deps.getActionItem(hit.id)
      if (!rec) continue // hard-deleted row (Windows) or index/DB drift → skip
      out.push({
        id: hit.id,
        description: rec.description,
        status: statusOf(rec),
        similarity: hit.similarity,
        match_type: 'vector',
        relevance_score: rec.relevanceScore,
        source: hit.source,
        backendId: rec.backendId
      })
    }
  } catch {
    // Mac logs and returns whatever it had — never propagate into the tool loop.
  }
  out.sort((a, b) => (b.similarity ?? 0) - (a.similarity ?? 0))
  return out
}

/**
 * Build the FTS5 MATCH query from a natural-language string, exactly as Mac does
 * (TaskAssistant.swift:1509–1512): split on whitespace, strip every non-alphanumeric
 * character from each token (removes FTS5 operators `- : * "` etc.), drop tokens
 * shorter than 3 chars, then OR-join `token*` prefix terms. Returns "" when no token
 * survives (the caller then skips the search).
 */
export function buildFtsQuery(query: string): string {
  return query
    .split(/\s+/)
    .map((w) => w.replace(/[^\p{L}\p{N}]/gu, '')) // keep only Unicode letters + numbers
    .filter((w) => w.length >= MIN_TOKEN_LEN)
    .map((w) => `${w}*`)
    .join(' OR ')
}

/**
 * `search_keywords` backend. Tokenizes `query` into an FTS5 prefix-OR expression and
 * runs it against BOTH `action_items` (completed included, per Mac) and
 * `staged_tasks`, appending both result lists (no cross-table dedupe — the two
 * rowid spaces are independent; see the file header). Empty token set → `[]`.
 * Never throws.
 */
export async function executeKeywordSearchWith(
  deps: KeywordSearchDeps,
  query: string
): Promise<TaskSearchResult[]> {
  const out: TaskSearchResult[] = []
  const ftsQuery = buildFtsQuery(query)
  if (!ftsQuery) return out
  try {
    for (const r of deps.searchActionItemsFTS(ftsQuery, KEYWORD_LIMIT, true)) {
      out.push({
        id: r.id,
        description: r.description,
        status: statusOf(r),
        similarity: null,
        match_type: 'fts',
        relevance_score: r.relevanceScore
      })
    }
    for (const r of deps.searchStagedTasksFTS(ftsQuery, KEYWORD_LIMIT)) {
      out.push({
        id: r.id,
        description: r.description,
        status: 'active', // Mac hardcodes staged FTS results as "active"
        similarity: null,
        match_type: 'fts',
        relevance_score: r.relevanceScore
      })
    }
  } catch {
    // Mac logs and returns the partial list — never propagate into the tool loop.
  }
  return out
}

/**
 * JSON-encode search results into the tool functionResponse string, exactly as
 * Mac's dispatch does (`JSONEncoder().encode(searchResults)`, falling back to the
 * literal `"[]"` if encoding somehow fails). The loop sends this string as the
 * `result` of the `search_similar` / `search_keywords` functionResponse.
 */
export function encodeSearchResults(results: TaskSearchResult[]): string {
  try {
    // Emit ONLY Mac's Codable fields — the Windows-only `source`/`backendId`
    // enrichment (for the `search_tasks` product tool) must not leak into the
    // extraction-loop functionResponse the model de-dupes against.
    return JSON.stringify(
      results.map((r) => ({
        id: r.id,
        description: r.description,
        status: r.status,
        similarity: r.similarity,
        match_type: r.match_type,
        relevance_score: r.relevance_score
      }))
    )
  } catch {
    return '[]'
  }
}

/** Narrow a full record to the `ResolvedTask` projection the backend needs. The
 *  caller passes the mutation-addressable `backendId`: an action item's own
 *  `backendId`, or `null` for a staged task — a `StagedTaskRecord.backendId` is a
 *  staged-table id the action-item mutation tools cannot resolve, so it must never be
 *  surfaced as a task handle. */
function projectRecord(
  r: ActionItemRecord | StagedTaskRecord,
  backendId: string | null
): ResolvedTask {
  return {
    description: r.description,
    completed: r.completed,
    deleted: r.deleted,
    relevanceScore: r.relevanceScore,
    backendId
  }
}

/**
 * WIRED `search_similar` — what the extraction loop calls. Binds the real embedding
 * + storage functions, dynamically imported so this module stays load-time-pure.
 *
 * The action-item-by-id resolver is composed from `getLocalActionItems` (WHERE
 * deleted = 0 → active + completed when `completed` is omitted): db.ts exposes no
 * action-item-by-id getter and storage is out of this file's scope to change.
 * Windows hard-deletes, so that list covers every resolvable id up to the same cap
 * as the embedding index (`searchSimilar` can only surface an id it holds, and the
 * index is capped at `MAX_INDEX_SIZE`). The map is built lazily (only when a vector
 * hit is an action item) and freshly per call, so it reflects the current DB.
 */
export async function executeVectorSearch(query: string): Promise<TaskSearchResult[]> {
  const [{ MAX_INDEX_SIZE, embedQuery, searchSimilar }, { getLocalActionItems, getStagedTask }] =
    await Promise.all([import('../../tasks/taskEmbeddingService'), import('../../ipc/db')])

  let byId: Map<number, ActionItemRecord> | null = null
  const getActionItem = (id: number): ResolvedTask | null => {
    if (!byId) {
      byId = new Map(getLocalActionItems({ limit: MAX_INDEX_SIZE }).map((r) => [r.id, r] as const))
    }
    const r = byId.get(id)
    return r ? projectRecord(r, r.backendId) : null
  }

  return executeVectorSearchWith(
    {
      embedQuery,
      searchSimilar,
      getStagedTask: (id) => {
        const s = getStagedTask(id)
        // A staged task carries no action-item identity → no mutatable backendId.
        return s ? projectRecord(s, null) : null
      },
      getActionItem
    },
    query
  )
}

/**
 * WIRED `search_keywords` — what the extraction loop calls. Binds the real FTS
 * readers (`action_items` with completed included, `staged_tasks`), dynamically
 * imported so this module stays load-time-pure.
 */
export async function executeKeywordSearch(query: string): Promise<TaskSearchResult[]> {
  const { searchActionItemsFTS, searchStagedTasksFTS } = await import('../../ipc/db')
  return executeKeywordSearchWith({ searchActionItemsFTS, searchStagedTasksFTS }, query)
}

/** Re-exported so callers can reference the discriminant without reaching into the
 *  embedding service. */
export type { TaskEmbeddingSource }
