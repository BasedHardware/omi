import { beforeEach, describe, expect, it, vi } from 'vitest'
import { candidateAgents, cancelTask, runCodingAgentTask } from './taskRunner'
import { AcpError } from './acp'
import { ADAPTER_PROFILES, adapterConfiguredCommand, adapterIsActivated } from './adapterRegistry'
import { readOutcomeLedger, recordAgentOutcome } from './agentOutcomeLedger'
import type {
  AdapterAttemptContext,
  AdapterEventSink,
  AdapterAttemptResult,
  OpenBindingInput,
  OpenedBinding,
  ProductionAdapterId,
  RuntimeAdapter
} from './interface'
import { adapterCapabilitiesFor } from './interface'
import type { CodingAgentEvent } from '../../shared/types'

vi.mock('./adapterRegistry', async () => {
  const actual = await vi.importActual<typeof import('./adapterRegistry')>('./adapterRegistry')
  return {
    ...actual,
    // Profiles keep their real shape; tests swap createAdapter per adapter id.
    ADAPTER_PROFILES: Object.fromEntries(
      Object.entries(actual.ADAPTER_PROFILES).map(([id, profile]) => [id, { ...profile }])
    ),
    adapterIsActivated: vi.fn(),
    adapterConfiguredCommand: vi.fn(() => undefined)
  }
})

// Real ranking math runs (agentConcierge.ts is NOT mocked) — only its disk
// dependency is, so these tests never touch a real userData file and never
// carry outcomes over from a previous test.
vi.mock('./agentOutcomeLedger', () => ({
  readOutcomeLedger: vi.fn(() => []),
  recordAgentOutcome: vi.fn()
}))

type FakeScript = {
  /** Throw from openBinding (simulates a dead/unconfigured adapter). */
  failOpen?: boolean
  /** Text deltas to stream before resolving. */
  stream?: string[]
  /** Throw from executeAttempt after streaming (post-output failure). */
  failAfterStream?: boolean
  /** Throw this exact error from executeAttempt before any output. */
  failWithError?: Error
  /** Resolve the attempt only when the signal aborts (for cancel tests). */
  hangUntilAborted?: boolean
}

function fakeAdapter(adapterId: ProductionAdapterId, script: FakeScript): RuntimeAdapter {
  return {
    adapterId,
    capabilities: adapterCapabilitiesFor(adapterId),
    start: async () => {},
    stop: async () => {},
    openBinding: async (input: OpenBindingInput): Promise<OpenedBinding> => {
      if (script.failOpen) throw new Error(`${adapterId} refused to start`)
      return {
        sessionId: input.sessionId,
        adapterId,
        adapterNativeSessionId: `${adapterId}-native`,
        resumeFidelity: 'none',
        cwd: input.cwd
      }
    },
    resumeBinding: async () => {
      throw new Error('not used')
    },
    executeAttempt: async (
      context: AdapterAttemptContext,
      sink: AdapterEventSink,
      signal: AbortSignal
    ): Promise<AdapterAttemptResult> => {
      if (script.failWithError) throw script.failWithError
      for (const text of script.stream ?? []) {
        sink({ type: 'text_delta', text })
      }
      if (script.failAfterStream) throw new Error(`${adapterId} crashed mid-run`)
      if (script.hangUntilAborted) {
        await new Promise<void>((resolve) => {
          if (signal.aborted) return resolve()
          signal.addEventListener('abort', () => resolve(), { once: true })
        })
        throw new Error('aborted')
      }
      return {
        text: (script.stream ?? []).join(''),
        adapterSessionId: context.binding.adapterNativeSessionId,
        terminalStatus: signal.aborted ? 'cancelled' : 'succeeded'
      }
    },
    cancelAttempt: async () => ({
      accepted: true,
      dispatchAttempted: true,
      adapterAcknowledged: false
    })
  }
}

function script(adapters: Partial<Record<ProductionAdapterId, FakeScript>>): void {
  for (const [id, s] of Object.entries(adapters) as Array<[ProductionAdapterId, FakeScript]>) {
    ADAPTER_PROFILES[id].createAdapter = () => fakeAdapter(id, s)
  }
}

function activate(...ids: ProductionAdapterId[]): void {
  vi.mocked(adapterIsActivated).mockImplementation(((id: ProductionAdapterId) =>
    ids.includes(id)) as never)
}

