# Staged source-frame boundary for recording close

Notify stays **OFF by default**, including image-only GKE rollouts. This is
staged implementation and regression coverage; it does not establish a production
one-minute seal or authorize enabling the protocol.

Close protocol v3 reserves one owner synchronously when a binary frame leaves
`receive_data`'s queue. Raw archive, capture sample ownership and relay enqueue
use that same owner across awaited work. Reservations cover capability negotiation
as well as an established socket. Once close retires a binding, later input uses
explicit unlinked custody until a successor exists. The current retired binding
survives bounded history eviction. Multi-channel sessions and sessions without
private cloud sync or the source-drain hook do not negotiate v3.

Commit requires no source frame in flight, a completed original-archive drain,
an ordered relay flush and an exact byte watermark on the acknowledged socket.
Pusher receipt/readback/upload, projection-debt acknowledgement, every producer
fence and privacy check still apply. No audio or foreign token is removed. A
failed/cancelled source frame refuses certification. Archive-drain cancellation
retains its pack and tracked storage task.

The existing five-second conversation poll now requests close before waiting
for successor persistence when Cloud Tasks has changed the current row out of
`in_progress`. Local finalization retains its direct notification. Neither path
runs a second finalizer.

A close attempt, including lock/storage/control-send waits, is limited to five
seconds; one pending handshake has a thirty-second deadline that survives
reconnect. The named expiry exit removes the local pending notification and
keeps the retired ingress boundary and producer custody fences. No new pusher
drain slot is retained. Existing seal-only retries remain limited to six
producer-pending refusals.

## Blocker and rollout

A prepared EOF, source failure or expired handshake is not a completed-tail proof.
The producer token can remain on a live healthy pusher after its listen owner has
gone, while fresh repair refuses that producer. Releasing it merely because a
clock elapsed could seal before a retained source tail arrives. A durable source
custody/recovery handoff, or an equally complete ordered proof, is required before
this can be default on. Process restart and old-container behavior have not been
accepted by this change's hermetic tests.

The registry owns the review date, expander and cohort plan. The first real-account
cohort is the consenting owner on a dedicated route after synthetic restart and
deadline proofs. The quality lead expands only after independent custody review,
zero owner/byte mismatch, zero new1011 or stranded live tokens, clean producer
pending/admission counts, and the target close/Home latency window. Until those
conditions pass, keep the flag false everywhere and report the ramp blocked.

Release staged code to pusher before backend-listen; Cloud Run uses the existing
completion row observed by listen and needs no new close transport. Never enable
v2 to bridge an image roll. A v3 listener with a v2/disabled pusher gets no matching
capability; a legacy/v2 listener on the v3 pusher gets no v3 capability. One-sided
switch states send no qualified close. Staged code can be rolled in either order
while disabled. Rollback is `PUSHER_RECORD_CLOSE_NOTIFY_ENABLED=false` on both
Deployments, preserving playback fast path, native seal wake and the bounded
producer-pending retries.
