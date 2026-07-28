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
- `OMI_QUALIFICATION_SWIFT_CACHE_ROOT` — owner-only exact-SHA SwiftPM cache.
  Defaults to `~/Library/Caches/OmiDesktop/qualification-swiftpm-v2`.
- `OMI_HARNESS_PORT_OFFSET` and `OMI_HARNESS_{FIRESTORE,AUTH,BACKEND,DESKTOP_BACKEND,REDIS,TYPESENSE}_PORT` — dev-harness controls. The qualifier exports the offset; direct per-service overrides remain available for debugging.

The offset applies to Firestore, Firebase Auth, backend, desktop backend,
Redis, and Typesense. The script also derives `OMI_AUTOMATION_PORT`; invalid
ports fail before launch.

## Gate phases

The qualification timing report classifies every in-script gate without changing
its authority:

| Phase | Classification | Failure meaning |
|---|---|---|
| Candidate/release evidence, tag binding, lease acquisition, static self-check | Immutable artifact/security | The exact signed candidate, source identity, or trusted evidence cannot be established |
| Automation bridge, Tier-2 user flows, fault user flow and both manifests | User-visible behavioral/fault coverage | The desktop UX or its required failure behavior did not pass |
| Capacity, fault-listener preflight, desktop preparation/provenance, final cleanup | Runner hygiene/cleanup | The controlled M1 host cannot safely start or reclaim this run |

All three classes remain fail-closed. The classification only makes a
non-product host prerequisite precise and early; it does not convert it to
passing evidence.

## Pre-tag trusted-M1 readiness

`desktop_auto_release.yml` keeps final source binding, offline readiness receipt
creation, receipt verification, and immutable tag publication in the same
non-cancelling `desktop-auto-release-tag-main` job on `omi-qual-m1-studio`.
There is no independent readiness job or cross-job artifact handoff.

The job invokes `desktop/macos/scripts/pre-tag-readiness.sh` against the exact
post-binding main SHA. That script obtains separate token-bound exact-SHA cache
and qualification leases, derives its state root/instance/port offset from the
immutable SHA and run scope, and runs `desktop-core-harness.sh --readiness` in
the cache checkout with an offline provider. Its receipt can pass only after the
readiness manifest matches the exact SHA and both authenticated leases have
released successfully. A stale or foreign listener is never broadly signalled:
the lease authority quarantines only a dead unproven pointer, retains state
for evidence, and refuses a passing receipt if its own cleanup cannot prove
ownership.

The receipt verifier rejects a wrong SHA, non-offline provider, failed or
missing checks, and any qualification/promotion field. The publisher still
refetches live `main` immediately before pushing; if it moved after readiness,
no tag is created and the next merge/planner pass must produce a fresh candidate.
This readiness gate never grants Beta or Stable authority.

## Runner capacity preflight

Before expanding the candidate checkout, the M1-only workflow loads the reclaim
authority from the exact immutable candidate and writes `runner-capacity.json`
in its run-isolated stage. The guard still requires at least 32 GiB of free
filesystem blocks plus 65,536 free inodes.

When capacity is low, reclaim considers only owner-only
`qualification-swiftpm-v2/<40-character-SHA>` entries with a valid v2 manifest,
completion marker, matching Git HEAD, and direct SwiftPM build directory. It
orders entries by last use and SHA, requires six hours of age, and removes at
most eight entries or 64 GiB per run, stopping as soon as the unchanged capacity
threshold passes. The active harness lease, live cache leases, and live process
references protect their exact worktrees. A malformed entry, symlink, unknown
lock, ambiguous harness lease, or live qualifier without an authoritative lease
refuses the entire plan before deletion. Run staging, cleanup artifacts,
qualification evidence, and release assets are outside the cache root and are
never reclaim targets.

On a controlled capacity failure, the workflow fails closed before candidate
assets or the full source checkout are fetched, then its normal finalizer writes
cleanup evidence and uploads both evidence files. The capacity report records
the before/after observations and the bounded exact-SHA deletion list; it does
not attribute a prior incident to a runner or host cause.

## Cleanup safety

On normal exit, `INT`, `TERM`, `HUP`, or the workflow `always()` finalizer,
release validates the authenticated lease token, state sentinel, process marker,
recorded process group, and matching port manifest before bounded
`INT`→`TERM`→`KILL` escalation. A stale lease is reclaimed only after its
recorded owner PID is dead and that provenance validates. Unknown listeners and
unrecorded processes are never killed. `--keep-stack` intentionally leaves the
recorded lease for later safe reclamation. Retention removes only completed,
sentinel-proven state and paired logs, never a live/incomplete or foreign root.

The automatic fault suite keeps its fault-inject state under the same
sentinel-protected lease root. Normal harness cleanup stops that token-bearing
process first; lease release is the fail-closed fallback for interruption paths.
Before signaling it, release revalidates the owner-only state files, lease token,
PID/process group, command marker, loopback URL, and exact listener PID. A
listener that fails any check is retained and never signaled.

The exact-SHA SwiftPM worktree has a separate owner-only, token-bound cache lease
from publication through harness cleanup. Normal exit and the workflow finalizer
release it only after the harness lease is safely released. `--keep-stack`
retains both authorities. A terminally interrupted lease is treated as stale
only when its recorded owner PID is dead; the harness worktree pointer remains a
separate preservation authority.

Automatic qualification now exercises that same ownership boundary immediately
after lease acquisition: it starts a disposable listener on the exact future
fault-suite port, then asks the lease authority to re-prove and reclaim it. A
known-owned listener produces `fault-listener-preflight.json` with `status:
passed`. A missing, replaced, foreign, or unreclaimable listener produces a
specific failed host-prerequisite result and stops before desktop preparation,
Tier-2, or the fault flow. Unknown listeners are retained and never signaled.
The real fault suite still runs later and its failing manifest still rejects
qualification evidence.

The main qualification app receives a separate run-unique launch token. `run.sh`
writes an owner-only launch signal, which the qualifier verifies against exactly
one token-bearing app process before writing a `0600` launch record. Cleanup
revalidates the recorded PID, start time, command hash, executable path, bundle,
and token immediately before `TERM` and again before bounded `KILL`; it never
quits by bundle ID or name. After the owned app exits, the qualifier requires its
automation port to be unbound. Missing provenance, changed process identity, an
unreleased port, or lease-release failure retains the lease and fails before any
success evidence is published.

## Phase timing

The automatic workflow uploads owner-only `phase-timings.json` with each phase's
classification, status, and duration in milliseconds, plus an explicit
`target_seconds: 1200`. Failed active phases and cleanup are recorded by the
exit trap, so the report distinguishes time spent in artifact/security,
user-visible behavior, and runner hygiene. The 20-minute target is measured from
this report; no Tier-2 or fault UX gate is skipped to meet it.
