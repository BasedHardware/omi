# Desktop Chat: Backend-Authoritative History (stop the wipe, rehydrate, backfill)

Date: 2026-07-22
Branch: `fix/desktop-chat-backend-authoritative` (base `main`)
Owner: Archit

## Problem

Desktop chat history repeatedly collapses to near-empty on the account. Verified live on the running
`com.omi.omi-main` build: its local journal holds **2 turns** (both proactive notifications); the backend
(`users/{uid}/messages`) returns the **same 2**; the production bundle `com.omi.computer-macos` still holds
**82 turns** (79 `backend_import`) in its *local* journal only.

### Root cause (confirmed end-to-end)

1. Desktop chat persists to the backend (`users/{uid}/messages`) and rehydrates via the working
   reconcile path (`GET /v2/desktop/messages/reconcile`, `chat_sessions.py:208`). Delivery is gated by
   **surface** (`LOCAL_ONLY_SURFACES = {task_chat, workstream}`), not origin — so `main_chat` turns
   (typed and notification) all persist. The backend is effectively authoritative already.
2. **A reset hard-wipes the entire backend chat.** `clearDefaultJournalForOnboardingReset()`
   (`ChatProvider.swift:5866`, called from `AppState+SystemActions.swift:199` during **onboarding reset**,
   *no production guard*) → `kernelTurnProjection.clear(surface: mainChat("default"))` →
   daemon `clearJournalConversation` (`conversation-journal.ts:1092`) → `enqueueBackendConversationDelete`
   (`:1536`). For the `default` surface `backendTargetForConversation` (`:1272`) resolves
   `target_kind = "messages"`, which drains to `DELETE /v2/desktop/messages` with **no session** —
   a batched **hard delete of ALL the user's main-chat messages** (`chat.py:820`, no tombstone).
3. Reconcile + the one-time importer then faithfully mirror the emptied backend to every install.
   Repeated onboarding-reset iterations drove 79 → 2.

This is a **production data-loss bug**: any real user who re-runs onboarding hard-deletes their cloud chat history.

## Goal

The backend (production) is the single authoritative archive. Every deployment — including a fresh /
renamed / promoted build — rehydrates the **full** history and stays in sync. No reset, migration, or
onboarding flow may silently destroy server history. Nothing lost: stranded local-only history is
restored to the backend.

## Design

### Part A — Stop the destructive wipe (P0, highest priority: the active bug)

A **reset is not a delete.** Resetting local app state (onboarding re-walkthrough, non-prod harness) must
clear only the **local** journal/projection and must **never** enqueue a backend `target_kind=messages`
delete.

- Daemon: add a **local-only clear** to `clearJournalConversation` (a `deleteBackend: bool` param, default
  keeps today's behavior for the explicit user path) that performs the local generation bump + local turn
  purge **without** calling `enqueueBackendConversationDelete`. Plumb through the `journal_clear_turns` RPC
  (`agent/src/index.ts:2449`, `protocol.ts:361`) and `KernelTurnProjection.clear(surface:localOnly:)`.
- Swift: `clearDefaultJournalForOnboardingReset()` and the non-prod harness resets call the **local-only**
  clear. Onboarding/harness never touch backend chat.
- Guardrail (mechanical, prevents recurrence): the daemon only enqueues a `target_kind=messages`
  delete-all from the **explicit** user clear path; a `local-only` clear that reaches
  `enqueueBackendConversationDelete` is a bug. Add a daemon unit test asserting a local-only clear inserts
  **zero** `backend_conversation_delete_outbox` rows.

The explicit user **"Clear history"** button (`clearChat()`, `:5872`) keeps deleting backend messages
(that is a deliberate user action), but scoped to the current chat/session as today.

### Part B — Backend-authoritative full rehydrate

- The reconcile driver already keyset-pages `/v2/desktop/messages/reconcile` continuously. Ensure
  `loadDefaultChatMessages()` drives a **full** reconcile (drains all pages) so a fresh install pulls the
  entire backend thread, not just the first page.
- Relax the one-time legacy-import checkpoint (`kernelJournal.legacyBackendImport.v1|...`,
  `ChatProvider.swift:3020-3073`): it is now redundant with continuous reconcile and can strand history if
  it set on a partial. Keep the import idempotent (it already replays via `importRemoteTurn`) but do not
  let a set checkpoint suppress a full reconcile. Local journal = cache; backend = truth.

### Part C — One-time backfill of stranded local history (idempotent, "nothing lost")

- On launch, a bounded migration re-asserts every local `main_chat` turn to the backend via
  `POST /v2/desktop/messages` with a **stable `client_message_id`** (the turn's existing canonical id /
  `client_message_id`, matching `^[A-Za-z0-9_-]{1,128}$`). Backend create is **create-if-absent** keyed on
  that id (`chat.py:747-763`), so:
  - turns already on the backend → no-op (`created: false`), no duplicates;
  - turns wiped from the backend but still in a local journal (e.g. production's 79) → **restored**, then
    propagated to all installs by reconcile.
- Runs where the history physically is (e.g. `com.omi.computer-macos`). Checkpointed
  (`kernelJournal.backfillReassert.v1|<owner>`) so it runs once per install; re-runnable is safe anyway.
- Ordering preserved by each turn's `created_at`.
- The migration **never calls DELETE** and never runs before Part A (or a stale delete could still be
  draining). Sequence in code: Part A guard active → reconcile → backfill.

## Non-goals / YAGNI

- No new backend `/reconcile` semantics — the endpoint exists and works.
- No soft-delete/tombstone system server-side (out of scope; Part A removes the destructive trigger instead).
- No cross-install shared local store (backend is the shared truth).

## Environment note

"The production one" = the prod backend. Shipped builds already target prod, so this makes them correct by
construction; the backfill uploads to prod. Dev/test bundles on the dev backend are a separate store
(expected).

## Testing

- **Daemon (TS):** local-only clear inserts 0 `backend_conversation_delete_outbox` rows; explicit clear
  inserts exactly 1. Backfill re-assert is idempotent (second run inserts 0 new backend rows).
- **Backend (Python, hermetic):** `save_message` idempotency by `client_message_id` (re-POST → `created:false`,
  no dup, counters not double-bumped) — regression test for the backfill's core guarantee.
- **Swift:** `clearDefaultJournalForOnboardingReset` uses the local-only path (no delete outbox enqueue);
  `loadDefaultChatMessages` drains all reconcile pages.
- **Live verification:** on `com.omi.omi-main`, clear the import checkpoint + run backfill from the
  production journal → confirm the full thread rehydrates from the backend and survives an onboarding reset.

## Rollout / sequencing (single PR, per user)

Part A first in the diff (stops active data loss), then Part B, then Part C. Full gate: `backend/test.sh`,
desktop build, daemon tests, pre-push, CI green, cubic review with no P1s → auto-merge (user pre-authorized,
including the prod-data backfill).
