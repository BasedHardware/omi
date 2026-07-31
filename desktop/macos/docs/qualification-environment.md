# Desktop qualification environment

`desktop/macos/scripts/qualify-desktop-beta.sh` gives each qualification a
recorded local lease before it starts the dev harness. It is deliberately
separate from ordinary `make dev-up`: normal development keeps the standard
ports and has no qualification lease.

For provisioning a new macOS qualification runner, see
[Runner provisioning](#runner-provisioning) below. Deprecated per-version host
artifacts are listed in `qualification-cleanup.md`.

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
authority from the exact immutable candidate and runs
`desktop/macos/scripts/qualification-runner-self-clean.py`. Maintainers can run
the same entrypoint with `--dry-run --report <path>` for a read-only before/after
process and capacity report. The workflow writes `runner-hygiene.json` in its
run-isolated stage. The guard still requires at least 32 GiB of free filesystem
blocks plus 65,536 free inodes.

When capacity is low, reclaim considers only owner-only
`qualification-swiftpm-v2/<40-character-SHA>` entries with a valid v2 manifest,
completion marker, matching Git HEAD, and direct SwiftPM build directory. It
orders entries by last use and SHA, removes hour-old idle entries first, then
admits younger idle entries only while the host is still below the capacity
gate. It removes at most sixteen entries or 128 GiB per run and stops as soon as
the threshold passes. Dead cache lease records are retired; the active harness
lease, live cache leases, and live process references protect their exact
worktrees. A malformed entry, symlink, unknown lock, ambiguous harness lease,
or live qualifier without an authoritative lease refuses the entire plan before
deletion. Run staging, cleanup artifacts, qualification evidence, and release
assets are outside the cache root and are never reclaim targets.

On a controlled capacity failure, the workflow fails closed before candidate
assets or the full source checkout are fetched, then its normal finalizer writes
cleanup evidence and uploads both evidence files. The hygiene report records the
before/after observations, known disposable process counts, abandoned run IDs,
and bounded exact-SHA deletion list; it does not attribute a prior incident to
a runner or host cause.

## Cleanup safety

On normal exit, `INT`, `TERM`, `HUP`, or the workflow `always()` finalizer,
release validates the authenticated lease token, state sentinel, process marker,
recorded process group, and matching port manifest before bounded
`INT`→`TERM`→`KILL` escalation. A stale lease is reclaimed only after its
recorded owner PID is dead and that provenance validates. Unknown listeners and
unrecorded processes are never killed. `--keep-stack` intentionally leaves the
recorded lease for later safe reclamation. Retention removes only completed,
sentinel-proven state and paired logs, never a live/incomplete or foreign root.

If Actions loses communication before the normal finalizer runs, the next
pre-tag or qualification invocation runs the self-clean entrypoint before
acquiring new capabilities. It reclaims only the dead authenticated lease,
listeners that remain in the exact recorded PGID (including fixed 8085/9099),
an exactly bound `omi-dev-harness-<lease>-typesense` container, token/start-time/
command-hash-proven `omi-fault-*` apps, and non-current numeric run stages with
no live path reference. `/Applications/Omi.app`, `Omi Beta.app`, their bundle
IDs, foreign listeners, and name-only process matches are never cleanup targets.

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

## Runner provisioning

Use this section when bringing up a new macOS ARM64 host as a desktop
qualification runner. Official Beta qualification (`desktop_qualify_beta.yml`)
only admits jobs that land on the M1 Studio label set; additional hosts may
share the `omi-desktop-qualification` pool for non-gating work but cannot
replace `omi-qual-m1-studio`.

### Hardware

| Requirement | Guidance |
|---|---|
| Architecture | Apple Silicon (ARM64) only |
| RAM | ≥ 32 GiB recommended; qualification rebuilds SwiftPM + hermetic harness |
| Free disk | ≥ 64 GiB usable, with a hard gate of 32 GiB free blocks and 65,536 free inodes before each run (`qualification-runner-self-clean.py`) |
| OS | Current macOS with a full GUI login session (launchd KeepAlive agents need a logged-in user) |

### Software prerequisites

Install and verify before registering the runner:

- Xcode Command Line Tools (`xcode-select --install`) and the pinned CI Xcode
  app expected by `desktop/macos/scripts/run-swift-ci.sh` (currently
  `/Applications/Xcode_16.4.app` when that path is used for Swift CI)
- Docker Desktop (daemon running; `docker info` must succeed)
- GitHub CLI (`gh`) authenticated to an account that can create repo runner
  registration tokens for `BasedHardware/omi`
- Python 3.11+ on `PATH` (`python3 --version`)
- Node.js 20+ on `PATH` (`node --version`)
- Flutter SDK on `PATH` (`flutter --version`) for monorepo tooling that still
  touches shared packages
- `make`, `curl`, `jq`, `git` on `PATH`
- Homebrew tools commonly needed by the harness (`/opt/homebrew/bin` on PATH)

### Clone and Omi setup

```bash
# Durable cache clone used by local evidence-only services and worktrees
mkdir -p ~/.cache/hermes
git clone --filter=blob:none git@github.com:BasedHardware/omi.git ~/.cache/hermes/omi
cd ~/.cache/hermes/omi
make setup          # hooks + backend pre-push env
make setup-backend  # if you need the desktop Python backend venv immediately
```

Dev-harness prerequisites for local/manual qualification:

```bash
make dev-check
# optional smoke of the hermetic stack on this host
make dev-up && make dev-status && make dev-down
```

### GitHub Actions runner registration

Download the latest macOS ARM64 actions runner into a durable home (example:
`~/.local/share/omi-actions-runner`), then register it with `config.sh`.

Labels required by `.github/workflows/desktop_qualify_beta.yml` for the
official qualifier:

```text
self-hosted, macOS, ARM64, omi-desktop-qualification, omi-qual-m1-studio
```

`self-hosted`, `macOS`, and `ARM64` are applied by the runner binary. Pass the
Omi-specific labels explicitly:

```bash
RUNNER_HOME=~/.local/share/omi-actions-runner
REPO=BasedHardware/omi
NAME=m1-mac-studio-qualification
LABELS=omi-desktop-qualification,omi-qual-m1-studio

api_token=$(gh auth token)
registration_token=$(curl -fsS -X POST \
  -H "Authorization: Bearer $api_token" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  "https://api.github.com/repos/${REPO}/actions/runners/registration-token" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')

"$RUNNER_HOME/config.sh" --unattended \
  --url "https://github.com/${REPO}" \
  --token "$registration_token" \
  --name "$NAME" \
  --labels "$LABELS" \
  --work _work
```

A secondary capacity host (for example the M4 Mini) may register with
`omi-desktop-qualification` only (plus an optional host-specific label such as
`omi-qual-m4-mini`). It will not receive `qualify-m1-studio` jobs.

Keep the runner alive across reboots with a GUI-session launch agent that
`exec`s `$RUNNER_HOME/run.sh` (`KeepAlive` + `RunAtLoad`). Export a PATH that
includes the backend venv and Homebrew, and set `OMI_ALLOW_ADHOC_SIGN=1` only
for the disposable `omi-qualification-*` bundles enforced by `run.sh`.

### Network access

The runner must reach:

- `github.com` / `api.github.com` / Actions service endpoints (checkout, release
  download/upload, app-token flows)
- Live desktop-backend health used by the workflow
  (`https://desktop-backend-hhibjajaja-uc.a.run.app/health`)
- Docker Hub / GHCR as required by the hermetic harness images
- Apple notarization is **not** required on the qualifier; signed candidate
  assets arrive from Codemagic via the GitHub Release

Outbound SMTP/Telegram is optional and only used by host-local notify helpers.

### Local evidence-only service (optional)

For host-local babysitting of a tagged candidate outside Actions, use the
portable service (also installable at `~/.hermes/scripts/`):

```bash
# From a checkout, or via ~/.hermes/scripts/qualify-desktop-beta-service.py
desktop/macos/scripts/qualify-desktop-beta-service.py \
  --health-port 8765 \
  v0.12.89+12089-macos
```

Behavior:

- Tag is a CLI argument (no per-version hardcoding)
- Discovers `git` / `gh` / `make` / Python at runtime (no `/Users/...` literals)
- Dual-logs to stdout and `~/.hermes/logs/qualify-desktop-beta-<tag>.log`
- Persists phase/attempt state under `~/.hermes/state/`
- Retries with exponential backoff (5m base → 30m cap)
- Serves `GET http://127.0.0.1:<port>/health` for watchdog probes
- Stops cleanly on `SIGINT` / `SIGTERM`

Pair long runs with `desktop/macos/scripts/qualification-watchdog.py` when you
need heartbeat + bounded process-group enforcement.

### Health verification

```bash
# Runner online with expected labels
gh api repos/BasedHardware/omi/actions/runners \
  --jq '.runners[] | {name,status,labels:[.labels[].name]}'

# Launch agent / process
launchctl print "gui/$(id -u)/com.omi.desktop-qualification-runner" | head
pgrep -lf 'Runner.Listener|omi-actions-runner' || true

# Capacity gate the workflow will enforce
python3 desktop/macos/scripts/qualification-runner-self-clean.py \
  --dry-run --report /tmp/runner-hygiene.json \
  --repo-root "$PWD" \
  --cache-root "${OMI_QUALIFICATION_SWIFT_CACHE_ROOT:-$HOME/Library/Caches/OmiDesktop/qualification-swiftpm-v2}" \
  --qualification-lease-root "${OMI_QUALIFICATION_LEASE_ROOT:-${TMPDIR:-/tmp}/omi-desktop-qualification}" \
  --stage-root "${RUNNER_TEMP:-/tmp}/desktop-beta-qualification" \
  --fault-temp-root "${TMPDIR:-/tmp}" \
  --capacity-path "${RUNNER_TEMP:-/tmp}" \
  --current-run-id dry-run \
  --minimum-free-kib 33554432 \
  --minimum-free-inodes 65536

# Optional local service health
curl -fsS http://127.0.0.1:8765/health | jq .
```

### Security notes

- `desktop_qualify_beta.yml` elevates `contents: write` on the M1 job so it can
  upload qualification evidence to the release. Treat the runner host as a
  secrets boundary: anyone who can execute on it can act with that write scope
  for the duration of a job.
- Runner registration tokens and `gh auth` credentials must stay on the host;
  do not commit them, and prefer short-lived app tokens inside workflows.
- Ad-hoc signing (`OMI_ALLOW_ADHOC_SIGN=1`) is restricted by `run.sh` to named
  disposable qualification bundles — never broaden that allowlist on a shared
  machine.
- Keep `/Applications/Omi.app` and `Omi Beta.app` out of qualification cleanup
  targets; the self-clean entrypoint already refuses them.
