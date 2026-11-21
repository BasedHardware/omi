# Pusher custody PCM storage byte admission (PR-B)

The [runtime contract](../../listen_pusher_pipeline.mdx) adds
`PUSHER_STORAGE_PCM_BUDGET_MB=0`: default off everywhere, with a proposed
512 MiB canary size. Deployment validation requires0 or at least27 MiB
(ceil of20 MiB x4/3), ensuring a largest legal socket window can progress when
the live lane is idle; smaller/malformed unvalidated runtime values select off. The [runbook](../../runbooks/audio-durable-outbox.md#pusher-pcm-storage-byte-admission-default-off)
owns sizing, metrics, the lifecycle-owned dev -> one pod 15min -> fleet ramp,
and chart-value-0 rollback. No enablement, merge or deployment is part of PR-B.

Admission is non-waiting immediately before custody storage submission. Live
windows can use 75%; shutdown tails can use the full total. A refusal returns
without a receipt, callback or ACK. Original buffers and checkpoints retain
both byte charge and conversation identity across size, conversation, process,
discontinuity and framed boundaries. The first refused live window immediately
pauses intake in the same cancellable receive task; admission is probed every
50 ms before another frame can be read. Refusals cannot accumulate toward the
socket byte limit. Enabled windows cap at 4096 checkpoints; shutdown tails use
the reserve without entering this pause. Known-deleted owners take the existing
gone-owner disposition. Acquire/release faults are transactional, fail open,
and have bounded enum counters and rate-limited logs; late post-cancellation
storage failures are also observed and logged.
Every unresolved owner is held in a finalizer `finally`, including failed retries
and cancellation. ACK departure after one committed owner cannot release the
producer fence of a later uncommitted owner. Refused tails
retain the producer fence without changing the normal close code. Queued/running storage
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

The final review delta offers 30 minute-long windows to the real receive loop
while live admission stays full for at least 30 probes: only the first window is
read/charged, below half the socket budget, with no receipt, ACK or close. It
checks recovery once, cancellation retaining the window for WAL replay, full-tail fence
retention, and accounting faults both before and after counter mutation. Flag 0
preserves successful PCM/checkpoint/receipt/ACK bytes and storage dispatch; the
new unresolved-owner finalizer may still hold fences and defer inline finish on
genuine failure at flag 0. It is not a claim of identical failure finalization.

An explicit admission-wait state lets outer-handler cancellation interrupt its
paused receive task. Cancelling the admission pause skips the new cancellation-time
tail commit entirely, including after peer disconnect: no storage submission,
receipt or ACK occurs in that cleanup path. The original window/checkpoints and
producer fence remain for client WAL replay. Event-stalled storage tests require
cleanup to complete within one second without calling storage. Already-submitted
storage retains its byte charge until actual settlement, releases it exactly
once and cannot send a late ACK. Normal tail commits still use the reserve;
flag-0 dispatch and cancellation behavior are unchanged by this focused fix.
