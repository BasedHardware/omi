# Dream agent phase 1

The worker defaults off in code. The production runtime declarations enable shadow
for David's two allowlisted UIDs only; TestFlight stays disabled. Prod backend and
backend-sync declare 24 scheduled passes/user/day, 20 manual runs/user/day and a
$60 global daily reservation ceiling. Other budget knobs keep their defaults.
Review API #20966 supplies the effect ledger; #20960 supplies
the dedicated-only reservation policy. Declaring runtime configuration does not
deploy it or change cloud resources.

Run an authorized local/dev shadow pass from the repository root:

```bash
cd backend
DREAM_AGENT_MODE=shadow DREAM_AGENT_UID_ALLOWLIST=synthetic-dev-user \
  .venv/bin/python scripts/dream-agent.py --uid synthetic-dev-user \
  --seed-ref conversations/synthetic-conversation
```

Configure that environment's authenticated internal gateway separately. The CLI
prints run metadata only. Proposed edits, evidence references, questions, invented
feedback, model tokens, reserved cost and cost upper bounds are encrypted in
`users/{uid}/dream_runs/{run_id}`. Shadow may write admission state and its run
report; it never edits records, enqueues questions/candidates/frames, changes
vocabulary, or files developer feedback. Report `expires_at` is 30 days; it is
metadata only until an operator configures TTL. No retention policy is changed
by this PR.

Production uses the existing `backend-sync` Cloud Run service and internal
`POST /v2/dream-agent/sweep`, registered in `route_policy_manifest.yaml`. It uses
the same `verify_cloud_tasks_oidc` dependency, sync task audience and invoker
identity as the sequencer sweep; Firebase user tokens cannot invoke it.
`deploy/scheduler/jobs.yaml` declares `dream-agent-sweep-hourly` for prod at
`0 * * * *` UTC, with a 180-second attempt deadline. The drain itself has a
120-second wall-clock bound including queue reads, admission and report writes;
the route middleware allows 150 seconds. Responses contain only complete, failed,
not-admitted and deadline counts. Off performs no Firestore reads.

There is no dev Scheduler entry: dev shares prod Firestore. The existing dev
`modal/memory_maintenance_job.py` also calls the bounded drain, but its dream mode
remains off. Production writer settings cover backend-listen, pusher (live finalization), backend,
backend-sync, backend-sync-backfill and backend-integration so the existing
post-write hooks actually enqueue the allowlisted cohort. Existing consolidation
and daily-sweep jobs remain in place. Apply Scheduler declarations through the
existing authorized Scheduler reconciliation; this code change applies nothing.

Shadow needs no feedback salt: privacy-checked would-file feedback remains in the
encrypted run report, and nothing enters `dream_feedback`. Before enabling `on`,
confirm the existing Review surface is enabled for live admission. As of
2026-10-09, `DREAM_AGENT_FEEDBACK_SALT` is provisioned in Secret Manager and bound
in prod on backend and backend-sync as
`DREAM_AGENT_FEEDBACK_SALT=DREAM_AGENT_FEEDBACK_SALT:latest`. Mode promotion
still requires separate authorization.

Each admitted producer write records distinct references at
`dream_users/{uid}/dirty/{sha256(collection + "/" + id)}`. Each document contains
`collection`, `id`, a unique `version`, server `last_changed_at`, and an atomic
`change_count`. Repeated writes replace the version/time and increment the count
without adding queue entries. State `score` still increments once per product
write (paid plans weight two, other plans one). Conversation processing,
canonical memory appends, legacy memory compatibility writes, tasks and
Candidates signal the queue. Self-writes do not dirty it again.

The ordinary enqueue reads the cohort user's document, batch-merges one dirty
document per distinct reference and atomically increments state score. It does
not transactionally read state. A count aggregation checks the 500-reference cap;
overflow transactions delete the oldest observed versions, preserving concurrent
refreshes. `dirty_dropped` accumulates pruning losses in state; each encrypted run
report counts drops since the previous report. Large writes are chunked at 400
references, with cap enforcement after each chunk. The cap is enforced before an
enqueue returns successfully; storage failures or in-flight concurrent writes
can leave transient overflow, which the next successful enqueue trims.

For a single-reference write below the cap, the previous cost was two document
reads (user + transactional state) and two writes (state + event), plus retries on
state contention. The new cost is one document read, one count aggregation
(normally one billed read below 1,000 index entries), and two writes (state +
dirty), without state-transaction retries. A chunk of n distinct references now
writes n dirty documents plus one score write on the final chunk, versus the old
one event per five references plus state. Overflow adds bounded query/document
reads and deletes. Coalescing reduces pass reads and retained documents for
repeated writes; it does not claim fewer billed writes for multi-reference batches.

