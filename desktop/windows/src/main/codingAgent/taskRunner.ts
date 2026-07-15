// One coding-agent task, end to end: pick an adapter, open a binding, stream
// the attempt, and fall back to the next connected agent if the chosen one
// fails before producing any output. Held in memory only — a task lives for
// one invocation and its adapter process is torn down afterwards.

import { existsSync } from 'fs'
import { homedir } from 'os'
import { randomUUID } from 'crypto'
import {
  ADAPTER_PROFILES,
  adapterActivationError,
  adapterConfiguredCommand,
  adapterIsActivated,
  type AdapterCommandOverrides
} from './adapterRegistry'
import {
  PRODUCTION_ADAPTER_IDS,
  type CodingAgentAdapterId,
  type ProductionAdapterId,
  type RuntimeAdapter
} from './interface'
import { failureFromError, messageFrom } from './failures'
import type { CodingAgentEvent, CodingAgentResult, CodingAgentRunArgs } from '../../shared/types'

/** Preference order when no agent is named (or the named one falls over). */
export const AGENT_FALLBACK_ORDER = PRODUCTION_ADAPTER_IDS

export function candidateAgents(
  named: CodingAgentAdapterId | undefined,
  overrides: AdapterCommandOverrides,
  env: NodeJS.ProcessEnv = process.env
): CodingAgentAdapterId[] {
  const connected = AGENT_FALLBACK_ORDER.filter((id) => adapterIsActivated(id, overrides, env))
  if (!named) return [...connected]
  return [named, ...connected.filter((id) => id !== named)]
}

const CONNECTION_TEST_TIMEOUT_MS = 20_000

/**
 * Probe an agent by spawning its adapter and completing the ACP `initialize`
 * handshake, then tearing it down. Proves the configured command actually
 * launches and speaks ACP — the check behind Settings → Agents' Test button.
 */
export async function testAgentConnection(
  agentId: ProductionAdapterId,
  overrides: AdapterCommandOverrides = {},
  log: (message: string) => void = () => {}
): Promise<{ ok: boolean; error?: string }> {
  if (!adapterIsActivated(agentId, overrides)) {
    return { ok: false, error: adapterActivationError(agentId) ?? 'Not connected.' }
  }
  const adapter = ADAPTER_PROFILES[agentId].createAdapter({
    log: (message) => log(`[${agentId}:test] ${message}`),
    command: adapterConfiguredCommand(agentId, overrides)
  })
  // All production adapters are AcpRuntimeAdapter instances; `request` is the
  // cheapest real round-trip (start + initialize) without opening a session.
  const probe = adapter as unknown as {
    request(method: string, params?: Record<string, unknown>): Promise<unknown>
  }
  try {
    await Promise.race([
      probe.request('initialize', { protocolVersion: 1 }),
      new Promise((_resolve, reject) =>
        setTimeout(
          () => reject(new Error('The agent did not answer the ACP handshake in time.')),
          CONNECTION_TEST_TIMEOUT_MS
        )
      )
    ])
    return { ok: true }
  } catch (error) {
    return { ok: false, error: messageFrom(error) }
  } finally {
    void adapter.stop().catch(() => {})
  }
}

type ActiveTask = {
  abort: AbortController
  adapter: RuntimeAdapter | null
}

const activeTasks = new Map<string, ActiveTask>()

export function cancelTask(taskId: string): boolean {
  const task = activeTasks.get(taskId)
  if (!task) return false
  task.abort.abort()
  void task.adapter?.stop().catch(() => {})
  return true
}

function resolveCwd(requested: string | undefined): string {
  if (requested && existsSync(requested)) return requested
  return homedir()
}

/**
 * Run one task, emitting streaming events through `emit`. Tries the named
 * agent first (when given), then falls back through the remaining connected
 * agents — but only while the failing agent produced no visible output, so a
 * half-answered task is never silently re-run elsewhere.
 */
export async function runCodingAgentTask(
  args: CodingAgentRunArgs,
  emit: (event: CodingAgentEvent) => void,
  log: (message: string) => void = () => {}
): Promise<CodingAgentResult> {
  const overrides = args.commandOverrides ?? {}
  const candidates = candidateAgents(args.agentId, overrides)
  if (candidates.length === 0) {
    return {
      taskId: args.taskId,
      ok: false,
      adapterId: null,
      text: '',
      error: 'No coding agents are connected.'
    }
  }

  const abort = new AbortController()
  const task: ActiveTask = { abort, adapter: null }
  activeTasks.set(args.taskId, task)
  const cwd = resolveCwd(args.cwd)
  let lastError = 'The agent failed to start.'

  try {
    for (let i = 0; i < candidates.length; i++) {
      const adapterId = candidates[i]
      if (abort.signal.aborted) break
      const profile = ADAPTER_PROFILES[adapterId]
      const adapter = profile.createAdapter({
        log: (message) => log(`[${adapterId}] ${message}`),
        command: adapterConfiguredCommand(adapterId, overrides)
      })
      task.adapter = adapter
      emit({
        type: 'agent_selected',
        taskId: args.taskId,
        adapterId,
        displayName: profile.displayName,
        fallback: i > 0
      })

      let producedOutput = false
      try {
        const binding = await adapter.openBinding({
          sessionId: `omi-task-${randomUUID()}`,
          cwd
        })
        const result = await adapter.executeAttempt(
          {
            sessionId: binding.sessionId,
            runId: args.taskId,
            attemptId: `${args.taskId}-a${i}`,
            binding,
            prompt: [{ type: 'text', text: args.prompt }],
            mode: 'act'
          },
          (event) => {
            if (event.type === 'text_delta' && event.text) producedOutput = true
            emit({ ...event, taskId: args.taskId })
          },
          abort.signal
        )
        return {
          taskId: args.taskId,
          ok: result.terminalStatus === 'succeeded',
          adapterId,
          text: result.text,
          costUsd: result.costUsd,
          error:
            result.terminalStatus === 'succeeded'
              ? undefined
              : (result.failure?.userMessage ?? `The agent run ${result.terminalStatus}.`)
        }
      } catch (error) {
        const failure = failureFromError(error, {
          code: 'agent_task_failed',
          adapterId,
          source: 'adapter_execution'
        })
        lastError = failure.userMessage
        log(`[${adapterId}] task failed: ${messageFrom(error)}`)
        if (abort.signal.aborted) {
          return { taskId: args.taskId, ok: false, adapterId, text: '', error: 'Cancelled.' }
        }
        // Visible output already reached the user — retrying elsewhere would
        // double-answer. Surface the failure instead.
        if (producedOutput || i === candidates.length - 1) {
          return { taskId: args.taskId, ok: false, adapterId, text: '', error: lastError }
        }
        emit({
          type: 'status',
          taskId: args.taskId,
          message: `${profile.displayName} failed (${failure.userMessage}) — trying the next agent…`
        })
      } finally {
        void adapter.stop().catch(() => {})
      }
    }
    return { taskId: args.taskId, ok: false, adapterId: null, text: '', error: lastError }
  } finally {
    activeTasks.delete(args.taskId)
  }
}
