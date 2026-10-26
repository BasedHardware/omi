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
before removing its active pack. LISTEN commits at the pack's own 60-second,
conversation/hour/size boundary, 4096-frame cap, or disconnect tail. The relay
path neither awaits uploads nor flushes an active window. Transcript
persistence and live STT delivery continue immediately; coverage ledger writes
and `capture_committed` events wait for the accepted original-audio checkpoint.
Snapshots coalesce per conversation (at most 32 queued conversations); overflow
withholds the optional coverage ACK and leaves the client's WAL retained.
A later window cannot release coverage across an earlier failed commit.
A transport send or transcript receipt
alone is never an audio archive receipt. Cloud-storage consent still applies;
users with storage disabled do not acquire a new archive obligation.
For those users, coverage follows the pre-custody transcript receipt contract:
only a successful durable transcript transaction permits coverage publication
and WAL release. It is never an audio-only receipt or proof of an immutable
audio archive. This preserves bounded client retention without inventing an
archive obligation. With storage consent, an empty archive cannot certify
coverage; its accepted-frame checkpoint must have committed original audio.

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
Windowed custody increases time-to-ACK and client WAL retention from roughly
one relay cycle to pack completion: up to an active 60-second pack plus storage
latency for audio-only receipts (or an earlier boundary). A coalesced coverage
snapshot can include frames from the next pack, so coverage-based WAL release
may wait into the following active window as well. A partial idle window stays unacknowledged until more audio
closes its window or disconnect flushes it. During outages, WAL retention lasts
through successful retry; there is no timed early release. A mid-window pod
loss has issued no audio or coverage custody ACK for that uncommitted window.

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
`omi_audio_custody_failures_total{stage,reason}` distinguishes commit and projection
failures; `reason` is `conflict` (deterministic projection mismatch, never retried),
`transient` (non-deterministic failure that exhausted its bounded requeue passes),
or `other`; `omi_audio_custody_commits_total` counts complete immutable receipts.
`omi_audio_custody_last_risk_timestamp_seconds` also exposes a refusal before
the first scrape, when a counter increase has no observed zero baseline.
The source Grafana rule `omi-audio-custody-pressure` alerts immediately on any
would-be drop or failure in five minutes. Provision split/combined alert JSON
through the existing approved monitoring path and verify Telegram delivery.

Windowed durable writes share the original pack boundaries, so Firestore
fence, tombstone and protection reads occur per committed window rather than
per relay cycle; no safety authority is cached across windows.
Measure GCS operation spend and listen latency during
the staging canary; tune batching only while preserving the custody barrier.
PCM custody writes preserve the original bytes without invoking an encoder;
encoding/decoding failure cannot prevent custody of even a one-sample frame.
Do not count savings or assume the rollout's extra cost is zero.

Emergency rollback: set `AUDIO_DURABLE_OUTBOX_ENABLED=false` on both listen and
pusher through a lead-approved train. This restores known lossy legacy caps;
retain all existing outbox objects and source WALs, record the incident ruling
and restore custody as soon as storage is healthy. Re-enable by removing that
override or setting it to `true`.
