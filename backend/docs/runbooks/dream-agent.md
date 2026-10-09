# Dream agent phase 1

The worker defaults off in code. The production runtime declarations enable shadow
for David's two allowlisted UIDs only; TestFlight stays disabled and all budgets
keep their defaults. Review API #20966 supplies the effect ledger; #20960 supplies
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
provision Secret Manager item `DREAM_AGENT_FEEDBACK_SALT` (at least 32 characters)
and bind `DREAM_AGENT_FEEDBACK_SALT=DREAM_AGENT_FEEDBACK_SALT:latest` on
backend-sync. The existing Review surface must also be enabled for live admission.
Secret creation, binding and mode promotion require separate authorization.

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
