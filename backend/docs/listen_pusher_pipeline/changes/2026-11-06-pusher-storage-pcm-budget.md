# Pusher custody PCM storage byte admission (PR-B)

The [runtime contract](../../listen_pusher_pipeline.mdx) adds
`PUSHER_STORAGE_PCM_BUDGET_MB=0`: default off everywhere, with a proposed
512 MiB canary size. The [runbook](../../runbooks/audio-durable-outbox.md#pusher-pcm-storage-byte-admission-default-off)
owns sizing, metrics, the lifecycle-owned dev -> one pod 15min -> fleet ramp,
and chart-value-0 rollback. No enablement, merge or deployment is part of PR-B.

Admission is non-waiting immediately before custody storage submission. Live
windows can use 75%; shutdown tails can use the full total. A refusal returns
without a receipt, callback or ACK. Original buffers and checkpoints retain
both byte charge and conversation identity across size, conversation, process,
discontinuity and framed boundaries. Later flushes retry in order. Enabled admission caps each window at 4096
checkpoints and retains at most 20 windows plus the boundary window. At that
metadata cap the existing receive task pauses intake and probes non-waiting
admission every50ms; no extra task, ACK, drop or error close is introduced.
Shutdown tails bypass this pause. Every retained owner is checked against the
socket gone-owner set before retry. These two safeguards address the independent
review findings for tiny-window metadata growth and deletion after refusal.
Refused tails
retain the producer fence without changing the normal close code. Existing
per-socket exhaustion remains the last-resort behavior. Queued/running storage
keeps its byte reservation across caller cancellation until actual settlement.

The unit saturation harness was written and run before admission code:
`tests/unit/test_pusher_storage_pcm_saturation.py`. Against base
`d47819297e390e0e16971b1f43ad0573ccd324bb`, its first run produced two passing
flag-zero characterizations and one strict xfail for unbounded submissions;
the expanded test-first run produced two passes and seven strict xfails.
The final harness scales to 50 synthetic producers each submitting a 512 KiB window to the real commit helper
and executor, with `commit_pcm_window` replaced by an event-controlled GCS stub.
At an 8 MiB budget, ordinary admission must hold at 6 MiB and refuse 38/50;
recovery must commit every window exactly once. 50 x 4 KiB tails fit inside
the reserved quarter during live saturation. Events model long GCS stalls
without real 30-120 second sleeps. The harness also covers failures, buffer and
checkpoint retention, real-router boundaries and record metadata liveness.

Local Python allocation, current RSS and RSS high-water checks are synthetic
bounds. Allocator pages need not return immediately: current RSS must stay on
its plateau after recovery, while live allocations fall and submitted bytes
drain to zero. The earlier test-first runs used 64 KiB windows / 1 MiB budget.
Not measured: listen re-offer cadence, projection debt aggregate, GCS SDK
internal buffering, real sockets/pod or production tail distribution. Existing
projection-debt contract and executor pools remain unchanged. Neither this
harness nor a local green suite proves deployed custody or installed client WAL
retention. Two independent parallel custody reviews, including Grok, are required
before publication.
