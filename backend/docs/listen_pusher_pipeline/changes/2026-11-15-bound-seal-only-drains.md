# Bound seal-only pusher retries

A drained recording can still fail sealing because another producer token remains.
Keeping its audio worker forever consumes the pod's retained-drain slots, then
capacity cancellation strands fresh recordings behind new producer tokens.

After six observed `producer_pending` seal refusals, the pusher now retires only
its local close scheduling, provided its own token and pending clears are gone.
The exponential retry backoff is unchanged. `event=record_seal_deferred
reason=producer_pending` reports this outcome; it is not seal success.

Other producers' tokens remain untouched, `record_audio_closed` remains false,
and existing repair must independently establish custody and privacy proof.
Metadata exceptions, unknown writes and admission refusals retain their retries.
This change does not repair the existing stock or recover permanently stuck
executor calls. Coordinate the repair-side recovery separately.

`PUSHER_RECORD_SEAL_PENDING_RETRY_BOUND_ENABLED` defaults on. Set it to `false`
to restore indefinite durable producer-pending retries. The retained-drain cap
stays unchanged; increasing it is not a durable fix.
