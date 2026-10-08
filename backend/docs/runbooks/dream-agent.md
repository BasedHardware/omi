# Dream agent phase 1

The worker defaults off. This change introduces no deployment, scheduled resource,
production flag operation or provider request. It stacks on Review API #20966;
#20960 supplies the dedicated-only reservation policy.

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

The existing `modal/memory_maintenance_job.py` runtime calls the bounded dream
queue drain. Its current deployment is dev-only. A production cadence would
need a separately authorized job/workflow and Scheduler binding; this PR adds
neither. Existing consolidation and daily-sweep jobs remain in place.

Each admitted producer write cheaply records references in `dream_users/{uid}`
and sequence-numbered `events` documents. Conversation processing, canonical
memory appends, legacy memory compatibility writes, tasks and Candidates signal
the queue. Self-writes do not dirty it again. Paid plans have weight two, other
plans one, using the shared plan catalog. Drain considers the highest weighted
score first, at most 100 users per invocation. Each pass reads up to four events
(five source references each), touches their entities/facts, and adds up to 30
synced OCR rows. A sequence watermark advances only after a successful pass;
arrivals after admission survive completion. The model sees bounded excerpts;
mutation tools retain complete snapshots and fence the current records.

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
| `DREAM_AGENT_PASSES_PER_DAY` | 2 per user, UTC; failed/shadow admissions count |
| `DREAM_AGENT_EDITS_PER_PASS` | 10, shared with slow task proposals and vocabulary |
| `DREAM_AGENT_DAILY_USD` | $20 global daily reservation ceiling |
| `DREAM_AGENT_MAX_USD_PER_TOKEN` | $0.00001 conservative upper bound |
| `DREAM_AGENT_UNDO_RATE` | 0.2; strictly above demotes that type |
| `DREAM_AGENT_UNDO_MIN_SAMPLES` | 10 in a bounded 30-day journal window |
| `DREAM_AGENT_VOCABULARY_STT` | false |
| `DREAM_AGENT_FEEDBACK_K` | 20, minimum 2 |
| `DREAM_AGENT_FEEDBACK_SALT` | unset; storage refuses without a 32-character secret |

Admission reserves the entire pass ceiling ($0.24 with defaults), and keeps it
reserved through success or ambiguous failure. Reports distinguish this ceiling
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
`{"release_channel":"testflight"}` when `Env.isTestFlight`, `app_store` for Store,
`dev` for development. Send on each authenticated app launch, including Store
launches so a prior TestFlight record is cleared. This is self-reported cohort
metadata, not an entitlement or trusted release attestation. The endpoint is
404 while dream is off. This PR adds the backend contract; the mobile rollout
must add the call. Store clients continue to avoid the Review endpoints.

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

Local safety suites: `test_dream_agent.py`, `test_dream_lanes.py` and
`test_dream_tools.py`, `test_dream_memory_merge.py`, and `test_dream_cohort.py`, through `backend/test.sh`. Repository typechecking,
Firestore query guards, Review/harness regressions and `make preflight` are
separate checks. No live canary or deployed acceptance is claimed.
