# Restored database-generation application gate

This unit makes canonical Firebase PostgreSQL authorization depend on an exact,
released database generation. It complements the per-account retained tombstone
gate: a request must pass both the global restore release and the account-local
deletion fence.

## Authority model

- `postgres_restore_admission_revisions` is append-only global safety evidence.
- A `released` revision requires an exact checkpoint candidate and
  consistency-evidence digest. Migration 36 implements David's amended
  authority rule for new releases: one operator authenticated through the
  reviewed GCP IAM/Cloud SQL role boundary, with no second approver, separate
  application approval receipt, or second manual-release workflow. Historical
  migration-29 release rows remain readable and immutable.
- `postgres_restore_admission_heads` selects the current revision for one opaque
  database-generation digest.
- The server configuration fixes the expected generation. Clients cannot choose
  it.
- Firebase preauthorization returns the exact released revision and content hash.
  The resulting context carries those coordinates in a private runtime binding;
  copying its visible fields cannot copy the binding.
- Every canonical Firebase PostgreSQL transaction re-locks the exact generation,
  release revision, and content hash before replay or repository work.

The only release mutation is the fixed
`release_postgres_restore_generation_v2` operation granted to
`omi_platform_restore_operator`. Application, cleanup, and ordinary restore
roles cannot execute it or mutate the tables. Production role membership/login
comes from reviewed GCP IAM; the database stores the release transition and
checkpoint evidence while GCP supplies operator authentication and audit.

## Honest boundary

This gate covers the route-free canonical Firebase read, write, and export
runtimes that use the shared authorization source and transaction boundary. It
does not yet cover internally issued service-worker contexts, arbitrary SQL by a
compromised database role, or infrastructure that fails to declare a newly
restored generation. Those remain explicit privilege and deployment-activation
gates. Restore and cleanup roles stay usable while application traffic is closed.

No release revision admits a retained per-account tombstone. The existing
account fence remains monotone and transaction-time dominant.
