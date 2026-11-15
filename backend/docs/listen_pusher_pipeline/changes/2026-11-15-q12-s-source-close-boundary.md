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

## Account cohort and settled EOF recovery

The opt-in boolean also requires account selection through the existing
`serving_for` parser. Its conventional `_SERVE_UID_SHA256S` (empty) and
`_SERVE_PERCENT` (100 when the boolean is enabled) companions are independently checked by listen and
pusher. Only two selected peers negotiate v3. An absent/false boolean ignores
cohort markers, and an explicitly unselected owner gets the original bytes and no close
inventories. All reader hosts have explicit bindings; no account digest is
checked into deployment sources.

Prepared-only actual EOF now reuses the capped abandonment metadata lane after
the receive task ends, other socket submitters stop, and its record worker and
shielded executor futures settle. Only prepared recording tokens minted by that
socket are attested; reconnect and unrelated tokens remain unchanged. The new
coordinator has a thirty-second deadline. Overflow, incomplete settlement or
cancellation leave the producer fenced, without adding retained drain slots.
Abandonment proves stoppage only; repair still requires retained-tail proof and
privacy/revision checks before releasing a token or sealing.

A live handshake expiry never abandons its producer. A verified latency caveat
remains: a prepared, uncommitted socket can carry that fence through a later
header rollover, while OFF can seal at that rollover. Default stays OFF pending
delta review and an owner-first account cohort; no universal one-minute bound
is claimed. Missing retained tails, timeout and coordinator overflow remain
fail-closed and may require existing process-death repair.

The quality lead executes the registry ramp by setting the boolean true,
percentage zero, and the same placeholder-resolved owner digest on both GKE
Deployments, pusher first then backend-listen. Clean owner and percentage-cohort
windows must show zero owner/byte mismatch, new1011 or stranded settled producer
tokens, no pending/admission growth, and the seal/Home targets. The review and
expansion decision is due 2026-11-16. Rollback sets the boolean false on both;
all cohort markers become inert. Cloud Run finalization reaches listen through
its existing five-second durable completion poll, so no new transport or
Cloud Run enablement is needed. Old/v2 peers and one-sided configurations use
the legacy path. Actual process kills, old images and account acceptance still
need release validation.

The owner authorized a fleet-on rollout through the lead. An absent percentage
therefore preserves the existing true-switch fleet path at 100 percent; the
new checked-in percentage binding is also 100. An absent/false boolean remains
inert. To narrow an enabled fleet to the owner, explicitly set percentage zero
and the owner digest on both peers; no route change is required.
