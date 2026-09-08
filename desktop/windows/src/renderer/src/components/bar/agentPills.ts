// Pure data model for the bar's "floating agent pills" — one live pill per
// kernel-tracked background run the user spawned via the spawn_agent tool
// (surfaceKind 'floating_bar'). This is a faithful port of the macOS
// AgentPillsManager mechanism (upstream FloatingControlBar/AgentPill.swift):
// projection merge, status mapping, and post-completion lifecycle. Kept out of
// React and free of any main/preload import so the load-bearing rules (no
// resurrection of a finished pill, drop-missing-id, soft-cap eviction order,
// viewed-TTL expiry) are unit-testable without a DOM or IPC. Later phases (B3)
// consume these exports to render the pills and wire the poll/subscribe door.
//
// Vocabulary (Mac spec §b — deliberately two granularities):
//  - Kernel WIRE status: what the run registry emits (AgentRunProjectionStatus).
//  - Pill DISPLAY status: the coarser chip vocabulary the bar shows.

/** Kernel wire status carried on a projection row (snake_case, as the Windows
 *  agent kernel emits). Mirrors Mac's AgentRunProjectionStatus. */
export type AgentPillWireStatus =
  | 'idle'
  | 'queued'
  | 'starting'
  | 'running'
  | 'waiting_input'
  | 'waiting_approval'
  | 'cancelling'
  | 'succeeded'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'timed_out'
  | 'orphaned'

/** The coarse status the pill chip shows. Mirrors Mac's AgentPill.Status
 *  (queued, starting, running, done, stopped, failed). */
export type AgentPillDisplayStatus =
  | 'queued'
  | 'starting'
  | 'running'
  | 'done'
  | 'stopped'
  | 'failed'

/** A neutral, className-ish tint token — NOT a raw color. B3 maps these to
 *  Tailwind classes. Intended palette (NO PURPLE — brand rule INV-UI-1):
 *    running → amber · done → emerald/green · stopped → neutral/gray ·
 *    failed → red · queued (also 'starting') → neutral.
 *  Never hardcode hex here. */
export type AgentPillTintToken = 'queued' | 'running' | 'done' | 'stopped' | 'failed'

/** One row of the `floating_agent_pills[]` array the renderer receives from the
 *  existing `list_agent_sessions` door. Matches `serializeFloatingPillSnapshot`
 *  in src/main/agentKernel/controlTools.ts exactly. `status` is a kernel WIRE
 *  status string (or 'unknown' when the kernel has none). */
export type PillProjectionRow = {
  id: string | null
  runId: string | null
  sessionId: string | null
  title: string | null
  status: string
  latestActivity: string
  query: string
  createdAtMs: number | null
  completedAtMs: number | null
  provider: string | null
  errorCode: string | null
  errorMessage: string | null
}

/** The bar's model of one floating agent pill. Merges the projected row with
 *  local-only state (`viewedAtMs`) that must survive every re-merge. */
export type AgentPill = {
  id: string
  runId: string
  sessionId: string
  title: string
  displayStatus: AgentPillDisplayStatus
  latestActivity: string
  query: string
  createdAtMs: number | null
  completedAtMs: number | null
  errorMessage: string | null
  provider: string | null
  /** When the user last opened this (finished) pill. null = never viewed.
   *  Local-only — never comes from a projection row; drives the viewed-TTL. */
  viewedAtMs: number | null
}

/** Soft cap on retained pills before eviction kicks in (Mac `maxPills = 8`). */
export const SOFT_CAP = 8

/** How long a finished pill survives after the user has viewed it
 *  (Mac `viewedFinishedTTL = 10 * 60`). Unviewed finished pills never
 *  timer-expire — they only leave under soft-cap pressure. */
export const VIEWED_FINISHED_TTL_MS = 10 * 60 * 1000

// ── Status mapping (Mac spec §b, applyProjectedStatus AgentPill.swift:1580-1598)

const WIRE_TO_DISPLAY: Record<AgentPillWireStatus, AgentPillDisplayStatus> = {
  idle: 'queued',
  queued: 'queued',
  starting: 'starting',
  running: 'running',
  waiting_input: 'running',
  waiting_approval: 'running',
  cancelling: 'running',
  succeeded: 'done',
  completed: 'done',
  cancelled: 'stopped',
  failed: 'failed',
  timed_out: 'failed',
  orphaned: 'failed'
}

const WIRE_STATUS_SET = new Set<string>(Object.keys(WIRE_TO_DISPLAY))

/** Coerce an arbitrary row status string (e.g. the serializer's 'unknown'
 *  fallback) to a known wire status; anything unrecognized becomes the
 *  non-terminal 'idle' so it can never spuriously read as finished. */
export function normalizeWireStatus(raw: string): AgentPillWireStatus {
  return WIRE_STATUS_SET.has(raw) ? (raw as AgentPillWireStatus) : 'idle'
}

