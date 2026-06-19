# V17 app/key memory grant storage readiness

**Date:** 2026-06-19  
**Scope:** Oracle P0-1/P0-6 server-owned per-app/per-key memory grants for external V17 memory consumers.

## Server-owned Firestore path

Canonical persisted document:

```text
users/{uid}/memory_control/v17_app_key_memory_grants
```

This document is read by the backend/Admin SDK helper:

```python
read_v17_app_key_memory_grants_state(uid, db_client)
```

The helper is fake-injectable and requires an explicit `db_client` so route code/tests do not rely on request-provided fields. It returns a small read decision with:

- `present=false`, `reason=missing_v17_app_key_memory_grants_state` for missing docs.
- `malformed=true`, `reason=malformed_v17_app_key_memory_grants_state` when the top-level grant contract is not a map with `grants`.
- `reason=ok` plus the raw nested state for valid-looking contract docs.

## Contract shape consumed by authorization

The storage doc intentionally stores the exact nested grant state already consumed by `authorize_v17_app_key_scope_memory_grant(...)`:

```yaml
grants:
  developer_api:
    apps:
      app_123:
        keys:
          key_456:
            enabled: true
            scopes:
              - memories.read
            default_read: true
            archive_read: false
            write: false
```

Path conversion:

- Firestore document path: `users/{uid}/memory_control/v17_app_key_memory_grants`
- In-document authorization path: `grants.<consumer>.apps.<app_id>.keys.<key_id>`
- Authorization helper example: `grants.developer_api.apps.app_123.keys.key_456`

External consumers (`developer_api`, `mcp`, `third_party`) still require both authenticated route scopes and persisted grant scopes. Default read never makes Archive default-visible. Archive still requires the stronger `memories.archive.read` operation grant and must be composed with explicit Archive intent / Archive route capability before exposure.

## Client self-grant denial expectation

`firestore.rules` denies client reads/writes to `users/{uid}/memory_control/{document}`; Admin SDK/IAM backend writes bypass client rules. The local emulator harness now specifically asserts a signed-in client cannot read/create/update/delete:

```text
users/v17-emulator-user/memory_control/v17_app_key_memory_grants
```

with a attempted self-grant at:

```text
grants.developer_api.apps.client-app.keys.client-key
```

Local proof command run in this slice:

```bash
npm run test:v17-app-key-grants-rules:emulator
```

Result: PASS under the local Firebase Firestore emulator. This is not a deployed/cloud rules or IAM proof.

## Remaining route dependencies before enforcement

This slice is storage/readiness, not full route enforcement. Remaining blockers:

- Developer API route dependencies currently enforce scopes but return only `uid`; V17 enforcement needs authenticated `key_id`, app identity, and verified scopes carried to the shared authorization context.
- MCP REST/SSE API key auth currently returns only `uid`; MCP key models do not persist scopes/key scope metadata yet.
- MCP SSE advertises OAuth `memories.read` / `memories.write`; route execution must carry the verified scopes/app/key identity to the V17 memory grant seam.
- Product `/v17` routes remain first-party `omi_chat`; first-party rollout/default-grant path is intentionally unchanged.

## Explicit non-claims

No production rollout approval, deployed Firestore rules proof, cloud IAM proof, route enforcement for developer/MCP app-key grants, MCP key scope persistence, production telemetry, benchmark, Pinecone validation, or V17 write convergence is claimed by this slice.
