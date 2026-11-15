# Silent batch units retain audio while skipping redundant projection reads

SCA-1757 / [PR #25140](https://github.com/BasedHardware/omi/pull/25140).
See the [batch silence runbook](../../runbooks/batch-silence-read-skip.md)
for the kept/skipped read inventory, reprocessing procedure, measurement queries
and rollout gates; the existing [pipeline contract](../../listen_pusher_pipeline.mdx)
continues to govern custody, erasure and completion.

Ordinary units classified as silence persist the existing zero-output ready receipt
inside the fenced assignment transaction. Completion verifies all siblings before
using zero-speech accounting. Both synchronous completion and async follow-up pass
the persisted outcome; async follow-up uses the validated transaction snapshot,
not the initial discovery hint. Mixed uploads, partial/prior charges and
record-origin/native-record paths keep ordinary accounting. Allowance settlement,
transcription observers, privacy/identity fences and retention acknowledgements stay.
Audio retention, erasure and T2 alarm thresholds are unchanged. False silence can
be reprocessed from retained audio under the existing privacy and retention rules.

`BATCH_PIPELINE_SILENCE_READ_SKIP_ENABLED` defaults on; `false`, `off` or `0`
restores full silent-unit processing. Deployment must explicitly pin it false
outside the approved small-percent/50/100 canary. This PR performs no deployment
or production flag change.

Validation for the async correction uses file-isolated Python 3.11 pytest runs
from `backend/` (`.venv/bin/python -m pytest -p no:langsmith_plugin -q <file>`):

- `tests/unit/test_batch_pipeline_projection_followup.py`: the real completion
  selector receives validated silence, success or missing outcomes despite a
  conflicting fetch hint; only enabled silence bypasses accounting preparation.
  Existing retry, privacy, page coalescing and cancellation coverage remains.
- `tests/unit/test_batch_pipeline_silence_reads.py`: strict transactional receipt,
  privacy, custody, replay, zero-usage observer and local read-budget coverage.
- `tests/unit/test_batch_pipeline_owner_chain_projection.py`,
  `tests/unit/test_batch_pipeline_projection.py` and
  `tests/unit/test_batch_pipeline_followup_desync.py`: assignment and recovery.

Final local results: 48 follow-up, 24 silence, 39 owner-chain, 69 projection
and 67 desynchronization cases passed (247 total).

The preceding head's CI [shard 6 log](https://github.com/BasedHardware/omi/actions/runs/43627657551/job/132547052120)
shows the vendor-outage test assertions passing, followed by a 1.02s call-CPU
measurement exceeding the unchanged 1.00s guard. A local file-isolated rerun of
`tests/unit/test_pipeline_sim_vendor_drills.py` with
`BACKEND_FAST_UNIT_FAIL_SECONDS=1.00` passed all ten cases. This establishes a
timing-only failure on that run, not a passing CI result for the new head.
No timing budget or allowlist is changed.

The runbook's 89 to 40 local document-lookup result is not a production billing
claim. Serving-revision proof, matched-hour silent-only billed-read reduction,
T2/retention/erasure/speech-latency guards and D+2 settled billing remain release
and verification requirements.
