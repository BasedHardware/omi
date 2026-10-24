# Durable live audio custody

`AUDIO_DURABLE_OUTBOX_ENABLED` is on by default. Only the literal `false`
selects emergency legacy behavior; empty or malformed values retain custody.
The rollout lead owns merge, coordinated listen/pusher rollout, alert activation
and any emergency rollback. This change does not authorize a production write.

This switch is the sole custody kill switch. `AUDIO_ARCHIVE_LIVE_ENABLED`
controls legacy raw admission only after the outbox switch is set to `false`;
it cannot disable the default-on custody barrier. `AUDIO_ARCHIVE_READ_ENABLED`
continues to control raw playback reads independently.

For consented capture, listen retains original packs through capacity pressure,
upload errors and cancellation. Four commits can run at once; the fifth waits
before removing its active pack. Transcript persistence and pusher audio flush
both wait for the raw archive barrier. A transport send or transcript receipt
alone is never an audio archive receipt. Cloud-storage consent still applies;
users with storage disabled do not acquire a new archive obligation.

Pusher commits every incoming PCM run before trimming overlap or adding it to
any derivative buffer. Its queue holds at most 20 generation-pinned receipts.
The producer waits when it fills. Pending conversations hold bounded lists of
references; the 21st conversation flushes an existing projection rather than
evicting PCM. Hydration is serial and bounded by the 20 MiB projection budget.
Projection failures leave remotely archived audio recoverable by receipt;
positioned v2 captures also participate in `raw-live` playback discovery.
Legacy headers estimate arrival time, so their projections keep the previous
continuous, spanless batching. Their immutable originals are marked
`clock_source=arrival_estimate` and recover by receipt; raw playback discovery
does not invent capture positions for them. No projection deletes the original
or manifest.

Media is immutable under `raw-live/<owner>/<conversation>/...`; each receipt
also pins an `audio-outbox/<owner>/...` manifest generation and both plaintext
SHA-256 digests. The manifest records source root/channel/clock, ordered frame
sequence, byte offsets, sample counts, gap positions and a capture-end
checkpoint. The checkpoint means the end of this committed pack, not the end
of an entire device recording. Unavailable device positions stay explicitly
unknown. Silence, undecodable originals and multichannel captures still retain
their bytes; unknown/gapped clocks never certify continuous playback coverage.

Listen emits additive `audio_custody` events only after both objects commit,
when the peer opts in with the WebSocket query `audio_custody=1`.
The event carries the receipt and per-frame source mappings when supplied by
the client. Unknown mappings cannot release a device WAL. Pusher can emit
opcode 203 with the same receipt when the caller opts in with
`audio_custody=1`; legacy peers receive no new opcode. Existing
`capture_committed` remains a transcript receipt. Client adoption of audio-only
WAL release is a separate compatibility/deployment requirement; this server
change cannot certify the retention behavior of already installed legacy apps.

## Recovery and acceptance

After a pod loss, list raw-live objects for the affected owner/conversation and
the corresponding immutable audio-outbox manifests. Fetch the pinned media
generation, decrypt under its owner, verify the plaintext digest, decode, and
verify PCM sample count/digest against the manifest. The raw playback index is
independent of the former pod's in-memory projection queue. A crash between
media and manifest commit issues no receipt; retry preserves the existing
immutable media. Never infer custody from a log, a transcript or readiness.

Release acceptance requires the fault suite (queue >20, 20 MiB budget, pending
overflow, four concurrent commits, failed uploads, cancellation, restart and
reconnect), plus the hermetic listen/pusher harness and an authorized staging
playback canary. Production acceptance additionally requires exact serving
revision identities and a visible new metric/log. Local tests alone do not
prove deployed playback or an installed client's WAL retention.

`omi_audio_custody_would_drop_total{stage}` counts averted loss paths;
`omi_audio_custody_backpressure_total{stage}` counts producer waits;
`omi_audio_custody_failures_total{stage}` distinguishes commit and projection
failures; `omi_audio_custody_commits_total` counts complete immutable receipts.
`omi_audio_custody_last_risk_timestamp_seconds` also exposes a refusal before
the first scrape, when a counter increase has no observed zero baseline.
The source Grafana rule `omi-audio-custody-pressure` alerts immediately on any
would-be drop or failure in five minutes. Provision split/combined alert JSON
through the existing approved monitoring path and verify Telegram delivery.

Small durable writes add storage operations before existing
60-second projections. Measure GCS operation spend and listen latency during
the staging canary; tune batching only while preserving the custody barrier.
PCM custody writes preserve the original bytes without invoking an encoder;
encoding/decoding failure cannot prevent custody of even a one-sample frame.
Do not count savings or assume the rollout's extra cost is zero.

Emergency rollback: set `AUDIO_DURABLE_OUTBOX_ENABLED=false` on both listen and
pusher through a lead-approved train. This restores known lossy legacy caps;
retain all existing outbox objects and source WALs, record the incident ruling
and restore custody as soon as storage is healthy. Re-enable by removing that
override or setting it to `true`.
