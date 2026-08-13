# Restored terminal application gate

Migration 0028 makes the retained per-account terminal fence a central negative
authorization coordinate for canonical PostgreSQL application traffic.

The Firebase pre-authorization lookup returns no row for a fenced account. The
serializable operation boundary then checks again while holding the same
account advisory lock as restore application. A context issued before replay
therefore cannot return a cached idempotent receipt, read a graph, or commit
after the tombstone is installed. The winning lock order is explicit: an
already-running application transaction may finish before restore, or restore
installs the fence first and the application transaction receives no authority.

The application role can execute only the deletion-aware wrappers. Execute
privilege on the older implementation functions is revoked. The wrappers add
no table mutation grant and return no new positive authority.

This gate is intentionally one half of restore admission. It proves that a
known replayed deletion dominates stale active account-control bytes. It does
not attest or release the restored database generation itself. Global
generation registration, checkpoint approval, and manual traffic release
remain separate infrastructure/action-layer authorities and stay inactive.
