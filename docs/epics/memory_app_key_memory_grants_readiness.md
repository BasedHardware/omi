# memory app/key memory grant storage readiness

**Date:** 2026-06-19
**Scope:** Oracle P0-1/P0-6 server-owned per-app/per-key memory grants for external memory memory consumers.

## Server-owned Firestore path

Canonical persisted document:

```text
users/{uid}/memory_control/app_key_memory_grants
```

This document is read by the backend/Admin SDK helper:

```python
read_app_key_memory_grants_state(uid, db_client)
```

The helper is fake-injectable and requires an explicit `db_client` so route code/tests do not rely on request-provided fields. It returns a small read decision with:

- `present=false`, `reason=missing_app_key_memory_grants_state` for missing docs.
- `malformed=true`, `reason=malformed_app_key_memory_grants_state` when the top-level grant contract is not a map with `grants`.
- `reason=ok` plus the raw nested state for valid-looking contract docs.

## Contract shape consumed by authorization

The storage doc intentionally stores the exact nested grant state already consumed by `authorize_app_key_scope_memory_grant(...)`:

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

- Firestore document path: `users/{uid}/memory_control/app_key_memory_grants`
- In-document authorization path: `grants.<consumer>.apps.<app_id>.keys.<key_id>`
- Authorization helper example: `grants.developer_api.apps.app_123.keys.key_456`

External consumers (`developer_api`, `mcp`, `third_party`) still require both authenticated route scopes and persisted grant scopes. Default read never makes Archive default-visible. Archive still requires the stronger `memories.archive.read` operation grant and must be composed with explicit Archive intent / Archive route capability before exposure.

## Client self-grant denial expectation

`firestore.rules` denies client reads/writes to `users/{uid}/memory_control/{document}`; Admin SDK/IAM backend writes bypass client rules. The local emulator harness now specifically asserts a signed-in client cannot read/create/update/delete:

```text
users/memory-emulator-user/memory_control/app_key_memory_grants
```

with a attempted self-grant at:

```text
grants.developer_api.apps.client-app.keys.client-key
```

Local proof command run in this slice:

```bash
npm run test:memory-app-key-grants-rules:emulator
```

Result: PASS under the local Firebase Firestore emulator. This is not a deployed/cloud rules or IAM proof.

## Narrow developer dependency/composition seam added in this slice

This follow-up carries Developer API authentication output closer to the memory app/key grant contract, but it remains intentionally narrow:

- `database.dev_api_key.get_user_and_scopes_by_api_key(...)` now returns `key_id` plus a stable `app_id` (`app_id` from key metadata when present, otherwise the explicit Developer API app bucket `developer_api`) in addition to the existing `user_id`/`scopes` fields.
- `dependencies.ApiKeyAuth` now carries optional `app_id` and `key_id`; existing uid-only helpers still return `auth.uid`, preserving compatibility for routes that only need the historical user id.
- Added `get_developer_memory_default_memory_read_context(...)`, which converts verified Developer API scopes (`memories:read`, `memories:write`) into the memory grant scope vocabulary (`memories.read`, `memories.write`) and returns `ProductAuthorizationContext` only when uid, app id, key id, and `memories:read` are present.
- Added `authorize_memory_external_default_memory_read(...)` to compose that authenticated context with `read_app_key_memory_grants_state(...)` and `authorize_app_key_scope_memory_grant(...)` for the required `DEFAULT_READ` operation.
- Wired the Developer API default memory list path (`GET /v1/dev/user/memories` without category filters) through this composition seam before memory default-list reads. Category-filtered Developer API list remains explicitly legacy-compatible and does not claim memory default-read enforcement.

The seam fails closed when authenticated app/key identity, required scope, stored app/key grant state, or the matching persisted operation grant is missing/malformed/wrong. Allowed default-read policies keep `archive_capability=false`; no Archive route/path was exposed.

## Remaining route dependencies before enforcement

This artifact is now partly route-wired for one Developer API default-list memory seam, but broad route enforcement remains incomplete:

- Developer API vector search still needs the same app/key grant composition before memory vector reads.
- Developer API category-filtered list remains a legacy compatibility path pending T22/T23 category/read/write convergence.
- MCP REST/SSE API key auth currently returns only `uid`; MCP key models do not persist scopes/key scope metadata yet.
- MCP SSE advertises OAuth `memories.read` / `memories.write`; route execution must carry the verified scopes/app/key identity to the memory memory grant seam.
- Product `/memory` routes remain first-party `omi_chat`; first-party rollout/default-grant path is intentionally unchanged.

## Safe admin assignment readiness runner

Added `backend/scripts/app_key_memory_grant_assignment_readiness.py` as the safe-by-default readiness runner for deterministic server/Admin-owned grant assignment planning.

Default command:

```bash
python3 backend/scripts/app_key_memory_grant_assignment_readiness.py
```

Default behavior is `status=NOT_RUN`, `read_only=true`, `mutation_allowed=false`, and no Firestore reads or writes. This is a readiness artifact only.

Dry-run validation command:

```bash
python3 backend/scripts/app_key_memory_grant_assignment_readiness.py \
  --execute \
  --assignment-file /secure/admin/memory-app-key-memory-grants.json
```

Write command, only for an intentional server/Admin context and deterministic input file:

```bash
python3 backend/scripts/app_key_memory_grant_assignment_readiness.py \
  --execute \
  --allow-write \
  --assignment-file /secure/admin/memory-app-key-memory-grants.json
```

The compact form is `python3 backend/scripts/app_key_memory_grant_assignment_readiness.py --execute --allow-write --assignment-file /secure/admin/memory-app-key-memory-grants.json`.

Assignment file shape:

```json
[
  {
    "uid": "<uid>",
    "consumer": "developer_api",
    "app_id": "developer-api",
    "key_id": "<existing-key-id>",
    "scopes": ["memories.read"],
    "default_read": true,
    "archive_read": false,
    "write": false,
    "archive_default_visible": false
  }
]
```

Validation/assignment contract:

- writes are unreachable unless **both** `--execute` and `--allow-write` are supplied with `--assignment-file`;
- writes target only `users/{uid}/memory_control/app_key_memory_grants`;
- in-document grant targets are deterministic: `grants.<consumer>.apps.<app_id>.keys.<key_id>`;
- allowed consumers are limited to `developer_api`, `mcp`, and `third_party`;
- allowed persisted scopes are limited to `memories.read`, `memories.write`, and `memories.archive.read`;
- `default_read=true` requires `memories.read`; `write=true` requires `memories.write`; `archive_read=true` requires `memories.archive.read`;
- `archive_default_visible` must be `false`; Archive is never default-visible even when the explicit `archive_read` capability is assigned;
- unknown consumers, scopes, fields/capabilities, malformed booleans, or client/tool-style scopes such as `tool.search_memories` are denied before writes;
- grants are never inferred from MCP advertised metadata, client request fields, or MCP/developer key scopes alone.

This runner was not executed against production in this slice; no app/key grants assigned in production or locally through a real Firestore client.

## Explicit non-claims

No production rollout approval, deployed Firestore rules proof, cloud IAM proof, broad route enforcement for all developer/MCP app-key grants, MCP key scope persistence, production app/key grant assignment, production telemetry, benchmark, Pinecone validation, or memory write convergence is claimed by this slice. The new assignment runner was not executed against production and no app/key grants assigned.
