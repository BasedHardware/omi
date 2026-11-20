# Patterns, and the check that enforces each

This codebase is written and changed by agents that start each task with no memory of the last
one. Every pattern here exists so that a change can be made correctly from local context: the
file being edited, its package README and the tests it names. Each pattern names its enforcement.
Where the enforcement is partial, it says so.

## 1. Decide in pure functions, act in a thin shell

A decision (what happens after a failure, whether a job may run, how a record is built) is a
function from values to a value. It takes no context, clock, database or client. The caller
gathers the facts, calls the rule, and performs what it decided.

- Model: [`internal/queue/rules`](../internal/queue/rules/rules.go), called from
  [`internal/queue/outcome.go`](../internal/queue/outcome.go) and `claim.go`. The kind-level
  model is [`internal/batchunit/unit.go`](../internal/batchunit/unit.go).
- Why: a rule can then be read and tested as a table, and changed without reading the code that
  executes it.
- Enforced by: `tools/archcheck`. A directory named `rules` may import only a short allowlist of
  the standard library and nothing from this module. It is an allowlist, so a new way to do I/O
  is excluded by default.

## 2. No hidden inputs

Time, configuration and cancellation arrive as parameters. Nothing is read from a global.

- Take a `clock.Clock` where you wait or read the time; take a `time.Time` where you only decide.
- Configuration is read once, in `cmd/<binary>/config.go`, into a typed value that is passed
  down. `queue.Open` validates its policy and every kind declaration before it connects.
- A function that can block takes the caller's `context.Context` as its first parameter and
  never stores it in a struct.
- Enforced by: `forbidigo` (`time.Now`, `time.Sleep`, timers, `os.Getenv`, `context.Background`
  are rejected outside `cmd/`, `internal/platform/clock` and the test helpers),
  `gochecknoglobals`, `gochecknoinits`, `containedctx`, `contextcheck`.

## 3. Closed sets are named types; open sets are declared

- States, terminal outcomes and decisions are named types with every value listed. A switch over
  one must name every case; `default` does not count.
- A set only its owner may extend is sealed: an interface with an unexported method, as
  `queue.Outcome` and `queue.Resolution` are. The constructors are the only way to make a value.
- A set others extend (kinds, formats, steps, causes) is declared in a `queue.Kind` and checked
  at start-up. An undeclared kind, format or step is refused at enqueue and at save. An
  undeclared cause is recorded as `unknown`, so `unknown` above zero is always a bug.
- Wire names live at the edge. Domain types carry no JSON tags; a small unexported struct beside
  the code that stores or serves it does (`stored` in `batchunit`, `unitWire` in `cmd/jobd`).
- Enforced by: `exhaustive`, `gochecksumtype`, `musttag`, the queue's registry, and `CHECK`
  constraints that repeat the closed sets in the database. Archcheck uses `go/types` to check
  that `States()` and `Terminals()` each return a slice naming every package constant of
  their type exactly once.

## 4. Errors are handled where they happen

- Every error is checked. `_ =` on an error is rejected.
- Wrap with the operation, not the data: `fmt.Errorf("renew lease: %w", err)`.
- Match with `errors.Is` or `errors.AsType`. Never compare message text.
- An adapter says what a failure means with `queue.Classify(err, outcome)`. A handler turns any
  error into an outcome with `queue.FromError`, which treats an unclassified failure as
  transient, never as success.
- Cleanup is registered with `defer` before the code it cleans up after, so it runs on a panic
  too, and uses `pg.Cleanup` so it has its own deadline after cancellation. Its error is joined to
  the original with `errors.Join`.
- A handler panic is a failed attempt of that job, reported once. It does not stop the replica.
- Enforced by: `errcheck` (with blank assignments and type assertions), `errorlint`, `nilerr`,
  `nilnesserr`, `errname`, `rowserrcheck`, `sqlclosecheck`, `bodyclose`; the queue tests named in
  its README for panics and lock release.

## 5. A package's path is its role, and its role is what it may import

| Path | Role | May import from this module |
| --- | --- | --- |
| `cmd/<binary>` | binary | anything; the only place adapters meet families |
| `internal/<family>` | family | its own subtree, `internal/queue`, platform `clock` and `crypt` |
| `**/rules` | rules | nothing |
| `internal/adapters/<name>` | adapter | platform, queue, families; not another adapter |
| `internal/queue` | queue | platform |
| `internal/platform/<name>` | platform | platform |
| `tools/<tool>` | tool | nothing |

A family also may not import a client library or the parts of the standard library that do I/O
(`net`, `os`, `database`, `log`). So a family cannot reach the outside world except through an
interface it declares and the binary fills in. A new family needs no entry in any list.

- Enforced by: `tools/archcheck` (`roles.go`), with fixture tests that use a family name the
  checker has never seen. A package outside these paths has no role and is reported.

## 6. Every write is fenced, every external call is guarded, every paid call is recoverable

- A worker changes its job only through `Run` methods, which apply the change only while the
  claim's token still holds an unexpired lease. A worker that lost its lease gets
  `queue.ErrLease` and must write nothing more.
