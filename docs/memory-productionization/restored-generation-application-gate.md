# Restored database-generation application gate

This unit makes canonical Firebase PostgreSQL authorization depend on an exact,
released database generation. It complements the per-account retained tombstone
gate: a request must pass both the global restore release and the account-local
deletion fence.

## Authority model

- `postgres_restore_admission_revisions` is append-only global safety evidence.
- A `released` revision structurally requires an exact checkpoint candidate and
  consistency-evidence digest, two distinct approval subjects and receipts, and
  one manual release receipt.
- `postgres_restore_admission_heads` selects the current revision for one opaque
  database-generation digest.
- The server configuration fixes the expected generation. Clients cannot choose
  it.
- Firebase preauthorization returns the exact released revision and content hash.
  The resulting context carries those coordinates in a private runtime binding;
  copying its visible fields cannot copy the binding.
- Every canonical Firebase PostgreSQL transaction re-locks the exact generation,
  release revision, and content hash before replay or repository work.

The migration intentionally provides no function or grant for creating release
revisions or advancing heads. Operator receipt authentication, two-person
approval composition, and the manual release action remain inactive until their
dedicated operational adapter and runbook are approved and qualified.

## Honest boundary

This gate covers the route-free canonical Firebase read, write, and export
runtimes that use the shared authorization source and transaction boundary. It
does not yet cover internally issued service-worker contexts, arbitrary SQL by a
compromised database role, or infrastructure that fails to declare a newly
restored generation. Those remain explicit privilege and deployment-activation
gates. Restore and cleanup roles stay usable while application traffic is closed.

No release revision admits a retained per-account tombstone. The existing
account fence remains monotone and transaction-time dominant.
