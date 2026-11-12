# Speaker final-pass artifact lifecycle and read diagnostics — 2026-11-05

Scope: local source inspection and hermetic synthetic replays on `lane/spkfix`,
starting at `95c330db3fef79386ccf790bc1952bbefaadc8dc`. No production access,
credentials, account data, deployment or publication. The owner's real-data
gate remains the parent's responsibility; local tests do not qualify that gate.

## The no-URI artifact rows are cleaned receipts

The supplied field sets match the existing retention lifecycle:

- `utils/batch_pipeline/retention.py::register_batch_artifact` always creates
  artifacts with `uri`, owner identity/key, unit ID, privacy generation and
  conversation membership. Registration precedes upload.
- `expire_completed_segment` arms object `cleanup_after` after successful
  projection completion. Results get 24 hours. Native-record audio manifests
  get 45 days; ordinary audio gets 24 hours. Reads never extend retention.
- `cleanup_completed_artifacts` calls `delete_uri` **before** updating the
  row to remove `uri`, `cleanup_after` and any cleanup hold, then sets
  `expires_at` to 45 days later. Erasure/shadow rows are instead deleted.
- This cleanup writer exists unchanged at serving release `7dd7bc1`, verified
  with local Git source. No second live-artifact writer with that no-URI schema
  was found in registration, intake, staging, missing-artifact or purge paths.

A future `expires_at` is the metadata receipt TTL. It does not prove usable
audio/results. The deterministic artifact key binds the old base URI, but cannot
reverse cleanup or authorize reading a retained GCS generation after cleanup.
`load_reference` now reports `skipped_expired` with the bounded reason
`artifact_cleaned`, after owner/unit/kind/generation/erasure checks. A missing URI
without the cleanup marker remains `uri_mismatch`. Live rows still require their
registered URI, privacy snapshot and GCS `if_generation_match`.

Both exact supplied field sets are literal test fixtures for audio and results,
including mixed live/cleaned rows. No account documents were inspected locally.

## Enrichment and retry timing

`Projector.finish_part` durably marks enrichment through
`database/batch_pipeline_projection.py::mark_enrichment`, enqueuing the
conversation's obligation before completion. `complete_content` completes and
publishes the content, then calls `expire_completed_segment` for each sibling.
Thus the 24-hour result clock starts after enrichment is queued, not after
enrichment actually runs. A missing audio cleanup field does not extend the
independent result deadline, or prove the results object is available.

The dedicated speaker-only outbox admits at most four claims. Its scheduled
delays for ordinary on-time claims are 30/60/120/240 seconds with 0.5–1.5 jitter: their maximum sum is
**675 seconds (11m15s)**. That is a scheduled-backoff bound, not an end-to-end
delivery guarantee. Work duration, queue backlog/outages and expired 900-second
leases and repair wakes can extend elapsed time; there is no finite wall-clock delivery bound.
A retry can therefore arrive after cleanup. It keeps terminal `skipped_expired`
and closes once; no retention extension or full-enrichment replay is introduced.
Tests cover a day-late delivery, duplicate wake, and the maximum jitter sum.

## Precision refusals

`final_pass_batch._assemble` positions decoded PCM using absolute unit capture
times at 16 kHz. If populated intervals overlap, their PCM must match byte for
byte. Different overlapping captures, or sparse retained manifests materialized
with padded holes, can fail this test. The current API has PCM, not verified
occupied-source geometry, so accepting a differing overlap would guess voice
evidence. This remains a legitimate precision refusal for the current adapter.
Tests replay identical, differing and padded-hole overlaps through the lab;
identical audio succeeds, incompatible audio leaves all labels untouched.

`projection_segment_missing` means the stored positive-duration ID is absent
from the freshly reconstructed unit/part grouping. IDs are UUIDs derived from
unit/part plus segment index. Old grouping/point-word behavior or subsequent
transcript edits can change those IDs; the scope alone proves no correspondence.
Existing literal multi-unit tests preserve an unmatched segment and update only
the other proven segments with terminal `partial_coverage`, without learning.
If no segment has evidence, the adapter refuses rather than guessing.

