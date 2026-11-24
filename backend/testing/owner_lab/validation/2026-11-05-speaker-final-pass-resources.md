# Speaker final-pass resource validation — 2026-11-05

Observed at 2026-11-05T05:49:42.927817+00:00. Local synthetic evidence; no production/account access or
GCP tier used. Branch `lane/spkfix`, parent `3de170bb1da18e749f9bfdbcf35001739384a9be`.
This record supersedes the resource bounds in the November 4 validation.

## Bounds and implementation

- Admission: **480 distinct candidate batch-unit IDs before any read**, derived
  from 7,200 seconds / 15 seconds. The producer targets 300-second units;
  this permits 20 times that fragmentation. It is a resource admission policy,
  not a claim about a minimum source-unit duration. Shorter units remain valid
  within the cap. Sync/non-batch scopes are filtered first. No-job candidate IDs
  consume admission because looking them up costs IO. Excess candidates produce
  the existing `failed_too_long` / `unit limit` terminal result.
- At most 480 initial reference lookups and another 480 revalidations. The
  artifact-object limit is **1,440**; the existing 320 MiB byte budget, 180-second
  reconstruction budget, two-hour summed audio/timeline caps and 600-second
  overall deadline remain independent.
- Reference reads use a consistent read-only Firestore snapshot, one attempt,
  without the SDK/contention retry loop. Begin and every metadata/privacy read
  carry `retry=None` and `timeout=min(10, remaining)`. Cleanup uses at most one
  remaining second; after expiry the read-only server lease expires without
  holding the worker. No commit or write occurs. Post-model revalidation uses
  the remaining overall deadline. A reference deadline aborts immediately.
- Only reference metadata is sorted. Reconstruction preallocates one timeline
  buffer, including the existing decode-rounding tolerance, and consumes decoded
  units incrementally. Consumed PCM is released in both the consumer and suspended
  decoder/lab generators. Overlap equality, gap silence and actual decoded end
  semantics remain unchanged. Word clock/label updates reuse dictionaries.
- The result is a read-only memoryview of actual decoded frames, with no full
  `bytes()` copy. `HttpDiarizer` streams 64 KiB byte chunks, supplies the original
  PCM content length and reconstructs its iterator for each HTTP retry. The
  iterator checks the overall deadline between chunks and after the last chunk. Bytes
  inputs retain their existing adapter contract.
- No flag defaults, deploy files, retry custody or speaker evidence rules changed.

## Verification

The final focused command below passed **421 tests**, including the maximum
stress case, non-batch admission, metadata rounding at the two-hour boundary,
and privacy/memo regressions.

The stress fixture contains **480 units, 7,200 seconds of actual 16 kHz mono
PCM16 and 21,600 words**. WAVs are generated lazily inside the traced region;
there is no preloaded full-size PCM fixture. It executes the real `_units`,
reconstruction, `_assemble`, `_run` and shared final-pass assignment path.
Firestore/blob/GPU transports are synthetic; the stress executes the real
`HttpDiarizer` adapter and drains its upload iterator without accumulating chunks. The assertion requires full success
and a full-length submitted PCM view, with **peak < 288 MiB**. Observed peak was
**240.31 MiB**, with 7.54 seconds of test wall time in that run. This bounds the
measured decoded assembly/word path, excluding process baseline, real VAD/model
working memory and external transport allocations; it is not a pod RSS claim.
The stress is explicitly `slow`; normal focused pytest runs it, while the fast
unit lane excludes it as prescribed by the repository.

SDK deadline tests use the real Firestore client/document/transaction helpers
with an anonymous synthetic GAPIC transport. They assert bounded timeout and no
retry on begin, jobs/results, privacy (including memo), artifacts and rollback;
expired budgets issue no RPC, stalled RPCs consume only remaining time, and a
terminal timeout does not try remaining units. Additional tests assert in-place
word reuse, overlap/gap/tail preservation and HTTP iterator restart.

From `backend/`, through the workspace `omi-heavy` admission gate:

```sh
.venv/bin/python -m pytest \
  tests/unit/test_batch_final_pass.py \
  tests/unit/test_batch_final_pass_repro.py \
  tests/unit/test_batch_final_pass_resources.py \
  tests/unit/test_batch_final_pass_retry.py \
  tests/unit/test_owner_lab_final_pass_repro.py \
  tests/unit/test_final_pass_assignment.py \
  tests/unit/test_final_pass_vad_compaction.py \
  tests/unit/test_sync_final_pass_budget.py \
  tests/unit/test_final_pass_promotion.py \
  tests/unit/test_final_pass_rehome.py \
  tests/unit/test_batch_pipeline_privacy.py \
  tests/unit/test_batch_privacy_conversation_fence.py \
  tests/unit/test_fsr_wq12_batch_privacy.py \
  tests/unit/test_bpp_generation_memo.py
```

The owner's private corpus was not accessed; the parent retains the real-data
acceptance run and publication boundary. No push or PR.

## Final checks

| Check | Result |
|---|---|
| Focused suites, final implementation | 421 passed |
| Resource module, isolated fast lane | 16 passed, stress deselected; 1.00-second CPU guard |
| Selected preflight guards | All 38 passed in partitioned validation against `6cf56c7e41925869b1cd5a61cfc73b3628ec6c00` |
| Firestore guard tests | All 828 cases across its seven files passed; tail files also rerun with file isolation |
| Affected static checks after upload deadline guard | 4 passed: async blockers, module isolation, import purity, diff hygiene |
| Pinned Black | All 11 changed Python files passed |

The first `make preflight` invocation exited with failure; its failing block was
lost in truncated tool output, so that invocation is **not** claimed green.
Validation was partitioned to retain complete diagnostic output: the initial
speaker/policy guards passed, the Firestore guard's seven files passed across
isolated reruns, and all remaining 35 manifest checks passed together. The shared
`origin/main` moved during the original run; reruns pinned the recorded base.
No cause is attributed to that ref movement. No current selected guard failure
was observed. After the final upload-only change (no import/closure changes), the
full focused suite, isolated fast resource suite and affected static checks were
rerun. The runtime image source-closure check passed in the 35-check run.

Final verification completed at 2026-11-05T06:19:01.021372+00:00.
