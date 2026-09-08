// Continuity-seed tests for HubController (PR-B). Two things are proven here:
//  1. The DEFAULT instruction builder folds the kernel seed into the realtime
//     session's <recent_top_level_conversation> block + renders the language line.
//  2. refreshSeedContext() reconnects the warm session ONLY when the fresh seed
//     carries a turn the session hasn't seen (a typed turn) — a self-produced voice
//     turn (marked known) does NOT thrash a reconnect, and it never runs mid-turn.

import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { VoiceProvider } from '../sessionMachine'
import type { VoiceSessionID, VoiceTurnID } from '../turn/voiceTurnMachine'
import type { HubSession, HubSessionEvents, HubBargeInStrategy, HubProvider } from './hubSession'

// The real provider sessions pull in pcmPlayer's AudioWorklet asset (unresolvable in
// node) — stub it; the controller injects a fake session anyway.
vi.mock('../pcmPlayer', () => ({
  createVoicePlayer: vi.fn(),
  base64ToBytes: (s: string) => new TextEncoder().encode(s)
}))
vi.mock('../../analytics', () => ({ trackEvent: vi.fn() }))
// Keep the daily-provider + about_user refreshes inert so warm() is hermetic.
vi.mock('../autoModelSelector', () => ({
  resolveEffectiveVoiceProvider: () => 'openai' as VoiceProvider,
  refreshIfStale: vi.fn()
}))
vi.mock('../aboutUser', () => ({ getAboutUserCard: () => '', refreshAboutUserCard: vi.fn() }))
// Drive the language line off a controlled pref (voiceLanguages empty → falls back
// to `language`, the behavior PR-B adds).
const prefs = { voiceLanguages: [] as string[], language: 'ru' }
vi.mock('../../preferences', () => ({ getPreferences: () => prefs }))

import { HubController } from './hubController'

class FakeSession implements HubSession {
  readonly provider: HubProvider = 'openai'
  readonly requiredInputSampleRate = 24000
  readonly bargeInStrategy: HubBargeInStrategy = 'inSessionCancel'
  warm = false
  toreDown = 0
  private resolveWarm: (() => void) | null = null
  constructor(
    readonly sessionID: VoiceSessionID,
    readonly instructions: string,
    readonly events: HubSessionEvents
  ) {}
  ensureWarm(): Promise<void> {
    if (this.warm) return Promise.resolve()
    return new Promise((resolve) => (this.resolveWarm = resolve))
  }
  connect(): void {
    this.warm = true
    this.events.onConnected?.(this.sessionID)
    this.resolveWarm?.()
    this.resolveWarm = null
  }
  isWarm(): boolean {
    return this.warm
  }
  beginTurn(): void {
    /* unused in seed tests */
  }
  appendAudio(): void {
    /* unused in seed tests */
  }
  commitTurn(): void {
    /* unused in seed tests */
  }
  cancelTurn(): void {
    /* unused in seed tests */
  }
  sendToolResult(): void {
    /* unused in seed tests */
  }
  teardown(): void {
    this.toreDown += 1
    this.warm = false
  }
}

const tick = (): Promise<void> => new Promise((r) => setTimeout(r, 0))
const SID = 'sess' as VoiceSessionID

type SeedSnapshot = { context: string; idempotencyKeys: string[] }

function harness(fetchSeed?: () => Promise<SeedSnapshot>) {
  const sessions: FakeSession[] = []
  let seq = 0
  const controller = new HubController({
    fetchSeed,
    mintToken: async () => 'ek_token',
    createSession: (spec) => {
      const s = new FakeSession(`${SID}-${++seq}` as VoiceSessionID, spec.instructions, spec.events)
      sessions.push(s)
      return s
    }
  })
  return { controller, sessions, latest: () => sessions[sessions.length - 1] }
}

/** Warm fully: mint → create → connect. */
async function warm(h: ReturnType<typeof harness>): Promise<void> {
  const p = h.controller.ensureWarm()
  await tick()
  h.latest().connect()
  await p
}

beforeEach(() => {
  prefs.voiceLanguages = []
  prefs.language = 'ru'
})

describe('HubController — default instruction folds in the seed + language', () => {
  it('builds the session with the seed block and the language line', async () => {
    const h = harness()
    // Simulate a seed already staged (a prior refresh) by refreshing before warm.
    const seeded = harness(async () => ({
      context: '[live:typed] User: my dog is Pixel',
      idempotencyKeys: ['typed-1']
    }))
    seeded.controller.refreshSeedContext()
    await tick()
    await warm(seeded)
    const instr = seeded.latest().instructions
    expect(instr).toContain('<recent_top_level_conversation>')
    expect(instr).toContain('my dog is Pixel')
    // Language falls back to the `language` pref (ru → Russian) when voiceLanguages
    // is empty.
    expect(instr).toContain('Russian')

    // And with no seed, the block is absent (unchanged baseline).
    await warm(h)
    expect(h.latest().instructions).not.toContain('<recent_top_level_conversation>')
  })
})

describe('HubController — refreshSeedContext reconnect policy', () => {
  it('reconnects when the fresh seed carries an UNSEEN turn (a typed turn)', async () => {
    const h = harness(async () => ({
      context: '[live:typed] User: hello',
      idempotencyKeys: ['typed-1']
    }))
    await warm(h)
    expect(h.sessions).toHaveLength(1)

    h.controller.refreshSeedContext()
    await tick() // fetch resolves → teardown + ensureWarm
    await tick() // new session minted
    h.latest().connect()
    await tick()

    expect(h.sessions).toHaveLength(2) // rebuilt
    expect(h.sessions[0].toreDown).toBe(1)
    expect(h.sessions[1].instructions).toContain('hello')
  })

  it('does NOT reconnect when every key is already known (no thrash)', async () => {
    const snap: SeedSnapshot = { context: '[live:voice] User: x', idempotencyKeys: ['voice-1'] }
    const h = harness(async () => snap)
    await warm(h)
    // The session produced voice-1 live — mark it known.
    h.controller.markSeedKeyProduced('voice-1')

    h.controller.refreshSeedContext()
    await tick()
    await tick()

    expect(h.sessions).toHaveLength(1) // no rebuild — the session already reflects it
  })

  it('defers a mid-turn refresh until the turn terminates', async () => {
    const h = harness(async () => ({
      context: '[live:typed] User: later',
      idempotencyKeys: ['typed-later']
    }))
    await warm(h)
    const turn = 'turn-1' as VoiceTurnID
    h.controller.beginTurn(turn)

    h.controller.refreshSeedContext()
    await tick()
    await tick()
    expect(h.sessions).toHaveLength(1) // deferred — no reconnect mid-turn

    h.controller.voiceTurnDidTerminate(turn)
    await tick() // deferred refresh runs
    await tick()
    h.latest().connect()
    await tick()
    expect(h.sessions).toHaveLength(2) // now reconnected with the fresh seed
  })
})