Without the specific owner artifacts, this source inspection cannot identify
which of these shapes caused the two reported owner cases. No blanket clock
relaxation, text matching or offset-based relabeling is justified by that report.

## Read diagnostics

Every replay result now includes `read_wall_seconds`, `read_bytes`,
`read_reserved_bytes`, and `read_objects`, even if metadata lookup or an artifact
read fails before a unit stream is returned. Time includes initial reference
snapshots, artifact retrieval/decoding/projection, and reference revalidation;
it excludes assembly, model transport/inference and application. CLI rows also
include `conversation_load_wall_seconds` for conversation/manual-receipt loading.

Received bytes count completed GCS response bodies before post-download
deadline/privacy checks: encrypted staging objects, retained manifests, and
generation-pinned retained sources. Partial transfers that fail inside the SDK
cannot be measured; reservations show the attempted payload size. Firestore
payloads and protocol overhead are excluded. The 180-second initial read budget,
10-second reference RPC ceiling and 600-second overall budget are unchanged.
References remain serial but bounded by the pre-read 480-candidate cap; no new
concurrency or production deadline change is justified by the laptop observation.

Source inspection found an additional timeout footgun: `ArtifactStore._read`
used ordinary Firestore transactions for privacy authorization before and after
blob retrieval, and after retained-source materialization. The artifact factory
now supplies a budgeted read-authorization callback using the existing read-only
snapshot helper and budgeted privacy reads (remaining budget, 10-second RPC
ceiling, no SDK retries). Unbudgeted writers retain their ordinary transaction
path. Real SDK/fake GAPIC tests prove pre-download and post-download stalls stop
at the remaining deadline, without a commit; nested-manifest tests cover its
final check. This fixes the in-flight-call gap without extending any deadline.

## Validation

- Final focused run: **749 passed** across 21 files, including the real
  multi-unit/mixed-authority `reproduce()` path, exact artifact row shapes,
  privacy/generation fences, late duplicate wake, overlap refusal, read timing,
  actual response-byte accounting, real SDK authorization/reference deadlines,
  retention/cleanup regressions and the two-hour/480-unit memory stress test.
- Repository file-isolated fast runner: **155 passed**, one slow stress case
  deselected, with `BACKEND_FAST_UNIT_FAIL_SECONDS=1.00` and one worker.
  Files: lifecycle, resources, boundary geometry, artifacts and owner-lab fence.
- Black: all 12 changed Python files formatted with the repository wrapper.
- Selected repository checks: **38 passed** against the recorded branch base
  `6cf56c7e41925869b1cd5a61cfc73b3628ec6c00`, using local draft metadata.
  This consists of 22 passed checks in the main run and the remaining 16 in a
  follow-up after supplying the earlier retry-wiring line-count declaration.
  Runtime source closure passed for all 19 registered images. No source changed
  between these final runs; only this validation text was completed afterward.

The first expanded test run found three stale boundary assertions from before
the existing float-rounding fix. Those tests now require acceptance at 100 ms
plus one PCM sample and rejection two samples beyond 100 ms, for both incoming
projection and multipart reconstruction. No production tolerance changed.

`make preflight` against the newer shared `origin/main` did **not** pass:
synthetic merge at `585545cb70b2830f810ea573bdacf2fa5d5da599` conflicts in
`backend/deploy/cloud_run_gmp_sync.yaml`. That first run also detected ongoing
local edits. A pinned-base rerun was interrupted to fix the subsequently found
artifact-authorization timeout gap. Final checks above used stable final code
and the recorded branch base. This commit does not claim current-main merge
readiness, an owner-data gate pass, deployment or publication; the current-main
GMP keep-list conflict remains for the parent's next integration.

The parent draft needs the existing retry-wiring growth declarations (the
ratchet compares growth even if target-branch endpoints move):

```text
Line-Count-Exception: backend/routers/sync.py | 3793 -> 3804 | Dispatch the speaker-only wake kind through the existing authenticated task edge without full-enrichment replay.
Line-Count-Exception: backend/utils/conversations/speaker_resolution.py | 1565 -> 1567 | Pass the dedicated final-pass retry obligation from the processing boundary to speaker resolution.
```
