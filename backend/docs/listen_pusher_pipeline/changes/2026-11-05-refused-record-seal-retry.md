# Retry record seals refused by another producer

Pusher now keeps a `producer_pending` seal refusal scheduled through the existing
close retry policy rather than immediately retiring the close. A later attempt
seals only after persisted producer tokens clear. This applies to the
[persisted-owner close barrier](../../listen_pusher_pipeline.mdx#durable-live-and-desktop-record-admission-dark).

The legacy drain retains its three-attempt limit; exhaustion ends only local
scheduling and leaves the durable token/seal debt for repair. Durable drains
retain their existing jittered exponential backoff (at most 60 seconds), bounded
metadata admission/outstanding calls, and process-wide closed-drain capacity.
They keep their existing retry lifetime until settlement, cancellation or process
exit; this change adds no task or loop. It does not expire another producer's token.

Other refusal outcomes end this drain: `upload_failed` is sticky and only the
full-proof repair path can clear it; `deleted` has no retained conversation to
seal; `not_batch_owner` belongs outside this batch barrier. None writes a seal.
Successful seals still retire retry state. No flag or runtime setting changes.

Hermetic coverage: `test_record_audio_seal.py` exercises pending -> retry -> seal,
terminal refusals, retry exhaustion and backoff; `test_pusher_record_abandon.py`
checks that abandoned/overflow producer fences remain pending.
