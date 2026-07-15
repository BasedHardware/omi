import { describe, it, expect } from 'vitest'
import {
  classifyHubClose,
  consumesStrike,
  shouldLogCloseError,
  HUB_IDLE_TEARDOWN_THRESHOLD_MS
} from './hubClose'

describe('classifyHubClose', () => {
  it('classifies a long-lived 1008 with no active turn as the expected provider idle teardown', () => {
    expect(
      classifyHubClose({
        message: 'websocket closed (1008)',
        closeCode: 1008,
        aliveForMs: HUB_IDLE_TEARDOWN_THRESHOLD_MS,
        hasActiveTurn: false
      })
    ).toBe('expected_idle_teardown')
  })

  it('classifies a FAST 1008 (short-lived socket) as a policy_fast failure', () => {
    expect(
      classifyHubClose({
        message: 'websocket closed (1008)',
        closeCode: 1008,
        aliveForMs: 1_000,
        hasActiveTurn: false
      })
    ).toBe('policy_fast')
  })

  it('classifies a 1008 during an ACTIVE turn as policy_fast even when long-lived (not an idle close)', () => {
    expect(
      classifyHubClose({
        message: 'websocket closed (1008)',
        closeCode: 1008,
        aliveForMs: 999_999,
        hasActiveTurn: true
      })
    ).toBe('policy_fast')
  })

  it('classifies any non-1008 close as transient', () => {
    expect(
      classifyHubClose({
        message: 'websocket closed (1006)',
        closeCode: 1006,
        aliveForMs: 999_999,
        hasActiveTurn: false
      })
    ).toBe('transient')
    expect(
      classifyHubClose({
        message: 'websocket closed (1011)',
        closeCode: 1011,
        aliveForMs: 10,
        hasActiveTurn: false
      })
    ).toBe('transient')
  })

  it('falls back to parsing the code out of the message when none is threaded structurally', () => {
    expect(
      classifyHubClose({
        message: 'websocket closed (1008) idle',
        aliveForMs: HUB_IDLE_TEARDOWN_THRESHOLD_MS + 1,
        hasActiveTurn: false
      })
    ).toBe('expected_idle_teardown')
    // An OpenAI error frame carries no code and no "websocket closed" text → transient.
    expect(
      classifyHubClose({ message: 'OpenAI realtime error', aliveForMs: 0, hasActiveTurn: true })
    ).toBe('transient')
  })
})

describe('consumesStrike / shouldLogCloseError', () => {
  it('an expected idle teardown neither spends a strike nor logs as a fault', () => {
    expect(consumesStrike('expected_idle_teardown')).toBe(false)
    expect(shouldLogCloseError('expected_idle_teardown')).toBe(false)
  })

  it('genuine failures spend a strike and log', () => {
    for (const category of ['policy_fast', 'transient'] as const) {
      expect(consumesStrike(category)).toBe(true)
      expect(shouldLogCloseError(category)).toBe(true)
    }
  })
})
