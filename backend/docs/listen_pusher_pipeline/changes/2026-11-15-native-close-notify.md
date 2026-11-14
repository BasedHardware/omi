# Close batch recordings independently of finalizer transport

Cloud Tasks finalization must also notify the pusher that the recording ended.
Listen requests `record_close_protocol=1`; only a pusher reply with opcode 204,
`type=record_close_ack`, integer `version=1` enables opcode 104 with
`record_close_only=true`. Old pushers receive no close-only frame. The control
never dispatches a finalizer. Deploying pusher before listen enables the change;
mixed versions preserve the old behavior until capability negotiation succeeds.

Listen flushes accepted audio under its audio flush lock before sending the
control on the same qualified socket. Failed/withheld audio retains the pending
close. Capability is reset on reconnect; an old socket cannot qualify its
replacement. Pending notifications retry on the one-second audio-consumer tick.

The durable pusher drain immediately flushes the ended conversation, verifies
generation-pinned receipts and PCM ranges, uploads encoded audio, and clears only
its own producer token. Other producers, missing tails, upload failures and all
privacy fences still prevent a clean seal. Close scans run between conversations
and after each flush; the just-dequeued reference is excluded until buffered.

Optional `audio_files` discovery runs in a tracked async coordinator with its own
cache, one storage call at a time, bounded to 128 conversations and 2048 pending
paths. It coalesces warm updates and schedules existing speaker/identity retries.
Closing also hands durable metadata debt to the existing rebuilder. Queue/debt
overflow restores synchronous discovery. A fresh owner deletion check precedes
each encoded projection; moving optional discovery does not remove that check.
Socket cleanup retains its total three-second metadata handoff budget. Slow
optional discovery may outlive the socket under process task supervision.
`drain_refresh` continues to time actual discovery, including background work.

Native sealing wakes fresh intake atomically with the conversation seal, using
Q12-B commit `17298c5201d7`'s lease rule. The transaction reads the job before any
write, verifies owner/conversation, `record_pending`, and enqueue age <=7200s.
It sets `available_at=0` only when already due or when the exact numeric
`record_intake_retry_at` equals `available_at`. Intake claims remove that marker;
future unmarked or stale-marker clocks remain untouched during rolling upgrades.
This wake grants no admission or custody authority. Integrate Q12-B's corrected
claim/defer marker writes for immediate wake of certified future retries.

Kill switches (all default on): set `PUSHER_RECORD_CLOSE_NOTIFY_ENABLED=false`
on listen/pusher to restore boundary/socket-only closure;
`PUSHER_RECORD_CLOSE_FAST_PATH_ENABLED=false` on pusher to restore serial,
synchronous playback refresh; `PUSHER_RECORD_SEAL_WAKE_ENABLED=false` on pusher
to restore intake polling after native seal. Disabling the durable projection
debt switch also restores synchronous metadata refresh.

Expected healthy close scheduling is <=1s to relay buffered audio plus <=1s to
enter the pusher drain, then mandatory custody readback/upload/transaction work.
There is no remaining 60s batching wait after the close control and no optional
discovery wait before token release. A fleet <=60s end-to-seal target still needs
post-deploy verification; storage latency and other producers are unbounded by
this change. Dead-pod tokens require the separate proven repair path.
