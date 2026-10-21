# Messaging package map

The gateway admits verified webhooks into an encrypted inbox, then separately runs
shared chat turns. Channel content is user-serving only. The package has no import-time
provider or database IO. See `backend/docs/messaging-channels.md` for Stage A and
`backend/docs/messaging-adapters.md` for Stage B configuration, provider facts and QA.

- `contracts.py`: channel messages, verified provider attachment references, owned
  artifacts, capabilities, principals and provider-neutral protocols.
- `access.py`, `identity.py`: existing entitlement/cohort admission and stable identity keys.
- `gateway.py`: durable admission, leases, media preparation, commands, shared turns,
  typing lifecycle, bounded awareness history, and fenced deferred replies.
- `outbound.py`, `delivery_context.py`: one reply policy and per-sink sequencing,
  retry guards, rendering metadata, artifacts and surface actions.
- `projection.py`: one catalog projection for advertisement and execution; channels
  omit device charts, app retains its existing tools.
- `turn_context.py`: original request clocks for shaped evidence and phone reminder confirmations.
- `history.py`, `app_awareness.py`: cross-surface append-only awareness and search.
- `utils/retrieval/chat_mount.py`: shared shaped prompt and surface-aware legacy
  prompt loading; channels avoid context IO for a prompt their runner discards.
- `undo.py`: shared encrypted five-minute inverse receipts, owner-scoped app undo,
  durable content-free audits, and exact field snapshots; reserves before supported writes,
  emits shared memoryLink/taskCard action receipts, scopes inverse claims per action,
  and delegates slow inverses to domain authorities without occupying the chat lease.
- `adapters/base.py`: shared pacing, owned-file tools and media preparation.
- `adapters/telegram.py`: private-chat Bot API verification, parsing, drafts and delivery.
- `adapters/linq.py`: replaceable `IMessageProvider` and Linq implementation.
- `adapters/transport.py`: bounded, redacted provider IO and retry semantics.
- `albums.py`: pure album merge/debounce rules; `album_turn.py`: incremental media
  preparation and generation sealing on the channel worker path.
  `database/messaging_albums.py` owns transactional batch append/seal on the existing inbox/lease.
- `adapters/modalities.py`: lightweight acknowledgements and untrusted location evidence.
- `adapters/media.py`: Omi's existing chat file store and prerecorded STT bridge.
- `adapters/delivery.py`: content-free provider receipts and atomic send/receive guard.
- `metrics.py`, `pacing.py`, `maintenance.py`: content-free instrumentation, shared Redis Telegram scheduling and bounded hourly retention.
- `adapters/runtime.py`: explicit opt-in registration and pending-only recovery.

Storage authority remains `database/messaging.py`, task codecs/inverses remain in
`database/action_items.py` and `database/action_item_codec.py`, and memory inverses use
`MemoryService`. No adapter can select a different user or accept arbitrary remote URLs
from tools. Test contracts, transport doubles and the manual live dev listener are under
`backend/testing/messaging`; executable suites are under `backend/tests/unit`.

Shaped context assembly is owned by `utils/retrieval/shaped_chat.py` and
`context.py`: shared 10–17-message epochs, encrypted rolling summary before history,
volatile digest/scope/clock in the final user turn, eligible stable explicit boundaries.
`database/chat_context.py` owns source paging, generation invalidation and CAS state.
Channel events remain bounded audit/fence data; only the current runtime event supplements
authoritative message history. Request context uses a four-worker zero-queue executor,
bounded RPCs, and a projected fresh fence check at mount. It fails open to plain history
without occupying setup's database workers. `database/chat_context_prefetch.py` owns
request snapshots and at-use fences; refresh keeps the transactional store.
Summaries refresh after turns in tracked, budgeted background jobs. See the rollout
runbook for index readiness and fallback operations.
