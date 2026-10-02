# Screen task extraction: default-off Jev gate

`screen_task_jev_gate` defaults off for every bundle. Off retains the existing
2.5 Flash tool loop. Enabling the flag is separate from merging this code.
Privacy approval is required: screen OCR and bounded local task/profile context
are a new data class sent to TypeSafe/Jev. No enablement is performed here.

When enabled, local Vision OCR feeds a conservative occurrence-aware line-subset dedupe, keyed
by owner, authorization generation and app, with a 60-second TTL and 64-entry
bound. Telegram/Messages ignore the approximate sidebar; other apps retain
all blocks. Novel text or any additional occurrence of an existing line always passes; empty OCR and errors fail open. Messaging
triggers use content dedupe rather than unread-count window titles. This is
not visual equivalence: layout-only/attachment changes can remain a limitation.

Local SQLite FTS selects at most eight related task rows, including staged,
completed and deleted suppression context. The existing semantic embedding
service calls the network, so this path uses FTS only. Gate context uses the
first four descriptions and 1024 profile characters. No full task dump.

Two backend round trips preserve bandwidth: authenticated OCR-only
`POST /v1/screen-task/gate`, then the existing company-paid Gemini proxy with
a raw base64 screenshot only when admitted (or randomly audited). Jev uses
the existing gateway decision lane, one attempt and a two-second deadline;
threshold `SCREEN_TASK_JEV_THRESHOLD` defaults .5, reject audit rate
`SCREEN_TASK_JEV_AUDIT_RATE` defaults .01. Empty/oversized OCR or transport
failure admits extraction with fallback telemetry. Rejection uploads no image
unless audited. Gate text limits prevent truncation from rejecting unseen asks.

The extractor makes one 3.8 Flash call, US multi-region, thinking level low,
2048 output tokens and structured JSON. Canonical capture kind, owner,
deliverable, broadcast/mention, confidence, tags, source classification,
deadlines and duplicate/refine/complete IDs map into the existing capture
policy and staging path (INV-TASK-2). Only supplied active canonical IDs may
be relation targets. Empty output preserves activity observations. Invalid
or failed extraction returns to the legacy loop; revoked owners cannot apply
late results. Queued frames retain their admission owner in a 64-entry bounded map. The flag is the kill switch.

Existing proxy terminal telemetry adds only bounded `gate_outcome` and
`audit_sample`. The existing Task Extracted event records rejected audit
the true successful staging count and bounded candidate count (0–8), including zero,
with `audit_sample=true` and `gate_outcome=rejected`. Audit extraction is a precise
stage: found tasks enter the normal staging/sync path. These are not shadow-only
observations or automatically accepted tasks. The ordinary per-task event is
suppressed for audits to avoid double counting. Flag-on logging is scoped across
extraction, fallback and staging; free-form context, titles, queries and errors
are suppressed, while analysis summaries contain only capped counts/outcomes.
Flag-off logs retain their existing content.
One bounded gate decision log contains no user text, identifiers or scores.
PR #20184 was open on 2026-10-02; this change does not depend on its required
lane/client_platform tags. Reconcile tags when that independent PR lands.

Benchmark aggregates: expanded mock schema 30/30 recall, zero false tasks,
5/5 relation cases. Real replay has no labeled ground truth: dedupe removed
7/250 (2.8%) with the original set-based rule, gate passed 63/243 (25.93%), retaining all three previously
reviewed emitting frames. Expected expanded-schema real cost is modeled at
about $1.54/1k incoming frames, $29.2/day at 19k, plus the fixed reservation
fee. The occurrence-aware correction was verified with synthetic regressions;
that personal replay was not rerun, so those savings are historical. Expanded schema was not rerun on personal frames. Production FTS ranking,
user mix, OCR layouts and schema costs require consented rollout validation.

Recommended ramp after approval: consenting dogfood, then 1%, 5%, 25%, 100%
of consenting eligible macOS users. At each stage review audited rejects,
accepted/false tasks, fallback rate, latency and cost; pause on a verified
miss or increased task noise. Percentages and hold periods are David's decision.
No live app acceptance or deployment was authorized in this run.

See [reservation transition](../../../backend/docs/vertex-pt-flash.md) for
3.8 dedicated promotion, old-client 2.5 on-demand cost, declared order location
and explicit global residency approval. The moved order's location is unknown.

Windows is excluded. Its port needs OCR bounds/main-pane policy, owner-scoped
bounded dedupe, local related-task retrieval, authenticated gate transport,
company-paid one-call screenshot transport, canonical result mapping, flag
registry/consent, bounded audit telemetry and equivalent behavioral tests.
