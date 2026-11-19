# Patterns, and the check that enforces each

This codebase is written and changed by agents that start each task with no memory of the last
one. Every pattern here exists so that a change can be made correctly from local context: the
file being edited, its package README and the tests it names. Each pattern names its enforcement;
a pattern without a check is a wish, and belongs in a pull request that adds the check.

## 1. Decide in pure functions, act in a thin shell

A decision (what happens after a failure, whether a job may run, how a record is built) is a
function from values to a value. It takes no context, clock, database or client. The caller
gathers the facts, calls the rule, and performs what it decided.

- Model: [`internal/queue/rules`](../internal/queue/rules/rules.go), called from
  [`internal/queue/outcome.go`](../internal/queue/outcome.go). The kind-level model is
  [`internal/batchunit/unit.go`](../internal/batchunit/unit.go).
- Why: a rule can then be read and tested as a table, and changed without reading the code that
  executes it.
- Enforced by: `depguard` rule `rules-are-pure` (a `rules` package cannot import `context`, `os`,
  `net`, `io`, `sync`, `log/slog`, the database driver or the clock).

## 2. No hidden inputs

Time, configuration and cancellation arrive as parameters. Nothing is read from a global.

- Take a `clock.Clock` where you wait or read the time; take a `time.Time` where you only decide.
- Configuration is read once, in `cmd/<binary>/config.go`, into a typed value that is passed down.
- A function that can block takes the caller's `context.Context` as its first parameter and
  never stores it in a struct.
- Enforced by: `forbidigo` (`time.Now`, `time.Sleep`, timers, `os.Getenv`, `context.Background`
  are rejected outside `cmd/` and `internal/platform/clock`), `gochecknoglobals`,
  `gochecknoinits`, `containedctx`, `contextcheck`.

## 3. Closed sets are named types with exhaustive handling

States, terminal outcomes, fault kinds and decisions are named types with every value listed.

- A switch over one must name every case; `default` does not count as handling.
- A set that only its owner may extend is sealed: an interface with an unexported method, as
  `queue.Outcome` is. The constructors are the only way to make a value.
- A set that others extend, like `queue.Cause`, is registered at start-up. The queue records
  anything unregistered as `unknown`, so `unknown` above zero is always a bug.
- Wire names live at the edge. Domain types carry no JSON tags; `cmd/jobd/http.go` maps them.
- Enforced by: `exhaustive`, `gochecksumtype`, `musttag`; the database repeats closed sets as
  `CHECK` constraints.

## 4. Errors are handled where they happen

- Every error is checked. `_ =` on an error is rejected.
- Wrap with the operation, not the data: `fmt.Errorf("renew lease: %w", err)`.
- Match with `errors.Is` or `errors.AsType`. Never compare message text.
- An adapter that knows what a failure means returns an error implementing `queue.Classified`.
  A handler turns any error into an outcome with `queue.FromError`, which treats an
  unclassified failure as transient, never as success.
- Cleanup that must run after cancellation uses `pg.Cleanup` so it has its own deadline, and its
  error is joined to the original with `errors.Join`.
- Enforced by: `errcheck` (with blank assignments and type assertions), `errorlint`, `nilerr`,
  `nilnesserr`, `errname`, `rowserrcheck`, `sqlclosecheck`, `bodyclose`.

## 5. A kind depends on ports, never on an adapter

A job kind declares the interfaces it needs from the outside world next to its own code
([`internal/batchunit/ports.go`](../internal/batchunit/ports.go)). The binary passes
implementations in. Swapping the stub for a real vendor client changes `cmd/`, not the kind.

- Keep a port small: at most six methods, named for what the kind needs, not for the vendor.
- State the port's contract in its comment, especially idempotency and charging.
- Enforced by: `depguard` (kinds cannot import each other; `internal/queue` cannot import a
  kind; `internal/platform` imports nothing from the module), `interfacebloat`.

## 6. Every write a worker makes is fenced; every external call is guarded

- A worker changes its job only through `Run` methods, which apply the change only while the
  claim's token still holds an unexpired lease. A worker that lost its lease gets
  `queue.ErrLease` and must write nothing more.
- A call to anything outside the database goes through `Run.Guard`. An erase waits for it and
  nothing for that tenant starts after it; a takeover cannot overlap it.
- A guarded call still needs a stable request id or a conditional write at the remote end,
  because a crash after the call cannot be undone locally.
- Enforced by: the queue's API (there is no unfenced write), the integration tests named in
  [`internal/queue/README.md`](../internal/queue/README.md), and the conformance kit's
  kill-and-restart run.

## 7. Plain SQL with typed rows

- SQL is written out, with explicit column lists, next to the function that runs it.
- One `scan` function per row type reads exactly the columns of one `columns` constant.
- A transaction is `pg.InTx`. Schema changes are new numbered files in `migrations/`; applied
  files are never edited.
- Enforced by: `depguard` (no ORM, no `database/sql`, no query builder), `unqueryvet`
  (no `SELECT *`), `sqlclosecheck`, `rowserrcheck`.

## 8. Nothing sensitive in logs, metrics or job rows

- Log a hash of a job id, a closed cause and a duration. Never a user id, a conversation id,
  payload text, a key, a header or remote error text.
- A metric label takes its values from a closed set.
- A job row holds identifiers and progress. Payload stays in the system that owns it.
- Enforced by: typed faults that carry no remote text (`httpx.Fault`), closed label types, and
  the conformance kit's database and log scans. This one is only partly mechanical: review for it.

## 9. Tests ship with the code and say what they protect

- A pure rule gets a table test whose case names read as the rule.
- Code that touches Postgres is tested against Postgres. There is no database fake.
- A test's name states the behaviour it protects. A fix ships with a test that fails without it.
- Tests run with the race detector and in parallel where they share nothing.
- Enforced by: `tools/archcheck` (a package with code has a test file), `tparallel`, `thelper`,
  the race detector in `make test`.

## 10. Small enough to read in one pass

- A file is at most 500 lines, a function at most 70 lines and 45 statements, with bounded
  complexity. An interface has at most six methods.
- A package that owns rules has a README listing each rule with the test that enforces it.
- `AGENTS.md` is a map of at most 60 lines.
- Temporary code carries a `CLEANUP-NOTE:` saying what it is for and how to remove it.
- Enforced by: `funlen`, `cyclop`, `gocognit`, `nestif`, `lll`, `interfacebloat`,
  `tools/archcheck`.

## Changing a rule

There is no suppression comment: `tools/archcheck` rejects `//nolint` and its relatives. If a
rule is wrong for a case, change `.golangci.yml` or `tools/archcheck` in a pull request of its
own, with the case that motivated it. A rule changed in passing, inside a feature, is not reviewed.
