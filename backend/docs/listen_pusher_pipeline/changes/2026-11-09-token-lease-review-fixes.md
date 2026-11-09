# Token lease review corrections

This supersedes the append/recovery descriptions in the earlier
[Part A receipt](2026-11-09-record-token-lease.md). Lead decisions A/B/C apply
to the FIX-FIRST correctness and custody reviews of `8ab8444009ec`.

The monitoring findings are already resolved: the two split alert objects are
in the aggregate, the three source metrics are declared in the production
inventory, and the seal worker's literal oldest-age Gauge is exported by its
HTTP registry. Mirror, source-emitter and endpoint tests cover these contracts.

## Custody ordering and retries

Serve-cohort uploads acquire a request-specific `custody:<job_id>` token before
local staging or archiving. It carries `signal_source=custody_append` and its
own lease. This changes neither the partial marker nor upload revision. A
concurrent partial pass must refuse while the token is live, and any old
admission/plan CAS must re-read the token map.

Only an accepted response with durable archived bytes bumps
`record_upload_revision` and clears that exact token. A refused/failed upload
(including 202/failed) clears only its token, without revision or late-counter
changes. A lost token cannot produce a successful ACK: the phone keeps its WAL
and retries under a fresh fence. A crash leaves the token protected by its own
lease. Other uploaders' tokens are never cleared.

Memoized waits return before token acquisition or renewal. Manifest heartbeats
and completed durable per-file archive appends renew existing clocks at most
once per lease/2 per conversation. A later upload's new token cannot postpone
renewal of an older live uploader. There is no idle timer. The two per-upload
fence create/finalize writes are custody transitions, separate from throttled
heartbeat renewal writes. Late-append counters are emitted only after accepted
durable append completion; shadow counts accepted late appends without reopening.

## Late audio and named exits

Late owner WAL holes are decoded and retained create-only against the actual
retained reference coverage. This supports partial rows and interior gaps,
unlike the existing tail-only gap-fill path. The normal partial worker sees
the new chunks. A conservative 503 can still retain chunks while the phone
keeps its WAL: the partial inventory is explicitly re-armed and its old CAS
invalidated, without bumping upload revision or counting that refused request.
Original raw archives and original retained chunks are never deleted/overwritten.

Serve-only frames on a complete seal reopen `record_audio_closed=false`, restore
the exact socket token with fresh clocks, bump revision and increment late_append.
The existing partial continuation processes newly retained audio, including an
interior gap when the old tail already reached finished_at. A distinct durable
coordinator preserves completed/leased original work and immutable projection
bindings. It uses the same privacy, payer, admission and annotated-text guards
as ordinary partial continuation. No completeness is invented: recovery carries
a partial marker and retains the existing partial continuation/retirement exits.
Off remains the old path; complete-seal shadow frame observations only count.

Named exits remain seal, partial_finish and reactivated. Custody reactivated now
means begin fence followed by durable finish; frames reactivated may schedule
partial continuation. Its record_pending exit is the existing partial worker;
unchanged inventories poll hourly and retire after the existing 24h idle window.
No Part B discovery or index implementation is added here.

## Validation

Final commands, exact counts and commit identities will be recorded after the
post-rebase validation run. No production/GCP access, push or PR is authorized.