- A call that leaves the process is a port method that takes a `queue.Guarded` (in a worker) or a
  `queue.Admitting` (in admission). The only way to get one is to be inside `Run.Guard` or
  `Store.Tenant`. An erase waits for the call and nothing for that tenant starts after it.
- An external operation's identity is `g.Operation(step)`. It depends only on the job and the
  step, so a retry, a takeover and a newer binary all send the same value.
- A paid adapter charges once per operation and can return a committed result by operation
  alone. A handler's `Exhausted` asks for it, so a result that was paid for just before a crash
  is recovered, not parked.
- A store of tenant data refuses a write for an account being deleted itself, in the same atomic
  step as the write (`docstore.Fenced`). The queue's guard alone is not enough: its locks end if
  the database session dies mid-call.
- Only `internal/platform/docstore` imports the Firestore client, so there is no way to write
  to Firestore that skips the marker read. `Fenced` also refuses a guard that is for a different
  tenant than the owner it is asked to write for.
- Enforced by: the type system (a port method cannot be called without the capability);
  `tools/archcheck` (`ports.go`: in a family, an interface method, a named function type and a
  function-typed field or parameter that take a context must take a capability, and
  `context.Context` may not be renamed; a capability cannot be made, stored in a struct, or
  minted with the test constructors outside tests; `roles.go`: the Firestore import rule); the
  contract tests in `internal/queue`, `internal/batchunit` and `internal/adapters/batchdocs`.
- Archcheck rejects direct capability arguments and receivers of `go` calls, and closures that
  capture a typed capability and are stored, returned, sent, or passed to an unknown callback
  consumer. A directly invoked closure and the synchronous `Scope.Subject` callback may capture
  an outer capability. Each nested closure is checked separately. Assigning a capturing
  helper to a local variable is rejected even if its only use is a synchronous call inside
  `Scope.Subject`. Call the literal directly or pass the capability as a parameter.
- Pointer chains retain the capability. Call its methods directly: a stored or passed bound
  method value retains the receiver, so archcheck rejects it at the selection. An unbound
  method expression such as `queue.Guarded.Err` can be stored and called with a guard.
  The check uses the static type at the use site. Values previously
  hidden behind an interface or container require review. Adapters still check `g.Err()`.

## 7. Plain SQL with typed rows

- SQL is written out, with explicit column lists, next to the function that runs it.
- One `scan` function per row type reads exactly the columns of one `columns` constant.
- A transaction is `pg.InTx`. Nothing inside a transaction waits on a network.
- A schema change is a new numbered file in `migrations/`. An applied file is never edited: the
  ledger stores each file's checksum and the queue refuses a database that disagrees.
- Enforced by: `depguard` (no ORM, no `database/sql`, no query builder), `unqueryvet`
  (no `SELECT *`), `sqlclosecheck`, `rowserrcheck`, the checksum ledger, and
  `scripts/migrations-frozen.sh` in CI. `TestJobScanMatchesItsProjection` passes distinct values through the job projection
  and scan on Postgres, varying each boolean independently to detect same-type swaps.
  Tenant predicates are covered by the queue's isolation and erase tests.

## 8. Nothing sensitive in logs, metrics or job rows

- A job row holds a reference to its input and a receipt for its result. The payload stays in
  the system that owns it.
- Log a hash of a job id, a closed cause and a duration. Never a user id, a conversation id,
  payload text, a key, a header or remote error text. Typed errors (`httpx.Fault`,
  `docstore.CallError`) carry a status code and nothing from the remote message. A panic is
  reported with its stack, not its value.
- A metric label takes its values from a declared set.
- Enforced by: the declared kinds, steps and causes; typed errors; the reference kind's test that
  scans its job row for transcript text; the conformance kit's database and log scans. This one
  is only partly mechanical: review for it.

## 9. Tests ship with the code, run on the real thing, and say what they protect

- A pure rule gets a table test whose case names read as the rule.
- Code that touches Postgres is tested against Postgres, and code that touches Firestore against
  the emulator. There is no database fake and no fake queue: a handler is tested on real workers
  through `internal/queue/queuetest`.
- Each test gets its own database (`pgtest`) and its own Firestore project (`docstoretest`), so
  tests run in parallel and two checkouts do not collide.
- A test's name states the behaviour it protects. A fix ships with a test that fails without it.
- Enforced by: `tools/archcheck` (a package with code has a test function; a README may only
  name tests that exist), `tparallel`, `thelper`, the race detector, and `make check` failing
  when Postgres is missing instead of skipping.

## 10. Small enough to read in one pass

- A file is at most 500 lines, a function at most 80 lines and 50 statements, with bounded
  cognitive complexity. An interface has at most six methods.
- The queue, each family and each adapter has a README listing each rule with the test that
  enforces it.
- `AGENTS.md` is a map of at most 60 lines.
- Temporary code carries a `CLEANUP-NOTE:` saying what it is for and how to remove it. (A
  convention; nothing checks it.)
- Enforced by: `funlen`, `gocognit`, `interfacebloat`, `tools/archcheck`.

## Changing a rule

There is no suppression comment: `tools/archcheck` rejects `//nolint` and its relatives. If a
rule is wrong for a case, change `.golangci.yml` or `tools/archcheck` in a pull request of its
own, with the case that motivated it. A rule changed in passing, inside a feature, is not reviewed.
