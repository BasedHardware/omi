# E2E bundle pool: pre-authorized named bundles for headless testing

A fixed pool of named bundles (`omi-e2e-1` … `omi-e2e-N`) that a human grants
every macOS permission **once**, and that headless agents then lease per task
instead of minting a fresh bundle. `scripts/omi-e2e-pool` owns the leases;
`run.sh` refuses to build a pool slot without one.

## Why a pool, not a bundle per task

macOS binds every TCC grant — Microphone, Screen Recording, Accessibility,
System Audio, Notifications, Automation, folder access — to the **bundle ID plus
the signing certificate**. Two consequences:

- A grant survives every rebuild as long as neither changes. That is what makes
  a slot reusable from any worktree, at any commit.
- Nothing but a human can create the grant. No agent, rule, or script can click
  the system dialog, and Screen Recording and Accessibility cannot be granted by
  `tccutil`, an MDM profile, or a database edit on a machine with SIP enabled.

`run.sh`'s default of deriving `omi-<worktree>` per linked worktree is right for
interactive work and wrong for headless work: every task starts with zero grants
and stops at the first dialog. A pool moves the human step from "once per task"
to "once per slot".

## One-time setup (a human, in the machine's GUI session)

Pick the pool size from how many lanes actually run at once; each slot costs one
grant pass. The default is 3 and any positive integer works:

```bash
export OMI_E2E_POOL_SIZE=3          # put it in the shell profile of the host
cd desktop/macos
./scripts/omi-e2e-pool setup        # prints the checklist below, per slot
```

For each slot:

1. Build and launch it once from any checkout. The pool pins the signing
   identity for the slot on first use (default `Omi Local Dev Signing`, the
   stable self-signed identity `run.sh` creates without a GUI; see
   [`local-code-signing.md`](local-code-signing.md)). Set
   `OMI_E2E_POOL_SIGN_IDENTITY` *before* the first acquire to pin an Apple
   identity instead; changing it later resets every grant the slot holds.
   ```bash
   ./scripts/omi-e2e-pool run --slot 1 -- ./run.sh --yolo --no-wait
   ```
2. Open the slot's Permissions page and grant every row when macOS asks. Screen
   Recording and Accessibility land in System Settings › Privacy & Security; let
   the app "Quit & Reopen" if it asks.
   ```bash
   OMI_AUTOMATION_PORT=47701 ./scripts/omi-ctl navigate settings permissions --show
   ```
3. Prove it, then release the slot:
   ```bash
   ./scripts/omi-e2e-pool check --slot 1     # every required row must read "granted"
   ./scripts/omi-e2e-pool release --slot 1
   ```

Recurring: macOS 15 and later periodically re-ask whether an app may keep
recording the screen. `check` reports that as `screen_recording=stale`; one
click clears it.

### Auth: shared (default) or isolated

- **shared** — a full launch clones the Omi Dev session before start, exactly
  as any named bundle does, **when the launcher can read the keychain**: a GUI
  shell can, a background agent shell (launchd `Background` session, ssh)
  cannot and launches the slot cold, leaving whatever session it already has.
  So sign in once during the grant pass; the session persists in the slot's
  own keychain item across rebuilds. Tests then run as the developer's account
  against the dev backend, so their writes are real.
- **isolated** — the slot keeps its own session. Sign in **once** inside the
  slot app with a dedicated test account; the session persists in the slot's
  own keychain item across rebuilds. The Rewind history is not cloned either.
  ```bash
  ./scripts/omi-e2e-pool acquire --slot 2 --auth isolated
  ```
  The mode sticks to the slot, not to the lane that set it, and `status` shows
  it.

## Using a slot from a task

```bash
cd desktop/macos
./scripts/omi-e2e-pool acquire            # first free slot; prints its number
eval "$(./scripts/omi-e2e-pool env)"      # OMI_APP_NAME, ports, identity, auth mode
./run.sh --yolo --fast-only --no-wait     # builds into the leased slot
./scripts/omi-e2e-pool check              # fail fast if a grant is missing
./scripts/omi-ctl wait-ready && ./scripts/omi-ctl navigate rewind
…
./scripts/omi-e2e-pool release            # when the lane is done
```

