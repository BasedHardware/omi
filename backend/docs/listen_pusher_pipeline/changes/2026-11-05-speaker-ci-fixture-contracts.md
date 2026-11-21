# Speaker final-pass CI contracts

The final-pass kill switch now uses a constant-named `_default_on` call so the
cross-service deployment scanner recognizes the existing runtime reader. Parsing,
defaults and serving behavior are unchanged; rollback remains
`BATCH_FINAL_PASS_ENABLED=false` across the serving runtimes in the
[runbook](../../runbooks/batch-conversation-speakers.md).

Budgeted read-only Firestore snapshots remain in `database.batch_pipeline_reads`.
`load_reference` and artifact authorization call that adapter directly instead of adding `read` to
`FirestoreStore`'s public surface. That surface is shared with Postgres and the
pipeline simulators, where `read` has different semantics. The existing parity
guard remains unchanged.

The identity-funnel fixture accepts the processing wrapper's `on_persist` keyword
while exercising the real resolver. Usage/persistence fixtures stub that wrapper
at the provider boundary; summary recovery fixtures use the renamed public
`dispatch_binding` helper. Production speaker signatures are unchanged.

CI evidence: both [run 42030341149](https://github.com/BasedHardware/omi/actions/runs/42030341149)
and [run 42042918880](https://github.com/BasedHardware/omi/actions/runs/42042918880)
reported `test_jobstore_protocol_parity.py::test_every_store_backend_serves_the_firestore_store_surface`
for `read-PostgresStore`, `read-SimStore` and `read-PgSimStore`. The latter also
reported the stale summary helper fixture. Validation runs the named failures,
the complete affected files in isolated pytest processes, the final-pass resource
and reconstruction suites, and the normal pre-push gate.

Local results: the named checks passed 57 cases. Complete affected files passed:
identity telemetry 75; deployment contracts 23 (three existing skips); jobstore
parity 66; usage/persistence 69; summary recovery 20; final pass 94; repro 26;
transient dependencies 105; lifecycle 17; owner-lab fence/metrics 40; resource
limits 20 (including the two-hour memory case); snapshot lifecycle 6; speaker
admission 16; recurring voices 18; environment-read ratchet 7. The initial
adapter move exposed two stale snapshot fixture seams and one artifact
authorization caller; all were updated and their affected suites rerun.

Named reproduction/verification, from `backend/` (prefixed with the workspace's
`omi-heavy run --wait 1800 --no-priority --` admission wrapper):

```sh
.venv/bin/python -m pytest -q \
  tests/unit/test_owner_identity_retry_telemetry.py::test_first_finalization_pipeline_emits_funnel_without_counting_reprocess \
  tests/unit/test_cross_service_deploy_contract.py::test_current_manifests_add_no_violation_beyond_known_gaps \
  tests/unit/test_cross_service_deploy_contract.py::test_constant_named_env_reads_are_resolved \
  tests/unit/test_cross_service_deploy_contract.py::test_default_on_wrapper_resolves_constant_env_key \
  tests/unit/test_jobstore_protocol_parity.py::test_every_store_backend_serves_the_firestore_store_surface \
  tests/unit/test_process_conversation_usage_context.py::test_fenced_completion_submits_nothing \
  tests/unit/test_summary_empty_recovery.py::test_transcript_append_reopens_debt_and_repair_reopens_exhausted_outbox
```

Complete files used `BACKEND_UNIT_TEST_FILE_LIST=<file-list>` with
`BACKEND_PYTEST_FILE_ISOLATION=1 BACKEND_PYTEST_WORKERS=1 bash test.sh`.
Additional direct pytest runs covered all of `test_batch_final_pass_resources.py`
(20 passed) and `test_batch_final_pass_types.py test_jobstore_protocol_parity.py`
(72 passed). Black and `git diff --check` passed. The shared PR preflight passed
55 checks; the normal push executes the complete installed pre-push gate.
