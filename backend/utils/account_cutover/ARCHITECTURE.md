# Account cutover utilities

LIFECYCLE: permanent

Owns the legacy monorepo foundation for whole-account cohort cutover:

| Module | Responsibility |
|--------|----------------|
| `state.py` | Legal transitions: legacy → migrating → new; new → rolled_back_stranded; stranded → migrating |
| `control.py` | Authenticated bootstrap projection (generations, min builds, client action, offline-queue instruction) |
| `fence.py` | Generation fence for legacy product writes and background job skip decisions |
| `access.py` | HTTP/WS fail-closed enforcement; auth/bootstrap/control paths stay reachable |
| `coordinator.py` | Resumable idempotent forward-migration manifest/checkpoint seam |
| `telemetry.py` | Enum-only Prometheus counters + logs (no raw user content) |

## Non-goals

- Destination backend implementation or binding (`destination_backend_bound` stays false here)
- Dual-write, reverse reconciliation, universal edge gateway
- Migrating any user by default (cohort enrollment set starts empty)

## Related seams reused

- Client device headers: `utils/client_device.py` + `X-App-Platform` / `X-App-Version` / `X-App-Build`
- Account-generation fencing pattern: task intelligence + memory V3
- Desktop required-update prompt: `DesktopUpdatePolicyManager` / `/v2/desktop/update-policy`
- Control projection pattern: `/v1/candidates/control`
