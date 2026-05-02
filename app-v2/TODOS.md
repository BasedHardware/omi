# TODOS — app-v2

Deferred work captured during planning. Add to a sprint when picking up.

## Bound `home.actions.v1` retention to 90 days

**What:** On `main()` boot, compact the `home.actions.v1` Hive box by deleting rows whose `ts` is older than 90 days.

**Why:** The action log accumulates a row per dismiss / snooze / tap-through / open / accept. Over months of dogfood, thousands of rows. Unbounded local growth has no functional value beyond ~30–60 days; older rows aren't read by any generator's dedup check.

**Pros:**
- Keeps Hive open-box latency bounded at cold start.
- Trivial implementation (~5 lines): iterate keys, delete where `now - ts > 90d`.
- Invisible to the user.

**Cons:**
- Tiny scope creep on whichever sprint picks it up.
- Loses ability to do retention analytics from prior 90+ days (but no current analysis depends on that).

**Context:** Surfaced during `/plan-eng-review` of the Companion Stream Home design (2026-04-30). The full design doc is at `~/.gstack/projects/togodynamicslab-omi/matheusoliviera-main-design-20260430-111632.md` — see "Performance notes" section.

**Depends on:** Sprint 0 having shipped (`home.actions.v1` Hive box must exist). After that, do anytime.

## Bound chat session message retention (per-session cap)

**What:** Replace the existing global `ChatBoxes.retentionLimit` cap in `ChatProvider._trim()` with a per-session cap (e.g., last 200 messages per session). After each message is added to a session, trim that session's list to the cap.

**Why:** Today the cap is global across all messages. With chat sessions landing, one chatty session can push out messages from other sessions. Result: user opens an older session and finds the start of the conversation gone, even though they only ever exchanged 50 messages there.

**Pros:**
- Each session preserves its own history independent of activity in other sessions.
- Same family of fix as `home.actions.v1` retention TODO — bounded local growth.
- Simple change (~15 min): `_trim(sessionId)` after each per-session insert.

**Cons:**
- Power users with one very long session would lose old messages there earlier than under the global cap.
- Still doesn't bound total session count (separate concern).

**Context:** Surfaced during `/plan-eng-review` of the chat-sessions design (2026-05-01). Full design doc at `~/.gstack/projects/togodynamicslab-omi/matheusoliviera-main-design-chat-sessions-20260501-093400.md` — see Performance Review issue 4.1.

**Depends on:** Chat sessions PR shipping first (`chat.sessions.v1` box and per-session message map must exist).

## Expose backend session_id on /v2/messages for true multi-session

**What:** In `backend/routers/chat.py`, accept an optional `session_id` query param on POST `/v2/messages`, GET `/v2/messages`, and DELETE `/v2/messages`. Overload `chat_db.acquire_chat_session` to either find a specific session by id or fall back to the current `(uid, app_id)` lookup. `backend/database/chat.py:get_chat_session_by_id` already exists — wire it as the primary lookup when session_id is supplied.

**Why:** Currently the backend has exactly one `ChatSession` per `(uid, app_id)`. App-v2's chat-sessions v0 ships client-side sessions on top, but the backend LLM still sees all messages for that user — server-side memory bleeds across what the user thinks are separate chats. ChatGPT parity needs server-side isolation.

**Pros:**
- True isolation: each chat thread has its own LLM context, no memory bleed between threads.
- Unblocks cross-device session sync (the same session_id works on iPhone + desktop-v2).
- Backend `ChatSession` model already exists (`backend/models/chat.py:204`) — much smaller change than originally estimated (~1 day, not 2-3).

**Cons:**
- Touches the chat router that desktop-v2 and the legacy app share — needs careful regression testing.
- Schema change on the `messages` and `chat_sessions` Firestore collections (backfill old messages with a default session_id).
- Mobile + desktop clients both need to pass session_id on every send after rollout.

**Context:** Surfaced during `/plan-eng-review` of chat-sessions design (2026-05-01). The original design doc premise stated "backend doesn't have session_id concept" — that was wrong; backend has a 1:1 `(uid, app_id)` → session model. This TODO is the v0.1 follow-up to make it n:1 per user.

**Depends on:** App-v2 chat-sessions v0 shipping first (so we have a real surface that exercises the backend change).

## Search across chat sessions

**What:** Add a search input to the top of the chat sessions drawer (`ChatSessionsDrawer`). Filter sessions by title + first user message text. Best implemented after the backend `session_id` work lands so the search hits the server's full session history rather than just local Hive cache.

**Why:** Once a user has 10+ chat sessions, scrolling Today / Yesterday / This Week / Older buckets to find "where did I ask about X?" gets tedious. Search is one of ChatGPT's most-used features.

**Pros:**
- Power-user feature that compounds value as the session count grows.
- Building once over the cross-device backend session_id substrate is the right move (avoids throwaway local-only search code).
- Small UI: search input in drawer header, filter logic in `ChatSessionsProvider` (or equivalent).

**Cons:**
- Until backend session_id ships, search would only see local sessions on the current device — incomplete answer for a cross-device user.
- Adds one more failure mode (search returns 0 results — needs empty state).

**Context:** Surfaced during `/plan-ceo-review` of chat-sessions design (2026-05-01, SELECTIVE EXPANSION mode). Considered for v0 inclusion and explicitly deferred — see CEO plan at `~/.gstack/projects/togodynamicslab-omi/ceo-plans/2026-05-01-chat-sessions.md` for the deferral reasoning.

**Depends on:** Backend session_id TODO (above) shipping first — search becomes meaningful once session history is cross-device.
