// Chat-session (v2) data-layer wire types for the Windows port. Types only —
// no client calls in this PR. Mirrors the backend contract in
// `backend/routers/chat_sessions.py` + `backend/models/chat_session.py`.
//
// Field naming: backend is snake_case on the wire; these TS shapes are camelCase
// and note the mapping per field (created_at → createdAt, etc.). The data layer
// (a later PR) is responsible for the snake↔camel translation.
//
// SHARED THREAD CONTINUITY (important): the default shared thread — the one
// mobile/web read via `/v2/messages` — is the `plugin_id == None` default
// session. To stay on it, OMIT `appId` and `sessionId` on saves. Passing a
// non-null `sessionId` targets a desktop-local sidebar thread that mobile's
// `/v2/messages` does NOT see. Only set them for explicit desktop-local threads.

/**
 * A v2 chat session (multi-session chat with title, preview, starring). Mirrors
 * backend `ChatSessionResponse`. `createdAt`/`updatedAt` come over the wire as
 * ISO-8601 strings (backend serializes `datetime`); `number` is allowed for
 * client-side epoch-ms usage. Backend always returns a `title` (defaults to
 * "New Chat"), so it is effectively always present. The backend also echoes a
 * `plugin_id` field that mirrors `app_id` for cross-platform query
 * compatibility; it is redundant with `appId` and omitted here.
 */
export interface ChatSession {
  id: string
  title?: string
  /** Preview text of the latest message (backend `preview`). */
  preview?: string
  /** Backend `created_at` (UTC), ISO-8601 string on the wire. */
  createdAt: number | string
  /** Backend `updated_at` (UTC), ISO-8601 string on the wire. */
  updatedAt: number | string
  /** Backend `app_id` — the app/plugin the session belongs to; null for main chat. */
  appId?: string
  /** Backend `message_count`. */
  messageCount: number
  starred: boolean
}

/** Body for `POST /v2/chat-sessions`. Mirrors backend `CreateChatSessionRequest`
 *  (`app_id` → `appId`). */
export interface CreateChatSessionRequest {
  title?: string
  appId?: string
}

/** Body for `PATCH /v2/chat-sessions/{id}`. Mirrors backend
 *  `UpdateChatSessionRequest`. */
export interface UpdateChatSessionRequest {
  title?: string
  starred?: boolean
}

/**
 * Body for `POST /v2/desktop/messages`. Mirrors backend `SaveMessageRequest`
 * (`app_id` → `appId`, `session_id` → `sessionId`, `client_message_id` →
 * `clientMessageId`, `message_source` → `messageSource`).
 *
 * `clientMessageId` (pattern `^[A-Za-z0-9_-]{1,128}$`) is the ONLY idempotency
 * key on the desktop persistence path — a retry with the same id is deduped.
 * OMIT `appId`/`sessionId` to write to the default shared thread (see file
 * header).
 */
export interface SaveDesktopMessageRequest {
  text: string
  sender: 'human' | 'ai'
  appId?: string
  sessionId?: string
  clientMessageId?: string
  messageSource?: 'desktop_chat' | 'realtime_voice'
  /**
   * DEVIATION FROM BRIEF / matches real backend: the backend `metadata` field
   * is typed `str | None` — a JSON-SERIALIZED STRING on the wire, not a JSON
   * object. Sending an object 422s. Callers must `JSON.stringify(...)` before
   * assigning (e.g. persisted resource cards under a `"resources"` key).
   */
  metadata?: string
}

/**
 * Ack for `POST /v2/desktop/messages`. Mirrors backend `SaveMessageResponse`.
 * `createdAt` is an ISO-8601 STRING (backend calls `datetime.isoformat()`).
 * `created` is false for an idempotent retry of an existing `clientMessageId`.
 * `sessionId` is optional to match the backend (`session_id: str | None`).
 */
export interface SaveDesktopMessageResponse {
  id: string
  createdAt: string
  sessionId?: string
  created: boolean
}
