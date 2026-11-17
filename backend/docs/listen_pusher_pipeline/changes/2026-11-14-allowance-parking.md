# Allowance parking outside active work

SCA-2195 adds `allowance_held` for current allowance refusals, an owner-generation
release index, count-only migration preview, separate held-stock telemetry and
an off-only rollback switch. Custody is retained; dispatch reauthorizes every
released unit. See `backend/docs/runbooks/batch-allowance-parking.md` for sweep
membership, mixed versions, migration, rollback and production acceptance.

Round-1 review correction: owner discovery composes referral grants alongside
commercial subscription authority, including time transitions. Shared parking
primitives live in the database layer. The runbook withdraws the initial read
envelope and records measured transaction profiles and revised planning reserves
that require rollout-lead acceptance before default-on deployment or migration.
