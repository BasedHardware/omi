# Mentor and commitment producers

`MENTOR_PIPELINE=cohort` is the only valid mode: the legacy mentor pipeline was
deleted once v2 reached 100% of eligible users. `cohort` selects per user
through the same server-side `proactivity_v2` resolver and cached PostHog client
as v2 admission: true selects v2; false, unknown or flag errors dispatch
nothing (fail closed) — there is no legacy lane to fall back to. Mentor hosts
and gateway admission use the same selector. Any other env value invokes
neither path and fails the runtime env validator. Selection is exclusive per
evaluation; a v2 failure never invokes a second lane. Existing buffering, rate
checks and debounce have a shared admission helper that v2 rides unchanged.
Merged PR #20434 supplies the shared paid-only admission helper and
default-on debounce; its former EXP-005 transcript shadow was removed before
merge. V2 additionally enforces strict spine admission, with draft usefulness
measured only by its own budgeted shadow judge.

All v2 model steps bound the serialized provider request to the producer registry's
byte ceiling before sending it. Gate, draft and critic retain the prompt template
and response schema, reduce optional history/facts first, and retain the newest
conversation tail when dialogue alone exceeds the ceiling. Messages, goals, facts
and history are trimmed as whole entries in source priority order. Only a single
oversized entry is trimmed within its text, with `[Context truncated]` marking it.
Jev prefilter, dedupe and usefulness requests obey the same ceiling, including
JSON escaping and UTF-8 bytes; follow-up copy obeys its smaller 8 KiB ceiling.
Luna calls explicitly send `stream=false` and `max_completion_tokens` (mentor 2048,
follow-up 512). Fixed instructions/schema that cannot fit still fail closed.
The gateway's byte, output, attribution, call and dollar checks remain authoritative.
`tests/unit/test_proactivity_v2_request_contract.py` drives the real producers,
gateway client, HTTP authentication/correlation, validators, executors and budget
reserve/settle with synthetic storage and only the provider HTTP transport faked
within the model-call path. It covers all six mentor steps, follow-up copy,
oversized Unicode/escaped context, pre-reservation rejection and retained unknown
spend without retry.

Gateway terminal warnings include `rejection_reason` for invalid requests, using
a closed vocabulary capped at 64 characters. Every proactivity budget rejection
has a stable code; admission codes include the bounded denial reason. Validator
parameters emit only recognized field roots, discarding dynamic question names
and unsupported keys. Exception messages, request content and credentials never
enter this diagnostic field. Validation before route selection uses the same
diagnostic on `llm_gateway_request_rejected`. Deploy the gateway as well as pusher
to receive these diagnostics.

Shared legacy formatting/admission and Cloud Tasks enqueue/OIDC helpers expose
public Python APIs. In-tree callers migrate together; their implementation and
legacy dispatch behavior are unchanged.

`backend/config/mentor_v2.json` selects `mentor_v2.prompt_version`, initially
`legacy-1`. Its gate/draft/critic prompt bytes match legacy. Add a prompt entry and
change the selected version for a later benchmark; also bump the producer registry
version when shipping changed generation semantics. The critic adds a required
structured `safety_escalation` boolean. Config defaults: prefilter disabled (`null`),
dedupe score threshold `0.525`, safety escalation `suppress`. The coordinator still
needs David's ratification of the safety default and any prefilter threshold.

`mentor_v2.usefulness_judge=off|shadow|enforce` defaults to `shadow`, with
`mentor_v2.usefulness_threshold=0.5`. The judge runs after the draft and existing
critic, including drafts the critic will reject, before those existing terminal
decisions. It asks the exact `Q` question/criteria from the private
`jev-pilots/mentor/clean_test.py` benchmark. Its state contains `user_name`, raw
`user_goals`, `proposed_notification` and the last eight transcript entries labelled
`USER:`/`OTHER:`. No private module is imported. In shadow, its score never changes
the gate, critic, safety, dedupe, feed or push decision. Enforce suppresses strictly
below the threshold with reason `usefulness_judge`; equality is kept. Off makes no
judge call or score write. Successful shadow/enforce calls persist only numeric
`usefulness_score` on the existing item. Jev errors/invalid probabilities fail open
without retry; typed budget denial, unknown spend and score-storage failures still
prevent publication. The historical transcript-only prefilter stays disabled.

David's 49 labels ranked at AUC 0.72 for this contextual draft judge, versus 0.50
for the transcript prefilter and 0.51 for draft-only; the Luna critic was at chance.
These are offline label results supplied with the task, not live outcome evidence.
Keep shadow enabled for live evaluation before selecting an enforced threshold.

The prefilter checks P(worth telling) = 1 - Jev P(nothing worth saying). Dedupe
uses the benchmark's same-point question and expected five-rung ordinal score,
against the last five delivered v2/legacy mentor notifications in one call.
Only confirmed v2 deliveries enter this history; human replies and unexposed v2
chat messages do not. Legacy AI mentor messages are the existing legacy delivery
proxy. The benchmark lives outside the repo; only its question/criteria are copied.
Jev errors fail open for quality decisions, with shared fallback telemetry. Budget
admission still denies, and unknown/unsettled spend still prevents publication,
as required by the spine. No retry or direct provider fallback is introduced.
Stored recent conversations supply historical context without an unbudgeted
embedding call. V2 writes the existing mentor chat message with an internal item
mapping: first publish the conversation-linked feed item, then persist chat, record
the confirmed message ID and persistence timestamp on that item, then attempt spine push.
A post-publication chat failure records `mentor_chat_state=failed`, skips push,
and leaves the feed available without chat delivery credit. A thread reply maps
only to that persisted message association or independently confirmed exposure.
Feed availability and FCM acceptance alone are never a reply anchor.
Push denial leaves the feed/chat intact. The normal mentor message route observes
the first reply within the spine's 24h delivery window.

