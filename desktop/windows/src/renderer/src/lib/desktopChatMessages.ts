// Explicit shared-thread persistence for the kernel-routed (pi_mono) chat engine
// (INV-CHAT-1). The legacy /v2/messages path gets shared/mobile-thread continuity
// for free as a server side-effect of that POST; the pi-mono managed-completions
// path does NOT, so the renderer must persist each turn's user + assistant message
// itself via POST /v2/desktop/messages (the same endpoint macOS's ChatProvider
// calls). Best-effort: continuity must never throw into or block the chat flow.
//
// Default shared thread: OMIT app_id and session_id so the write lands on the
// `plugin_id == None` default session that mobile/web read via /v2/messages.
// Windows default typed chat is ALWAYS the default chat, so both are always omitted.

import { omiApi } from './apiClient'
import type {
  SaveDesktopMessageRequest,
  SaveDesktopMessageResponse
} from '../../../shared/chatSessions'

/**
 * Persist one chat message to the shared thread. Returns the server ack, or `null`
 * when the write failed (network/auth/validation) — callers treat continuity as
 * fire-and-forget and never surface this failure in the chat UI.
 *
 * The wire body is snake_case with nil optionals OMITTED (not sent as null); an
 * object `metadata` 422s, so callers pass a pre-serialized JSON string.
 */
export async function saveDesktopMessage(
  req: SaveDesktopMessageRequest
): Promise<SaveDesktopMessageResponse | null> {
  const body: Record<string, unknown> = {
    text: req.text,
    sender: req.sender,
    message_source: req.messageSource ?? 'desktop_chat'
  }
  if (req.appId !== undefined) body.app_id = req.appId
  if (req.sessionId !== undefined) body.session_id = req.sessionId
  if (req.clientMessageId !== undefined) body.client_message_id = req.clientMessageId
  if (req.metadata !== undefined) body.metadata = req.metadata
  try {
    const res = await omiApi.post('/v2/desktop/messages', body)
    return res.data as SaveDesktopMessageResponse
  } catch {
    return null
  }
}
