# backend-go

The Go home for Omi's backend runtime code: a durable job queue on Postgres and the job kinds that
run on it. Python stays for the ML services; state families move here one at a time.

Agents and people start with [AGENTS.md](AGENTS.md). The reasons behind the rules are in
[docs/patterns.md](docs/patterns.md).

## Status

- `internal/queue` and `internal/platform` are the foundation: reviewed shape, enforced rules.
- `internal/batchunit` with `internal/adapters/batchdocs` is the reference kind and the reference
  adapter. Together they show a paid call that is charged once and recovered after a crash, and a
  Firestore write that an account deletion can always stop.
- `internal/conformance` and `cmd/jobd` hold the flow, stub adapter and binary ported from the
  language bake-off. They exist so the conformance kit (a black-box suite of 261 cases, a
  kill-and-restart run and a load run) can drive the queue end to end. `cmd/jobd` is a kit binary:
  it binds to every interface and exposes unscoped read, redrive and erase routes, so it must
  never become a production server by small additions. Production gets its own `cmd/<binary>`.
  This code is held to the correctness rules but not the style rules, and is replaced by the real
  conversation finalization family.

## Dependencies

| Module | Why |
| --- | --- |
| `github.com/jackc/pgx/v5` | Postgres driver: plain SQL, typed scans, connection pools. |
| `cloud.google.com/go/firestore` | Firestore client, used only inside `internal/platform/docstore`. It brings gRPC and the Google API libraries with it. |

Tooling is pinned in the Makefile and run through the module cache: `golangci-lint`. `go.mod`
names the minimum Go version; CI builds with exactly that version.

## What `make check` needs

- **Postgres 16.** Found on `PATH` or in the usual Homebrew and Debian locations, and started
  privately for the run; or set `TEST_DATABASE_URL`. Without it the check fails.
- **The Firestore emulator** (firebase-tools and a JDK). Started privately for the run; or set
  `FIRESTORE_EMULATOR_HOST`. Without it the Firestore tests skip with a notice, and CI runs them.

Each test creates its own database and its own Firestore project, so two checkouts on one machine
do not disturb each other.