describe('candidateAgents', () => {
  beforeEach(() => {
    vi.mocked(adapterIsActivated).mockReset()
    vi.mocked(adapterConfiguredCommand).mockReturnValue(undefined)
    vi.mocked(readOutcomeLedger).mockReturnValue([])
  })

  it('orders unnamed tasks Claude Code first, connected agents only', () => {
    activate('acp', 'codex')
    expect(candidateAgents(undefined, {})).toEqual(['acp', 'codex'])
  })

  it('puts the named agent first with the rest as fallbacks', () => {
    activate('acp', 'openclaw', 'hermes')
    expect(candidateAgents('hermes', {})).toEqual(['hermes', 'acp', 'openclaw'])
  })

  it('ranks the unnamed fallback order by fit instead of just the declared list', () => {
    // Declared order (interface.ts's PRODUCTION_ADAPTER_IDS) is
    // acp, openclaw, hermes, codex. OpenClaw's real, matrix-documented gap —
    // it can't call tools at all (toolSupport: unsupported) — is a genuine
    // handicap for a coding task, so it drops to last instead of staying
    // second just because it was declared second.
    activate('acp', 'openclaw', 'hermes', 'codex')
    expect(candidateAgents(undefined, {})).toEqual(['acp', 'hermes', 'codex', 'openclaw'])
  })

  it('lets a task-shaped prompt move a better-suited agent ahead', () => {
    // Hermes documents real session/set_model support; Codex's is an
    // unverified known_limitation. That's a sourced reason to prefer Hermes
    // for a wide refactor specifically, not just a coin flip.
    activate('hermes', 'codex')
    expect(candidateAgents(undefined, {}, process.env, 'bulk_refactor')).toEqual([
      'hermes',
      'codex'
    ])
  })

  it('lets recorded history move the unnamed fallback order', () => {
    activate('hermes', 'codex')
    vi.mocked(readOutcomeLedger).mockReturnValue([
      { adapterId: 'codex', tag: 'general', outcome: 'success', ts: 1 },
      { adapterId: 'codex', tag: 'general', outcome: 'success', ts: 2 },
      { adapterId: 'codex', tag: 'general', outcome: 'success', ts: 3 }
    ])
    expect(candidateAgents(undefined, {}, process.env, 'general')).toEqual(['codex', 'hermes'])
  })
})

