# Local Auth-emulator identity acceptance

This opt-in workflow proves official Firebase Admin Auth-emulator verification and
PostgreSQL account/grant admission through the mounted production memory process.
It is **not** model-rendering, production Firebase, DEV deployment, or full app
acceptance. The account is explicitly required to be empty. The actual structural renderer
runs; its model port throws if any inference is requested.
Normal `bun run prod-local` now shares this real empty structural-render path.
Nonempty memory rendering remains unsupported and fails closed; it never reports
an invented empty history. Full rendering still needs separate configuration and
qualification.

Without explicit `--local-identity` (or `OMI_PROD_LOCAL_IDENTITY=emulator`),
`prod-local` rejects an ambient emulator host. The identity acceptance process
uses `runtime_mode=local_test`; deployed authentication remains unchanged.

## Prerequisites

Use the managed local PostgreSQL harness exclusively. Coordinate with any other
real-PG test run first:

```sh
bun run test:postgres:setup
bun run test:postgres:preserve
```

The preserved real gate must release the qualification generation through its
existing controlled flow. The seed refuses an unreleased generation and never
inserts a fabricated restore-admission record. No DEV database is used.

Use the project-pinned **Bun 1.3.14**. Emulator startup rejects a different Bun
version before spawning a child. Install Firebase CLI **15.25.1** locally and expose `firebase` on PATH. The script
resolves its installed entry and validates the package version before running it
with Bun; it does not download a CLI at execution time. The Auth-only child gets
only Bun's directory on PATH, leaving the parent environment unchanged. This
keeps the optional macOS `lsof` probe unavailable, so the official CLI uses its
real `node:net` bind probe; no executable shim or synthetic probe result is used. Auth-only emulator ports
19099, 14400 and 14500 must be unused. It binds loopback only.

## Acceptance

```sh
bun run scripts/prod-local-identity-e2e.ts
```

The command owns a new emulator, creates two synthetic identities, seeds only
one, and serves the actual production process on an OS-assigned loopback HTTP
port. It requires health 200, readiness 200, authorized empty memories 200, and
unseeded identity 403. An unavailable backend is a failure, never proof of denial.
Bearer values are retained in memory and omitted from acceptance output.

Startup, HTTP probes and child commands have deadlines. Failure unwinds service
and emulator cleanup before the command exits unsuccessfully. An exclusive private lifecycle lease spans startup, proof and shutdown. Existing emulator
state is refused rather than adopted or stopped by the acceptance command.
There is no port-4851 fallback and no process-enumeration dependency for socket
checks. The direct `prod-local` launcher retains its fixed, allowlisted port 4851. It
uses a real socket bind check and refuses an occupied port without touching the
existing listener. Startup and bind failures, SIGINT and SIGTERM share one cleanup
path: stop the listener, drain the production process, then release identity and
storage. Cleanup failures cannot silently produce a successful exit.

The standalone lifecycle commands remain available:

```sh
bun run scripts/prod-local-identity.ts --status
bun run scripts/prod-local-identity.ts --start
bun run scripts/prod-local-identity.ts --mint
bun run scripts/prod-local-identity.ts --stop
```

State and private logs live in `omi-prod-local-identity` beneath the OS temporary
directory. Shutdown verifies the recorded PID command matches the owned emulator
before signaling its process group. A stale record pointing to an unrelated
process fails closed and leaves that process untouched.

After acceptance, dispose only the managed test PostgreSQL lifecycle:

```sh
bun run test:postgres:destroy
```

## Seed scope

The seed writes local `platform_accounts`, account revision/head authorization,
Firebase application credentials, the `memories.read` grant, and Firebase identity
and application-credential bindings for `app:omi-local-pg`. Application-role
lookup verifies the seeded ownership. No live account, DEV grant, model output,
or subscription entitlement is manufactured.

## Verified local acceptance

The repaired workflow passed on macOS with the installed Firebase CLI
15.25.1: health 200, readiness 200, seeded identity 200, unseeded identity 403,
and owned emulator teardown. The managed PostgreSQL 18.4 gate passed 28 tests
with 11,182 assertions, a 53-migration/120-table logical restore, and both pinned
Bun and Node runtime parity before this acceptance. This evidence covers local
emulator identity/admission only; it is not a live Firebase or deployment proof.

Bun 1.3.14 completed four consecutive owned emulator start/stop cycles. Bun 1.4.0
had an intermittent upstream emulator-startup timeout after its socket probes;
this path therefore enforces the existing project runtime pin. This observation
does not attribute a broader application failure to Bun 1.4.0.

The normal launcher lifecycle is covered through its production lifetime helper,
including pre-abort, cancellation during pending startup, constructor failure,
cleanup failure, and a real socket collision on an owned ephemeral test port.
The existing service on port 4851 was not stopped, restarted, or used for these
checks; this is not an additional live fixed-port launcher certification.
