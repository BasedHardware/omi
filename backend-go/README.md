# backend-go

The Go home for Omi's backend runtime code: a durable job queue on Postgres and the job kinds that
run on it. Python stays for the ML services; state families move here one at a time.

Agents and people start with [AGENTS.md](AGENTS.md). The reasons behind the rules are in
[docs/patterns.md](docs/patterns.md).

## Status

- `internal/queue` and `internal/platform` are the foundation: reviewed shape, enforced rules.
- `internal/batchunit` is the reference kind.
- `internal/conformance` holds the flow and stub adapter ported from the language bake-off. They
  exist so the conformance kit (a black-box suite of 261 cases, a kill-and-restart run and a load
  run) can drive the queue end to end. They are replaced by the real conversation finalization
  family and real adapters, and are held to the correctness rules but not the style rules.

## Dependencies

| Module | Why |
| --- | --- |
| `github.com/jackc/pgx/v5` | Postgres driver: plain SQL, typed scans, connection pools. |

Tooling is pinned in the Makefile and run through the module cache: `golangci-lint`.

## Layout rules, enforced

- `internal/platform/*` imports nothing else from this module.
- `internal/queue` imports no job kind.
- Job kinds do not import each other, or an adapter. They declare ports.
- A package named `rules` does no I/O.
