# backend-go: start here

New backend runtime code is written here, in Go. This file is a map. The rules are enforced by
`make check`; the reasons are in [docs/patterns.md](docs/patterns.md).

## Where things are

| Path | What it is | It may import |
| --- | --- | --- |
| `internal/queue` | The durable job queue. Knows no job kind. Start with its README. | platform |
| `internal/<family>` | A job kind or domain family. **`internal/batchunit` is the reference: copy its shape.** | its own subtree, `internal/queue`, platform `clock` and `crypt` |
| `internal/<family>/rules`, `internal/queue/rules` | Decisions as pure functions. | a short list of the standard library |
| `internal/adapters/<name>` | Implements a family's ports against a real system. **`batchdocs` is the reference.** | platform, queue, families |
| `internal/platform/*` | Shared helpers: `clock`, `pg`, `httpx`, `crypt`, `docstore`, and test helpers. | platform |
| `cmd/<binary>` | Reads the environment and wires adapters into families. Nothing else does. | anything |
| `internal/conformance/*`, `cmd/jobd` | A ported flow and stub adapter that let the conformance kit drive the queue. Not a style reference. | |
| `tools/archcheck` | The structural rules. A package's path gives it its role; no list to edit. | standard library |

## Adding a job kind

1. Create `internal/<family>` with three files like `batchunit`: `unit.go` (declaration, types,
   pure decisions), `ports.go` (what it needs from outside), `service.go` (admission and handler).
2. Write its adapters under `internal/adapters/`, and add one entry to `kinds()` and one to the
   handler map in the binary. Nothing in the queue or the lint config changes.
3. Test the handler on real workers with `internal/queue/queuetest`, and list each rule with its
   test in the package README.

## The rules you will hit first

- **A family does no I/O.** Every call that leaves the process is a port method that takes a
  `queue.Guarded` (worker) or `queue.Admitting` (admission). You get one only inside `Run.Guard`
  or `Store.Tenant`, and cannot make or store one.
- **A paid or external call uses `g.Operation(step)` as its identity** so a retry is charged once
  and its result can be recovered. **A store of tenant data is written through
  `docstore.Fenced`**, so a write for an account being deleted is refused by the store itself.
- **A job row holds references and receipts, never payload.** Logs and metrics hold closed
  causes and durations, never ids of users or conversations, keys, or remote text.
- **No hidden inputs.** No `time.Now`, `os.Getenv`, globals, `init`, or `context.Background`
  outside `cmd/`. Take a `clock.Clock`, a typed config value, and the caller's context.
- **Closed sets are types** with exhaustive switches. Steps and causes are declared in the
  kind's `Declaration`; an undeclared one is refused or recorded as `unknown`.
- **Plain SQL, typed rows.** No ORM. A schema change is a new numbered file in `migrations/`.
- **Tests ship with the code** and run against real Postgres and the Firestore emulator. There
  is no fake queue and no database fake. A fix ships with a test that fails without it.
- **Nothing silences a check.** Fix the code, or change the rule in its own reviewed change.

## Commands

| Command | Does |
| --- | --- |
| `make check` | vet, lint, structural rules, every test with the race detector. Starts its own Postgres and Firestore emulator; fails if Postgres is missing. |
| `make quick` | The tests that need no database, for a fast loop. Not a substitute. |
| `make test-public KIT=/path/to/kit` | The conformance kit's public suite against `bin/jobd`. |
| `make fmt` | Format. |
