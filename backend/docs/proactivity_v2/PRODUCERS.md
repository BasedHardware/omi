# Mentor and commitment producers

`MENTOR_PIPELINE=legacy` remains the default. `v2` exclusively dispatches the
conversation mentor through the v2 ledger and reserved gateway calls; invalid
values invoke neither path, and a v2 failure never invokes legacy. Existing
buffering, rate checks and debounce have a shared admission helper. Legacy code
remains for the follow-on retirement PR. Merged PR #20434 supplies the shared
paid-only admission helper and default-on debounce; its EXP-005 shadow remains
exclusive to legacy dispatch. V2 additionally enforces strict spine admission.

`backend/config/mentor_v2.json` selects `mentor_v2.prompt_version`, initially
`legacy-1`. Its gate/draft/critic prompt bytes match legacy. Add a prompt entry and
change the selected version for a later benchmark; also bump the producer registry
version when shipping changed generation semantics. The critic adds a required
structured `safety_escalation` boolean. Config defaults: prefilter disabled (`null`),
dedupe score threshold `0.525`, safety escalation `suppress`. The coordinator still
needs David's ratification of the safety default and any prefilter threshold.

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
mapping, publishes the conversation-linked feed item, then attempts spine push.
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

- Mentor per-item call ceiling 3 -> 5 for optional prefilter, gate, draft, critic,
  and dedupe; 60/day and dollar caps are unchanged. Follow-ups retain 1/item, 9/day.
- `dedupe` is an authenticated Jev gateway step, with its own deterministic call ID.
- Gateway admission errors carry a typed marker so quality fail-open cannot mask
  budget/call-limit denial.
- Terminal reasons add `duplicate`, `safety_escalation`, and `source_changed`.
- Optional `publish_item(source_guard=...)` checks canonical task open status/due
  fields inside the existing publication transaction. It writes no source fields
  and leaves existing callers unchanged.
- Three producer history/outcome indexes and real-query driver registrations.

Both registry rows retain provisional G1 targets, estimates, >=200-delivery kill
rules and push policy. New indexes and the callback queue must be provisioned by
the integration owner before enablement. Hermetic verification is not rollout or
notification-quality acceptance; real benchmark/client acceptance remains gated.
