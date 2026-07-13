/**
 * One-time, user-confirmed backfill of pre-sync local screen recordings
 * ("Sync past recordings" in Conversations).
 *
 * Legacy rows only kept a DISPLAY transcript (no raw segments), so segments are
 * synthesized from the transcript text: speaker-prefixed lines become segments
 * with times spread proportionally (by text length) across the recording's real
 * duration. Posting is paced to stay under the from-segments rate limit
 * (30/hour → we use at most 25/hour, persisted across runs in localStorage), so
 * a large backlog syncs across multiple user-triggered runs — each row's outbox
 * state persists, which is what makes the whole thing resumable.
 */
import { queueForSync } from './outbox'
import { syncLocalConversation } from './conversationSync'
import { POST_HISTORY_KEY } from './backfillStorageKey'
import type { LocalConversation, SyncSegment } from '../../../../shared/types'

export { POST_HISTORY_KEY }

export const BACKFILL_HOURLY_CAP = 25 // headroom under the 30/hour from-segments limit
const HOUR_MS = 3_600_000
/** Pause between posts within one run — keeps the burst gentle. */
export const BACKFILL_PACE_MS = 2_000

/** Legacy local screen recordings eligible for backfill: recordings that never
 * entered the sync pipeline and actually have transcript text to sync. Failed /
 * unconfirmed rows are NOT backfill candidates — the retry pass owns those. */
export function backfillCandidates(locals: LocalConversation[]): LocalConversation[] {
  return locals.filter(
    (c) =>
      (c.kind ?? 'recording') === 'recording' &&
      (c.syncState ?? 'local_only') === 'local_only' &&
      c.transcript.trim().length > 0
  )
}

/** Which of `candidateIds` may post now given the persisted post history, and —
 * when capped — how long until the next slot frees up. */
export function planBackfill(
  candidateIds: string[],
  recentPostTimes: number[],
  now: number,
  cap = BACKFILL_HOURLY_CAP
): { postNow: string[]; waitMs: number | null } {
  const inWindow = recentPostTimes.filter((t) => now - t < HOUR_MS).sort((a, b) => a - b)
  const allowed = Math.max(0, cap - inWindow.length)
  const postNow = candidateIds.slice(0, allowed)
  const capped = candidateIds.length > postNow.length
  const waitMs = capped && inWindow.length > 0 ? Math.max(0, inWindow[0] + HOUR_MS - now) : capped ? HOUR_MS : null
  return { postNow, waitMs }
}

// Display-transcript parsing ------------------------------------------------

const LANE_HEADERS = new Map<string, 'mic' | 'system'>([
  ['microphone:', 'mic'],
  ['system audio:', 'system']
])

/**
 * Synthesize from-segments transcript segments out of a saved DISPLAY transcript
 * (formatTranscript's output): optional "Microphone:" / "System audio:" block
 * headers, lines optionally prefixed "Speaker: text". Times are spread across
 * [0, durationSec] proportionally to text length; speakers map to stable ids
 * ('You' → 0/is_user, others sequential).
 */
export function transcriptToSegments(transcript: string, durationSec: number): SyncSegment[] {
  type Parsed = { text: string; speakerLabel: string | null; lane: 'mic' | 'system' }
  const parsed: Parsed[] = []
  let lane: 'mic' | 'system' = 'mic'
  for (const rawLine of transcript.split('\n')) {
    const line = rawLine.trim()
    if (!line) continue
    const header = LANE_HEADERS.get(line.toLowerCase())
    if (header) {
      lane = header
      continue
    }
    const m = line.match(/^([^:]{1,40}):\s+(.*)$/)
    if (m && m[2].trim()) parsed.push({ text: m[2].trim(), speakerLabel: m[1].trim(), lane })
    else parsed.push({ text: line, speakerLabel: null, lane })
  }
  if (parsed.length === 0) return []

  // Stable speaker ids: 'You' (mic) is the user with id 0; every other distinct
  // label — and each lane's unlabeled bucket — gets the next id.
  const idByLabel = new Map<string, number>()
  let nextId = 1
  const speakerIdFor = (p: Parsed): { id: number; isUser: boolean; label: string } => {
    if (p.lane === 'mic' && (p.speakerLabel === 'You' || p.speakerLabel === null)) {
      return { id: 0, isUser: true, label: 'You' }
    }
    const key = p.speakerLabel ? `label:${p.speakerLabel}` : `lane:${p.lane}`
    if (!idByLabel.has(key)) idByLabel.set(key, nextId++)
    const id = idByLabel.get(key)!
    return { id, isUser: false, label: p.speakerLabel ?? `SPEAKER_${id}` }
  }

  const totalChars = parsed.reduce((n, p) => n + p.text.length, 0)
  const duration = Math.max(durationSec, 1)
  let cursorChars = 0
  return parsed.map((p) => {
    const start = (cursorChars / totalChars) * duration
    cursorChars += p.text.length
    const end = (cursorChars / totalChars) * duration
    const sp = speakerIdFor(p)
    return {
      text: p.text,
      speaker: sp.label,
      speaker_id: sp.id,
      is_user: sp.isUser,
      person_id: null,
      start: Math.round(start * 100) / 100,
      end: Math.round(end * 100) / 100
    }
  })
}

// Runner ---------------------------------------------------------------------

function readPostHistory(): number[] {
  try {
    const v = JSON.parse(localStorage.getItem(POST_HISTORY_KEY) ?? '[]')
    return Array.isArray(v) ? v.filter((t) => typeof t === 'number') : []
  } catch {
    return []
  }
}

function recordPost(now: number): void {
  const next = [...readPostHistory().filter((t) => now - t < HOUR_MS), now]
  localStorage.setItem(POST_HISTORY_KEY, JSON.stringify(next))
}

export type BackfillProgress = { total: number; synced: number; failed: number; capped: boolean }

/**
 * Post as many backfill candidates as the hourly budget allows, serially and
 * paced. Each row first gets its synthesized segments persisted (so a crash or
 * cap mid-run leaves resumable 'pending' rows), then rides the normal outbox.
 */
export async function runBackfill(
  locals: LocalConversation[],
  onProgress?: (p: BackfillProgress) => void
): Promise<BackfillProgress> {
  const candidates = backfillCandidates(locals)
  const plan = planBackfill(
    candidates.map((c) => c.id),
    readPostHistory(),
    Date.now()
  )
  const byId = new Map(candidates.map((c) => [c.id, c]))
  const progress: BackfillProgress = {
    total: candidates.length,
    synced: 0,
    failed: 0,
    capped: plan.postNow.length < candidates.length
  }
  for (let i = 0; i < plan.postNow.length; i++) {
    if (i > 0) await new Promise((r) => setTimeout(r, BACKFILL_PACE_MS))
    const c = byId.get(plan.postNow[i])!
    const segments = transcriptToSegments(c.transcript, Math.max(1, (c.endedAt - c.startedAt) / 1000))
    if (segments.length === 0) {
      progress.failed++
      onProgress?.({ ...progress })
      continue
    }
    // Persist segments + queue the row BEFORE posting (resumable on crash/cap).
    const queued = queueForSync(c, segments)
    await window.omi.insertLocalConversation(queued)
    recordPost(Date.now())
    const out = await syncLocalConversation(queued)
    if (out?.status === 'done') progress.synced++
    else progress.failed++
    onProgress?.({ ...progress })
  }
  return progress
}
