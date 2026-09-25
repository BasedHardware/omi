import type { ChatEvidenceReference } from './knowledgeLedger'

export type JitRequestedFrameTerminalState = 'available' | 'offline' | 'pruned' | 'failed'

/** One stable local route for a JIT evidence card. Query values are encoded and
 * contain no screenshot bytes or OCR text. The existing Rewind route remains
 * the single UI owner for rendering the frame. */
export function rewindDeepLink(frameId: string | number): string {
  const value = String(frameId).trim()
  if (!value || value.length > 128 || !/^[A-Za-z0-9._:-]+$/.test(value))
    throw new Error('invalid rewind frame id')
  return `/#/rewind?frame_id=${encodeURIComponent(value)}`
}

export function buildJitKeyframeReference(input: {
  frameId: string | number
  capturedAtMs?: number
  conversationId?: string
}): ChatEvidenceReference {
  const id = String(input.frameId).trim()
  return {
    id: `jit-keyframe:${id}`,
    kind: 'keyframe',
    state: 'available',
    title: 'Screen keyframe',
    conversationId: input.conversationId,
    frameId: id,
    capturedAtMs: input.capturedAtMs,
    metadata: {
      deepLink: rewindDeepLink(id),
      retention: 'conversation_or_account_lifetime',
      retentionExempt: true,
      pin: 'conversation_keyframe'
    }
  }
}

export function buildJitRequestedFrameReference(input: {
  requestId: string
  state: JitRequestedFrameTerminalState
  errorCode?: string
  errorMessage?: string
  requestedAtMs?: number
  expiresAtMs?: number
}): ChatEvidenceReference {
  const requestId = input.requestId.trim()
  if (!requestId || requestId.length > 128) throw new Error('invalid frame request id')
  const requestedAtMs = input.requestedAtMs ?? Date.now()
  const expiresAtMs = input.expiresAtMs ?? requestedAtMs + 7 * 24 * 60 * 60_000
  if (
    !Number.isFinite(requestedAtMs) ||
    !Number.isFinite(expiresAtMs) ||
    expiresAtMs < requestedAtMs ||
    expiresAtMs - requestedAtMs > 7 * 24 * 60 * 60_000
  )
    throw new Error('requested frame TTL must be at most seven days')
  return {
    id: `jit-request:${requestId}`,
    kind: 'request',
    state: input.state,
    requestId,
    ...(input.errorCode ? { errorCode: input.errorCode.slice(0, 128) } : {}),
    ...(input.errorMessage ? { errorMessage: input.errorMessage.slice(0, 600) } : {}),
    metadata: { retention: 'temporary_unattached_request', requestedAtMs, expiresAtMs }
  }
}

/** Conversation JIT is allowed to attach at most one approved keyframe. */
export function selectSingleConversationKeyframe(frameIds: Array<string | number>): string | null {
  const candidates = frameIds
    .map(String)
    .map((value) => value.trim())
    .filter((value) => /^[A-Za-z0-9._:-]{1,128}$/.test(value))
    .sort()
  return candidates[0] ?? null
}
