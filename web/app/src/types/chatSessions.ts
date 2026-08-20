/**
 * Chat-session wire types, mirroring `backend/routers/chat_sessions.py`.
 *
 * Shapes are camelCase to match the desktop clients (and so the ported view
 * helpers work unchanged); `lib/api.ts` translates snake_case on the wire.
 *
 * Shared-thread continuity: the default thread every client reads through
 * `/v2/messages` is the `plugin_id == null` session. Omitting `chat_session_id`
 * stays on it; passing one targets that specific session.
 */
export interface ChatSession {
  id: string;
  title?: string;
  /** Preview text of the latest message (backend `preview`). */
  preview?: string;
  /** Backend `created_at` (UTC), ISO-8601 on the wire. */
  createdAt: number | string;
  /** Backend `updated_at` (UTC), ISO-8601 on the wire. */
  updatedAt: number | string;
  /** Backend `app_id`; null for the main chat. */
  appId?: string;
  /** Backend `message_count`. */
  messageCount: number;
  starred: boolean;
}
