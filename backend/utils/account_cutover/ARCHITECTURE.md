# Account cutover utilities

LIFECYCLE: permanent

Owns the legacy monorepo foundation for whole-account cohort cutover:

| Module | Responsibility |
|--------|----------------|
| `state.py` | Legal transitions: legacy → migrating → new; new → rolled_back_stranded; stranded → migrating |
| `control.py` | Authenticated bootstrap projection (generations, min builds, client action, offline-queue instruction) |
| `fence.py` | Generation fence for legacy product writes and background job skip decisions |
| `access.py` | HTTP/WS fail-closed enforcement; auth/bootstrap/control paths stay reachable |
| `coordinator.py` | Resumable idempotent forward-migration manifest/checkpoint seam; explicit cohort enrollment; transactional/locked CAS writes; offline drain only pre-fence |
| `telemetry.py` | Enum-only Prometheus counters + logs (no raw user content) |

## Offline-queue protocol

- `prepare_offline_drain` while legacy/stranded → `drain`
- `begin` → `migrating` + `quarantine` (accepted bounded loss of undrained items)

## Non-goals

- Destination backend implementation or binding (`destination_backend_bound` stays false here)
- Dual-write, reverse reconciliation, universal edge gateway
- Migrating any user by default (cohort enrollment set starts empty; `begin` refuses non-members)
- Advancing `ui_generation` / `api_generation` without `bind_destination_product_generations`

## Related seams reused

- Client device headers: `utils/client_device.py` + `X-App-Platform` / `X-App-Version` / `X-App-Build`
- Account-generation fencing pattern: task intelligence + memory V3
- Desktop required-update prompt: `DesktopUpdatePolicyManager` / `/v2/desktop/update-policy`
- Control projection pattern: `/v1/candidates/control`
