// IPC surface for realtime-hub voice turns → the one kernel-owned transcript
// (INV-CHAT-1). The default (hub-native) voice path produces AND speaks a reply on
// the bar without ever reaching the kernel — so typed chat, the context tail, and
// mobile never see it. These two handlers close that gap the way macOS
// RealtimeHubController does:
//
//   * `voiceHub:recordTurn` records a COMPLETED hub turn (user + assistant) into the
//     SAME main_chat/chat/<chatId> conversation typed chat reads, origin
//     'realtime_voice'. That surface is the ONLY one whose turns appear in the typed
//     context tail (getMainChatTurnTail) — any other surfaceKind is a different
//     conversation. It records straight to the kernel store (no second transcript
//     store — INV-CHAT-1); the shared/mobile echo is the renderer's saveDesktopMessage.
//   * `voiceHub:getSeedContext` reads that same conversation back as the voice
//     session's continuity seed (read-only; never creates the conversation).
//
// OWNER AUTHORITY (INV-AGENT). The ownerId is host state (`controlPlaneOwnerId`),
// never taken off the renderer's args — same posture as agentControl.ts / mainChat.ts.
// Both handlers refuse while the owner is the shared DEFAULT_LOCAL_OWNER_ID (not
// signed in / the auth relay has not arrived) rather than key a conversation under
// the collision-prone default (the cold-start window mainChat.ts also fails closed on).

import { ipcMain } from 'electron'
import {
  controlPlaneOwnerId,
  getAgentRuntimeKernel,
  hasKnownControlPlaneOwner
} from '../agentKernel/controlPlane'
import type { AgentRuntimeKernel } from '../agentKernel/kernel'
import type { SurfaceRef } from '../agentKernel/surfaceSession'
import type {
  VoiceHubRecordTurnArgs,
  VoiceHubRecordTurnResult,
  VoiceHubSeedContext,
  VoiceHubSeedContextArgs
} from '../../shared/types'

/** Voice continuity seed window — a small Mac-parity window (macOS reads ~8 turns /
 *  3500 chars), deliberately distinct from the kernel's larger default so the seed
 *  the realtime instruction carries stays inside a low-latency budget. */
const VOICE_SEED_MAX_TURNS = 8
const VOICE_SEED_MAX_CHARACTERS = 3500

/** What the handlers need from the host. Defaulted to the process-wide kernel and
 *  the main-side authoritative owner; injected in tests. */
export interface VoiceHubDeps {
  kernel: AgentRuntimeKernel
  ownerId: string
  ownerReady: boolean
}

function defaultDeps(): VoiceHubDeps {
  return {
    kernel: getAgentRuntimeKernel(),
    ownerId: controlPlaneOwnerId(),
    ownerReady: hasKnownControlPlaneOwner()
  }
}

function mainChatSurfaceRef(chatId?: string): SurfaceRef {
  return {
    surfaceKind: 'main_chat',
    externalRefKind: 'chat',
    externalRefId: chatId?.trim() || 'default'
  }
}

/**
 * Record a completed hub voice turn into the kernel transcript. Origin
 * 'realtime_voice'; the kernel appends one user + one assistant row and dedupes on
 * `idempotencyKey` (the per-press turnId) via a last-32 metadata scan, so a retried
 * or double-fired record is a no-op. Fire-and-forget from the renderer's view.
 */
export function recordVoiceHubTurn(
  args: VoiceHubRecordTurnArgs,
  deps: VoiceHubDeps = defaultDeps()
): VoiceHubRecordTurnResult {
  if (!deps.ownerReady) return { recorded: false, duplicate: false, reason: 'owner_not_ready' }
  const userText = (args.userText ?? '').trim()
  const assistantText = (args.assistantText ?? '').trim()
  if (!userText && !assistantText) return { recorded: false, duplicate: false, reason: 'empty' }

  const result = deps.kernel.recordSurfaceTurn({
    ownerId: deps.ownerId,
    surfaceRef: mainChatSurfaceRef(args.chatId),
    userText,
    assistantText,
    origin: 'realtime_voice',
    interrupted: args.interrupted === true,
    idempotencyKey: args.idempotencyKey
  })
  return {
    recorded: result.recorded,
    duplicate: result.duplicate,
    conversationId: result.conversationId
  }
}

/**
 * Read the voice continuity seed for the main_chat conversation. Read-only: an
 * absent conversation returns an empty seed, so a renderer seed refresh never
 * writes to the store.
 */
export function readVoiceHubSeedContext(
  args: VoiceHubSeedContextArgs,
  deps: VoiceHubDeps = defaultDeps()
): VoiceHubSeedContext {
  if (!deps.ownerReady) return { context: '', idempotencyKeys: [] }
  const snapshot = deps.kernel.getVoiceSeedContextForMainChat({
    ownerId: deps.ownerId,
    chatId: args.chatId,
    maxTurns: VOICE_SEED_MAX_TURNS,
    maxCharacters: VOICE_SEED_MAX_CHARACTERS
  })
  return { context: snapshot.context, idempotencyKeys: snapshot.idempotencyKeys }
}

export function registerVoiceHubHandlers(): void {
  ipcMain.handle(
    'voiceHub:recordTurn',
    (_e, args: VoiceHubRecordTurnArgs): VoiceHubRecordTurnResult => recordVoiceHubTurn(args)
  )
  ipcMain.handle(
    'voiceHub:getSeedContext',
    (_e, args: VoiceHubSeedContextArgs = {}): VoiceHubSeedContext => readVoiceHubSeedContext(args)
  )
}
