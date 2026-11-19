# backend-go: start here

New backend runtime code is written here, in Go. This file is a map. The rules are enforced by
`make check`; the reasons are in [docs/patterns.md](docs/patterns.md).

## Where things are

| Path | What it is |
| --- | --- |
| `internal/queue` | The durable job queue. Knows no job kind. Start with its README. |
| `internal/queue/rules` | The queue's decisions as pure functions. The model for every `rules` package. |
| `internal/batchunit` | **The reference job kind. Copy its shape for a new kind.** |
| `internal/platform/*` | Shared leaves: `clock`, `pg`, `httpx`, `crypt`. They import nothing else from this module. |
| `internal/conformance/*` | A ported flow and a stub adapter that let the conformance kit drive the queue. Not a style reference; being replaced. |
| `cmd/jobd` | The reference binary. The only place that reads the environment and wires dependencies. |
| `tools/archcheck` | Structural rules a linter cannot express. |

## Before you write code

1. Read the README of the package you are changing, then the test it names for the rule you touch.
2. A new job kind is three files, like `internal/batchunit`: types and pure decisions, ports, a thin
   service. Decisions go in pure functions; I/O goes behind a port the binary passes in.
3. Run `make check`. It must pass before you push. There is no way to silence a finding:
   fix the code, or change the rule in `.golangci.yml` in its own reviewed change.

## The rules you will hit first

- **No hidden inputs.** No `time.Now`, `os.Getenv`, globals, `init`, or `context.Background` outside
  `cmd/`. Take a `clock.Clock`, a typed config value, and the caller's context.
- **Closed sets are types.** A set of states, outcomes or causes is a named type with listed
  constants. Switches over it must be exhaustive.
- **Errors are values you handle.** Every error is checked and wrapped with what you were doing.
  Never log remote text, identifiers of users or conversations, keys, or payloads.
- **Plain SQL, typed rows.** No ORM, no query builder, no `SELECT *`. Schema changes are new files in
  a package's `migrations/`.
- **External calls are guarded and idempotent.** A worker calls out through `Run.Guard`, with a
  stable request id, so a retry is charged once and an erased tenant sees nothing after the erase.
- **Tests ship with the code.** Pure rules get table tests; anything touching Postgres gets a test
  against a real database (`QUEUE_TEST_DATABASE_URL`). A fix ships with a test that fails without it.
- **Files stay under 500 lines**, functions under 70. Split by responsibility, not by size alone.

## Commands

| Command | Does |
| --- | --- |
| `make check` | vet, lint, structural rules, tests with the race detector |
| `make test QUEUE_TEST_DATABASE_URL=postgres://...` | includes the Postgres integration tests |
| `make test-public KIT=/path/to/kit` | the conformance kit's public suite against `bin/jobd` |
| `make fmt` | format |