Drain considers the highest weighted score first, at most 100 users per
invocation. A pass reads distinct queued references newest first, at most 400
before enrichment, stopping when their conservatively encoded triage excerpts
would exceed `min(6000, Caps.tokens / 3)` including schema/framing/completion.
Touched identities and up to 30 synced OCR rows share that budget. Records
changed after admission stay queued. Successful completion deletes only the
versions actually selected; failed passes retain the queue. Missing or invisible
records are acknowledged without purchasing inference. A pass with no visible
records returns `not_admitted` and refunds its provisional admission/reservation.

The dirty set is authoritative. The timestamp `watermark` is a diagnostic
frontier and never advances past older unread references; it does not filter the
queue. Existing shadow-only sequence `events` documents are ignored and are not
backfilled or deleted. No historical customer records are rewritten. The model
sees bounded excerpts; mutation tools retain complete snapshots and fence the
current records.

Triage uses `omi:auto:dream-triage` (Luna). Empty triage buys no reasoning. Main
reasoning uses `omi:auto:dream-reasoning`: Luna before #20960, then the gateway's
reserved-only Gemini artifact and its Luna fallback. Dream derives that policy
from the gateway's generated artifact; no caller selects a Gemini model or
constructs a provider SDK. Unknown/inactive/full reservation policy belongs to
#20960. No shared/on-demand Gemini route is created here.

All knobs are declared in `config/feature-flags.yaml`:

| Knob | Default |
| --- | --- |
| `DREAM_AGENT_MODE` | `off`; accepts `shadow`, `on`; unknown fails off |
| `DREAM_AGENT_UID_ALLOWLIST` | empty |
| `DREAM_AGENT_TESTFLIGHT_ENABLED` | false |
| `DREAM_AGENT_TOKENS_PER_PASS` | 24,000 across both stages |
| `DREAM_AGENT_PASSES_PER_DAY` | 2 per user, UTC; billable/ambiguous failed and shadow admissions count |
| `DREAM_AGENT_EDITS_PER_PASS` | 10, shared with slow task proposals and vocabulary |
| `DREAM_AGENT_DAILY_USD` | $20 global daily reservation ceiling |
| `DREAM_AGENT_MAX_USD_PER_TOKEN` | $0.00001 conservative upper bound |
| `DREAM_AGENT_UNDO_RATE` | 0.2; strictly above demotes that type |
| `DREAM_AGENT_UNDO_MIN_SAMPLES` | 10 in a bounded 30-day journal window |
| `DREAM_AGENT_VOCABULARY_STT` | false |
| `DREAM_AGENT_FEEDBACK_K` | 20, minimum 2 |
| `DREAM_AGENT_FEEDBACK_SALT` | unset; storage refuses without a 32-character secret |

Admission reserves the entire pass ceiling ($0.24 with defaults), and keeps it
reserved through success or ambiguous failure. Idle passes and confirmed first-call
gateway rejections release the reservation and decrement the admission count.
Local configuration failures and timeouts before any model dispatch also refund
spend/admissions; a timeout retains the worker-safety lease.
Token usage is captured before typed-output validation, so an invalid paid response
still counts. A rejection after a successful triage call still counts; transport
failures with unknown usage retain the reservation. Refunds use the admission UTC
day, even if completion crosses midnight. Reports distinguish this ceiling
from measured tokens and their conservative cost upper bound; they do not claim
an actual provider bill. The provider adapter bounds input using encoded bytes
plus framing/schema overhead, and limits completion before purchasing a call.
At most 83 default admissions fit the daily reservation ceiling. Set the token
cost ceiling at or above all admitted route rates before operating a different
model policy.

Leases are persistent and cannot be stolen. A timeout retains the lease because
an offloaded storage operation may still be completing. For a crashed or timed
out worker, an operator must prove the worker has exited and any write outcome
has settled before clearing `dream_users/{uid}.lease`. Do not clear a live lease.
This safety choice can strand a user until recovery; it prevents overlapping
passes after expiry or process failure. No recovery automation is included.

Live edits call the Review ledger/journal seams. Transcript name fixes retain
storage encryption/compression and clear stale evidence references and
`client_processing` in the same reversible patch. Memory duplicate merges
supersede both canonical facts; undo appends two direct-user tails, preserving
original history. Memory correction keys use content, subject, slot and privacy;
new undo tail IDs and alternate spelling/rewrite tools cannot bypass suppression.
Memory spelling and rewrite edits share one demotion bucket. People merges keep redirect identities. Derived entity-page
summaries use the existing cache writer with a reversible journal entry. Slow tasks become pending Candidates,
never accepted action items. Per-type demotion keeps proposed edits in the run
report as `suggest_only`. Questions use the existing Review queue and its shared
three-answer UTC daily budget. Image-only questions may enqueue short-lived
frame requests; the pass never waits for macOS fulfilment.