Or in one step: `./scripts/omi-e2e-pool run -- ./run.sh --yolo --fast-only`.

`acquire` also writes `<worktree>/.dev/e2e-pool.env`, so any later shell in the
same worktree finds its slot with `env` and never needs to re-acquire. Every
`env`, `verify`, `check`, and `run` refreshes the lease's heartbeat.

Each slot has fixed ports, so nothing needs to be threaded through by hand:

| Slot N | Bundle | Bridge port | Desktop backend | Python backend |
| --- | --- | --- | --- | --- |
| N | `com.omi.omi-e2e-N` | 47700 + N | 10100 + N | 8300 + N |

All three bases sit outside the per-worktree ranges `scripts/dev-instance.sh`
derives — the bridge and desktop-backend bases below them, the Python base
above the bounded `8080 + offset` range (max 8279) — so a pool slot never
collides with an auto-isolated worktree.
`./scripts/omi-e2e-pool slots` prints the table for the configured size.

## Leases: who owns a slot, and when it is given up

A lease belongs to a **worktree**. `run.sh` calls `omi-e2e-pool verify <slug>`
before it touches `/Applications`, and lets the build proceed only when the
calling worktree holds the slot (or carries the slot's `OMI_E2E_POOL_TOKEN`).
Anyone else is refused with the holder's name and worktree — in seconds, not
after a flow times out 30 s later inside a route that reads like a product bug.

A lease is **defunct**, and the next `acquire` reclaims it loudly, when:

- the holder's worktree directory no longer exists (`omi-lane finish`,
  `git worktree remove`, a deleted checkout);
- the holder's `.dev/e2e-pool.env` is gone while the worktree remains — a lane
  that deleted its pool state has given the slot up;
- a holder pid recorded with `--pid` has died (pass the pid of the agent run or
  harness that owns the lane, when there is one);
- as a backstop only, no pool command has touched it for
  `OMI_E2E_POOL_STALE` seconds (default 6 h).

A live holder is **never** evicted: `acquire` on a full pool lists the holders
and stops, and says how to grow the pool. `reap` frees defunct leases and
reports — but does not kill — a slot app left running by a vanished lane; the
next launch replaces it.

`acquire`, `release`, and `reap` decide from the lease files and then write
them, so those sequences run under one pool lock: two lanes acquiring at the
same moment are serialized, and each ends up holding a distinct slot.

`release --slot N` still resolves the caller's worktree before releasing. A
live slot held by another worktree is refused even when the caller names the
slot directly. `--worktree PATH` supplies the caller identity for a harness
invoked outside that checkout. Defunct leases remain releasable so a vanished
lane can be cleaned up. Ownership is compared on the canonical worktree path,
so a lease acquired through a relative path or a symlink is released by the
owner's default resolution without repeating `--worktree`.

A holder that comes back after the backstop simply refreshes its own lease; the
backstop reclaims slots from lanes that vanished, it does not lock a live lane
out of its own slot.

`status` shows every slot: installed or not, app running, bridge port bound,
holder, heartbeat age, auth mode.

## What the pool does not cover

- **Shared hardware.** Slots can coexist, but there is one microphone and one
  ScreenCaptureKit on the machine. A test asserting on captured audio or frames
  needs a separate capacity-1 capture lease; two lanes feeding audio at once
  produce misdirected failures, not contention errors.
- **The GUI session.** Launching a GUI app from a background agent shell works
  only while a user is logged in at the console with WindowServer running. That
  is a host precondition, not something a slot can supply.
- **Onboarding and permission flows themselves.** A pool slot is already past
  onboarding and already granted. To test those flows, use a throwaway named
  bundle as `AGENTS.md` describes.

## Contract

`tests/test-omi-e2e-pool.sh` is the hermetic contract (no app, no TCC, no
`/Applications`) and runs in the launcher-test discovery loop on every CI run.
