# contracts/ — the single source of truth

Pure declarations. Nothing in here executes; everything in here is compiled by
`../codegen/` into TS types, Dart/Swift bridge stubs, and conformance fixtures, and any
drift between a declaration and its generated output is a CI failure.

The backend rewrite and the client core both pivot on this directory: a domain's
contract is ratified here **before** either end of the wire moves (WS-002's
dual-migration rule). Ratification = the tracker records the decision and the contract
file lands with its conformance fixtures.

Planned layout (files land as domains are ratified; tasks first):

- `ids.md` + `ids.schema.json` — the ADR-006 slug grammar and `legacy-UUID | slug`
  acceptance rule.
- `errors/` — the transport/write error taxonomy with terminal states (retryable /
  permanent / rate-limited / auth-invalid), and the `Degraded` fallback-telemetry
  contract.
- `bridge/` — the privileged bridge interfaces every shell binds: `DurableLog`-shaped
  storage, secure credential custody, capture-core observation, notification delivery.
- `domain/` — per-domain record schemas + write contracts (tasks, memories,
  conversations, goals, chat, settings).
- `wire/listen/` — `/listen` protocol JSON Schema (WS-003); generated decoders live in
  `@omi-core/wire-listen`. Entitlement payload REST envelope is WS-005; chat session
  protocol is WS-006 (gated).
