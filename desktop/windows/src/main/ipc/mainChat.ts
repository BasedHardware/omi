// IPC surface for kernel-routed main chat (the pi-mono managed-cloud door).
// Follows the house pattern: invoke-style handlers plus a broadcast channel for
// streaming turn events (the main window and the bar may render the same turn).
//
// DARK after PR-E1: the door exists but nothing in the renderer calls it. Default
// typed chat still routes through /v2/messages; PR-E2 adds the renderer branch on
// `chat:getEngine`. Routing a turn here goes through the kernel run path
// (resolveSurfaceSession -> sendAgentMessage), NOT the control-tool spawn path that
// `assertControlSpawnAdapterNotManagedCloud` guards — this is a different door.

import { ipcMain, BrowserWindow } from 'electron'
import { getAppSettings } from '../appSettings'
import { getAgentRuntimeKernel, controlPlaneOwnerId } from '../agentKernel/controlPlane'
import type { AgentRuntimeKernel } from '../agentKernel/kernel'
import type { AgentEvent } from '../agentKernel/types'
import type { MainChatEvent, MainChatResult, MainChatSendArgs } from '../../shared/types'

/** The main_chat surface the kernel resolves a turn against. */
const MAIN_CHAT_ADAPTER_ID = 'pi-mono'

/** Kernel run-lifecycle event types that mean the turn is over. */
const TERMINAL_RUN_EVENT_TYPES = new Set(['run.succeeded', 'run.failed', 'run.cancelled'])

/** What `runMainChatTurn` needs from the host. Defaulted to the process-wide
 *  kernel and the main-side authoritative owner; injected in tests. */
export interface MainChatTurnDeps {
  kernel: AgentRuntimeKernel
  ownerId: string
}

function defaultDeps(): MainChatTurnDeps {
  return { kernel: getAgentRuntimeKernel(), ownerId: controlPlaneOwnerId() }
}

function broadcast(event: MainChatEvent): void {
  for (const win of BrowserWindow.getAllWindows()) {
    if (!win.isDestroyed()) {
      win.webContents.send('mainChat:event', event)
    }
  }
}

function parsePayload(event: AgentEvent): Record<string, unknown> {
  try {
    const parsed = JSON.parse(event.payloadJson)
    return parsed && typeof parsed === 'object' ? (parsed as Record<string, unknown>) : {}
  } catch {
    return {}
  }
}

/**
 * Project one persisted kernel event onto the main-chat wire union, or `null` for
 * events the chat UI does not render. Streaming events (`message.delta`,
 * `progress.updated`, `tool.*`) carry the raw adapter stream event as their
 * payload, so the inner `type` is the source of truth for tool_activity vs
 * tool_result_display (both of which the kernel collapses onto `tool.completed`).
 */
export function projectKernelEvent(
  event: AgentEvent,
  requestId: string,
  runId: string
): MainChatEvent | null {
  const payload = parsePayload(event)
  switch (event.type) {
    case 'run.starting':
    case 'run.running':
      return { type: 'status', requestId, runId, message: event.type }
    case 'message.delta':
      return { type: 'text_delta', requestId, runId, text: String(payload.text ?? '') }
    case 'progress.updated':
      if (payload.type !== 'thinking_delta') return null
      return { type: 'thinking_delta', requestId, runId, text: String(payload.text ?? '') }
    case 'tool.started':
    case 'tool.updated':
    case 'tool.failed':
    case 'tool.completed': {
      if (payload.type === 'tool_result_display') {
        return {
          type: 'tool_result_display',
          requestId,
          runId,
          toolUseId: String(payload.toolUseId ?? ''),
          name: String(payload.name ?? ''),
          output: String(payload.output ?? '')
        }
      }
      if (payload.type === 'tool_activity') {
        return {
          type: 'tool_activity',
          requestId,
          runId,
          name: String(payload.name ?? ''),
          status: payload.status as 'started' | 'completed' | 'failed',
          toolUseId: payload.toolUseId === undefined ? undefined : String(payload.toolUseId),
          input:
            payload.input && typeof payload.input === 'object'
              ? (payload.input as Record<string, unknown>)
              : undefined
        }
      }
      return null
    }
    case 'message.completed':
      return { type: 'completed', requestId, runId, text: String(payload.text ?? '') }
    case 'run.succeeded':
      return { type: 'run_finished', requestId, runId, status: 'succeeded' }
    case 'run.cancelled':
      return { type: 'run_finished', requestId, runId, status: 'cancelled' }
    case 'run.failed':
      return {
        type: 'run_finished',
        requestId,
        runId,
        status: 'failed',
        error: payload.errorMessage ? String(payload.errorMessage) : undefined
      }
    default:
      return null
  }
}