/** Map a kernel wire status to the coarse pill display status. */
export function mapWireStatusToDisplay(wire: AgentPillWireStatus): AgentPillDisplayStatus {
  return WIRE_TO_DISPLAY[wire]
}

const FINISHED_DISPLAY = new Set<AgentPillDisplayStatus>(['done', 'stopped', 'failed'])

/** True when a display status is terminal (done/stopped/failed). A finished
 *  pill stays finished — see the no-resurrection rule in `mergeProjectedPills`. */
export function isFinished(display: AgentPillDisplayStatus): boolean {
  return FINISHED_DISPLAY.has(display)
}

const TERMINAL_WIRE = new Set<AgentPillWireStatus>([
  'succeeded',
  'completed',
  'cancelled',
  'failed',
  'timed_out',
  'orphaned'
])

/** True when a wire status is terminal. Note `cancelling` is NOT terminal
 *  (the run is still winding down → maps to display 'running'). */
export function isTerminalWire(wire: AgentPillWireStatus): boolean {
  return TERMINAL_WIRE.has(wire)
}

const DISPLAY_LABEL: Record<AgentPillDisplayStatus, string> = {
  queued: 'Queued',
  starting: 'Starting',
  running: 'Running',
  done: 'Done',
  stopped: 'Stopped',
  failed: 'Failed'
}

/** The human chip label for a display status. */
export function displayLabel(display: AgentPillDisplayStatus): string {
  return DISPLAY_LABEL[display]
}

const DISPLAY_TINT: Record<AgentPillDisplayStatus, AgentPillTintToken> = {
  queued: 'queued',
  starting: 'queued',
  running: 'running',
  done: 'done',
  stopped: 'stopped',
  failed: 'failed'
}

/** The neutral tint token (never a raw color) B3 maps to a Tailwind class. */
export function displayTintToken(display: AgentPillDisplayStatus): AgentPillTintToken {
  return DISPLAY_TINT[display]
}

// ── Title derivation (Mac AgentPill.deriveTitle, cap 32 chars)

const TITLE_CAP = 32

function cap(text: string): string {
  return text.slice(0, TITLE_CAP).trim()
}

/** The pill title: the kernel-supplied title when non-empty, else the first
 *  ~3 words of the user's query. Both capped at 32 chars. Falls back to
 *  'Agent' only when neither is available (a pill must never be blank). */
export function deriveTitle(row: Pick<PillProjectionRow, 'title' | 'query'>): string {
  const title = typeof row.title === 'string' ? row.title.trim() : ''
  if (title) return cap(title)
  const query = typeof row.query === 'string' ? row.query.trim() : ''
  if (query) return cap(query.split(/\s+/).slice(0, 3).join(' '))
  return 'Agent'
}

// ── Projection merge (Mac mergeProjectedPills AgentPill.swift:1176-1244)

function nonEmpty(value: string | null | undefined): string | null {
  return typeof value === 'string' && value.trim() !== '' ? value : null
}

/** Resolve the error message for a display status. A `failed` pill MUST carry a
 *  non-empty message (falls back to 'Agent failed') so B3 always renders a
 *  visible error, never a silent stall. */
function resolveError(
  display: AgentPillDisplayStatus,
  rowError: string | null,
  existingError: string | null
): string | null {
  if (display === 'failed') {
    return nonEmpty(rowError) ?? nonEmpty(existingError) ?? 'Agent failed'
  }
  return nonEmpty(rowError) ?? existingError ?? null
}

function createPill(
  id: string,
  runId: string,
  sessionId: string,
  row: PillProjectionRow,
  nowMs: number
): AgentPill {
  const displayStatus = mapWireStatusToDisplay(normalizeWireStatus(row.status))
  const finished = isFinished(displayStatus)
  return {
    id,
    runId,
    sessionId,
    title: deriveTitle(row),
    displayStatus,
    latestActivity: typeof row.latestActivity === 'string' ? row.latestActivity : '',
    query: typeof row.query === 'string' ? row.query : '',
    createdAtMs: typeof row.createdAtMs === 'number' ? row.createdAtMs : null,
    completedAtMs: finished
      ? typeof row.completedAtMs === 'number'
        ? row.completedAtMs
        : nowMs
      : null,
    errorMessage: resolveError(displayStatus, row.errorMessage, null),
    provider: nonEmpty(row.provider),
    viewedAtMs: null
  }
}

