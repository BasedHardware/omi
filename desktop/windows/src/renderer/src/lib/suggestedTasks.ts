import { omiApi } from './apiClient'
import { getCacheUid } from './persistentCache'
import type { CandidateRecord, CandidateStatus, TaskWorkflowControl } from './omiApi.generated'

// Suggested tasks (mac parity: SuggestedTasksStore). Backed by the canonical
// Candidates API: the control gate decides whether the account's task workflow is
// in read mode at all, pending create-task candidates project into cards, a
// per-owner suppression map keeps rejected/deferred cards away, and the visible
// set is hard-capped. Accept/reject terminalize server-side; attribution feedback
// is fire-and-forget here (mac's durable feedback outbox is a follow-up).

/** The generated CandidateRecord union omits the envelope fields the backend
 *  actually returns on every record (mac reads record.candidateId etc.); extend
 *  it locally rather than trusting the lossy generated shape. */
type CandidateWire = CandidateRecord & {
  candidate_id?: string
  status?: CandidateStatus | null
  created_at?: string
}

export type ProjectedCandidate = {
  id: string
  title: string
  detail: string | null
  /** Wire created_at, kept for the deterministic intervention expiry (mac:
   *  deterministicInterventionExpiry). Null when the record carries none. */
  createdAt: string | null
}

export type SuggestedCandidate = ProjectedCandidate & {
  /** The control's account generation, stamped at load time and echoed on
   *  accept/reject and feedback headers. */
  accountGeneration: number
}

export type SuggestedLoadResult = {
  candidates: SuggestedCandidate[]
  /** The control's account generation — sent back on accept/reject. */
  accountGeneration: number
}

/** Mac's hard display cap (SuggestedTasksStore.maxVisibleCandidates). */
export const MAX_VISIBLE_SUGGESTED = 5

// Suppression windows (mac: dismiss = 30 days, later = 24 hours).
export const DISMISS_SUPPRESSION_MS = 30 * 24 * 60 * 60 * 1000
export const LATER_SUPPRESSION_MS = 24 * 60 * 60 * 1000

const SUPPRESSION_KEY_PREFIX = 'omi.suggestedSuppressions.v1.'

function suppressionKey(): string {
  return `${SUPPRESSION_KEY_PREFIX}${getCacheUid() ?? 'anon'}`
}

type SuppressionMap = Record<string, number>

function readSuppressions(now: number): SuppressionMap {
  try {
    const raw = window.localStorage.getItem(suppressionKey())
    if (!raw) return {}
    const parsed: unknown = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object') return {}
    const map: SuppressionMap = {}
    for (const [id, expiry] of Object.entries(parsed as Record<string, unknown>)) {
      if (typeof expiry === 'number' && expiry > now) map[id] = expiry
    }
    return map
  } catch {
    return {}
  }
}

function writeSuppressions(map: SuppressionMap): void {
  try {
    window.localStorage.setItem(suppressionKey(), JSON.stringify(map))
  } catch {
    // Quota failure degrades to a session-only suppression.
  }
}

export function suppressCandidate(id: string, durationMs: number, now: number = Date.now()): void {
  const map = readSuppressions(now)
  map[id] = now + durationMs
  writeSuppressions(map)
}

export function isSuppressed(id: string, now: number = Date.now()): boolean {
  return readSuppressions(now)[id] != null
}

/** Mac's project(_:) rule: only pending, create-task candidates with a non-empty
 *  description become cards. Updates/completions/workstream proposals stay out of
 *  the Suggested rail. */
export function projectCandidate(record: CandidateWire): ProjectedCandidate | null {
  const id = record.candidate_id
  if (!id) return null
  if (record.status != null && record.status !== 'pending') return null
  if (record.subject_kind != null && record.subject_kind !== 'task') return null
  if (record.proposed_action != null && record.proposed_action !== 'create') return null
  const change = record.task_change as { description?: unknown } | null | undefined
  const title = typeof change?.description === 'string' ? change.description.trim() : ''
  if (!title) return null
  const detailRaw = (change as { context_summary?: unknown } | null | undefined)?.context_summary
  return {
    id,
    title,
    detail: typeof detailRaw === 'string' && detailRaw.trim() ? detailRaw.trim() : null,
    createdAt: typeof record.created_at === 'string' ? record.created_at : null
  }
}

export type SuggestedDeps = {
  get?: typeof omiApi.get
  post?: typeof omiApi.post
  now?: () => number
}

/** Load the Suggested rail. Control-gated: anything but workflow read mode means
 *  an empty rail (mac clears candidates when control.workflowMode != .read). A
 *  404 from the list is "empty", not an error. */
export async function loadSuggestedCandidates(
  deps: SuggestedDeps = {}
): Promise<SuggestedLoadResult> {
  const get = deps.get ?? omiApi.get.bind(omiApi)
  const now = deps.now ?? Date.now

  const controlRes = await get('/v1/candidates/control')
  const control = (controlRes.data ?? {}) as TaskWorkflowControl
  const accountGeneration = control.account_generation ?? 0
  if (control.workflow_mode !== 'read') {
    return { candidates: [], accountGeneration }
  }

  let records: CandidateWire[] = []
  try {
    const listRes = await get('/v1/candidates', {
      params: { status: 'pending', limit: 100, offset: 0, surface: 'suggested' }
    })
    const data = listRes.data as { candidates?: CandidateWire[] } | null
    records = Array.isArray(data?.candidates) ? data.candidates : []
  } catch (e) {
    const status = (e as { response?: { status?: number } }).response?.status
    if (status === 404) return { candidates: [], accountGeneration }
    throw e
  }

  const suppressions = readSuppressions(now())
  const projected: SuggestedCandidate[] = []
  for (const record of records) {
    const card = projectCandidate(record)
    if (!card || suppressions[card.id] != null) continue
    projected.push({ ...card, accountGeneration })
    if (projected.length >= MAX_VISIBLE_SUGGESTED) break
  }
  return { candidates: projected, accountGeneration }
}

