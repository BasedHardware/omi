# Speaker final-pass transient custody — 2026-11-05

Local synthetic validation only; no production access, account data or GCP tier.
The owner-data gate remains unverified by this work.

Fix before rebase: `42ad95e32b061ad88b9e7bda554bc004820d4d41`.
Fetched/rebased target: `feffb957c54a1cd6f62296e31b364036f5207940`.
Rebased fix: `5a590b0f0e89304632972d9c9f8a30d1e8be7897`.

## Classification and custody

| Failure | Result |
| --- | --- |
| ServiceUnavailable, DeadlineExceeded, Aborted, InternalServerError | `deferred_transient` |
| TooManyRequests / ResourceExhausted | `deferred_transient` |
| Connection resets, connection errors, native/requests/httpx read timeouts | `deferred_transient` |
| Elapsed artifact read deadline | `deferred_transient` |
| Artifact object/byte caps | Terminal `failed_read_budget` |
| Unit count or admitted audio/timeline limits | Terminal `failed_too_long` |
| Permanent data/authority failures | Existing terminal reference/artifact outcome; permanent reload errors use `failed_dependency` |
| Four unsuccessful outbox claims | Exactly one terminal `skipped_retry_exhausted` |

The classifier uses types, errno values and explicit causes. It never searches
provider error messages; only the code-owned ArtifactReadLimit deadline marker
distinguishes elapsed time from structural caps. SSL configuration failures do
not become retryable connection errors. Structural caps override wrapped causes.

Firestore deadline conversion retains the original cause. Unit reconstruction
cannot turn an explicit transient cause into terminal incomplete coverage, and
the shared diarizer adapter propagates transients to the batch boundary. Legacy
lanes keep their existing fallback policy. Required read failures abort initial
reference lookup immediately; no new SDK retry loop or slot wait is introduced.

Both initial passes and retry deliveries use the existing speaker-only durable
outbox. There are at most four outbox processing claims after the initial pass;
attempts survive lease repair, and duplicate wakes cannot reopen closed rows.
Deferrals are outside terminal counts. Settlement counts a final result once,
including exhaustion. Retries reload authority and persist only identity through
the existing revision fence; they cannot replay notes, memory or integrations.
The lab captures `requeue_calls` without Firestore/Cloud Tasks writes.

## Rebase and verification

Git fetch completed before rebasing onto the pinned target above. Two GMP
keep-list conflicts occurred while replaying earlier commits. Their alternatives
were unioned at the shared `omi_` prefix and outer branches, retaining both sides;
all other YAML fields follow the new main. The final GMP diff is one line.
The range-diff shows the transient fix unchanged by rebase; resource-fix changes
are context adjustments around main's newer store contention accounting.

Through the workspace `omi-heavy` gate, from `backend/`:

- **853 passed before rebase; 853 passed after rebase**, across 22 focused files.
  These include the real multi-unit/mixed-authority `reproduce()` path, maximum
  memory stress, retention, privacy, identity promotion and SDK deadline suites.
- **182 fast-lane tests passed**, one slow stress test deselected, through
  `test.sh` with one worker and the 1-second CPU failure guard. Selected files:
  transient, retry, lifecycle, resources and owner-lab fence.
- The transient suite tests every requested class at reference, result, audio,
  revalidation and batch diarizer stages; each class also reaches the four-claim
  cap once, and transient reloads defer. Negative cases prove permanent failures
  and object/byte/unit caps remain terminal. Recovery performs only speaker work.
- Black formatted all 11 changed Python files before the fix commit; its hook
  confirmed they were unchanged. No push, amend or PR was performed.

The full focused command is the previous lifecycle record's suites plus
`tests/unit/test_batch_final_pass_transient.py`. The new classification tests
are literal synthetic faults over production-shaped unit/projection fixtures;
they make no network calls.

Repository verification after rebase: **`make preflight` passed all 40 selected
checks** against `origin/main` at the fetched target, including runtime image
source closure. The local draft metadata supplies the existing retry-wiring
line-count growth declarations recorded in the lifecycle note; no PR was opened.
An independent read-only check confirmed the final GMP regex contains every
alternative from fetched main and the pre-rebase branch, plus matches for both
final-pass counters and the privacy/caller read counters. The earlier GMP
integration conflict recorded in the lifecycle note is resolved by this rebase.

The focused command, run before and after rebase through `omi-heavy`:

```sh
.venv/bin/python -m pytest \
  tests/unit/test_batch_final_pass.py \
  tests/unit/test_batch_final_pass_repro.py \
  tests/unit/test_batch_final_pass_lifecycle.py \
  tests/unit/test_batch_final_pass_resources.py \
  tests/unit/test_batch_final_pass_retry.py \
  tests/unit/test_batch_final_pass_transient.py \
  tests/unit/test_owner_lab_final_pass_repro.py \
  tests/unit/test_final_pass_assignment.py \
  tests/unit/test_final_pass_vad_compaction.py \
  tests/unit/test_sync_final_pass_budget.py \
  tests/unit/test_final_pass_promotion.py \
  tests/unit/test_final_pass_rehome.py \
  tests/unit/test_batch_pipeline_privacy.py \
  tests/unit/test_batch_privacy_conversation_fence.py \
  tests/unit/test_fsr_wq12_batch_privacy.py \
  tests/unit/test_bpp_generation_memo.py \
  tests/unit/test_batch_pipeline_artifacts.py \
  tests/unit/test_batch_cleanup_custody.py \
  tests/unit/test_batch_pipeline_quarantine_recovery.py \
  tests/unit/test_batch_pipeline_speech_redrive_retention.py \
  tests/unit/test_batch_pipeline_leaf_timings.py \
  tests/unit/test_batch_pipeline_boundary_geometry.py -q
```
