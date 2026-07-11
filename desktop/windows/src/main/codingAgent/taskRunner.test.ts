import { beforeEach, describe, expect, it, vi } from 'vitest'
import { candidateAgents, cancelTask, runCodingAgentTask } from './taskRunner'
import { ADAPTER_PROFILES, adapterConfiguredCommand, adapterIsActivated } from './adapterRegistry'
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

type FakeScript = {
  /** Throw from openBinding (simulates a dead/unconfigured adapter). */
  failOpen?: boolean
  /** Text deltas to stream before resolving. */
  stream?: string[]
  /** Throw from executeAttempt after streaming (post-output failure). */
  failAfterStream?: boolean
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
  })

  it('orders unnamed tasks Claude Code first, connected agents only', () => {
    activate('acp', 'codex')
    expect(candidateAgents(undefined, {})).toEqual(['acp', 'codex'])
  })

  it('puts the named agent first with the rest as fallbacks', () => {
    activate('acp', 'openclaw', 'hermes')
    expect(candidateAgents('hermes', {})).toEqual(['hermes', 'acp', 'openclaw'])
  })
})

describe('runCodingAgentTask', () => {
  beforeEach(() => {
    vi.mocked(adapterIsActivated).mockReset()
    vi.mocked(adapterConfiguredCommand).mockReturnValue(undefined)
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
})
