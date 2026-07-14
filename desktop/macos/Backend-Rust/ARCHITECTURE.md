# Desktop Rust Backend Architecture

The Rust process is the desktop control and provider proxy plane. It is not a
second implementation of the product data API. Conversation, memory, message,
task, app, persona, folder, goal, and user-settings CRUD belongs to the Python
backend at `api.omi.me`.

## Runtime boundaries

The active Rust routes cover authentication, provider proxies, realtime session
minting, desktop chat, TTS, screen activity ingestion, release manifests, agent
VM control, support webhooks, and health/configuration endpoints.

Firestore access is deliberately limited to data required by those routes:

| Repository | Live responsibility |
| --- | --- |
| `users_repository` | BYOK enrollment, effective subscription, account age, and agent VM fields |
| `agent_vm_repository` | Desktop agent VM state |
| `action_items_repository` | Sentry support-action lookup and creation |
| `conversations_repository` | Narrow source lookup used to enrich support actions |
| `llm_usage_repository` | Desktop/realtime usage accounting and minted realtime sessions |
| `screen_activity_repository` | Screen activity batch ingestion |
| `desktop_releases_repository` | Desktop update manifests and channel promotion |

Redis is likewise limited to the live Gemini/chat and TTS rate-limit counters.
It does not mirror Python CRUD or sharing repositories.

## Legacy route contract

Old Rust data routes remain registered only as a compatibility facade that
returns a structured HTTP 410 response pointing clients to `api.omi.me`.
`routes/deprecated.rs` builds a state-free `Router<()>`; by construction those
handlers cannot acquire `AppState`, Firestore, Redis, or provider clients. Its
behavioral test covers representative methods, static paths, and parameterized
paths.

Do not add an implementation behind this facade. A product data endpoint should
be added to the Python backend and consumed through the desktop Python API base
URL. Remove a legacy path only when the supported-client compatibility window
has ended.

## Adding persistent state

Add Rust persistence only when a live Rust route owns the behavior. Keep the
repository operation narrow, add a behavioral test through a controllable seam,
and avoid importing Python data models wholesale. Pure Firestore wire parsing
belongs in `services/firestore/values.rs` so it can be tested without credentials
or a network connection.

The Firestore and Redis modules deny dead code and unreachable public items.
Unused parity helpers should be deleted, not retained with lint allowances.

## Verification

Run from this directory:

```bash
cargo fmt --check
cargo clippy --locked -- -D warnings
cargo test --locked
```
