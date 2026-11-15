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
After a successful closing refresh, the coordinator retires only the exact
marker write version acknowledged by that drain, using Firestore's conditional
delete. A later upload's replacement marker survives. Failed, incomplete and
non-closing refreshes retain debt. This adds one conditional delete, no read.
Coordinator overflow leaves durable cold debt; it never invokes synchronous
playback discovery in the drain. Socket cleanup may wait up to its existing total
three-second handoff budget after drain ownership is settled; the audio drain
never awaits discovery. `drain_refresh` times actual background discovery.

The authenticated audio URL reader distinguishes an empty batch projection with
outstanding durable debt with the existing modelled field `poll_after_ms=5000`.
The real FastAPI route/response-model test verifies this survives serialization.
Current mobile and desktop decode this field but stop on an empty list; clients
need a follow-up to poll an empty projection with this hint. No fake file/URL is
emitted to work around their no-audio guard.
Each empty batch URL poll adds one marker point read; no collection scan is added.
An unavailable debt read also returns pending. Confirmed absent debt retains the
existing empty-audio response. The reader never manufactures an audio URL.

## Intake wake, rollout and rollback

The intake claim/defer marker writer from integration2b1690066827 is an optional wake
dependency: claims remove `record_intake_retry_at`; certified deferrals set it to
exactly `available_at`. Native seal reads the job before transaction writes and
wakes only a due clock or an exact matching marker. Future retries cannot be
woken without the marker writer; unmarked future clocks stay protected as
possible live claims. Its read budget is one job document per eligible transaction
attempt, with a planning envelope of 2.4 million reads/day (240000 recordings/day at a
sustained10000/hour, times10 attempts/duplicate closes); producer-pending refusals do not read the job.
This is a planning bound, not measured spend or a traffic cap.
Invalid runtime stage skips optional wake, never guesses
a production collection or prevents the native custody seal.

Both **Cloud Run -> listen -> pusher** and **marker writers -> pusher -> listen**
are protocol-safe; no special train order is required. The marker writer is
needed for the optional wake of future retry clocks, not native sealing. Intake-only preserves old pusher behavior. New pusher plus old listen
uses the old close path because old listen never negotiates close-v2. New listen
plus an old pusher sends no close-v2 controls without capability and retains
buffered audio/pending requests. New/new enables prepare/commit. A pusher rollback
forces reconnect and capability reset; live new listen pods keep pending closes
and use slow closure until a capable pusher returns. A prepared, uncommitted
producer remains fenced for full-proof repair, rather than being cleared on loss
of the protocol connection.

All switches default on and have explicit dev/prod runtime and chart bindings:
`PUSHER_RECORD_CLOSE_NOTIFY_ENABLED` and `PUSHER_RECORD_CLOSE_FAST_PATH_ENABLED`
on pusher, backend-listen, every Cloud Run backend service
(dev/prod); the cohost gate requires identical GKE literals. The native
`PUSHER_RECORD_SEAL_WAKE_ENABLED` remains pusher-only. All three are registered in
the helper-aware flag budget. Set notify=false on every listener host and pusher,
fast-path=false on every playback host and pusher, and wake=false on pusher for
full rollback. This restores slow closure, the original scheduled metadata debt
handoff on the DB executor, zero new empty-playback reads/fields, and polling. Disabling durable
projection debt also disables asynchronous playback deferral. No rollout may
clear foreign producers or bypass privacy to restore speed.

Healthy scheduling is one prepare round trip, <=1s relay tick and <=1s pusher
tick, plus mandatory custody/readback/upload, acknowledged debt and seal/wake
transactions. Close bypasses the60s audio-batch timer. Approximately60s end to
seal remains a post-deploy target; hermetic interleaving tests prove ordering,
not production storage latency or five-minute Home delivery.

## Incremental cost envelope

Per recording with B uploaded drain batches and P empty playback polls: B owner
point reads and B marker writes (one of each per uploaded drain batch), one job
read and at most one intake wake write per eligible seal transaction attempt, P
marker point reads, and at most one conditional debt delete per successful closing
refresh. Existing custody/storage/privacy work is additional and unchanged.
At sustained10000 recordings/hour (240000/day), ten eligible seal attempts alone
plan for2400000 job reads/day, exceeding the earlier1M declaration. The combined
added read envelope is240000 * (B + 10 + P)/day; retries or repeated successful
close refreshes require separate accounting and this is no runtime cap.
Normal one-attempt, B=1, P=0 is480000 reads/day, not a measured production saving.

The two optional executors can create four additional lazy threads/process:
68 threads across17 pusher pods if all are exercised. RSS is unmeasured. Global
coordinator bounds remain128 keys/2048 paths/two active calls; marker queue32.

Desktop backend uses the separate desktop_backend:create_app entrypoint, which
mounts neither transcribe/listen nor sync playback; it needs neither shared flag.
All four Cloud Run main:app services bind both switches even where a listener
cannot connect to a hosted pusher.

## Long-lived connections and image-only GKE roll

Terminal listener ACKs do not consume the pending-close admission count. Recent
terminal boundaries are capped at the100-request code default. An explicitly
old conversation offer outside the current/pending set is refused before relay
acceptance; already accepted/replay runs keep their recorded owner and proof.
Pusher retires received counters and active requests only on terminal drain
cleanup, retaining at most128 recent idempotent replies. An evicted old request
must prepare again under its own producer fence. The150-sequential-recording
single-socket test verifies actual durable receipt drains/seals and bounded wire
inventories; the uncommitted reservation test still requires a producer fence.

An unsupported response terminates that connection's protocol attempt, removes
the matching pending request, and suppresses further close controls on that
socket. Ordinary finalization remains active. A frozen boundary stays frozen;
a replacement connection can negotiate anew. A duplicate old capability ACK
cannot override the negative result.

Tonight's GKE roll patches only the image. Shared switches and native wake all
default on in code; targeted env patches, not chart values, flip rollback on
serving GKE pods. Safety needs no new chart/overlay value: pending closes100,
wire active/recent histories128 each, coordinator128 keys/2048 paths/two workers,
metadata executor2 workers/zero queued calls, debt executor2 workers/32 queued
calls, retained-drain default32 (clamped8..128), abandon default4 (clamped0..16),
close calls4 active/at most12 outstanding with16 default barrier threads, and
producer-pending retirement after6 refusals. All are safe code defaults or
constants. Existing GKE env overrides survive an image-only patch. RSS remains
unmeasured. Cloud Run rendered bindings are declared; GKE image-only activation
and any kill-switch env patch require independent runtime verification.
