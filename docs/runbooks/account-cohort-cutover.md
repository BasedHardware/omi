# Account cohort cutover (legacy foundation)

Operator contract for the legacy-monorepo foundation that prepares whole-account
cohort cutover. **This foundation does not migrate any user.**

## What landed

| Surface | Path |
|---------|------|
| Persisted state | `users/{uid}/account_cutover/state` |
| Control projection | `GET /v1/account/cutover/control` |
| Legal states | `legacy`, `migrating`, `new`, `rolled_back_stranded` |
| Enforcement flag | `ACCOUNT_CUTOVER_ENFORCEMENT=off\|on` (default **off**) |
| Cohort enrollment | `backend/config/account_cutover.py` (`ACCOUNT_CUTOVER_COHORT`, starts empty) |
| Min builds | `MINIMUM_SUPPORTED_BUILDS` (all `0` until bridge release) |

## Rollout stages

1. **Ship bridge clients** that poll `/v1/account/cutover/control`, send
   `X-App-Platform` + `X-App-Build` (and version), and fail closed on
   `force_upgrade` / `migration_maintenance`.
2. **Raise minimum supported builds** for ios/android/macos after the bridge
   release is mandatory.
3. **Enable** `ACCOUNT_CUTOVER_ENFORCEMENT=on` in runtime env (no user migrated).
4. **Enroll** UIDs into `ACCOUNT_CUTOVER_COHORT` only with an explicit ceremony PR
   after the destination backend importer exists.
5. **Run** `AccountCutoverCoordinator.begin(uid)` per enrolled account; advance
   checkpoints only while honest about `destination_backend_bound=false`.

## No-go boundaries

- Do not set `destination_backend_bound=true` without a real importer.
- Do not dual-write or auto reverse-reconcile.
- Do not enable enforcement with nonzero min builds before the bridge clients
  are forced.
- Lossy rollback (`rolled_back_stranded`) accepts stranded new-backend writes;
  treat `stranded_new_data=true` as observable operator state, not a silent heal.

## External prerequisites (honest gaps)

- Destination backend + importer binding
- Product decision for exact bridge build numbers per platform
- Cohort enrollment ceremony and production runtime env flip
- New UI surfaces beyond fail-closed force-upgrade / migration-maintenance gates

## Telemetry

- `omi_account_cutover_transitions_total{from_state,to_state,reason}`
- `omi_account_cutover_access_total{state,decision,client_action}`

No raw user content is logged.
