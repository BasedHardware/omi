# Framed custody reader repairs before the writer ramp

Repairs for the dark framed pack in #24409 are independent of the seal index
parked in #24410. They must land before `AUDIO_CUSTODY_FRAMED_PERCENT` moves
from 0. The custody [receipt contract](../../runbooks/audio-durable-outbox.md)
and stored capture bytes remain unchanged; stop-PCM stays off.

- Clipping retains native sample offsets, counts and rate, exact untouched
  capture endpoints, and exact 16 kHz rendition bounds. Playback and replay
  select and count the same captured samples.
- Replay proof decodes a native-rate framed PCM projection into the requested
  rendition before selecting spans, then checks the raw archive independently.
  Both committed sources must agree with every replayed sample before a new
  projection or tail is written. Stored projections are never resampled in place.
- Framed manifests larger than the existing reader bound cannot issue a
  custody receipt. A media-only orphan cannot release phone WAL.
- Optional raw-listing failures log a closed result bucket without paths or
  exception text; required replay proof still fails closed on listing failure.

The bounded replay cache already on main keys whole objects by bucket, path
and generation. Its 65-disjoint-span regression remains part of verification;
spans do not each consume an object slot or reread their shared projection.

No seal writer, index flags, index tests, manifest-first reader or rollout
configuration is introduced. Original bytes, frame positions and both-object
receipt verification remain authoritative: no silence inserted, no captured
sample dropped, no phone release without a receipt. Rollback is revert of these
repairs while the framed writer percent remains 0. The lead owns any ramp,
after the matched baseline and phone-WAL acceptance gates in the rollout plan.