The backend previously had no mobile release-channel record. The app must call
`PUT /v1/users/release-channel` with its Firebase authorization and JSON:
`{"release_channel":"testflight","app_build":300}` when `Env.isTestFlight`,
`app_store` for Store, and `dev` for development. `app_build` is optional for
backwards compatibility. Send on each authenticated app launch, including Store
launches, so a prior TestFlight record is cleared; an omitted build clears any
previous build value. The channel and build are client assertions, bounded by
the global daily spend cap and scoped to the caller's own user document; they
are not release attestations. TestFlight admission additionally requires
`DREAM_AGENT_TESTFLIGHT_ENABLED=true`, a configured
`DREAM_AGENT_TESTFLIGHT_MIN_BUILD`, and a reported build at least that value.
When the minimum build is unset or invalid, the TestFlight cohort is closed.
The endpoint is 404 while dream is off. Store clients continue to avoid the
Review endpoints.

Live capture combines the encrypted dream vocabulary with existing user terms,
behind `DREAM_AGENT_VOCABULARY_STT`. Soniox still requires its existing
`SONIOX_CONTEXT_TERMS=true` gate. Vocabulary reads degrade to existing terms on
failure, with standard fallback telemetry. No STT flag is changed here.

Feedback accepts only the typed component/failure/severity enums and numeric
diagnostics plus an invented reproduction. Code rejects any four-word sequence
shared with the full pass input, including sequences crossing fields, and any
vocabulary name/alias. Storage has no uid; a secret-keyed HMAC rotates weekly for
distinct counting. Aggregation counts distinct users within one epoch only,
returns no reproduction or user hashes, and hides patterns below k. The optional
aggregate CLI `scripts/dream-agent.py --feedback-patterns` is an operator script,
not a user endpoint. It reads at most 10,000 reports from the current epoch.
Feedback collection requires `on`; shadow stores only privacy-checked would-file
reports in the user's encrypted run document.

Local safety suites: `test_dream_queue.py`, `test_dream_sweep.py`, `test_dream_agent.py`, `test_dream_lanes.py` and
`test_dream_tools.py`, `test_dream_memory_merge.py`, and `test_dream_cohort.py`, through `backend/test.sh`. Repository typechecking,
Firestore query guards, Review/harness regressions and `make preflight` are
separate checks. No live canary or deployed acceptance is claimed.

The queue fixture's ordered reads, atomic transforms and transaction deletes are
also checked against a local Firestore emulator by
`tests/integration/test_dream_queue_emulator.py`, selected explicitly through
`backend/test.sh` with `BACKEND_PYTEST_MARK_EXPR=integration`. Use only a loopback
emulator and the synthetic `demo-dream-coalesce` project.

## Owner reports and manual runs

`DREAM_SELF_REPORT_MODE=on` enables Firebase-authenticated `GET /v1/dream/runs`
and `POST /v1/dream/runs` only for the existing allowlisted or gated TestFlight
cohort. Off, invalid, dream-off and callers outside the cohort return
`404 {"detail":"dream_report_disabled"}`. GET defaults to 10 newest runs, at most
20. Server-side projection decrypts only the caller's reports using the same
Review codec as the writer. It resolves short labels through owner-visible
record readers; missing, locked or invisible targets become `Deleted item`.
Evidence refs, document IDs, frame requests, reproductions, usage ambiguity and
reserved spend never enter this wire projection.

POST accepts `{}` and uses the same persistent lease, mode, token/edit limits
and global spend reservation as scheduled passes. `DREAM_AGENT_MANUAL_RUNS_PER_DAY`
defaults to 3 and uses a separate UTC counter; it never consumes scheduled passes.
A held lease returns 409 `dream_run_in_progress`; exhausted manual allowance
returns 429 `dream_manual_limit`. Empty queues return an empty `idle` run without
admission. Invisible/deleted-only evidence refunds the provisional manual count.
Unavailable global spend or invalid admission budgets return 503
`dream_budget_unavailable`. The request has an 85-second application deadline
and a 90-second middleware deadline, including admission/report reads; its worker
has a 70-second planning bound. A deadline returns a `deadline` run and retains
ambiguous leases/reservations for the existing operator recovery procedure.
When report settlement itself times out, its empty run ID indicates that no
settled report could be retrieved; query GET after storage settles.

