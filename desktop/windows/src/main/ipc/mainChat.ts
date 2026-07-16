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
import { DEFAULT_LOCAL_OWNER_ID } from '../agentKernel/controlTools'
import { formatTranscriptTail } from '../agentKernel/turnContext'
import type { AgentRuntimeKernel } from '../agentKernel/kernel'
import type { AgentEvent } from '../agentKernel/types'
import type { MainChatEvent, MainChatResult, MainChatSendArgs } from '../../shared/types'

/** The main_chat surface the kernel resolves a turn against. */
const MAIN_CHAT_ADAPTER_ID = 'pi-mono'

/** How many prior transcript turns to inject as the per-session context tail.
 *  Matches getMainChatTurnTail's default (kernelSessions.ts). */
const MAIN_CHAT_TAIL_LIMIT = 8

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
    case 'run.failed': {
      // Two terminal-failure payload shapes carry the message differently:
      //  - pre-execution failure (failAttemptBeforeExecution): { errorMessage, failure }
      //  - adapter-returned failure (finishAttemptAndRun, the common case): payload is
      //    { runId, status, failure } with the message at failure.userMessage — NO
      //    errorMessage key. Read both so the streamed error is never dropped.
      const failure = payload.failure as { userMessage?: unknown } | undefined
      const error = payload.errorMessage
        ? String(payload.errorMessage)
        : failure?.userMessage
          ? String(failure.userMessage)
          : undefined
      return { type: 'run_finished', requestId, runId, status: 'failed', error }
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
    // Cold-start gate: refuse before the auth relay has wired the signed-in owner.
    // pi-mono managed cloud requires a Firebase session anyway, so ownerId still at
    // the shared DEFAULT_LOCAL_OWNER_ID means either not-signed-in or the relay has
    // not arrived yet. Resolving a surface session here would key it under that
    // shared constant — the exact cross-account collision the owner wiring closes —
    // and it would never migrate to the real uid. Fail closed instead.
    if (ownerId === DEFAULT_LOCAL_OWNER_ID) {
      throw new Error('Sign-in has not completed yet — try again in a moment.')
    }
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

    // Per-session memory (Approach B): pi-mono's run does NOT thread a surfaceRef
    // through assembleTurnContext, so it never gets the per-chatId
    // <conversation_history> tail. And a pi subprocess has no native resume
    // (resumeFidelity:'none') — a restart drops its in-memory conversation. So we
    // inject the tail here: read THIS chatId's prior turns and prepend them to the
    // prompt. The read happens BEFORE recordSurfaceTurn below so the just-sent user
    // turn is not in the tail (no duplication). On a session's first turn the
    // conversation is empty → no tail → prompt unchanged. Keyed by chatId + read
    // from SQLite, so it is per-session and cross-restart durable, with no
    // kernel-core edit. (Verified live: chat A→B→A — B never sees A's context, A
    // recalls after the detour; matches macOS's shipped multichat behavior.)
    //
    // Cross-session isolation holds because pi-mono is requiresPinnedWorker:true —
    // each chatId pins its OWN worker+subprocess (workerPool.ts), so a live pi
    // conversation is never shared between chats. The pin-EVICTION edge — when
    // concurrently-active pinned pi chats exceed the worker-pool cap, an evicted
    // worker reassigned to a new chat kept its still-alive subprocess (its old
    // chat's turns), a narrow same-user context bleed — is now closed:
    // PiMonoRuntimeAdapter.openBinding sends pi `new_session` when it reassigns a
    // live subprocess (piMono.ts), and the pi-mono pool is capped at
    // configuredPiMonoMaxWorkers (workerPool.ts). This tail injection then
    // re-seeds the reassigned chat's own history.
    const tail = kernel.getMainChatTurnTail(ownerId, MAIN_CHAT_TAIL_LIMIT, chatId)
    const history = formatTranscriptTail(tail.turns)
    const effectivePrompt = history ? `${history}\n\n${args.prompt}` : args.prompt

    // Record the clean user turn on the kernel transcript (empty assistant text →
    // only the user turn is appended; the run appends the assistant turn at
    // completion). Idempotency-keyed on `idempotencyKey ?? requestId`: a retried
    // send with the same id never double-appends, AND a voice CASCADE turn threads
    // its per-press turnId here so its user-turn record shares the key a hub-native
    // record would use — the belt-and-suspenders half of the INV-CHAT-1
    // double-record fix (primary guarantee: hub XOR cascade per press).
    kernel.recordSurfaceTurn({
      ownerId,
      surfaceRef,
      userText: args.cleanUserText,
      assistantText: '',
      origin: 'main_chat',
      idempotencyKey: args.idempotencyKey?.trim() || requestId
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
      prompt: effectivePrompt,
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
