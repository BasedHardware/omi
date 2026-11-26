# Fast finish: long and multi-unit recordings in concurrent chunks

SCA-4434, Lane A. Goal: 95% of deliberate v3 Finishes show a first Home card within 60 s.

Baseline (prod, 12 h, about 96 Finishes reaching the server): 55 got a fast card, about 95% of
those within 60 s. Misses: 16 `too_long` (over the 20-minute cap), 7 `multi_unit_deferred`
(several units whose pass did not write), 2 errors. Provider stage p50/p90/p95 about 15/34/46 s,
from one serial provider request per unit.

## What changed

`CONVERSATIONS_V3_FAST_FINISH_CHUNKED` (ops kill, default `on`) changes how the fast first
transcript (`utils/conversations/v3/fast_finish.py`) calls the provider:

- Every unit is split into chunks of at most five minutes. A cut is the middle of a retained-audio
  silence of at least 1 s near the even chunk length; with none, the cut is at the even length and
  the next chunk starts 3 s earlier. The rest of the unit is shared evenly, so there are no slivers.
- Chunks go to the prerecorded provider concurrently: at most four in flight per pass, at most six
  per process on the new `fast_finish_chunk` pool. `_FAST_FINISH_SLOTS` still bounds whole passes
  (two per process). The pass coordinates from its storage thread and the chunk requests are
  leaves on their own pool, so neither pool waits on itself.
- Words are placed on the unit clock and each is kept once, by the chunk that owns its midpoint.
  Lines are formed per chunk and stitched in order; each unit keeps its padded outer edges.
- The recording bound rises from 20 minutes to two hours (still at most eight units). Memory per
  pass stays explicit: at most four five-minute chunk buffers (38 MB, what the 20-minute cap
  allowed) plus one decoded source pack, independent of recording length.
- Multi-unit recordings were already written in one pass with the cut stored only after the whole
  transcript; they were deferred when that pass was skipped or did not write (most often over the
  cap). Their units now go out concurrently too, and the cut still waits for the write.

Every existing check stays: consent and funding for the whole recording, the privacy answer before
any audio is read and again before each round of chunk requests, the in-transaction privacy fence,
eligibility before the provider and before the write (`superseded`), one pass per recording
(`already_started`), protection level, custody of the canonical transcript. One failed chunk, an
audio error or a refusal stops the pass: queued chunks are cancelled, running ones drained, nothing
is written or cut, and the admitted batch job delivers as before.

## Metrics

New, unlabelled histograms: `omi_conversations_v3_fast_finish_chunks` (chunks per chunked pass),
`omi_conversations_v3_fast_finish_chunk_seconds` (one chunk request) and
`omi_conversations_v3_fast_finish_wall_seconds` (a written pass, start to write and cut). In the
chunked path `omi_conversations_v3_fast_finish_seconds{stage="provider"}` is the whole concurrent span,
the interleaved audio reads included; `stage="audio"` is the read time within it. All three are kept
by `cloud_run_gmp_sync.yaml`.

## Rollout and rollback

On by default and declared `on` for prod `backend` and `backend-integration` (the projection pump
inherits integration's value). Rollback: set `CONVERSATIONS_V3_FAST_FINISH_CHUNKED=off` on
`backend-integration`; later passes use one serial request per unit and the 20-minute cap. Provisional
segments already written are replaced by the batch record projection as usual.

Known limit: diarization labels are per chunk, so a provisional `SPEAKER_00` in one chunk need not be
the same person in the next. Provisional rows claim no speaker number and the canonical transcript
replaces them.

[Pipeline contract](../../listen_pusher_pipeline.mdx)
