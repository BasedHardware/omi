# 0007. Finish unprovable recordings explicitly partial

- Status: Accepted
- Date: 2026-10-31
- Deciders: David (2026-10-31 ruling); rollout lead (design acceptance bus 7e2a57)
- Owner: batch transcription rollout lead
- Review by: 2026-11-07 or the next ramp expansion, whichever comes first

## Context

The supplied 2026-10-31 census found 107 unsealed recordings: 63 tail-lagging
proof refusals, 21 size-budget refusals and 14 live-producer holds, plus nine
other outcomes. These are historical aggregates, not current release evidence.
Waiting for complete-tail proof can withhold stored speech indefinitely.

## Decision

After 30 minutes from finalization, repair may finish an unprovable recording
with a separate `record_audio_partial` receipt. Complete seals keep their proof.
Partial never means complete and never deletes audio. Live or unidentified
producer tokens wait for their own drain or the existing fresh producer-death
proof; age never releases them. Privacy, deletion, tombstone and BYOK fences
remain authoritative. The default-on `RECORD_AUDIO_PARTIAL_ENABLED=false`
kill switch stops new partial finishes and admissions.

Late retained audio schedules a serial continuation. Its immutable encrypted
plan recognizes only stored sample ranges absent from prior durable coverage.
Existing transcript text and user edits survive. Each worker binding has at
most 128 siblings; partial units have at most 256 references and 300 seconds.
The implementation bounds a source snapshot and coverage at 8,192 entries;
larger snapshots remain reported debt, never truncated input or complete seals.
Completed coordinators poll inventory hourly and retire after 24 hours without
an inventory change, leaving audio and partial status intact. Repair can reopen
one after a new producer upload revision; an unsignalled storage-only arrival
after retirement needs operator recovery. Partial projection fills only empty
text spans, even on the first pass, and refuses ambiguous overlap.

## Consequences

Clients receive the available transcript plus optional partial metadata through
the existing API, without new UI. Reports count partial/unprovable separately;
the seal gate treats explicit partial finish as finished while retaining its
pending/applied split. No hard-3 threshold changes. The lead applies the paired
collector patch with the release. Available audio remains recoverable during
worker, privacy or capacity failures; local tests do not establish live latency.

## Implemented in

`config/record_partial.py`, `database/record_partial.py`,
`utils/batch_pipeline/record_partial.py`, `record_partial_audio.py`,
`tests/unit/test_record_partial.py`; operator details in
`docs/listen_pusher_pipeline.mdx`.
