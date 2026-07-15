import { describe, it, expect } from 'vitest'
import {
  deriveOrbState,
  isBarBusy,
  omiChatListStatus,
  deriveAgentRows,
  agentRowStatus,
  pillLabel,
  agentDraftPrefill,
  nextConversationDraft,
  type BarAgentRow
} from './barDisplay'
// Imported (not edited) to prove the seed actually triggers agent delegation.
import { detectAgentTask } from '../../lib/agentTask'
import type { BarChatState, CodingAgentInfo } from '../../../../shared/types'

const chat = (partial: Partial<BarChatState> = {}): BarChatState => ({
  messages: [],
  sending: false,
  status: 'idle',
  ...partial
})

describe('deriveOrbState', () => {
  const base = {
    recording: false,
    transcribing: false,
    status: 'idle',
    continuousListening: false,
    agentsActive: false
  } as const

  it('recording → speaking WITH the user amplitude (the blob reacts to the mic)', () => {
    expect(deriveOrbState({ ...base, recording: true })).toEqual({
      state: 'speaking',
      withAmplitude: true
    })
  })

  it('recording wins even while a reply is still speaking/streaming', () => {
    expect(deriveOrbState({ ...base, recording: true, status: 'speaking' }).withAmplitude).toBe(
      true
    )
    expect(deriveOrbState({ ...base, recording: true, status: 'sending' }).state).toBe('speaking')
  })

  it('a tap-to-locked capture shows the distinct listening pose, still amplitude-reactive', () => {
    expect(deriveOrbState({ ...base, recording: true, locked: true })).toEqual({
      state: 'listening',
      withAmplitude: true
    })
  })

  it('TTS playback → speaking WITHOUT amplitude (Omi is talking)', () => {
    expect(deriveOrbState({ ...base, status: 'speaking' })).toEqual({
      state: 'speaking',
      withAmplitude: false
    })
  })

  it('streaming/finalizing → thinking', () => {
    expect(deriveOrbState({ ...base, status: 'sending' }).state).toBe('thinking')
    expect(deriveOrbState({ ...base, transcribing: true }).state).toBe('thinking')
  })

  it('continuous listening → listening; otherwise idle', () => {
    expect(deriveOrbState({ ...base, continuousListening: true }).state).toBe('listening')
    expect(deriveOrbState(base).state).toBe('idle')
  })

  it('running coding-agent → agents pose (over generic thinking; both are status=sending)', () => {
    expect(deriveOrbState({ ...base, agentsActive: true, status: 'sending' })).toEqual({
      state: 'agents',
      withAmplitude: false
    })
    // agents also wins over passive continuous listening
    expect(deriveOrbState({ ...base, agentsActive: true, continuousListening: true }).state).toBe(
      'agents'
    )
  })

  it('live voice still wins over an active agent (user turn is most salient)', () => {
    // user holding PTT during an agent task → the user's reactive mic turn
    expect(deriveOrbState({ ...base, agentsActive: true, recording: true })).toEqual({
      state: 'speaking',
      withAmplitude: true
    })
    // Omi speaking a reply also outranks the agents pose
    expect(deriveOrbState({ ...base, agentsActive: true, status: 'speaking' }).state).toBe(
      'speaking'
    )
  })
})

describe('isBarBusy (pill retract-hold)', () => {
  it('holds the pill open during recording / finalizing / streaming / speaking', () => {
    expect(isBarBusy({ recording: true, transcribing: false, status: 'idle' })).toBe(true)
    expect(isBarBusy({ recording: false, transcribing: true, status: 'idle' })).toBe(true)
    expect(isBarBusy({ recording: false, transcribing: false, status: 'sending' })).toBe(true)
    expect(isBarBusy({ recording: false, transcribing: false, status: 'speaking' })).toBe(true)
  })

  it('is idle when nothing is in flight (the pill may retract)', () => {
    expect(isBarBusy({ recording: false, transcribing: false, status: 'idle' })).toBe(false)
  })
})

describe('omiChatListStatus', () => {
  it('reflects the live activity first', () => {
    expect(omiChatListStatus(chat({ status: 'speaking' }))).toBe('Speaking…')
    expect(omiChatListStatus(chat({ status: 'sending' }))).toBe('Thinking…')
  })

  it('previews the last turn (prefixing the user’s own line)', () => {
    expect(
      omiChatListStatus(chat({ messages: [{ role: 'assistant', content: 'Here is the answer' }] }))
    ).toBe('Here is the answer')
    expect(omiChatListStatus(chat({ messages: [{ role: 'user', content: 'what is next' }] }))).toBe(
      'You: what is next'
    )
  })

  it('collapses whitespace so a multi-line reply stays one line', () => {
    expect(
      omiChatListStatus(chat({ messages: [{ role: 'assistant', content: 'a\n\n  b   c' }] }))
    ).toBe('a b c')
  })

  it('invites when the thread is empty', () => {
    expect(omiChatListStatus(chat())).toBe('Ask me anything')
  })
})

