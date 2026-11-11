# INV-CUTOVER-1: Whole-account cohort cutover authority

**Status:** locked

This revision is proposed as of 2026-08-07. It must remain unchanged for seven
days, with its behavioral guards, before a follow-up can lock it.

**Statement:** Whole-account migration between the legacy monorepo backend and a
future destination backend is server-authoritative. An account moves atomically
`legacy → migrating → new`. Rollback from `new` is explicitly
`rolled_back_stranded` and may leave new-backend writes stranded without
automatic reverse reconciliation. Bridge clients discover state only through the
authenticated cutover control projection and fail closed into force-upgrade or
migration-maintenance before product traffic.

## MUST NOT

- Invent a parallel account-generation, cohort, or control primitive when the
  cutover control document and `/v1/account/cutover/control` projection exist.
- Allow dormant pre-bridge clients to mutate legacy product data after an
  account leaves `legacy`, once `ACCOUNT_CUTOVER_ENFORCEMENT=on`.
- Block authentication, update-policy, or cutover control routes while fencing
  product traffic.
- Pretend the destination backend is bound (`destination_backend_bound=true`)
  without an external importer implementation.
- Dual-write, auto-reconcile reverse migration, or silently drop the stranded
  new-data signal after lossy rollback.
- Migrate any user by merging an empty default cohort enrollment.
- Project a malformed cutover control document as implicit legacy.
- Advertise `offline_queue_instruction=drain` after the account has entered
  `migrating` (drain is only legal before the migration fence).

## Surfaces

- Backend cutover state, fence, coordinator, control route
- Flutter bootstrap gate + offline WAL instruction handling
- macOS bootstrap gate + offline/outbox instruction handling

## Guard tests

- `backend/tests/unit/test_account_cutover_foundation.py`
- `app/test/unit/account_cutover_gate_test.dart`
- `desktop/macos/Desktop/Tests/AccountCutoverControlTests.swift`

## Path globs

- `backend/models/account_cutover.py`
- `backend/config/account_cutover.py`
- `backend/database/account_cutover.py`
- `backend/utils/account_cutover/**`
- `backend/routers/account_cutover.py`
- `app/lib/services/account_cutover/**`
- `desktop/macos/Desktop/Sources/AccountCutover/**`

## PR rule

Name this invariant ID in the PR body if you touch the path globs above.

## Deliberate migration exception (INV-DATA-1)

This invariant is the explicit customer data-plane migration ceremony required
by `INV-DATA-1`. Shipping a destination backend binding or enabling cohort
enrollment requires citing both IDs.
