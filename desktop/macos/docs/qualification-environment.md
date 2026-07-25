# Desktop qualification environment

`desktop/macos/scripts/qualify-desktop-beta.sh` gives each qualification a
recorded local lease before it starts the dev harness. It is deliberately
separate from ordinary `make dev-up`: normal development keeps the standard
ports and has no qualification lease.

## Variables

- `OMI_QUALIFICATION_LEASE_ROOT` — root for lease metadata, owned state, and
  logs. Defaults to `$TMPDIR/omi-desktop-qualification`.
- `OMI_QUALIFICATION_PORT_OFFSET` — non-negative offset for a qualification
  run. If unset, the script derives it from the candidate SHA and run-scoped
  lease identity, so a rerun does not reuse a prior stack's ports.
- `OMI_QUALIFICATION_RETAINED_RUNS` and
  `OMI_QUALIFICATION_RETENTION_AGE_SECONDS` — bounded retention for completed,
  sentinel-proven state/log pairs (defaults: 3 runs and 14 days).
- `OMI_HARNESS_PORT_OFFSET` and `OMI_HARNESS_{FIRESTORE,AUTH,BACKEND,DESKTOP_BACKEND,REDIS,TYPESENSE}_PORT` — dev-harness controls. The qualifier exports the offset; direct per-service overrides remain available for debugging.

The offset applies to Firestore, Firebase Auth, backend, desktop backend,
Redis, and Typesense. The script also derives `OMI_AUTOMATION_PORT`; invalid
ports fail before launch.

## Cleanup safety

On normal exit, `INT`, `TERM`, `HUP`, or the workflow `always()` finalizer,
release validates the authenticated lease token, state sentinel, process marker,
recorded process group, and matching port manifest before bounded
`INT`→`TERM`→`KILL` escalation. A stale lease is reclaimed only after its
recorded owner PID is dead and that provenance validates. Unknown listeners and
unrecorded processes are never killed. `--keep-stack` intentionally leaves the
recorded lease for later safe reclamation. Retention removes only completed,
sentinel-proven state and paired logs, never a live/incomplete or foreign root.

The main qualification app receives a separate run-unique launch token. `run.sh`
writes an owner-only launch signal, which the qualifier verifies against exactly
one token-bearing app process before writing a `0600` launch record. Cleanup
revalidates the recorded PID, start time, command hash, executable path, bundle,
and token immediately before `TERM` and again before bounded `KILL`; it never
quits by bundle ID or name. After the owned app exits, the qualifier requires its
automation port to be unbound. Missing provenance, changed process identity, an
unreleased port, or lease-release failure retains the lease and fails before any
success evidence is published.