describe('deriveAgentRows', () => {
  const info = (
    over: Partial<CodingAgentInfo> & { id: CodingAgentInfo['id'] }
  ): CodingAgentInfo => ({
    displayName: over.id,
    connected: false,
    ...over
  })

  it('lists only connected agents (the summon list is for acting, not setup)', () => {
    const rows = deriveAgentRows(
      [
        info({ id: 'acp', displayName: 'Claude Code', connected: true }),
        info({ id: 'codex', displayName: 'Codex', connected: false })
      ],
      null,
      false
    )
    expect(rows.map((r) => r.id)).toEqual(['acp'])
    expect(rows[0].displayName).toBe('Claude Code')
  })

  it('marks exactly the active adapter as working while a task runs', () => {
    const agents = [
      info({ id: 'acp', displayName: 'Claude Code', connected: true }),
      info({ id: 'codex', displayName: 'Codex', connected: true })
    ]
    const rows = deriveAgentRows(agents, 'codex', true)
    expect(rows.find((r) => r.id === 'codex')?.working).toBe(true)
    expect(rows.find((r) => r.id === 'acp')?.working).toBe(false)
  })

  it('no row is working once the global agentsActive drops, even with a stale active id', () => {
    const agents = [info({ id: 'acp', displayName: 'Claude Code', connected: true })]
    expect(deriveAgentRows(agents, 'acp', false).every((r) => !r.working)).toBe(true)
  })
})

describe('agentRowStatus', () => {
  it('reads Working… while running, Ready otherwise', () => {
    expect(agentRowStatus({ id: 'acp', displayName: 'Claude Code', working: true })).toBe(
      'Working…'
    )
    expect(agentRowStatus({ id: 'acp', displayName: 'Claude Code', working: false })).toBe('Ready')
  })
})

describe('agentDraftPrefill', () => {
  const rows: BarAgentRow[] = [
    { id: 'acp', displayName: 'Claude Code', working: false },
    { id: 'openclaw', displayName: 'OpenClaw', working: false },
    { id: 'hermes', displayName: 'Hermes', working: false },
    { id: 'codex', displayName: 'Codex', working: false }
  ]

  it('seeds a leading-mention string detectAgentTask matches for EVERY agent', () => {
    // The whole point of the prefill: what the user types after it is delegated
    // to that agent. Assert detection fires and resolves to the right adapter id.
    for (const row of rows) {
      const seed = agentDraftPrefill(row.displayName)
      const detected = detectAgentTask(`${seed}fix the failing test`)
      expect(detected).not.toBeNull()
      expect(detected?.agentId).toBe(row.id)
    }
  })

  it('the bare seed (before the user types) already reads as a delegation', () => {
    // A row click prefills before any typing; the seed alone must not fall back
    // to normal Omi chat, so the header/framing stays truthful.
    expect(detectAgentTask(agentDraftPrefill('Claude Code'))).not.toBeNull()
  })
})

describe('nextConversationDraft', () => {
  const acp: BarAgentRow = { id: 'acp', displayName: 'Claude Code', working: false }
  const codex: BarAgentRow = { id: 'codex', displayName: 'Codex', working: false }

  it('seeds the agent phrasing when an agent row opens an empty draft', () => {
    expect(nextConversationDraft({ target: acp, previous: null, current: '' })).toBe(
      'Claude Code, '
    )
  })

  it('leaves the Omi thread draft empty when the Omi row opens', () => {
    expect(nextConversationDraft({ target: null, previous: null, current: '' })).toBe('')
  })

  it('drops a stale agent seed when returning to the Omi row (no leftover prefill)', () => {
    // Open Claude Code (draft seeded), go back, open Omi → clean, empty draft.
    expect(nextConversationDraft({ target: null, previous: acp, current: 'Claude Code, ' })).toBe(
      ''
    )
  })

  it('replaces one agent seed with the next agent seed when switching agents', () => {
    expect(nextConversationDraft({ target: codex, previous: acp, current: 'Claude Code, ' })).toBe(
      'Codex, '
    )
  })

  it('never clobbers text the user actually typed', () => {
    // Typed an Omi message, wandered to the list, opened an agent → keep the text.
    expect(nextConversationDraft({ target: acp, previous: null, current: 'draft I wrote' })).toBe(
      'draft I wrote'
    )
    // Typed on top of a seed, then returned to Omi → not a bare seed, so kept.
    expect(
      nextConversationDraft({ target: null, previous: acp, current: 'Claude Code, do X' })
    ).toBe('Claude Code, do X')
  })
})

describe('pillLabel', () => {
  it('says "Listening" whenever the user is being captured — a PTT hold OR always-on', () => {
    // PTT hold: recording even though the orb pose derives as 'speaking'.
    expect(pillLabel({ recording: true, continuousListening: false })).toBe('Listening')
    // Always-on continuous listening.
    expect(pillLabel({ recording: false, continuousListening: true })).toBe('Listening')
  })

  it('keeps the resting "Omi" wordmark when the user is NOT being captured', () => {
    // Idle.
    expect(pillLabel({ recording: false, continuousListening: false })).toBe('Omi')
  })
})