/** A per-send client id, unique so `run.queued` can be correlated to this send. */
function generateClientId(): string {
  return `main-chat-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

/**
 * Route one main-chat turn through the kernel to the managed-cloud pi-mono adapter,
 * streaming projected events over `broadcast` and resolving with the final outcome.
 *
 * Correlation: the kernel assigns the runId internally, so we subscribe BEFORE
 * dispatching and capture it from the first `run.queued` event whose payload
 * carries our (uniquely generated) clientId. From then on we forward only events
 * for that runId, so concurrent turns never leak into each other's stream, and we
 * unsubscribe on the terminal run event.
 *
 * Transcript: the run records only the ASSISTANT turn (bare sendAgentMessage does
 * not thread a surfaceRef, and threading one would re-run assembleTurnContext and
 * store the contexted prompt as the user turn). So we record the CLEAN user turn
 * ourselves — main-side, before dispatch — via recordSurfaceTurn with an empty
 * assistant text (which appends only the user turn). Both land on the SAME
 * conversation the run resolves, giving one clean user + one assistant turn per
 * send. Keeping this write here (not in a separate renderer IPC call) makes the
 * main-chat door the single kernel-transcript writer.
 */
export async function runMainChatTurn(
  args: MainChatSendArgs,
  emit: (event: MainChatEvent) => void,
  deps: MainChatTurnDeps = defaultDeps()
): Promise<MainChatResult> {
  const { kernel, ownerId } = deps
  const requestId = args.requestId
  const clientId = generateClientId()
  const chatId = args.chatId?.trim() || 'default'
  let capturedRunId: string | null = null
  let unsubscribe: () => void = () => {}

  try {
    const surfaceRef = {
      surfaceKind: 'main_chat',
      externalRefKind: 'chat',
      externalRefId: chatId
    }
    // Pin the session to pi-mono / managed_cloud FIRST (this creates the session +
    // surface_conversations mapping), so the user-turn record below reads that
    // pinned session rather than creating an unpinned 'acp' one.
    const session = kernel.resolveSurfaceSession({
      ownerId,
      surfaceRef,
      defaultAdapterId: MAIN_CHAT_ADAPTER_ID
    })

    // Record the clean user turn on the kernel transcript (empty assistant text →
    // only the user turn is appended; the run appends the assistant turn at
    // completion). Idempotency-keyed on requestId so a retried send with the same
    // id never double-appends.
    kernel.recordSurfaceTurn({
      ownerId,
      surfaceRef,
      userText: args.cleanUserText,
      assistantText: '',
      origin: 'main_chat',
      idempotencyKey: requestId
    })

    unsubscribe = kernel.subscribe((event) => {
      if (capturedRunId === null) {
        if (event.type !== 'run.queued' || event.runId === null) return
        if (parsePayload(event).clientId !== clientId) return
        capturedRunId = event.runId
        emit({ type: 'accepted', requestId, runId: capturedRunId })
        return
      }
      if (event.runId !== capturedRunId) return
      const projected = projectKernelEvent(event, requestId, capturedRunId)
      if (projected) emit(projected)
      if (TERMINAL_RUN_EVENT_TYPES.has(event.type)) unsubscribe()
    })

    const result = await kernel.sendAgentMessage({
      sessionId: session.agentSessionId,
      ownerId,
      clientId,
      requestId,
      prompt: args.prompt,
      adapterId: MAIN_CHAT_ADAPTER_ID
    })

    return {
      runId: result.run.runId,
      requestId,
      ok: result.terminalStatus === 'succeeded',
      text: result.text,
      terminalStatus: result.terminalStatus,
      costUsd: result.run.costUsd ?? undefined,
      error: result.run.errorMessage ?? undefined
    }
  } catch (error) {
    // resolveSurfaceSession / the pre-dispatch boundary check can throw; the run
    // itself resolves with terminalStatus 'failed' rather than throwing. Surface a
    // terminal event either way so a subscribed renderer stops waiting.
    const message = error instanceof Error ? error.message : String(error)
    emit({
      type: 'run_finished',
      requestId,
      runId: capturedRunId ?? '',
      status: 'failed',
      error: message
    })
    return {
      runId: capturedRunId ?? '',
      requestId,
      ok: false,
      text: '',
      terminalStatus: 'failed',
      error: message
    }
  } finally {
    unsubscribe()
  }
}

export function registerMainChatHandlers(): void {
  ipcMain.handle(
    'mainChat:send',
    (_e, args: MainChatSendArgs): Promise<MainChatResult> => runMainChatTurn(args, broadcast)
  )

  ipcMain.handle('mainChat:cancel', async (_e, runId: string): Promise<boolean> => {
    const result = await getAgentRuntimeKernel().cancelRun(runId, {
      ownerId: controlPlaneOwnerId()
    })
    return result.accepted
  })

  ipcMain.handle('chat:getEngine', (): 'legacy_sse' | 'pi_mono' => getAppSettings().chatEngine)
}
