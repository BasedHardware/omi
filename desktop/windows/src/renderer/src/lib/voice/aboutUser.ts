// The <about_user> card injected into the realtime session's system instruction
// — Windows port of macOS AboutUserCard.swift. Identity + rough situation only,
// so the voice assistant knows WHO it is talking to and never invents facts
// about them. Best-effort: any failure degrades to a smaller card, never throws.
//
// Never blocks the voice warm path (macOS RealtimeHubController.aboutUserCard is
// a cached ivar refreshed off the hot path): `getAboutUserCard()` is a synchronous
// cache read, and `refreshAboutUserCard()` is fire-and-forget. A cache miss emits
// no card at all rather than a card that falsely claims Omi knows nothing.
//
// PII: the card holds the user's name and memory contents — it is never logged.

import { auth } from '../firebase'
import { omiApi } from '../apiClient'
import { fetchTaskCounts, ZERO_TASK_COUNTS, type TaskCounts } from './taskCounts'

const MAX_FACTS = 8
const FACT_MAX_CHARS = 120

type MemoryRecord = { content?: string; created_at?: string }

export type AboutUserData = {
  name: string
  facts: string[]
  overdue: number
  dueToday: number
}

/** Pure formatter — kept separate from the build so it is unit-testable
 *  (AboutUserCard.render). Compact newline-joined block, no blank lines. */
export function renderAboutUserCard({ name, facts, overdue, dueToday }: AboutUserData): string {
  const lines = ['<about_user>']
  if (name) lines.push(`Name: ${name}`)
  lines.push('What Omi knows about them:')
  if (facts.length === 0) lines.push('- Nothing saved yet.')
  else for (const fact of facts) lines.push(`- ${fact}`)
  lines.push(
    overdue === 0 && dueToday === 0
      ? 'Right now: nothing overdue or due today.'
      : `Right now: ${overdue} overdue, ${dueToday} due today.`
  )
  // macOS ends this card with "(… call get_tasks / get_action_items.)". Windows'
  // voice surface advertises get_action_items but NOT get_tasks (no host executor —
  // see buildVoiceHubToolCatalog), so the pointer names only the tool the model can
  // actually call here.
  lines.push('(This is a quick snapshot — for the exact or current list, call get_action_items.)')
  lines.push('</about_user>')
  return lines.join('\n')
}

/** Trim + cap one memory to the card's per-fact budget (macOS: >120 chars →
 *  first 117 + "…"). Empty after trimming → null (dropped from the card). */
export function truncateFact(raw: string): string | null {
  const text = raw.trim()
  if (text.length === 0) return null
  return text.length > FACT_MAX_CHARS ? `${text.slice(0, FACT_MAX_CHARS - 3)}…` : text
}

function extractMemories(data: unknown): MemoryRecord[] {
  if (Array.isArray(data)) return data as MemoryRecord[]
  return ((data as { memories?: MemoryRecord[] })?.memories ?? []) as MemoryRecord[]
}

/** The user's newest memories, capped and truncated for the card. Any failure →
 *  no facts (the card still renders). Owns its own fetch: the Memories hook is a
 *  React hook with no synchronous getter, and is owned by another track. */
async function fetchFacts(): Promise<string[]> {
  try {
    const res = await omiApi.get('/v3/memories', { params: { limit: MAX_FACTS, offset: 0 } })
    // The server ignores `limit` at offset 0 and returns everything, unsorted —
    // sort newest-first ourselves before taking the top N (same as the Memories page).
    return extractMemories(res.data)
      .slice()
      .sort((a, b) => new Date(b.created_at ?? 0).getTime() - new Date(a.created_at ?? 0).getTime())
      .slice(0, MAX_FACTS)
      .map((m) => truncateFact(m.content ?? ''))
      .filter((f): f is string => f !== null)
  } catch {
    return []
  }
}

/** Gather the card's data (auth name, top memories, task counts) and render it.
 *  Fetchers are injectable so the assembly is testable without a network. */
export async function buildAboutUserCard(deps?: {
  name?: () => string
  facts?: () => Promise<string[]>
  counts?: () => Promise<TaskCounts>
}): Promise<string> {
  const name = (deps?.name ?? currentDisplayName)()
  const [facts, counts] = await Promise.all([
    (deps?.facts ?? fetchFacts)().catch(() => [] as string[]),
    (deps?.counts ?? fetchTaskCounts)().catch(() => ZERO_TASK_COUNTS)
  ])
  return renderAboutUserCard({ name, facts, overdue: counts.overdue, dueToday: counts.dueToday })
}

// Firebase Auth's displayName is the only account-level name Windows has (there
// is no `givenName` and no backend name endpoint — see lib/userProfile.ts).
function currentDisplayName(): string {
  return (auth.currentUser?.displayName ?? '').trim()
}

// ── Cache (read synchronously at session start, refreshed off the hot path) ────
// Keyed by uid so a cached card can never leak across an account switch.

let cached: { uid: string; card: string } | null = null
let inFlight: Promise<void> | null = null
// The uid the in-flight build was started for (see refreshAboutUserCard).
let inFlightUid = ''
// Bumped by resetAboutUserCard so an in-flight build from before the reset
// (e.g. the previous account's) can never land in the cache afterwards.
let generation = 0

/** The cached card, or '' when nothing has been built for this user yet (in
 *  which case the caller simply omits the block — never a stale/other-user card
 *  and never a blocking fetch). */
export function getAboutUserCard(): string {
  const uid = auth.currentUser?.uid ?? ''
  return cached && cached.uid === uid ? cached.card : ''
}

/** Rebuild the card in the background (fire-and-forget, deduped). Warmed at
 *  sign-in (App.tsx) and re-kicked at voice session start: THIS session uses
 *  whatever is cached, the next one gets the fresh card — a slightly stale card
 *  is acceptable, a slow session start is not. */
export function refreshAboutUserCard(): void {
  const uid = auth.currentUser?.uid ?? ''
  // Dedupe only against a build for the SAME account — an account switch must be
  // able to start its own build even while the previous one is still in flight.
  if (inFlight && inFlightUid === uid) return
  const gen = generation
  inFlightUid = uid
  const build = buildAboutUserCard()
    .then((card) => {
      // Cache only if that account is still the signed-in one. The build's fetches
      // ran against whatever token was current when they landed, so an account
      // switch mid-build would otherwise file the NEW user's name and memories
      // under the OLD uid — and serve them back if the old account returned.
      if (gen === generation && (auth.currentUser?.uid ?? '') === uid) cached = { uid, card }
    })
    .catch(() => {
      /* best-effort: keep whatever card we already had */
    })
    .finally(() => {
      if (inFlight === build) inFlight = null
    })
  inFlight = build
}

/** Await the in-flight refresh — tests only (production never blocks on this). */
export function whenAboutUserCardSettled(): Promise<void> {
  return inFlight ?? Promise.resolve()
}

/** Drop the cached card and abandon any in-flight build. Called on sign-out
 *  (App.tsx) so a card can never outlive the account it was built for, and by
 *  tests to reset module state. */
export function resetAboutUserCard(): void {
  cached = null
  inFlight = null
  inFlightUid = ''
  generation++
}
