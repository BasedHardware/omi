# The storm damper is process-shared: one window per namespace, not per store

`firestore_transaction_contention operation=<label> attempt=5/5
outcome=exhausted` kept burning even after the store damper shipped, because
the damper's whole contract — an exhaustion's re-strike window damps the next
entry of that label — was scoped to ONE store instance, and the process does
not have one store instance. Serving, intake, provider STT, voice evidence
and cap-hold admission each construct their own `FirestoreStore` for the same
namespace, several of them per call (an intake admission check, a durable
status probe), and the diarizer worker builds its own alongside the runtime
store. A label that exhausted through one instance armed a window that died
with that instance: the next entry of the same label on any sibling instance
consulted an empty damper and re-struck the hot documents immediately. For
the labels whose call sites build a store per call, no window ever survived
long enough to damp anything.

Failure-Class: FC-storm-damper-window-dies-with-its-store-instance

## What changed

- `FirestoreStore` keeps one process-shared damper per namespace through the
  registry (`shared_storm_damper`): every store constructed without an
  explicit `storm_damper=` joins it, so an exhaustion armed through any
  instance spaces the next entry of that label on every instance of the same
  namespace. The consult/peek/arm/note-success/wave-rung contract is
  unchanged — only its reach changed, from one instance to the process.
- The get-or-create is double-checked under a lock: stores are constructed on
  executor threads (intake admissions, serving pulls), so two concurrent
  constructions of one namespace must observe the same damper object.
- Namespace validation runs before the damper is resolved, so an invalid
  namespace still refuses without registering any state.
- `reset_shared_storm_dampers()` drops the registry; the unit conftest calls
  it around every test so one test's armed window cannot leak into the next
  test's stores of the same namespace.

## What did not change

- The damper's ladder shape, caps, jitter, label cap, generation guard, and
  the exhaustion-driven stamping of `FirestoreContentionExhausted.retry_after`
  are untouched. Sharing moves WHERE the windows live, never their size.
- An explicitly injected `storm_damper=` is honored verbatim and never
  registered: tests own their damper identity, and a foreign damper must not
  leak state into the shared one.
- Dormant behavior is byte-identical: with either contention kill switch off
  there is no consult, no peek, no arm, and the schedule stays the bare
  ladder — sharing changes nothing when nothing arms.
- The mid-ladder gate and per-rung wave waits stay per-chain and are still
  never recorded on the shared label state; exhaustion stamping stays
  exhaustion-driven.
- Non-transactional read paths (`probe`, `due`, `oldest`,
  `service_frontier_hint`) never touch the damper, shared or not.

## Boundary notes

- Two different namespaces still get independent dampers — sharing is keyed
  by namespace, and a prod store has never damped a dev store.
- The registry is bounded by the namespace count (prod/dev processes hold one
  or two); the per-damper label cap still bounds state inside each damper.
- A test that needs isolation from the shared registry resets it
  (`reset_shared_storm_dampers`) rather than constructing dampers by hand.

Failure-Class: FC-storm-damper-window-dies-with-its-store-instance