New run docs carry plaintext numeric `records_read`, `records_queued_after`,
`tokens`, and `cost_usd`, plus `trigger=schedule|manual`. Content remains encrypted.
`cost_usd` is the conservative token-price estimate, not an invoiced provider
charge; the reservation ceiling still drives admission. Older reports default
to scheduled trigger and use their encrypted counters where available.

The bounded API schema is `backend/docs/api/dream-openapi.json`; generated mobile
DTOs are `app/lib/backend/schema/gen/dream_wire.g.dart`, using the same generator
as review wire types. `GeneratedDreamRunsResponse`
decodes GET and `GeneratedDreamRun` decodes POST, with generated nested edit,
question, task, vocabulary and feedback types. `GeneratedDreamRunRequest` emits `{}`.
The separate export surface avoids growing the existing 79,000-line app-client
schema and large client artifacts. Regenerate/check using:

```bash
cd backend
scripts/openapi_runner.sh scripts/export_openapi.py --surface dream --write
.venv/bin/python scripts/generate_dart_models.py --group dream
scripts/openapi_runner.sh scripts/export_openapi.py --surface dream --check
.venv/bin/python scripts/generate_dart_models.py --all --check
```

## Synthetic end-to-end canary

`POST /v2/dream-agent/canary` uses the sweep's service OIDC verifier. Configure
`DREAM_AGENT_CANARY_UID=dream-canary-<dedicated-synthetic-name>` on backend-sync;
never add it to `DREAM_AGENT_UID_ALLOWLIST`. The reserved namespace and a
`dream_canary=true` owner marker are required. The route creates an absent
synthetic owner atomically; it refuses to overwrite any existing unmarked owner.
Ordinary user eligibility rejects this identity even if mistakenly allowlisted
or marked TestFlight. No ordinary user is a canary fallback.

Each check replaces one fixed, encrypted synthetic conversation using the
product conversation serializer and `after_write` dirty hook. It verifies dirty
enqueue, transactional admission, paid responses through both real dream lanes,
and the persisted/decryptable shadow report. Empty triage fails the model stage;
a triage-only response cannot certify the reasoning lane. Canary leases are
always shadow, including when global mode is on. No product effects execute.
The maximum pass cap is 16,000 tokens (or a smaller global per-pass cap), with
at most 256 completion tokens per lane and a 65-second worker bound. Its 96/day
synthetic admission allowance permits the half-hour schedule and bounded retries;
all reservations count toward the same global daily USD ceiling. At defaults,
48 checks reserve at most $7.68/day; observed token-price cost is much smaller.
The schema's conservative byte ceiling explains the input cap. The 88-second
route bound includes a three-second durable health-write attempt.

Scheduler declares `dream-agent-canary-half-hourly` at `*/30 * * * *` UTC:
prod ENABLED with sweep OIDC/retry bindings, dev PAUSED because it shares prod
Firestore. Configure the synthetic UID and deploy the source before separately
reconciling this entry. Enabling owner reports also requires the flag on the
user-serving backend hosts; manual runs need their authenticated gateway bindings
and the existing dream mode/cohort configuration there. Nothing in this change
applies env, Scheduler, alerts, TTL, secrets, or deployments.

One counts-only log line reports `Dream canary status=pass|fail
stage=enqueue|admit|model|report error_type=<class>` plus the durable consecutive
failure count. A verified success resets `dream_canary_health/current.canary_failures`.
Prometheus exports `omi_dream_dirty_enqueue_total{outcome=ok|failed}`,
`omi_dream_pass_total{status,error_type}`, `omi_dream_tokens_total`, and
`omi_dream_canary_total{status,stage}`. Exception labels use a closed allowlist,
otherwise `other`; no metric labels contain a UID or arbitrary provider error.

`backend/deploy/monitoring/dream-canary-failures.metric.json` and
`dream-canary.alert.json` declare the log-based counter and alert for the second
consecutive failure, across Cloud Run instances. Before an authorized apply,
bind the approved notification channel IDs; no resources are created here.
If Firestore itself cannot persist the streak, counts-only failures still log
but cannot advance that counter. Configure a complementary missing-success
alert at 65 minutes to cover that outage and a stopped scheduler.

Local coverage includes owner API projection, manual allowance/lease/spend
behavior, real serialized synthetic evidence and transport requests, counts-only
stage/streak reporting, gateway lane membership, and local emulator contention.
These are offline checks; a deployed canary remains separate acceptance evidence.

User-serving hosts should declare the same `DREAM_AGENT_PASSES_PER_DAY` as the
sweep host (currently 24 in the production source declarations), along with the
same global spend/token-price limits, so GET presents the scheduler's allowance.
