import { describe, it, expect } from 'vitest'
import {
  constantLevelWaveformSource,
  deriveOrbState,
  deriveBarVoiceState,
  deriveTurnPhase,
  isBarBusy,
  isPlaybackLevelFresh,
  PLAYBACK_LEVEL_FRESH_MS,
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

describe('deriveTurnPhase (the ONE precedence ladder orb + pill derive from)', () => {
  const base = {
    recording: false,
    transcribing: false,
    status: 'idle',
    continuousListening: false,
    agentsActive: false
  } as const

  it('orders the ladder: capturing › replying › agents › thinking › ambient › idle', () => {
    // Each row flips everything below it ON to prove the higher rung wins.
    expect(
      deriveTurnPhase({
        ...base,
        recording: true,
        status: 'speaking',
        agentsActive: true,
        transcribing: true,
        continuousListening: true
      })
    ).toBe('capturing')
    expect(
      deriveTurnPhase({
        ...base,
        status: 'speaking',
        agentsActive: true,
        transcribing: true,
        continuousListening: true
      })
    ).toBe('replying')
    expect(
      deriveTurnPhase({
        ...base,
        agentsActive: true,
        transcribing: true,
        continuousListening: true
      })
    ).toBe('agents')
    expect(deriveTurnPhase({ ...base, transcribing: true, continuousListening: true })).toBe(
      'thinking'
    )
    expect(deriveTurnPhase({ ...base, status: 'sending', continuousListening: true })).toBe(
      'thinking'
    )
    expect(deriveTurnPhase({ ...base, continuousListening: true })).toBe('ambient')
    expect(deriveTurnPhase(base)).toBe('idle')
  })
})

describe('constantLevelWaveformSource', () => {
  it('reads the live level through the getter and paints every bin clamped', () => {
    let level = 0.5
    const src = constantLevelWaveformSource(() => level)
    expect(src.getOrbLevel?.()).toBe(0.5)
    const bins = new Uint8Array(4)
    src.getByteFrequencyData(bins)
    expect(Array.from(bins)).toEqual([128, 128, 128, 128])
    // Hot input: fast lane passes it through (the mapper bounds it downstream),
    // the bin painter clamps.
    level = 1.7
    expect(src.getOrbLevel?.()).toBe(1.7)
    src.getByteFrequencyData(bins)
    expect(Array.from(bins)).toEqual([255, 255, 255, 255])
  })
})

describe('deriveOrbState', () => {
  const base = {
    recording: false,
    transcribing: false,
    status: 'idle',
    continuousListening: false,
    agentsActive: false
  } as const

  it('recording → speaking WITH the user MIC amplitude (the blob reacts to the mic)', () => {
    expect(deriveOrbState({ ...base, recording: true })).toEqual({
      state: 'speaking',
      amplitude: 'mic'
    })
  })

  it('recording wins even while a reply is still speaking/streaming', () => {
    expect(deriveOrbState({ ...base, recording: true, status: 'speaking' }).amplitude).toBe('mic')
    expect(deriveOrbState({ ...base, recording: true, status: 'sending' }).state).toBe('speaking')
  })

  it('a tap-to-locked capture shows the distinct listening pose, still amplitude-reactive', () => {
    expect(deriveOrbState({ ...base, recording: true, locked: true })).toEqual({
      state: 'listening',
      amplitude: 'mic'
    })
  })

  // Regression ("when it's speaking the visualizer stays put"): the spoken reply
  // now animates the orb from the PLAYBACK lane — the audio actually playing —
  // instead of a frozen no-amplitude speaking pose.
  it('TTS playback → speaking WITH the playback amplitude (the reply animates the dots)', () => {
    expect(deriveOrbState({ ...base, status: 'speaking' })).toEqual({
      state: 'speaking',
      amplitude: 'playback'
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
      amplitude: null
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
      amplitude: 'mic'
    })
    // Omi speaking a reply also outranks the agents pose
    expect(deriveOrbState({ ...base, agentsActive: true, status: 'speaking' }).state).toBe(
      'speaking'
    )
  })
})

describe('deriveBarVoiceState (warm-hub → bar signals)', () => {
  const hub = (partial: Partial<Parameters<typeof deriveBarVoiceState>[0]['hub']> = {}) => ({
    active: false,
    isListening: false,
    isThinking: false,
    isResponseActive: false,
    ...partial
  })
  const call = (
    overrides: Partial<Parameters<typeof deriveBarVoiceState>[0]> = {}
  ): ReturnType<typeof deriveBarVoiceState> =>
    deriveBarVoiceState({
      hub: hub(),
      localRecording: false,
      localTranscribing: false,
      chatStatus: 'idle',
      ...overrides
    })

  it('hub inactive → the local PTT/chat signals pass through unchanged', () => {
    expect(call({ localRecording: true }).recording).toBe(true)
    expect(call({ localTranscribing: true }).transcribing).toBe(true)
    expect(call({ chatStatus: 'speaking' }).status).toBe('speaking')
    expect(call().hubSpeaking).toBe(false)
  })

  // The regression: a hub SPOKEN reply must NOT be reported as thinking, and must map
  // to the 'speaking' chat status so deriveOrbState shows the speaking pose. Before the
  // fix isResponseActive folded into transcribing → the orb stuck in the thinking pose.
  it('hub speaking its reply → speaking status, NOT thinking, and flags hubSpeaking', () => {
    const v = call({ hub: hub({ active: true, isResponseActive: true }) })
    expect(v.status).toBe('speaking')
    expect(v.transcribing).toBe(false)
    expect(v.hubSpeaking).toBe(true)
    // …and fed through deriveOrbState it yields the speaking pose driven by the
    // playback lane (the hub reply's own audio animates the dots).
    expect(
      deriveOrbState({
        recording: v.recording,
        transcribing: v.transcribing,
        status: v.status,
        continuousListening: false,
        agentsActive: false
      })
    ).toEqual({ state: 'speaking', amplitude: 'playback' })
  })

  it('hub awaiting its response → thinking (unchanged), not speaking', () => {
    const v = call({ hub: hub({ active: true, isThinking: true }) })
    expect(v.transcribing).toBe(true)
    expect(v.status).toBe('idle')
    expect(v.hubSpeaking).toBe(false)
    expect(
      deriveOrbState({ ...v, locked: false, continuousListening: false, agentsActive: false }).state
    ).toBe('thinking')
  })

  it('hub capturing the user → recording (the reactive listening/speaking pose)', () => {
    const v = call({ hub: hub({ active: true, isListening: true }) })
    expect(v.recording).toBe(true)
    expect(v.transcribing).toBe(false)
    expect(v.hubSpeaking).toBe(false)
  })

  it('cascade TTS (no hub turn) still yields speaking via chat.status', () => {
    const v = call({ chatStatus: 'speaking' })
    expect(v.status).toBe('speaking')
    expect(deriveOrbState({ ...v, continuousListening: false, agentsActive: false }).state).toBe(
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
  const base = {
    recording: false,
    transcribing: false,
    status: 'idle',
    continuousListening: false,
    agentsActive: false
  } as const

  it('says "Listening" whenever the user is being captured — a PTT hold OR always-on', () => {
    // PTT hold: recording even though the orb pose derives as 'speaking'.
    expect(pillLabel({ ...base, recording: true })).toBe('Listening')
    // Always-on continuous listening.
    expect(pillLabel({ ...base, continuousListening: true })).toBe('Listening')
  })

  // Regression ("the word in the bar still doesn't change"): the pill must track
  // the whole turn, not stay on the capture word.
  it('tracks the turn: Thinking while finalizing/awaiting, Speaking while the reply plays', () => {
    // Finalizing the transcript (local cascade) / hub isThinking.
    expect(pillLabel({ ...base, transcribing: true })).toBe('Thinking')
    // Awaiting/streaming the reply.
    expect(pillLabel({ ...base, status: 'sending' })).toBe('Thinking')
    // The spoken reply is playing (hub reply folds into status 'speaking' via
    // deriveBarVoiceState; the cascade TTS raises the same chat status).
    expect(pillLabel({ ...base, status: 'speaking' })).toBe('Speaking')
    // …even when continuous listening is on underneath.
    expect(pillLabel({ ...base, status: 'speaking', continuousListening: true })).toBe('Speaking')
  })

  it('an active capture outranks a still-playing reply (mirrors deriveOrbState)', () => {
    expect(pillLabel({ ...base, recording: true, status: 'speaking' })).toBe('Listening')
  })

  it('keeps the resting "Omi" wordmark when idle', () => {
    expect(pillLabel(base)).toBe('Omi')
  })

  it('a delegated coding-agent run rests on "Omi" — the orb agents pose is the indicator', () => {
    // Agent tasks ride status 'sending' for minutes; the pill must not pin "Thinking".
    expect(pillLabel({ ...base, agentsActive: true, status: 'sending' })).toBe('Omi')
  })
})

describe('isPlaybackLevelFresh (playback-amplitude fallback rule)', () => {
  it('fresh within the window, stale after it (unfed lane ⇒ pose-only fallback)', () => {
    expect(isPlaybackLevelFresh(1000, 1000 + PLAYBACK_LEVEL_FRESH_MS - 1)).toBe(true)
    expect(isPlaybackLevelFresh(1000, 1000 + PLAYBACK_LEVEL_FRESH_MS)).toBe(false)
  })

  it('a never-fed lane (at=0) is stale from the start', () => {
    expect(isPlaybackLevelFresh(0, PLAYBACK_LEVEL_FRESH_MS + 1)).toBe(false)
  })
})
