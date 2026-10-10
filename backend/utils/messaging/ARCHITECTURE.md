# Messaging package map

The gateway admits verified webhooks into an encrypted inbox, then separately runs
shared chat turns. Channel content is user-serving only. The package has no import-time
provider or database IO. See `backend/docs/messaging-channels.md` for Stage A and
`backend/docs/messaging-adapters.md` for Stage B configuration, provider facts and QA.

- `contracts.py`: channel messages, verified provider attachment references, owned
  artifacts, capabilities, principals and provider-neutral protocols.
- `access.py`, `identity.py`: existing entitlement/cohort admission and stable identity keys.
- `gateway.py`: durable admission, leases, media preparation, commands, shared turns,
  typing lifecycle, append-only history, and fenced deferred replies.
- `outbound.py`, `delivery_context.py`: one reply policy and per-sink sequencing,
  retry guards, rendering metadata, artifacts and surface actions.
- `projection.py`: one catalog projection for advertisement and execution; channels
  omit device charts, app retains its existing tools.
- `history.py`, `app_awareness.py`: cross-surface append-only awareness and search.
- `undo.py`: encrypted five-minute inverse receipts; reserves before supported writes,
  reports outcomes, and delegates inverses to domain authorities.
- `adapters/base.py`: shared pacing, owned-file tools and media preparation.
- `adapters/telegram.py`: private-chat Bot API verification, parsing, drafts and delivery.
- `adapters/linq.py`: replaceable `IMessageProvider` and Linq implementation.
- `adapters/transport.py`: bounded, redacted provider IO and retry semantics.
- `adapters/media.py`: Omi's existing chat file store and prerecorded STT bridge.
- `adapters/delivery.py`: content-free provider receipts and atomic send/receive guard.
- `adapters/runtime.py`: explicit opt-in registration and pending-only recovery.

Storage authority remains `database/messaging.py`, task codecs/inverses remain in
`database/action_items.py` and `database/action_item_codec.py`, and memory inverses use
`MemoryService`. No adapter can select a different user or accept arbitrary remote URLs
from tools. Test contracts, transport doubles and the manual live dev listener are under
`backend/testing/messaging`; executable suites are under `backend/tests/unit`.
