import { DatabaseSync } from 'node:sqlite'
import { describe, expect, it } from 'vitest'
import { createJitFeedbackTransport, drainJitFeedback } from './jitFeedback'
import { setBackendSession } from '../assistants/core/session'
import {
  enqueueJitFeedback,
  initializeJitTriggerMirror,
  listPendingJitFeedback,
  type JitMirrorDb
} from './jitTriggerMirror'

describe('Windows JIT feedback boundary', () => {
  it('retries transport failures from the durable outbox and never fabricates success', async () => {
    const db = new DatabaseSync(':memory:')
    const mirror = db as unknown as JitMirrorDb
    initializeJitTriggerMirror(mirror)
    enqueueJitFeedback(mirror, {
      eventId: 'a'.repeat(64),
      ownerId: 'user-1',
      accountGeneration: 3,
      action: 'missed_or_late',
      subjectId: 'trigger-1',
      triggerRevision: 1,
      occurredAt: 100,
      snoozedUntil: null
    })
    const first = await drainJitFeedback(
      mirror,
      async () => {
        throw new Error('endpoint unavailable')
      },
      32,
      100
    )
    expect(first).toEqual({ sent: 0, failed: 1 })
    expect(db.prepare('SELECT state, attempts FROM jit_feedback_outbox').get()).toEqual({
      state: 'failed',
      attempts: 1
    })
    const second = await drainJitFeedback(mirror, async () => {}, 32, 30_100)
    expect(second).toEqual({ sent: 1, failed: 0 })
    expect(db.prepare('SELECT state, attempts FROM jit_feedback_outbox').get()).toEqual({
      state: 'complete',
      attempts: 2
    })
  })

  it('uses the typed backend feedback contract when an authority session exists', async () => {
    const token = `header.${Buffer.from(JSON.stringify({ sub: 'user-1' })).toString('base64')}.signature`
    const eventId = 'a'.repeat(64)
    setBackendSession({ apiBase: 'https://api.test', desktopApiBase: '', token })
    let request: RequestInit | undefined
    const transport = createJitFeedbackTransport({
      fetch: async (_url, init) => {
        request = init
        return new Response(
          JSON.stringify({
            applied: true,
            trigger_memory_id: 'trigger-1',
            trigger_revision: 2,
            trigger_status: 'active',
            receipt: {
              schema_version: 'jit_trigger_feedback.v1',
              uid: 'user-1',
              feedback_id: eventId,
              event_id: eventId,
              trigger_memory_id: 'trigger-1',
              account_generation: 3,
              expected_trigger_revision: 2,
              action: 'missed_or_late',
              recorded_at: '2026-08-24T12:00:00.000Z',
              snoozed_until: null,
              request_hash: 'b'.repeat(64),
              applied_trigger_revision: 2
            }
          }),
          { status: 200 }
        )
      }
    })
    await transport({
      eventId,
      ownerId: 'user-1',
      accountGeneration: 3,
      action: 'missed_or_late',
      subjectId: 'trigger-1',
      triggerRevision: 2,
      occurredAt: Date.parse('2026-08-24T12:00:00Z'),
      snoozedUntil: null,
      attempts: 0,
      state: 'sending',
      lastError: null
    })
    expect(request?.method).toBe('POST')
    expect(JSON.parse(String(request?.body))).toMatchObject({
      feedback_id: eventId,
      trigger_memory_id: 'trigger-1',
      account_generation: 3,
      trigger_revision: 2,
      action: 'missed_or_late'
    })
    setBackendSession(null)
  })

  it('terminalizes legacy ambient rows as unsupported instead of retrying a null revision forever', async () => {
    const db = new DatabaseSync(':memory:')
    const mirror = db as unknown as JitMirrorDb
    initializeJitTriggerMirror(mirror)
    enqueueJitFeedback(mirror, {
      eventId: 'c'.repeat(64),
      ownerId: 'user-1',
      accountGeneration: 3,
      action: 'useful',
      subjectId: 'ambient:context-1',
      triggerRevision: null,
      occurredAt: 100,
      snoozedUntil: null
    })
    const result = await drainJitFeedback(
      mirror,
      async () => {
        throw new Error('must not call unsupported transport')
      },
      32,
      100
    )
    expect(result).toEqual({ sent: 0, failed: 1 })
    expect(db.prepare('SELECT state, last_error FROM jit_feedback_outbox').get()).toEqual({
      state: 'unsupported',
      last_error: 'ambient feedback has no supported trigger revision receipt'
    })
    expect(listPendingJitFeedback(mirror, 32, 100)).toEqual([])
  })
})
