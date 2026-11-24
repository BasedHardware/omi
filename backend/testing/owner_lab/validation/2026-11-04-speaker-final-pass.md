# Speaker final-pass local validation — 2026-11-04

Observed at 2026-11-04T14:41:12.479256+00:00. This is local fixture evidence, not production acceptance.

- Validated code: `6e4b6fa8ec19ca2550971ae583a17830e734cbfb`.
- Implementation: `e34def1dbcca6e0802cf82020cb5d0c9cb131158`.
- Fetched rebase target: `6cf56c7e41925869b1cd5a61cfc73b3628ec6c00`.
- Pre-rebase implementation: `20bc8e112bae4330ae6cbc8c07c9e6449410b0b8`.
- Branch: `lane/spkfix`. No push or PR. No production access or GCP tier used.
- The owner's supplied corpus was not accessed. The parent must rerun it to
  attribute the previously reported individual failures and verify acceptance.

## Findings and policy

1. Exception diagnostics retain the class and innermost backend-relative
   `file:line:function`. Unknown messages remain `unclassified` with a location;
   an unraised exception explicitly uses `unavailable`. No locals, arbitrary
   messages, transcript text or UID enter these diagnostics. Exception
   stringification is not invoked. Batch production logs and lab JSONL carry
   the same fields.
2. The old `5a918ea` metric guard was executed against the actual lazy gauge
   initializer. It reproduced:

   ```text
   exception_type=AttributeError reason=unclassified
   location=utils/observability/stt_cap_dispatch.py:24:<module>
   ```

   `labels().set_function()` is a concrete failure, and the old silent child
   also lacked timer/exception-counter/in-progress contexts. The replacement
   supports contexts, decorators, callbacks, private values and child access.
   The retry-custody argument is supplied correctly by `reproduce()`.
3. Reference refusals distinguish missing job/result/receipt/artifact, bound
   owner/unit/kind, generation, erasure and URI failures. Projection validation
   uses specific `projection_*` codes. Impossible document IDs are excluded;
   otherwise absent jobs remain unproved scopes. Their segments keep their
   labels and can be omitted from an explicitly partial pass. No remapping to
   another job is guessed. Expired/merged outcomes and whole-pass abstention
   for shared audio are retained.
4. The conversation no longer borrows a 128-unit bound. Partial retained
   recordings can split source holes into many short units. Registered units
   charge `max(1, duration_seconds)` against 7,200 seconds, bounding both audio
   and IO fan-out. The floor is a resource charge, not a claimed minimum unit
   duration. Artifact reads have a 21,600-object ceiling plus independent
   320 MiB and 180-second bounds; the assembled timeline still caps at two
   hours. Both 129 registered units and excess non-job scopes are tested.
5. Word bounding preserves tokens; EOF tolerance can turn a word into a point.
   Other coverage gaps arise from projection grouping/version ID differences
   or changed text at the same ID. Label updates require matching ID/text and
   positive word evidence. Missing positive segments retain their labels,
   verified segments can update with terminal `partial_coverage`, and partial
   passes never learn recurring profiles. Point-only inputs skip with no
   changes. Full success excludes partial passes.
6. Rebase completed onto the fetched target. Range-diff confirmed the substantive
   implementation patch was unchanged. The GMP file was verified byte-for-byte
   against that target after removing only the added
   `transcription_final_pass_(total|unit_skips_total)|` alternative. Both sides'
   metric families are preserved. A separate follow-up replaced namespace
   interpolation with parsed unit-ID comparisons for the display guard.

## Checks

| Check | Result | Scope |
|---|---|---|
| Focused pytest | 283 passed | After rebase and parsed-scope follow-up |
| Isolated replay module | 26 passed | Rebased implementation, 1.00-second per-test CPU guard |
| Full `make preflight` | 38 checks passed | Validated code SHA above, target `6cf56c7e4192` |
| PR metadata | 4 checks passed | Rebased implementation and exact line-count exceptions |
| Black | Passed | Commit hooks left all staged Python files unchanged |
| GMP merge verification | Passed | Fetched target plus both final-pass counters only |

Focused suite, from `backend/`, through the host's shared `omi-heavy` gate:

```sh
.venv/bin/python -m pytest \
  tests/unit/test_batch_final_pass.py \
  tests/unit/test_batch_final_pass_repro.py \
  tests/unit/test_batch_final_pass_retry.py \
  tests/unit/test_owner_lab_final_pass_repro.py \
  tests/unit/test_final_pass_assignment.py \
  tests/unit/test_final_pass_vad_compaction.py \
  tests/unit/test_sync_final_pass_budget.py \
  tests/unit/test_final_pass_promotion.py \
  tests/unit/test_final_pass_rehome.py
```

The new replay test module uses literal stored segments and receipts, real
Firestore reference/reconstruction/assembly/final-pass functions and the real
diarization helper. Blob transport is synthetic and the diarizer is the lab
projection stub. It covers record origin, multipart VAD, float rounding, point
words, mixed authority, partial coverage, safe error locations, silent metric
contexts, lazy production gauge initialization and unit-count boundaries.

Full preflight used `OMI_CHECKS_JOBS=1`, `BACKEND_PYTEST_WORKERS=1` and the PR
metadata below. Temporary logs are not the durable evidence; this record and
its linked source SHAs identify the tested result.

## PR metadata

INV-MEM-4 and INV-TASK-2: speaker-only retries do not replay memory/task
extraction or other enrichment effects; identity persistence keeps its existing
revision/manual-assignment fence.

Failure-Class: FC-unit-label-as-conversation-identity

Line-Count-Exception: backend/utils/conversations/speaker_resolution.py | 1565 -> 1567 | Forward retry custody without importing the scheduler into the shared GPU layer.

Line-Count-Exception: backend/routers/sync.py | 3793 -> 3804 | Dispatch speaker-only retries through the existing authenticated legacy task edge.

Pusher's finalizer reaches the retry/outbox via `process_conversation` and
`processing_speakers`; the GPU batch-pipeline worker excludes that dependency.
Source closure passed. Pusher's checked-in lock contains Firestore 2.20.0,
Cloud Tasks 2.16.4 and Prometheus 0.21.1. This does not claim an image runtime smoke.

Private `owner_lab/guard.py` and `snapshot.py` remain untracked and uncommitted.
ANX orientation returned `workspace_unavailable` (HTTP 404, no write sent);
repository evidence remains available independently of that service.
