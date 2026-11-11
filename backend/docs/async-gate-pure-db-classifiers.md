# Async-blocker gate: pure database-module classifiers

## What broke

The batch pipeline publication re-strike lane (`utils/batch_pipeline/pump.py`,
`Pump._restrike_publication`) classifies a lost publication transition with
`publication_loss_is_contention()` -> `is_transaction_contention()`. The
classifier is imported from `database.firestore_transaction_retry` and walks
an exception `__cause__` chain with `isinstance` checks; it never touches
Firestore or the network.

The async-blocker manifest check
(`scripts/pr-preflight` check `backend-async-blockers`) classifies every name
imported from a `database.*` module as blocking persistence I/O. That
heuristic flagged the re-strike lane:

```
async_helpers_with_blocking: backend/utils/batch_pipeline/pump.py:1042
  | _restrike_publication | publication_loss_is_contention()
  -> is_transaction_contention
```

Because the check runs on every PR, **every candidate PR failed preflight**
and none could open: the landed fixes for the top production error
signatures (empty-ASR quarantine, batch validation demotion, the store
storm gate) sat parked on the branch while the sensor kept burning on the
unfixed deployed code.

## The fix

`scan_async_blockers.py` gained a second source-resolved exemption beside
the existing context-manager one: a callable imported from a `database.*`
module is exempt when its defining module proves it pure.

The proof, resolved from source on every scan (never cached across runs):

- single top-level `def` (duplicate definitions are ambiguous and refused);
- no decorators (a decorated function is a wrapper this analysis cannot
  see through — that includes `@contextmanager`, which the context-manager
  resolution owns);
- no generator behavior (`yield` defers side effects);
- no offload wrappers in the body (`run_blocking`, `to_thread`,
  `run_in_executor` — a body that offloads exists because the wrapped work
  blocks);
- empty blocking-effect set under the module-local transitive analysis with
  the module's own imports;
- module-level assignment aliases (`is_transaction_contention =
  _is_transaction_contention`) resolve through a bounded, cycle-checked
  chain to such a function.

Conservative posture, shared with the context-manager resolution: missing,
unparsable, or ambiguous source stays classified as blocking. The exemption
covers only the direct call of the imported name outside a `with`
statement; its arguments and everything around the call stay fully checked.
With-context expressions belong to the context-manager resolution, so the
two resolvers have disjoint domains.

Drift auto-revokes the exemption: if the classifier ever gains a db call,
file I/O, network I/O, sleep, or an offload wrapper, the next scan's proof
fails and the call is blocking again. Nothing needs to be removed by hand.

## Contract surface (regression grids)

- `tests/unit/test_async_gate_pure_classifier_resolution_grid.py` — the
  pure-resolution decision table (def-form x effect-form x import-form).
- `tests/unit/test_async_gate_context_manager_resolution_grid.py` — the
  same lattice for the context-manager resolution, including the
  asymmetry cells (a body that only offloads is context-manager-exempt but
  pure-refused).
- `tests/unit/test_async_gate_sink_classification_grid.py` — the sink
  classification lattice (sink kind x call form x context).
- `tests/unit/test_async_gate_batch_lane_real_module_grid.py` — the real
  batch-lane modules: every pump async function gate-clean in the fixed
  posture and flagged-with-ablation exactly where the exemption is what
  keeps it clean, every module-level helper's effect set, and the resolver
  membership of every database name the pump imports.

Failure-Class: FC-async-blocker-gate-false-positive-on-pure-db-classifiers
