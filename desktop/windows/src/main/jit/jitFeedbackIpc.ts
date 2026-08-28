import { ipcMain } from 'electron'
import { getBackendSession } from '../assistants/core/session'
import { getJitDatabase } from '../ipc/db'
import { enqueueJitFeedback, type JitFeedbackAction, type JitMirrorDb } from './jitTriggerMirror'
import { createJitFeedbackTransport, drainJitFeedback } from './jitFeedback'

const ACTIONS: readonly JitFeedbackAction[] = [
  'useful',
  'false_positive',
  'snooze',
  'disable',
  'missed_or_late'
]

function ownerFromToken(token: string): string | null {
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

export function registerJitFeedbackHandlers(): void {
  const db = getJitDatabase() as unknown as JitMirrorDb
  ipcMain.handle(
    'jit:feedback',
    async (
      _event,
      input: {
        eventId: string
        lane: 'planned' | 'ambient'
        action: JitFeedbackAction
        subjectId: string
        triggerRevision: number | null
        accountGeneration: number
        snoozedUntil?: string | null
      }
    ): Promise<{ queued: true }> => {
      const session = getBackendSession()
      const ownerId = session ? ownerFromToken(session.token) : null
      if (
        !ownerId ||
        !ACTIONS.includes(input.action) ||
        typeof input.eventId !== 'string' ||
        (input.lane !== 'planned' && input.lane !== 'ambient') ||
        typeof input.subjectId !== 'string' ||
        (input.lane === 'planned' &&
          (typeof input.triggerRevision !== 'number' ||
            !Number.isInteger(input.triggerRevision) ||
            input.triggerRevision < 1)) ||
        // The backend feedback endpoint requires a trigger memory revision.
        // Ambient candidates have no such authority fence yet, so do not
        // expose or enqueue an action that can never receive a receipt.
        input.lane === 'ambient' ||
        !Number.isInteger(input.accountGeneration) ||
        input.accountGeneration < 0 ||
        (input.action === 'snooze') !== Boolean(input.snoozedUntil)
      )
        throw new Error('invalid jit feedback action')
      enqueueJitFeedback(db, {
        eventId: input.eventId,
        ownerId,
        accountGeneration: input.accountGeneration,
        action: input.action,
        subjectId: input.subjectId,
        triggerRevision: input.triggerRevision,
        occurredAt: Date.now(),
        snoozedUntil: input.snoozedUntil ?? null
      })
      // Attempt a bounded immediate drain for responsive authenticated use;
      // failures remain persisted with next_attempt_at for the launch/backoff
      // loop and are never reported as success here.
      await drainJitFeedback(db, createJitFeedbackTransport(), 8).catch(() => undefined)
      return { queued: true }
    }
  )
  ipcMain.handle(
    'jit:feedbackDrain',
    async (): Promise<{ sent: number; failed: number }> =>
      drainJitFeedback(db, createJitFeedbackTransport())
  )
}