describe('runCodingAgentTask', () => {
  beforeEach(() => {
    vi.mocked(adapterIsActivated).mockReset()
    vi.mocked(adapterConfiguredCommand).mockReturnValue(undefined)
    vi.mocked(readOutcomeLedger).mockReturnValue([])
    vi.mocked(recordAgentOutcome).mockClear()
  })

  it('runs the named agent and streams its output', async () => {
    activate('acp', 'openclaw')
    script({ openclaw: { stream: ['done ', 'and dusted'] } })
    const events: CodingAgentEvent[] = []

    const result = await runCodingAgentTask(
      { taskId: 't1', prompt: 'fix it', agentId: 'openclaw' },
      (e) => events.push(e)
    )

    expect(result).toMatchObject({ ok: true, adapterId: 'openclaw', text: 'done and dusted' })
    expect(events[0]).toMatchObject({
      type: 'agent_selected',
      adapterId: 'openclaw',
      fallback: false
    })
    expect(events.filter((e) => e.type === 'text_delta')).toHaveLength(2)
  })

  it('falls back to the next connected agent when the first fails before producing output', async () => {
    activate('acp', 'openclaw', 'hermes')
    script({
      openclaw: { failOpen: true },
      acp: { stream: ['fallback answer'] }
    })
    const events: CodingAgentEvent[] = []

    const result = await runCodingAgentTask(
      { taskId: 't2', prompt: 'fix it', agentId: 'openclaw' },
      (e) => events.push(e)
    )

    expect(result).toMatchObject({ ok: true, adapterId: 'acp', text: 'fallback answer' })
    const selections = events.filter((e) => e.type === 'agent_selected')
    expect(selections.map((e) => (e.type === 'agent_selected' ? e.adapterId : ''))).toEqual([
      'openclaw',
      'acp'
    ])
    expect(selections[1]).toMatchObject({ fallback: true })
    expect(events.some((e) => e.type === 'status' && /trying the next agent/.test(e.message))).toBe(
      true
    )
  })

  it('does NOT retry elsewhere once the failing agent already produced visible output', async () => {
    activate('acp', 'openclaw')
    script({
      openclaw: { stream: ['partial answer…'], failAfterStream: true },
      acp: { stream: ['should never run'] }
    })
    const events: CodingAgentEvent[] = []

    const result = await runCodingAgentTask(
      { taskId: 't3', prompt: 'fix it', agentId: 'openclaw' },
      (e) => events.push(e)
    )

    expect(result.ok).toBe(false)
    expect(result.adapterId).toBe('openclaw')
    expect(events.filter((e) => e.type === 'agent_selected')).toHaveLength(1)
  })

  it('reports failure when every candidate fails', async () => {
    activate('acp')
    script({ acp: { failOpen: true } })

    const result = await runCodingAgentTask({ taskId: 't4', prompt: 'fix it' }, () => {})

    expect(result.ok).toBe(false)
    expect(result.error).toBeTruthy()
  })

  it('emits auth_required and stops (no fallback) when Claude Code hits an auth error', async () => {
    activate('acp', 'openclaw')
    script({
      acp: { failWithError: new AcpError('Authentication required', -32000) },
      openclaw: { stream: ['should never run'] }
    })
    const events: CodingAgentEvent[] = []

    const result = await runCodingAgentTask(
      { taskId: 't-auth', prompt: 'fix it', agentId: 'acp' },
      (e) => events.push(e)
    )

    expect(result).toMatchObject({ ok: false, adapterId: 'acp' })
    expect(result.error).toMatch(/Sign in to Claude/)
    expect(events).toContainEqual({ type: 'auth_required', taskId: 't-auth', adapterId: 'acp' })
    // A login fixes it — don't silently retry another agent for the same task.
    expect(events.filter((e) => e.type === 'agent_selected')).toHaveLength(1)
  })

  it('reports no-agents-connected when nothing is activated', async () => {
    activate()

    const result = await runCodingAgentTask({ taskId: 't5', prompt: 'fix it' }, () => {})

    expect(result).toMatchObject({ ok: false, adapterId: null })
    expect(result.error).toContain('No coding agents are connected')
  })

  it('cancelTask aborts a running task', async () => {
    activate('acp')
    script({ acp: { hangUntilAborted: true } })

    const running = runCodingAgentTask({ taskId: 't6', prompt: 'never finishes' }, () => {})
    // Let the task reach executeAttempt before cancelling.
    await new Promise((resolve) => setTimeout(resolve, 10))
    expect(cancelTask('t6')).toBe(true)
    const result = await running

    expect(result.ok).toBe(false)
    expect(result.error).toBe('Cancelled.')
    expect(cancelTask('t6')).toBe(false) // already finished/cleaned up
  })

  it('records a successful attempt so future ranking can learn from it', async () => {
    activate('acp')
    script({ acp: { stream: ['ok'] } })

    await runCodingAgentTask({ taskId: 't7', prompt: 'fix it' }, () => {})

    expect(recordAgentOutcome).toHaveBeenCalledWith({
      adapterId: 'acp',
      tag: 'general',
      outcome: 'success'
    })
  })

  it('records a failed attempt on the agent that actually ran, for every agent tried', async () => {
    activate('acp', 'openclaw')
    script({ openclaw: { failOpen: true }, acp: { stream: ['fallback answer'] } })

    await runCodingAgentTask({ taskId: 't8', prompt: 'fix it', agentId: 'openclaw' }, () => {})

    expect(recordAgentOutcome).toHaveBeenCalledWith({
      adapterId: 'openclaw',
      tag: 'general',
      outcome: 'failure'
    })
    expect(recordAgentOutcome).toHaveBeenCalledWith({
      adapterId: 'acp',
      tag: 'general',
      outcome: 'success'
    })
  })

  it('does not record an outcome for an auth prompt (not a capability signal)', async () => {
    activate('acp')
    script({ acp: { failWithError: new AcpError('Authentication required', -32000) } })

    await runCodingAgentTask({ taskId: 't9', prompt: 'fix it', agentId: 'acp' }, () => {})

    expect(recordAgentOutcome).not.toHaveBeenCalled()
  })

  it('does not record an outcome for a cancelled attempt', async () => {
    activate('acp')
    script({ acp: { hangUntilAborted: true } })

    const running = runCodingAgentTask({ taskId: 't10', prompt: 'never finishes' }, () => {})
    await new Promise((resolve) => setTimeout(resolve, 10))
    cancelTask('t10')
    await running

    expect(recordAgentOutcome).not.toHaveBeenCalled()
  })

  it('skips spawning a named-but-unconnected agent and hands over the real install command', async () => {
    // Nothing about Codex is configured — asking for it should never reach
    // profile.createAdapter (which would just throw a raw "requires
    // OMI_CODEX_ADAPTER_COMMAND" internal error instead of this).
    activate('acp')
    script({ acp: { stream: ['fallback answer'] } })
    const events: CodingAgentEvent[] = []

    const result = await runCodingAgentTask(
      { taskId: 't11', prompt: 'fix it', agentId: 'codex' },
      (e) => events.push(e)
    )

    expect(result).toMatchObject({ ok: true, adapterId: 'acp', text: 'fallback answer' })
    const statusMessages = events
      .filter((e): e is Extract<CodingAgentEvent, { type: 'status' }> => e.type === 'status')
      .map((e) => e.message)
    expect(statusMessages.some((m) => m.includes('npm install -g @openai/codex'))).toBe(true)
    // Codex was never actually spawned — only the fallback shows up as selected.
    const selected = events.filter(
      (e): e is Extract<CodingAgentEvent, { type: 'agent_selected' }> => e.type === 'agent_selected'
    )
    expect(selected.map((e) => e.adapterId)).toEqual(['acp'])
  })

  it('surfaces the install command as the final error when the named agent is the only candidate', async () => {
    activate()

    const result = await runCodingAgentTask(
      { taskId: 't12', prompt: 'fix it', agentId: 'codex' },
      () => {}
    )

    expect(result).toMatchObject({ ok: false, adapterId: null })
    expect(result.error).toContain('npm install -g @openai/codex')
  })
})
