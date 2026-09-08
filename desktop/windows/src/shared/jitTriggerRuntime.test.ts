import { describe, expect, it } from 'vitest'
import {
  compileTriggerSnapshotRow,
  evaluateJitTrigger,
  evaluateJitWatchlist,
  JIT_RUNTIME_DEFAULT_AUTHORITY,
  JitTriggerCompileError,
  type JitTriggerSnapshotRow
} from './jitTriggerRuntime'

const row = (
  condition: Record<string, unknown>,
  overrides: Partial<JitTriggerSnapshotRow> = {}
): JitTriggerSnapshotRow => ({
  memoryId: 'trigger-1',
  itemRevision: 1,
  updatedAt: '2026-08-24T12:00:00.000Z',
  triggerConditionJson: JSON.stringify({
    schema_version: 'jit_trigger.v1',
    match_mode: 'all',
    action: { type: 'agent_prompt', prompt: 'Follow up on the current work.' },
    ...condition
  }),
  action: { type: 'agent_prompt', prompt: 'Follow up on the current work.' },
  wakeupBudgetPerDay: 1,
  ...overrides
})

describe('Windows JIT trigger contract', () => {
  it('matches deterministic app and time conditions and respects the per-trigger budget', () => {
    const compiled = compileTriggerSnapshotRow(
      row({
        apps: ['Visual Studio Code'],
        time: { weekdays: [0], start: '08:00', end: '18:00', timezone: 'UTC' }
      })
    )
    const observation = {
      appName: 'visual studio code',
      occurredAt: new Date('2026-08-24T12:00:00Z')
    }
    const first = evaluateJitTrigger(compiled, observation, '2026-08-24')
    expect(first.status).toBe('match')
    expect(first.wakeupsUsed).toBe(1)
    expect(evaluateJitTrigger(compiled, observation, '2026-08-24', 1).reason).toBe(
      'wakeup_budget_exhausted'
    )
  })

  it('fails closed when the daily wakeup budget is missing', () => {
    const compiled = compileTriggerSnapshotRow(
      row({ apps: ['Visual Studio Code'] }, { wakeupBudgetPerDay: null })
    )
    const result = evaluateJitTrigger(compiled, { appName: 'Visual Studio Code' }, '2026-08-24')
    expect(result.status).toBe('no_match')
    expect(result.reason).toBe('wakeup_budget_missing')
  })

  it('honors the authoritative timezone-aware trigger snooze and resumes at expiry', () => {
    const compiled = compileTriggerSnapshotRow(
      row({ apps: ['Visual Studio Code'] }, { snoozedUntil: '2026-08-24T13:00:00+01:00' })
    )
    expect(
      evaluateJitTrigger(
        compiled,
        { appName: 'Visual Studio Code', occurredAt: new Date('2026-08-24T11:59:59Z') },
        '2026-08-24'
      ).reason
    ).toBe('trigger_snoozed')
    expect(
      evaluateJitTrigger(
        compiled,
        { appName: 'Visual Studio Code', occurredAt: new Date('2026-08-24T12:00:00Z') },
        '2026-08-24'
      ).status
    ).toBe('match')
  })

  it('rejects a trigger snooze without an explicit timezone', () => {
    expect(() =>
      compileTriggerSnapshotRow(row({ apps: ['Code'] }, { snoozedUntil: '2026-08-24T13:00:00' }))
    ).toThrow('snooze malformed')
  })

  it('rejects impossible calendar dates instead of trusting Date.parse normalization', () => {
    expect(() =>
      compileTriggerSnapshotRow(row({ apps: ['Code'] }, { snoozedUntil: '2026-02-30T13:00:00Z' }))
    ).toThrow('snooze malformed')
  })

  it('does not guess when calendar or embedding evidence is absent/unattested', () => {
    const compiled = compileTriggerSnapshotRow(
      row({
        calendar: { event_keywords: ['planning'], event_types: [] },
        embedding: {
          prototype_id: 'proto',
          prototype_revision: 'r1',
          model_id: 'local',
          model_version: '1',
          language: 'en',
          min_similarity: 0.82
        }
      })
    )
    const result = evaluateJitTrigger(compiled, {}, '2026-08-24')
    expect(result.status).toBe('no_match')
    const attested = evaluateJitTrigger(
      compiled,
      {
        calendarEvents: [{ title: 'Planning', eventType: 'meeting' }],
        calendarAuthorized: true,
        embeddingScores: {
          proto: {
            score: 0.9,
            modelId: 'local',
            modelVersion: '1',
            language: 'en',
            prototypeRevision: 'r1'
          }
        }
      },
      '2026-08-24',
      0,
      { modelId: 'local', modelVersion: '1', language: 'en', prototypeRevision: 'r1' }
    )
    expect(attested.status).toBe('match')
  })

  it('uses the ratified .74-.82 embedding band for bounded triage', () => {
    const compiled = compileTriggerSnapshotRow(
      row({
        embedding: {
          prototype_id: 'proto',
          prototype_revision: 'r1',
          model_id: 'local',
          model_version: '1',
          language: 'en',
          min_similarity: 0.82
        }
      })
    )
    const contract = {
      modelId: 'local',
      modelVersion: '1',
      language: 'en',
      prototypeRevision: 'r1'
    }
    const score = (value: number) => ({
      embeddingScores: {
        proto: {
          score: value,
          modelId: 'local',
          modelVersion: '1',
          language: 'en',
          prototypeRevision: 'r1'
        }
      }
    })
    expect(evaluateJitTrigger(compiled, score(0.75), '2026-08-24', 0, contract).status).toBe(
      'ambiguous'
    )
    expect(evaluateJitTrigger(compiled, score(0.73), '2026-08-24', 0, contract).status).toBe(
      'no_match'
    )
  })

  it('rejects unknown and duplicate authority keys', () => {
    expect(() => compileTriggerSnapshotRow(row({ nope: true }))).toThrow(JitTriggerCompileError)
    expect(() =>
      compileTriggerSnapshotRow({
        ...row({}),
        triggerConditionJson:
          '{"schema_version":"jit_trigger.v1","schema_version":"jit_trigger.v1","match_mode":"all","action":{"type":"agent_prompt","prompt":"Follow up on the current work."}}'
      })
    ).toThrow(/duplicate|malformed/i)
  })

  it('keeps the runtime inactive unless the complete backend authority is current', () => {
    const compiled = compileTriggerSnapshotRow(row({ apps: ['Code'] }))
    const observation = { appName: 'Code' }
    expect(
      evaluateJitWatchlist(JIT_RUNTIME_DEFAULT_AUTHORITY, [compiled], observation, '2026-08-24')
        .status
    ).toBe('inactive')
    expect(
      evaluateJitWatchlist(
        {
          mode: 'enabled',
          killSwitchEnabled: false,
          ownerId: 'u',
          accountGeneration: 2,
          snapshotOwnerId: 'u',
          snapshotAccountGeneration: 2,
          snapshotIsAuthoritative: true,
          authorizationIsCurrent: true
        },
        [compiled],
        observation,
        '2026-08-24'
      ).nextLane
    ).toBe('planned_trigger')
    expect(
      evaluateJitWatchlist(
        {
          mode: 'enabled',
          killSwitchEnabled: false,
          ownerId: 'u',
          accountGeneration: 2,
          snapshotOwnerId: 'u',
          snapshotAccountGeneration: 2,
          snapshotIsAuthoritative: true,
          authorizationIsCurrent: true
        },
        [],
        observation,
        '2026-08-24'
      ).nextLane
    ).toBe('none')
  })
})
