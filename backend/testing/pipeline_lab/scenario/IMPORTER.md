# Scenario importer (slice 2 design, not built)

Goal: turn one production capture -> Finish -> Home incident into a scenario file, so an engineer or
agent can reproduce it locally with `scenario run` and test a fix in minutes. The importer reads the
incident's **shape**: spans, stamps and counts. It never exports speech, titles, names or ids.

## Who may run it

- Only for an incident whose owner has approved it on the tracking issue. The approval names the window
  and the approver. The uid is read from a 0600 file by path, as `overlay from-runtime-env --owner-uid-file`
  does. It never appears in argv, logs or the output.
- It runs under a read-only GCP agent tier and reuses `v3/prod_export.py`'s owner guard, injected by path.
  It makes no writes anywhere in production.
- Firestore cost: it reads the recordings and v3 conversations whose `finished_at` falls in the window,
  plus the finalization jobs and batch-projection receipts those recordings name. That is under 100
  documents per incident, read once. Every run prints `rows scanned`. A window wider than 2 hours is refused.

## What it reads (field masks, clear fields only)

| Scenario field | Production source |
|---|---|
| origins | `client_device_id` and `source`, mapped to `O1`, `O2`, ... in order of first appearance |
| recording session | `external_data.recording_session_id`, mapped to `S1`, `S2`, ... |
| `audio` | `started_at` / `finished_at`, or `server_batch_audio_start` / `_end` where present |
| `sealed_at` | `record_sealed_at` |
| `transcript_at` | the batch projection's completion stamp for the recording, else `v3_speech_landed_at` |
| `finish.at`, branch | the `client_finalize` finalization job's `created_at`, or `v3_finish_no_pointer_*` on the source |
| `provisional_latency` | the first `v3_speech_landed_at` of the recording the Finish cut, minus `finish.at` |
| `sync[]` | sync-created recordings in the window: audio span and creation instant (arrival) |
| speech | per transcript segment: `start`, `end`, word count, `is_user` and a speaker index |

Speech timing needs the segments, which are stored encrypted. The importer decodes them in memory and
keeps only `(start, end, words, is_user, speaker index)` per segment. The text is dropped before anything
is written. Because this still decodes content in memory, it needs the owner's approval each time.

## What it writes

A scenario JSON under the lab root (`$OMI_PIPELINE_LAB_ROOT/scenarios/<issue>.json`, mode 0600, never in
git), containing:

- times as seconds from `t0`, with `t0` set to the synthetic date `2026-03-14T09:00:00Z`, so the real date
  does not travel;
- labels `R1..Rn`, `O1..`, `S1..` and no production identifiers;
- speech as `fill`-style placeholder lines with the measured word count and timing per segment;
- an `observed` block with production's result per v3 conversation: member labels, word count, visible,
  hidden reason and manual end. `scenario run` prints it next to the replay's result, so the first run
  shows whether the lab reproduced production.

`expect` starts empty, and a person writes it: what *should* have happened. A reviewer who confirms the
file holds only synthetic labels and placeholder text may copy it into `scenario/scenarios/` as a
regression scenario, with `expected_failure` naming the bug until its fix lands.

## Command

```bash
python -m testing.pipeline_lab scenario import --owner-uid-file F --window START,END --issue SCA-NNNN --out FILE
```

## Open questions for the owner

- Whether the projection completion stamp is kept long enough (receipt TTL) to recover `transcript_at` for
  incidents older than a few days. Otherwise `v3_speech_landed_at` is the fallback, and it records only
  the first landing.
- Whether one decision should be stored for incident work in general (one approval covers decoding segment
  timing in memory) or the importer asks each time. This design asks each time.