Follow-ups use the existing action-item reminder send/reconcile functions. A named,
one-shot Cloud Task wakes the backend at the due revision; there is no new cron.
Tasks more than 30 days ahead use deterministic 28-day hops with no model work.
Changed due dates or closed/retired/deleted/manual tasks are ignored on execution.
A repeated callback is the same ledger identity (task + UTC due revision + `due`).
The single phrasing call uses the existing pinned Luna route with low reasoning
and 512 output tokens: this reuses its tested reservation envelope without adding
a model route. It produces a bounded title/body, feed-only, with no task mutation.
Canonical single/batch completion persistence calls the server outcome reducer.
Completion without prior confirmed feed exposure cannot earn value credit.

Infrastructure failures before durable claim return HTTP 503 so Cloud Tasks retries
the same deterministic event. Policy denials and already-terminal duplicates ack.
Claims younger than five minutes return 503; after five minutes a claimed item
with no durable attempt can rotate its claim token and resume. An abandoned claim
with any attempt is closed failed, preserving every reservation and unknown cost
for accounting reconciliation; it never re-dispatches. Deterministic gateway call
IDs fence late workers, and rotated claim tokens fence their publication. Infrastructure errors after claim return 503 and retain the claim for this
same recovery path. Terminal policy denials close failed/suppressed; if that
bookkeeping write fails, the callback returns 503 for reconciliation.

The worker is off unless all three deployment settings exist:

- `COMMITMENT_FOLLOWUP_TASKS_QUEUE`
- `COMMITMENT_FOLLOWUP_TASKS_HANDLER_URL` (the exact callback URL/audience)
- `COMMITMENT_FOLLOWUP_TASKS_INVOKER_SA` (the expected OIDC service-account email)

It reuses `SYNC_TASKS_PROJECT` and `SYNC_TASKS_LOCATION`. The coordinator provisions
the queue and deploys these settings through the existing release path; this lane
changes no workflow, cloud resource, rollout flag or account data. The hidden
`POST /v1/commitment-followup-jobs/run` accepts only that OIDC identity and opaque
owner/task/due routing fields; canonical state supplies all model content.
Initial enqueue failure is logged and never rolls back a saved task.

Minimal spine extensions:

- Mentor per-item call ceiling 3 -> 6 (previously 5) for optional prefilter, gate,
  draft, critic, usefulness and dedupe; 60/day and dollar caps are unchanged.
  Follow-ups retain 1/item, 9/day.
- `usefulness` and `dedupe` are authenticated Jev gateway steps with deterministic call IDs.
- A claim/account-fenced first-score writer stores one finite numeric probability
  on the item; one extra write for a successful judge, no second ledger.
- Gateway admission errors carry a typed marker so quality fail-open cannot mask
  budget/call-limit denial.
- Terminal reasons add `duplicate`, `safety_escalation`, `source_changed`, and `usefulness_judge`.
- Optional `publish_item(source_guard=...)` checks canonical task open status/due
  fields inside the existing publication transaction. It writes no source fields
  and leaves existing callers unchanged.
- Three producer history/outcome indexes and real-query driver registrations.
- First timeout event IDs now persist in the bounded outcome map. Replays are
  read-only, cross-action UUID reuse conflicts with 409, and all metric flags remain unchanged.

Both registry rows retain provisional G1 targets, estimates, >=200-delivery kill
rules and push policy. New indexes and the callback queue must be provisioned by
the coordinator before enablement; the complete host/index/TTL/queue/flag checklist
is in `CONTRACT.md` under Enablement prerequisites. Hermetic verification is not rollout or
notification-quality acceptance; real benchmark/client acceptance remains gated.

## Live usefulness aggregate readout

Join `usefulness_score`, `acted_24h` and `negative` directly on the same ledger item.
Use the spine's seven complete UTC creation days ending at least 48 hours ago,
one producer version and one known shadow-config interval. Include only confirmed
deliveries whose full 24-hour opportunity has elapsed. Retain missing-score counts
as judge coverage; do not treat failures as zero scores or undelivered/suppressed
items as unacted deliveries. Acted and negative remain independent labels.

The offline reader `backend/scripts/report_mentor_usefulness.py` accepts an already
authorized content-free JSON array projection: `producer`, `producer_version`,
`created_at`, `delivered`, `delivered_at`, `usefulness_score`, `acted_24h`, `negative`.
Timestamp strings are timezone-aware ISO 8601. It never queries account stores and
prints only aggregate JSON. Keep exports and generated reports outside Git.

```sh
backend/.venv/bin/python backend/scripts/report_mentor_usefulness.py /tmp/mentor-score-cohort.json \
  --cohort-start 2026-10-04T00:00:00Z --cohort-end 2026-10-11T00:00:00Z \
  --now 2026-10-13T00:00:00Z --producer-version 1 \
  --threshold 0.25 --threshold 0.5 --threshold 0.75
```

Read `scored.deliveries`, `missing_score_deliveries`, `acted_auc`, `negative_auc`
and each `by_threshold` entry's `kept`/`dropped` delivery counts, acted rates and
negative rates. AUC is P(positive score > negative score), with ties worth 0.5;
undefined single-class AUC and empty-group rates are `null`, never zero.
Higher acted AUC is desirable; higher negative AUC means higher scores rank
negative feedback, so lower is preferable for that independent readout.
Threshold equality is kept, matching enforcement. Dropped rates in a shadow
cohort are counterfactual selection statistics over actually delivered items.
Enforce cohorts cannot reveal outcomes for suppressed drafts and must not be mixed
with shadow to claim an unbiased full-score AUC. This report does not alter the
existing kill-rule aggregate or automatically change thresholds/modes.
