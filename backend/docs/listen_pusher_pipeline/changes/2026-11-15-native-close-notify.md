# Native close-v2: accepted audio, acknowledgments and playback debt

This supersedes the original one-frame close protocol from 75c22cbc3258. No
producer token, privacy refusal or retained-tail proof is bypassed.

## Accepted-audio boundary

Listen negotiates `record_close_protocol=2`; pusher replies on opcode204 with
integer version2. Version1, absent capability and replacement-socket ACKs cannot
qualify a socket. The close-only opcode104 control has an exact request_id,
conversation_id, phase and byte watermark; it never dispatches a finalizer.

Prepare reserves the close and holds the producer fence. It can yield while
`audio_bytes_send` accepts more runs for that conversation. Pusher reports its
received-byte baseline. Listen then flushes every accepted run under the audio
flush lock, freezes acceptance synchronously, and sends commit with that baseline
plus subsequent successfully sent bytes. There is no await between the empty
accepted-buffer check and freezing. New input after the frozen boundary raises
backpressure before entering the relay buffer; it retains the caller's existing
archive/WAL custody, rather than silently appending behind commit.

Pusher validates the watermark, hands its remaining PCM buffer to durable
custody, and only then commits the close reservation. Existing receipt readback,
SHA/PCM verification, encoded upload, own-token clearing and foreign-producer
checks remain mandatory. Negotiated open sockets cannot seal on rollover alone.
A disconnect before a prepared close commits retains that producer's fence.
Unprepared conversations fall back to ordinary socket-end drainage.

Every prepare/commit response uses opcode206 and echoes phase, request_id and
watermark. Capacity, unsupported, producer-unavailable and watermark refusals
are explicit. A WebSocket send never counts as acceptance. Listen retains and
retries the same request until a matching commit acceptance arrives; reconnect
re-prepares on the newly qualified socket while preserving the frozen boundary.
Duplicate controls are idempotent. A full local pending inventory sends no
unretained close; that conversation retains the slower socket-close behavior.
Both endpoints bound their close inventories to128 conversations per socket.

## Optional playback work

One process-wide coordinator owns at most128 conversation jobs and2048 pending
path arguments, with two active jobs. It uses a dedicated two-thread executor
with zero queued calls, isolated from mandatory storage/custody work. Marker
writes use a separate two-thread executor with at most32 queued calls; timeout
retries cannot grow an unbounded DB queue. Shared
playback inventories are globally capped at128 conversations/2048 cached chunks.
A key is never refreshed concurrently; same-key pending updates coalesce.

Every deferred upload first waits for its rebuild-marker commit acknowledgment.
Failed/unknown commits retain the producer fence and retry metadata, without
replaying proven PCM. A new upload invalidates that socket's prior marker ACK.
Coordinator overflow leaves durable cold debt; it never invokes synchronous
playback discovery in the drain. Socket cleanup may wait up to its existing total
three-second handoff budget after drain ownership is settled; the audio drain
never awaits discovery. `drain_refresh` times actual background discovery.

The authenticated audio URL reader distinguishes an empty batch projection with
outstanding durable debt as `metadata_status=pending`, `retry_after_seconds=5`.
Each empty batch URL poll adds one marker point read; no collection scan is added.
An unavailable debt read also returns pending. Confirmed absent debt retains the
existing empty-audio response. The reader never manufactures an audio URL.

## Intake wake, rollout and rollback

The intake claim/defer marker writer from integration2b1690066827 is a deployment
dependency: claims remove `record_intake_retry_at`; certified deferrals set it to
exactly `available_at`. Native seal reads the job before transaction writes and
wakes only a due clock or an exact matching marker. Future retries cannot be
woken without the marker writer; unmarked future clocks stay protected as
possible live claims. Its read budget is one job document per eligible transaction
attempt, with a planning envelope of one million reads/day (100000 recordings
times10 attempts/duplicate closes); producer-pending refusals do not read the job.
This is a planning bound, not measured spend or a traffic cap.
Invalid runtime stage skips optional wake, never guesses
a production collection or prevents the native custody seal.

Roll out **intake with the marker writer first, pusher second, backend-listen
last**. Intake-only preserves old pusher behavior. New pusher plus old listen
uses the old close path because old listen never negotiates close-v2. New listen
plus an old pusher sends no close-v2 controls without capability and retains
buffered audio/pending requests. New/new enables prepare/commit. A pusher rollback
forces reconnect and capability reset; live new listen pods keep pending closes
and use slow closure until a capable pusher returns. A prepared, uncommitted
producer remains fenced for full-proof repair, rather than being cleared on loss
of the protocol connection.

All switches default on and have explicit dev/prod runtime and chart bindings:
`PUSHER_RECORD_CLOSE_NOTIFY_ENABLED` on both hosts (cohost gate requires identical
literals), and `PUSHER_RECORD_CLOSE_FAST_PATH_ENABLED` plus
`PUSHER_RECORD_SEAL_WAKE_ENABLED` on pusher. Set the respective switch false to
restore slow closure, synchronous playback or intake polling. Disabling durable
projection debt also disables asynchronous playback deferral. No rollout may
clear foreign producers or bypass privacy to restore speed.

Healthy scheduling is one prepare round trip, <=1s relay tick and <=1s pusher
tick, plus mandatory custody/readback/upload, acknowledged debt and seal/wake
transactions. Close bypasses the60s audio-batch timer. Approximately60s end to
seal remains a post-deploy target; hermetic interleaving tests prove ordering,
not production storage latency or five-minute Home delivery.