function mergePill(existing: AgentPill, row: PillProjectionRow, nowMs: number): AgentPill {
  const nextDisplay = mapWireStatusToDisplay(normalizeWireStatus(row.status))
  const wasFinished = isFinished(existing.displayStatus)

  // No resurrection (Mac AgentPill.swift:1581-1583): once a pill is finished, a
  // later NON-terminal projection (e.g. a stale poll returning 'running') is
  // ignored wholesale — the pill stays exactly as it finished.
  if (wasFinished && !isFinished(nextDisplay)) {
    return existing
  }

  const becameFinished = !wasFinished && isFinished(nextDisplay)
  const completedAtMs = becameFinished
    ? typeof row.completedAtMs === 'number'
      ? row.completedAtMs
      : nowMs
    : existing.completedAtMs

  return {
    ...existing,
    title: deriveTitle(row),
    displayStatus: nextDisplay,
    latestActivity: nonEmpty(row.latestActivity) ?? existing.latestActivity,
    query: nonEmpty(row.query) ?? existing.query,
    createdAtMs:
      existing.createdAtMs ?? (typeof row.createdAtMs === 'number' ? row.createdAtMs : null),
    completedAtMs,
    errorMessage: resolveError(nextDisplay, row.errorMessage, existing.errorMessage),
    provider: nonEmpty(row.provider) ?? existing.provider,
    // Local-only field must survive every merge.
    viewedAtMs: existing.viewedAtMs
  }
}

/**
 * Merge freshly projected rows into the current pills.
 *  - New id → create a pill.
 *  - Known id → update in place (order preserved).
 *  - A row missing `id`, `sessionId`, or `runId` is DROPPED and counted in
 *    `droppedMissingId`.
 *  - Existing pills absent from `rows` are KEPT (removal is the job of
 *    `expireViewedFinished` / `trimForSoftCap`, not the merge).
 *  - A finished pill is never resurrected by a later non-terminal row.
 */
export function mergeProjectedPills(
  existing: AgentPill[],
  rows: PillProjectionRow[],
  nowMs: number
): { pills: AgentPill[]; droppedMissingId: number } {
  const pills = existing.slice()
  const indexById = new Map<string, number>()
  pills.forEach((pill, i) => indexById.set(pill.id, i))

  let droppedMissingId = 0
  for (const row of rows) {
    const id = nonEmpty(row.id)
    const runId = nonEmpty(row.runId)
    const sessionId = nonEmpty(row.sessionId)
    if (!id || !runId || !sessionId) {
      droppedMissingId += 1
      continue
    }
    const idx = indexById.get(id)
    if (idx === undefined) {
      indexById.set(id, pills.length)
      pills.push(createPill(id, runId, sessionId, row, nowMs))
    } else {
      pills[idx] = mergePill(pills[idx], row, nowMs)
    }
  }
  return { pills, droppedMissingId }
}

// ── Lifecycle after completion (Mac spec §d)

/** Stamp `viewedAtMs` on a FINISHED pill (arms its viewed-TTL). A no-op on a
 *  non-finished pill or an unknown id. Returns a new array. */
export function markViewed(pills: AgentPill[], pillId: string, nowMs: number): AgentPill[] {
  return pills.map((pill) =>
    pill.id === pillId && isFinished(pill.displayStatus) ? { ...pill, viewedAtMs: nowMs } : pill
  )
}

/**
 * Remove finished pills the user has already viewed once their TTL has elapsed.
 * NEVER removes the currently-active pill. Unviewed finished pills and any
 * non-finished pill are exempt (they never timer-expire).
 */
export function expireViewedFinished(
  pills: AgentPill[],
  nowMs: number,
  ttlMs: number = VIEWED_FINISHED_TTL_MS,
  activePillId: string | null = null
): AgentPill[] {
  return pills.filter((pill) => {
    if (pill.id === activePillId) return true
    if (!isFinished(pill.displayStatus)) return true
    if (pill.viewedAtMs === null) return true
    return nowMs - pill.viewedAtMs <= ttlMs
  })
}

function ageOf(pill: AgentPill): number {
  // Older = smaller createdAtMs. A pill with no timestamp is treated as newest
  // so pills of known age are evicted first.
  return pill.createdAtMs ?? Number.POSITIVE_INFINITY
}

/**
 * Under soft-cap pressure, evict the oldest FINISHED 'done' pill first, then
 * the oldest finished pill of any kind. NEVER evicts the active pill and NEVER
 * a non-finished pill (so the cap is soft — it may be exceeded when everything
 * over it is still running). Order is otherwise preserved.
 */
export function trimForSoftCap(
  pills: AgentPill[],
  activePillId: string | null,
  cap: number = SOFT_CAP
): AgentPill[] {
  if (pills.length <= cap) return pills
  let result = pills.slice()
  while (result.length > cap) {
    const evictable = result.filter((p) => p.id !== activePillId && isFinished(p.displayStatus))
    if (evictable.length === 0) break
    const done = evictable.filter((p) => p.displayStatus === 'done')
    const pool = done.length > 0 ? done : evictable
    const victim = pool.reduce((oldest, p) => (ageOf(p) < ageOf(oldest) ? p : oldest))
    result = result.filter((p) => p !== victim)
  }
  return result
}
