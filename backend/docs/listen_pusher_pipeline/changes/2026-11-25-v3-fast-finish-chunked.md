# Fast finish: long and multi-unit recordings in concurrent chunks

SCA-4434, Lane A. Goal: 95% of deliberate v3 Finishes show a first Home card within 60 s.

Baseline (prod, 12 h, about 96 Finishes reaching the server): 55 got a fast card, about 95% of
those within 60 s. Misses: 16 `too_long` (over the 20-minute cap), 7 `multi_unit_deferred`
(several units whose pass did not write), 2 errors. Provider stage p50/p90/p95 about 15/34/46 s,
from one serial provider request per unit.

## What changed

`CONVERSATIONS_V3_FAST_FINISH_CHUNKED` (ops kill, default `on`) changes how the fast first
transcript (`utils/conversations/v3/fast_finish.py`) calls the provider.

- **Split.** Each unit becomes chunks of at most five minutes. A cut goes in the middle of a retained-audio
  silence of at least 1 s near the even chunk length. With none, it goes at the even length and the next
  chunk starts 3 s earlier. The rest of the unit is shared evenly, so no chunk is a sliver.
- **One end-to-end deadline.** 45 s from record admission (`PASS_DEADLINE_SECONDS`), so the write, the
  builder and Home still fit the 60 s target. Slot wait, audio reads, chunk queue wait and provider
  requests all count, and so does one retry. Provider HTTP timeouts are capped to the time left
  (`verification_stt_deadline`, which also keeps the provider's own retry and Soniox credit failover off
  for these requests; batch keeps both). Past the deadline the pass cancels queued chunks, waits for
  running ones (their timeouts end at the deadline), writes nothing and yields to batch as `deadline`.
- **Rounds and caps.** A short pass, at most four chunks (about 19.8 minutes), is one round with every
  chunk in flight. A long pass keeps three in flight and is capped at nine chunks (three rounds, about
  44.6 minutes). A longer recording returns `too_long` before any spend, because it cannot meet the
  deadline. A 2-hour recording is 25 chunks, about nine rounds of three, so it is refused up front.
- **Fairness.**
  - Short and serial passes share two pass slots. A long pass takes its own single slot, so long passes
    never hold a short Finish's slot.
  - A short Finish waits up to 10 s (inside its deadline) for a slot instead of answering `busy` at once.
  - On the six-worker `fast_finish_chunk` pool, a long pass's three in flight always leave three workers
    for short Finishes.
  - Memory per process is at most 11 chunk buffers (about 106 MB) plus one decoded pack per pass.
- **Privacy at dispatch.** Privacy is asked before any audio is read, as before, and again inside every
  chunk job just before its provider request (and before its retry). A chunk that waited in the shared
  pool's queue is therefore asked when it actually starts. A refusal stops the pass. Cancellation stops
  queued chunks; a request already dispatched may finish, but its result is never written. The write is
  still fenced inside its transaction.
- **Retry and language.** A chunk that fails is sent once more if at least 10 s of the deadline is left.
  The language is resolved once per pass, on the first chunk's audio (`prerecorded_bytes_route`), and
  every chunk reuses that provider selection.
- **Stitching.** Parakeet and Modulate return utterances lasting seconds, not words, so ownership is by
  start time.
  - At a fixed cut the earlier chunk owns lines that start before the overlap's middle.
  - A later line that starts in the overlap and ends before that middle was heard whole by the earlier
    chunk, and is dropped.
  - A later line that straddles the middle is trimmed at the seam. Where its head repeats the end of the
    earlier chunk's text (allowing one clipped last token), the repeat is dropped. Otherwise it loses the
    share of its tokens that falls before the earlier chunk's last line ended.
  - Parakeet's text-only fallback, stamped `[0, 0]`, spans its whole chunk instead of being dropped.
- **Multi-unit recordings.** These were already written in one pass, with the cut stored only after the
  whole transcript was written. They were deferred when that pass was skipped or did not write. Their
  units now go out concurrently too, and the cut still waits for the write.

## The long-recording canary

Recordings over 20 minutes are the spend this change adds. They take the chunked path only for
`CONVERSATIONS_V3_FAST_FINISH_LONG_PERCENT` of owners (default 25, salted uid bucket
`v3-fast-finish-long`; outside it, `long_canary`). They are also limited to
`CONVERSATIONS_V3_FAST_FINISH_LONG_DAILY_SECONDS` of their audio per process per UTC day (default 7200;
past it, `long_cap`). Finishes up to 20 minutes are not gated.

## Metrics

New metrics, all with no labels unless noted:
- `omi_conversations_v3_fast_finish_chunks`
- `omi_conversations_v3_fast_finish_chunk_seconds`
- `omi_conversations_v3_fast_finish_chunk_queue_seconds`
- `omi_conversations_v3_fast_finish_wall_seconds` (every written pass, from admission)
- `omi_conversations_v3_fast_finish_audio_seconds_total{path=short|long}` (provider audio, retries included)

New outcomes: `deadline`, `long_canary`, `long_cap`. In the chunked path,
`omi_conversations_v3_fast_finish_seconds{stage="provider"}` is the whole concurrent span. All of these
are kept by `cloud_run_gmp_sync.yaml`.

## Rollout and rollback

`CONVERSATIONS_V3_FAST_FINISH_CHUNKED` is declared `on` for prod `backend` and `backend-integration`.
`CONVERSATIONS_V3_FAST_FINISH_LONG_PERCENT=25` and `CONVERSATIONS_V3_FAST_FINISH_LONG_DAILY_SECONDS=7200`
are declared for `backend-integration`; the projection pump inherits integration's values.

Rollback options:
- `CONVERSATIONS_V3_FAST_FINISH_LONG_PERCENT=0` stops long passes only.
- `CONVERSATIONS_V3_FAST_FINISH_CHUNKED=off` restores one serial request per unit and the 20-minute cap.

Provisional segments already written are replaced by the batch record projection as usual.

Known limit: diarization labels are per chunk, so the same provisional `SPEAKER_00` in two chunks may be
two different people. Provisional rows claim no speaker number, and the canonical transcript replaces them.

[Pipeline contract](../../listen_pusher_pipeline.mdx)
