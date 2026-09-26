import {
  listPendingJitFeedback,
  markJitFeedbackResult,
  markJitFeedbackSending,
  markJitFeedbackUnsupported,
  type JitFeedbackOutboxEntry,
  type JitMirrorDb
} from './jitTriggerMirror'
import { fetchWithFreshToken, getAbortSignal, getBackendSession } from '../assistants/core/session'

/** Injectable feedback transport. Local enqueue is never treated as a server
 * success; the typed HTTP implementation below drains it only after the
 * authenticated backend receipt is returned. */
export type JitFeedbackTransport = (entry: JitFeedbackOutboxEntry) => Promise<void>

export type JitFeedbackTransportDeps = {
  fetch?: typeof fetch
  session?: () => ReturnType<typeof getBackendSession>
  signal?: () => AbortSignal | undefined
}

function tokenOwnerId(token: string): string | null {
  try {
    const payload = JSON.parse(
      Buffer.from(token.split('.')[1] ?? '', 'base64').toString('utf8')
    ) as {
      sub?: unknown
      user_id?: unknown
    }
    const owner = payload.user_id ?? payload.sub
    return typeof owner === 'string' && owner.trim() ? owner.trim() : null
  } catch {
    return null
  }
}

/** The backend feedback route is explicit and idempotent; local enqueue still
 * remains pending until this transport receives a successful response. */
export function createJitFeedbackTransport(
  deps: JitFeedbackTransportDeps = {}
): JitFeedbackTransport {
  const doFetch = deps.fetch ?? fetch
  const session = deps.session ?? getBackendSession
  const signal = deps.signal ?? getAbortSignal
  return async (entry) => {
    const current = session()
    if (
      !current ||
      tokenOwnerId(current.token) !== entry.ownerId ||
      entry.triggerRevision === null ||
      !Number.isInteger(entry.triggerRevision) ||
      entry.triggerRevision < 1
    )
      throw new Error('jit feedback authority unavailable')
    const response = await fetchWithFreshToken(
      async (current) =>
        doFetch(`${current.apiBase}/v1/jit/trigger-feedback`, {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${current.token}`,
            'Content-Type': 'application/json',
            'X-App-Platform': 'windows'
          },
          signal: signal(),
          body: JSON.stringify({
            feedback_id: entry.eventId,
            event_id: entry.eventId,
            trigger_memory_id: entry.subjectId,
            account_generation: entry.accountGeneration,
            trigger_revision: entry.triggerRevision,
            action: entry.action,
            recorded_at: new Date(entry.occurredAt).toISOString(),
            ...(entry.snoozedUntil ? { snoozed_until: entry.snoozedUntil } : {})
          })
        }),
      'jit:feedback'
    )
    if (!response.ok) throw new Error(`jit feedback http ${response.status}`)
    const body = (await response.json()) as unknown
    if (!body || typeof body !== 'object' || Array.isArray(body))
      throw new Error('malformed jit feedback response')
    const envelope = body as Record<string, unknown>
    const receipt = envelope.receipt
    if (
      typeof envelope.applied !== 'boolean' ||
      envelope.trigger_memory_id !== entry.subjectId ||
      typeof envelope.trigger_revision !== 'number' ||
      !Number.isInteger(envelope.trigger_revision) ||
      envelope.trigger_revision < 1 ||
      typeof envelope.trigger_status !== 'string' ||
      envelope.trigger_status.length === 0 ||
      !receipt ||
      typeof receipt !== 'object' ||
      Array.isArray(receipt)
    )
      throw new Error('malformed jit feedback response')
    const parsed = receipt as Record<string, unknown>
    const appliedRevision = parsed.applied_trigger_revision
    if (
      parsed.schema_version !== 'jit_trigger_feedback.v1' ||
      parsed.uid !== entry.ownerId ||
      parsed.feedback_id !== entry.eventId ||
      parsed.event_id !== entry.eventId ||
      parsed.trigger_memory_id !== entry.subjectId ||
      parsed.account_generation !== entry.accountGeneration ||
      parsed.expected_trigger_revision !== entry.triggerRevision ||
      parsed.action !== entry.action ||
      typeof parsed.recorded_at !== 'string' ||
      !Number.isFinite(Date.parse(parsed.recorded_at)) ||
      (appliedRevision !== null &&
        (typeof appliedRevision !== 'number' ||
          !Number.isInteger(appliedRevision) ||
          appliedRevision < 1)) ||
      (envelope.applied && appliedRevision !== envelope.trigger_revision) ||
      typeof parsed.request_hash !== 'string' ||
      !/^[a-f0-9]{64}$/.test(parsed.request_hash) ||
      (entry.action === 'snooze') !== (typeof parsed.snoozed_until === 'string')
    )
      throw new Error('malformed jit feedback receipt')
  }
}

export async function drainJitFeedback(
  db: JitMirrorDb,
  transport: JitFeedbackTransport,
  limit = 32,
  now = Date.now()
): Promise<{ sent: number; failed: number }> {
  let sent = 0
  let failed = 0
  for (const entry of listPendingJitFeedback(db, limit, now)) {
    if (entry.triggerRevision === null) {
      markJitFeedbackUnsupported(
        db,
        entry.eventId,
        'ambient feedback has no supported trigger revision receipt',
        now
      )
      failed++
      continue
    }
    markJitFeedbackSending(db, entry.eventId, now)
    try {
      await transport(entry)
      markJitFeedbackResult(db, entry.eventId, true, undefined, now)
      sent++
    } catch (error) {
      markJitFeedbackResult(
        db,
        entry.eventId,
        false,
        error instanceof Error ? error.message : 'feedback transport failed',
        now
      )
      failed++
    }
  }
  return { sent, failed }
}

let retryTimer: ReturnType<typeof setTimeout> | null = null

/** Keep the durable feedback outbox live across launch, auth changes, and
 * transient network failures. The outbox's persisted next_attempt_at controls
 * backoff; this loop is only a bounded wake-up, never an unbounded retry storm. */
export function startJitFeedbackRetryLoop(
  db: JitMirrorDb,
  transport: JitFeedbackTransport,
  intervalMs = 30_000
): () => void {
  if (retryTimer) clearTimeout(retryTimer)
  let stopped = false
  const run = async (): Promise<void> => {
    if (stopped) return
    try {
      await drainJitFeedback(db, transport, 8)
    } catch {
      /* The next scheduled pass re-reads persisted due rows. */
    }
    if (stopped) return
    retryTimer = setTimeout(() => void run(), intervalMs)
    retryTimer.unref?.()
  }
  void run()
  return () => {
    stopped = true
    if (retryTimer) clearTimeout(retryTimer)
    retryTimer = null
  }
}
