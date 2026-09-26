import { createHash } from 'node:crypto'
import { describe, expect, it } from 'vitest'
import {
  parseJitLedgerMirrorPage,
  parseJitProactivityReservation,
  parseJitRolloutDecision,
  parseJitTriggerSnapshot
} from './jitAuthorityClient'

describe('Windows JIT authority wire parsing', () => {
  it('maps the authenticated snake_case rollout envelope', () => {
    expect(
      parseJitRolloutDecision({
        rollout: 'enabled',
        kill_switch: 'disabled',
        effective: 'enabled',
        reason: 'evaluated',
        error_class: 'none'
      })
    ).toEqual({
      rollout: 'enabled',
      killSwitch: 'disabled',
      effective: 'enabled',
      reason: 'evaluated',
      errorClass: 'none'
    })
  })

  it('maps the complete trigger snapshot and rejects malformed rows', () => {
    const parsed = parseJitTriggerSnapshot({
      owner_id: 'u',
      account_generation: 2,
      head_commit_id: 'h',
      commit_sequence: 3,
      snapshot_revision: 'r',
      complete: true,
      policy: {
        schema_version: 'jit_trigger_policy.v1',
        planned_notifications_per_trigger_per_day: 1,
        total_proactive_notifications_per_day: 3,
        ambiguous_nano_triages_per_day: 8,
        full_agent_turns_per_candidate: 1,
        max_calendar_events: 32,
        embedding: {
          enabled: false,
          match_similarity: 0.82,
          triage_similarity: 0.74,
          model_id: null,
          model_version: null,
          language: null
        }
      },
      rows: [
        {
          memory_id: 't',
          item_revision: 1,
          updated_at: '2026-08-24T12:00:00Z',
          trigger_condition_json: '{}',
          action: { type: 'agent_prompt', prompt: 'p' },
          wakeup_budget_per_day: null,
          snoozed_until: null
        }
      ]
    })
    expect(parsed.rows[0].memoryId).toBe('t')
    expect(parsed.policy.totalProactiveNotificationsPerDay).toBe(3)
    expect(() =>
      parseJitTriggerSnapshot({
        owner_id: 'u',
        account_generation: 2,
        commit_sequence: 3,
        head_commit_id: 'h',
        snapshot_revision: 'r',
        complete: true,
        rows: [
          {
            memory_id: 't',
            item_revision: 1,
            updated_at: 'now',
            trigger_condition_json: '{}',
            action: { type: 'wrong', prompt: 'p' }
          }
        ]
      })
    ).toThrow('malformed')
    expect(() =>
      parseJitTriggerSnapshot({
        owner_id: 'u',
        account_generation: 2,
        commit_sequence: 3,
        head_commit_id: 'h',
        snapshot_revision: 'r',
        complete: true,
        policy: {
          schema_version: 'jit_trigger_policy.v1',
          planned_notifications_per_trigger_per_day: 1,
          total_proactive_notifications_per_day: 3,
          ambiguous_nano_triages_per_day: 8,
          full_agent_turns_per_candidate: 1,
          max_calendar_events: 32,
          embedding: {
            enabled: false,
            match_similarity: 0.82,
            triage_similarity: 0.74,
            model_id: null,
            model_version: null,
            language: null
          }
        },
        rows: [
          {
            memory_id: 't',
            item_revision: 1,
            updated_at: '2026-08-24T12:00:00Z',
            trigger_condition_json: '{}',
            action: { type: 'agent_prompt', prompt: 'p' },
            wakeup_budget_per_day: 1,
            snoozed_until: '2026-08-24T13:00:00'
          }
        ]
      })
    ).toThrow('snooze')
  })

  it('maps the fenced ledger mirror page without accepting content-free malformed rows', () => {
    const parsed = parseJitLedgerMirrorPage({
      schema_version: 'knowledge_ledger_mirror.v1',
      owner_id: 'u',
      account_generation: 2,
      source_generation: 3,
      writer_epoch: 4,
      head_commit_id: 'h',
      commit_sequence: 5,
      epoch_id: 'epoch',
      page_revision: 'page',
      chain_revision: 'chain',
      scanned_count: 1,
      projected_count: 1,
      terminal_count: 0,
      rows: [
        {
          memory_id: 'fact-1',
          item_revision: 2,
          status: 'active',
          source_state: 'attested',
          canonical_memory_id: null,
          content_purged: false,
          memory: { kind: 'fact', content: 'redacted from test output' }
        }
      ],
      aliases: [],
      next_cursor: null,
      final_page: true,
      failure_reason: null
    })
    expect(parsed.rows[0].memoryId).toBe('fact-1')
    expect(parsed.finalPage).toBe(true)
    expect(() => parseJitLedgerMirrorPage({ ...parsed })).toThrow('malformed')
  })

  it('keeps compatibility with the current mirror envelope when terminal_count is absent', () => {
    const parsed = parseJitLedgerMirrorPage({
      schema_version: 'knowledge_ledger_mirror.v1',
      owner_id: 'u',
      account_generation: 2,
      source_generation: 3,
      writer_epoch: 4,
      head_commit_id: 'h',
      commit_sequence: 5,
      epoch_id: 'epoch',
      page_revision: 'page',
      chain_revision: 'chain',
      scanned_count: 2,
      projected_count: 2,
      rows: [
        {
          memory_id: 'old-1',
          item_revision: 2,
          status: 'superseded',
          source_state: 'active',
          canonical_memory_id: 'fact-1',
          content_purged: false,
          memory: { kind: 'fact' }
        },
        {
          memory_id: 'fact-1',
          item_revision: 3,
          status: 'active',
          source_state: 'active',
          canonical_memory_id: null,
          content_purged: false,
          memory: { kind: 'fact' }
        }
      ],
      aliases: [],
      next_cursor: null,
      final_page: true,
      failure_reason: null
    })
    expect(parsed.terminalCount).toBe(1)
    expect(parsed.terminalCountFromServer).toBe(false)
  })

  it('requires a notification parent for full turns and validates hashed identities', () => {
    const eventId = 'a'.repeat(64)
    const candidateId = 'b'.repeat(64)
    const deviceId = 'c'.repeat(64)
    const parentEventId = 'd'.repeat(64)
    const expected = {
      eventId,
      candidateId,
      operation: 'full_turn' as const,
      accountGeneration: 3,
      deviceId,
      triggerMemoryId: 'trigger-1',
      triggerRevision: 2,
      parentEventId
    }
    const requestHash = createHash('sha256')
      .update(
        JSON.stringify({
          account_generation: 3,
          candidate_id: candidateId,
          device_id: deviceId,
          event_id: eventId,
          operation: 'full_turn',
          parent_event_id: parentEventId,
          schema_version: 'jit_proactivity_event.v1',
          trigger_memory_id: 'trigger-1',
          trigger_revision: 2,
          uid: 'u'
        })
      )
      .digest('hex')
    const parsed = parseJitProactivityReservation(
      {
        reserved: true,
        receipt: {
          schema_version: 'jit_proactivity_event.v1',
          uid: 'u',
          event_id: eventId,
          candidate_id: candidateId,
          operation: 'full_turn',
          account_generation: 3,
          trigger_memory_id: 'trigger-1',
          trigger_revision: 2,
          parent_event_id: parentEventId,
          budget_day: '2026-08-24',
          device_id: deviceId,
          created_at: '2026-08-24T12:00:00.000Z',
          request_hash: requestHash,
          feedback_id: null
        }
      },
      expected,
      'u'
    )
    expect(parsed.receipt.parentEventId).toBe(parentEventId)
    expect(() =>
      parseJitProactivityReservation(
        {
          reserved: true,
          receipt: { ...parsed.receipt, parent_event_id: 'f'.repeat(64) }
        },
        expected,
        'u'
      )
    ).toThrow('malformed')
  })
})
