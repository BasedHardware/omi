# Listen formation ingestion contract

Status: implemented production-neutral mapping and acceptance adapter; no
Listen finalization transaction, outbox, route composition, or activation.

`apps/service/listen/formation-ingestion.ts` is the semantic bridge between an
exact terminal Listen transcript and the existing durable formation-work
acceptance port.

## Exact seal

One finalization binds the account, Listen session, conversation, terminal
status, capture completeness, start/end time, source, and every ordered segment
including its id, exact text, `is_user` observation, and time span. The
account/session-derived formation work id is stable on replay; the transcript
and finalization digests change when any bound input changes. The downstream
formation input manifest therefore turns changed bytes under that same work id
into an idempotency conflict.

`completed` maps to complete capture. `entitlement_exhausted` maps to explicit
incomplete capture and retains every sealed segment. `interrupted` is retained
but not submitted. An empty eligible transcript is likewise not submitted.

## Identity authority

`is_user` is retained only as observed attribution evidence. Its two values map
to two distinct source-local channels within the Listen session. Both channels
have producer-null and asserted-identity-null coordinates, and the adapter
mints no owner identity, entity binding, identity authorization, `subject:*`
label, speaker rendering, or second-person presentation.

The snapshot deliberately carries a null identity-authority context. Existing
authorization revisions are preserved as graph inputs, but they cannot be used
without their complete immutable confirmation/producer-policy support. A later
belief/calibration stage may consume `is_user` together with independent
evidence; this adapter never interprets it as proof.

## Boundaries and limits

- The caller supplies one exact account-local graph snapshot and all explicit
  policy/frontier versions. The adapter detaches its plain tree before use.
- At most 4,096 segments and 1,000,000 text code units may enter one seal; every
  segment is already bounded to the 1,500-code-unit evidence budget.
- Proxy, accessor, decorated/sparse array, duplicate segment id, invalid time,
  wrong owner, wrong frontier, changed digest, and unsupported session state
  inputs fail before formation acceptance.
- Transcript text remains inside the sensitive formation snapshot. This
  adapter creates no telemetry, logs, outbox diagnostic, or durable error text.
- The adapter invokes the existing formation acceptance port once and never
  invokes a model directly.

## Deliberate production gap

The canonical app-facing Listen store is still a local/QA SQLite or in-memory
adapter. Socket closure currently updates Listen state and the conversation
projection synchronously; there is no production PostgreSQL Listen transcript
authority and no same-transaction outbox.

Consequently this adapter is **not** called from the Listen route. Production
wiring requires a durable finalization unit of work that atomically commits the
immutable transcript seal, conversation-finalization intent, and outbox record.
Only that outbox consumer may load the current graph and invoke this adapter.
A direct callback after socket close would have an uncloseable crash gap and is
therefore forbidden.

This contract also does not choose a model, prompt, worker cadence, probability
threshold, shadow retention disposition, product expression, cohort, or
deployment default.
