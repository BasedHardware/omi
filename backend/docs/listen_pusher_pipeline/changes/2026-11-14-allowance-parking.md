# Allowance parking outside active work

SCA-2195 adds `allowance_held` for current allowance refusals, an owner-generation
release index, count-only migration preview, separate held-stock telemetry and
an off-only rollback switch. Custody is retained; dispatch reauthorizes every
released unit. See `backend/docs/runbooks/batch-allowance-parking.md` for sweep
membership, mixed versions, migration, rollback and production acceptance.