/** In-session intervention registrations by candidate (mac:
 *  SuggestedTasksStore.interventionIDs). The PROMISE is cached, not the id, so
 *  concurrent feedback sends share one in-flight registration; the server also
 *  dedupes on dedupe_key + Idempotency-Key, so a lost cache only costs an extra
 *  idempotent POST. */
const interventionRequests = new Map<string, Promise<string>>()

/** Test seam: the cache is module-level state. */
export function __resetInterventionCacheForTest(): void {
  interventionRequests.clear()
}

/** Mac's candidateRecommendationDedupeKey: `candidate_` + first 16 bytes of
 *  SHA-256(candidateId), hex. */
async function candidateDedupeKey(candidateId: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(candidateId))
  const prefix = [...new Uint8Array(digest).slice(0, 16)]
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('')
  return `candidate_${prefix}`
}

/** Mac's deterministicInterventionExpiry: created_at + 10 years, anchored to
 *  2100-01-01 when the record has no parseable created_at. */
function interventionExpiry(createdAt: string | null): string {
  const parsed = createdAt == null ? NaN : Date.parse(createdAt)
  const anchor = Number.isNaN(parsed) ? 4_102_444_800_000 : parsed
  return new Date(anchor + 10 * 365 * 24 * 60 * 60 * 1000).toISOString()
}

/** Register (or reuse) the presentation intervention for a candidate, mirroring
 *  mac's ensureIntervention. FeedbackCreate.validate_action REJECTS dismiss /
 *  later / do_now feedback without an intervention_id, so feedback must thread
 *  the returned id or the backend 422s and attribution never records. */
function ensureIntervention(
  post: typeof omiApi.post,
  candidate: SuggestedCandidate
): Promise<string> {
  const cached = interventionRequests.get(candidate.id)
  if (cached) return cached
  const registration = (async () => {
    const res = await post(
      '/v1/task-intelligence/interventions',
      {
        surface: 'suggested',
        subject_kind: 'candidate',
        subject_id: candidate.id,
        dedupe_key: await candidateDedupeKey(candidate.id),
        expires_at: interventionExpiry(candidate.createdAt)
      },
      {
        headers: {
          'Idempotency-Key': `suggested-presentation:${candidate.id}`,
          'X-Account-Generation': candidate.accountGeneration
        }
      }
    )
    const record = res.data as { intervention_id?: string } | null
    const interventionId = record?.intervention_id
    if (!interventionId) throw new Error('intervention response carried no intervention_id')
    return interventionId
  })()
  // A failed registration must not poison the cache; the next send retries.
  interventionRequests.set(
    candidate.id,
    registration.catch((e) => {
      interventionRequests.delete(candidate.id)
      throw e
    })
  )
  return interventionRequests.get(candidate.id) as Promise<string>
}

/** Fire-and-forget attribution. Registers the presentation intervention first
 *  and threads its id into the generated FeedbackCreate shape (mac's
 *  recordOrQueueFeedback order); the endpoint requires both the idempotency key
 *  and the account generation header. */
function sendFeedback(
  post: typeof omiApi.post,
  candidate: SuggestedCandidate,
  action: 'accept_candidate' | 'dismiss'
): void {
  void (async () => {
    const interventionId = await ensureIntervention(post, candidate)
    await post(
      '/v1/task-intelligence/feedback',
      {
        action,
        subject_id: candidate.id,
        subject_kind: 'candidate',
        intervention_id: interventionId
      },
      {
        headers: {
          'Idempotency-Key': `suggested:${candidate.id}:${action}`,
          'X-Account-Generation': candidate.accountGeneration
        }
      }
    )
  })().catch(() => {
    // Attribution is best-effort in this first Windows cut; mac queues failures
    // in a durable outbox — tracked as a follow-up.
  })
}

export async function acceptSuggestedCandidate(
  candidate: SuggestedCandidate,
  deps: SuggestedDeps = {}
): Promise<{ taskId: string | null }> {
  const post = deps.post ?? omiApi.post.bind(omiApi)
  const res = await post(
    `/v1/candidates/${candidate.id}/accept`,
    {},
    { headers: { 'X-Account-Generation': candidate.accountGeneration } }
  )
  sendFeedback(post, candidate, 'accept_candidate')
  const receipt = res.data as { task_id?: string | null } | null
  return { taskId: receipt?.task_id ?? null }
}

export async function rejectSuggestedCandidate(
  candidate: SuggestedCandidate,
  deps: SuggestedDeps = {}
): Promise<void> {
  const post = deps.post ?? omiApi.post.bind(omiApi)
  const now = deps.now ?? Date.now
  await post(
    `/v1/candidates/${candidate.id}/reject`,
    { reason: null },
    { headers: { 'X-Account-Generation': candidate.accountGeneration } }
  )
  // Mac persists the 30-day suppression once the reject sticks.
  suppressCandidate(candidate.id, DISMISS_SUPPRESSION_MS, now())
  sendFeedback(post, candidate, 'dismiss')
}
