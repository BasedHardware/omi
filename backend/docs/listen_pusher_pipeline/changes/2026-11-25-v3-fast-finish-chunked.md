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
  builder and Home still fit the 60 s target. The clock starts when admission's hook runs
  (`_manual_finish_admitted`), not at the Finish tap: the time from the tap to admission (upload, seal,
  admission) is outside it, and outside `omi_conversations_v3_fast_finish_wall_seconds`.
  - Slot wait, the Firestore reads before chunking (row refresh, funding, privacy), audio reads, the
    language probe, chunk queue wait and provider requests all count, and so does one retry. The pass
    checks the deadline after each Firestore call and before every retained-audio reference it reads.
  - Each reference's storage metadata and download timeouts are capped to what is left
    (`ArtifactReadBudget`); the serial kill-switch path keeps its 30 s and 60 s.
  - Under `verification_stt_deadline` a request's connect, pool, write and read timeouts share what is
    left (`budget_timeout`) instead of each taking all of it. That context also keeps the provider's own
    retry and Soniox credit failover off for these requests; batch keeps both. The vendor language
    probe's 8 s timeout and the self-hosted gate's 6 s are capped the same way.
  - Past the deadline the pass cancels queued chunks, waits at most `STOP_GRACE_SECONDS` (2 s) more for
    running ones, writes nothing, releases its slot and yields to batch as `deadline`. A request still
    running then ends on its own timeouts, and its result is dropped.
  - A pass that stops early (`provider_error`, `privacy_blocked`, `audio_error`) sends no further request
    or retry, cancels queued chunks and releases its slot as soon as the requests already in flight end.
- **Short and long.** Long means over 20 minutes of audio, never merely many chunks. A six-minute Finish
  split into six units, or one 19.9-minute unit of five chunks, is short.
  - A short pass keeps four chunks in flight (one round up to about 19.8 minutes, two above).
  - A long pass keeps three in flight and is capped at nine chunks (three rounds, about 44.6 minutes).
  - A longer recording returns `too_long` before any spend, because it cannot meet the deadline. A
    2-hour recording is 25 chunks, about nine rounds of three, so it is refused up front.
- **Fairness.**
  - Short and serial passes share two pass slots. A long pass takes its own single slot.
  - Length, canary and cap refusals are counted before any slot is taken, so they never hold a slot or
    read as `busy`.
  - A short Finish waits up to 10 s, inside its deadline, for a slot instead of answering `busy` at once.
  - On the six-worker `fast_finish_chunk` pool, a long pass's three in flight always leave three workers
    for short Finishes.
  - Memory per process is at most 11 chunk buffers (about 106 MB), plus one per pool worker for a request
    a stopped pass left running, plus one decoded pack per pass.
- **Privacy at dispatch.** Privacy is asked before any audio is read, as before, and again inside every
  chunk job just before its provider request (and before its retry). It is also asked right before the
  language probe posts audio to the vendor or the self-hosted classifier. A refusal stops the pass.
  Cancellation stops queued chunks; a request already dispatched may finish, but its result is never
  written. The write is still fenced inside its transaction.
- **Retry and language.** A chunk that fails is sent once more if at least 10 s of the deadline is left.
  The language is resolved once per pass, on the first chunk's audio (`pre_recorded.prerecorded_bytes_route`),
  and every chunk reuses that provider selection. The deadline context and its timeouts live in the leaf
  module `utils/stt/prerecorded_deadline.py`, which the provider, the vendor probe and the gate import.
- **Stitching.** At a fixed cut the earlier chunk owns lines that start before the overlap's middle.
  Every later line that starts before the earlier chunk's last line ended is compared against it.
  - Words, which have their own timing, go by time.
  - Utterances (Parakeet and Modulate return utterances lasting seconds) go by text. Where the head of
    the later text repeats the end of the earlier text, allowing a clipped word on either side, the
    repeat and the clipped fragments are dropped. Otherwise each such line loses the share of its tokens
    that falls before the earlier chunk's last end.
  - Parakeet's text-only fallback, stamped `[0, 0]`, spans its whole chunk instead of being dropped.
- **Multi-unit recordings.** These were already written in one pass, with the cut stored only after the
  whole transcript was written. They were deferred when that pass was skipped or did not write. Their
  units now go out concurrently too, and the cut still waits for the write.

## The long-recording canary

Recordings over 20 minutes are the spend this change adds. They take the chunked path only for
`CONVERSATIONS_V3_FAST_FINISH_LONG_PERCENT` of owners (default 25, salted uid bucket
`v3-fast-finish-long`; outside it, `long_canary`). They are also limited to
`CONVERSATIONS_V3_FAST_FINISH_LONG_DAILY_SECONDS` of their audio per process per UTC day (default 7200;
past it, `long_cap`). The cap counts the audio actually sent: chunk overlaps, retries and the vendor
language probe included, and chunks never sent refunded. It is an in-memory counter for the life of the
process: each new or restarted instance starts the day at 0, so the fleet's daily total is not this value
times a fixed instance count when instances scale or restart. Finishes up to 20 minutes are not gated.

## Metrics

New metrics, all with no labels unless noted:
- `omi_conversations_v3_fast_finish_chunks`
- `omi_conversations_v3_fast_finish_chunk_seconds`
- `omi_conversations_v3_fast_finish_chunk_queue_seconds`
- `omi_conversations_v3_fast_finish_wall_seconds` (every written pass, from admission)
- `omi_conversations_v3_fast_finish_audio_seconds_total{path=short|long}` (provider audio, retries and the
  vendor language probe clip included: the same audio the daily cap charges)

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
