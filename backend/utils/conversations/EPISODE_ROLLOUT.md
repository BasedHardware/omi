# LIFECYCLE: permanent

# Episode notes rollout

Owner: David. No production enablement in this PR. Held-out acceptance on a new
cohort must precede the first ramp. Sharing remains a decision about the whole note.

Round-9 DEV status: **hold at 0%**. No measured configuration establishes all
quality and production-deadline gates. Deterministic selection with claims off
and default effort is the safe experimental default, not a launch approval.
Xhigh improves coverage and faithfulness in both judge samples, but 7/24 writer
calls exceeded the existing 60s deadline (maximum 164s). Do not enable it on
foreground routes without separately validating the complete route budget.
The eval endpoint's 300s timeout does not establish production completion.

Writer configuration (episode cohort only, read at each call):

- `MEETING_NOTES_EPISODE_SELECTION=deterministic` (default), `compact`, or `model`.
- `MEETING_NOTES_EPISODE_CLAIMS_ENABLED=false` (default); true restores metadata.
- `MEETING_NOTES_EPISODE_EFFORT=default` (default), `high`, or `xhigh`.
- Optional selector: `MEETING_NOTES_EPISODE_SELECTION_EFFORT=low` and
  `MEETING_NOTES_EPISODE_SELECTION_TIMEOUT_SECONDS=30` (bounded 1–30).

Invalid settings retain these defaults. The model selector adds a paid call and
up to 30s before the writer; invalid selection falls back to deterministic links.
DEV did not justify its extra cost. References/judges remain unchanged. Do not
raise an effort or enable the selector during a ramp without renewed acceptance.

Set `MEETING_NOTES_EPISODE_EVIDENCE_ENABLED=true` AND
`MEETING_NOTES_EPISODE_EVIDENCE_PERCENT=1` for a sticky SHA-256 UID cohort.
Default/malformed percentages or missing UID keep baseline; no user-level reads.
Raise 1 → 10 → 50 → 100 after at least 24h and 200 kept notes per step.
Keep the boolean true and percent zero for immediate baseline-only operation.
**Kill switch:** boolean false (or percent 0); no migration/reprocessing required.
Apply consistently to every service that finalizes notes; do not enable only one replica.

Compare the baseline control with the episode cohort, stratified by duration,
source, admitted screen volume and capture completeness. `conversation_notes_receipt`
logs numeric usage/latency/retries/claim count, arm (`episode`, `baseline`,
`baseline_long`), fixed violation classes, vacuity, best-note fallback and errors.
Logs contain no note/evidence text. Usage is provider input/output/cache-read metadata;
missing usage is unknown, not zero. Existing fallback counters retain each violation.
Receipts also record reasoning tokens, effort, selection mode/effort/deadline,
claims enabled, selection calls and model errors. Retry count excludes selection.
Recoverable selector/repair errors are separate from processing errors.
Count retrieval reads with the existing Firestore read-site instrumentation. Billing,
LLM gateway routing, cache writes and physical attempts need separate dashboards;
these receipts count model invocations, not gateway/direct transport hops.

Hold or abort a step if, relative to the simultaneous baseline control:

- Processing errors rise >0.5 percentage points for 30 min, or p95 note latency
  exceeds the accepted configuration's latency ceiling for 30 min.
- Mean billed cost exceeds David's explicitly accepted configuration premium, or
  p95 latency exceeds the route budget. Set that premium before enabling the
  cohort; improved coverage may justify spend, but not an unbounded budget.
- Vacuity rises >1 percentage point or repair/best-note fallback exceeds 10%.
- Audited unsupported/wrong-provenance rates rise >2 percentage points; unrelated
  content exceeds baseline. Review a consented random sample, not logs of note text.
- Kept/discarded counts or per-kept retrieval reads change unexpectedly. Episode
  admission does not alter relevance/discard; discarded conversations have no new reads.

Do not advance on improved information coverage alone. Confirm stable cache-hit share
and long-meeting completion; long speech (>240k transcript-prefix UTF-8 bytes) stays on
rich baseline, and episode repair is bounded to remaining 60s (no transport retries).
At most two model calls per episode note; long evidence (>120k message UTF-8 bytes)
within the episode arm gets one call plus local repair.
Those counts apply to the default deterministic/compact modes. Optional model
selection permits one additional call (three total), skips large evidence, and
consumes repair headroom; it can add up to 30s before a 60s initial writer call.
Transport deadlines and gateway/direct hops are not hard wall-clock guarantees.
The baseline_long arm retains baseline presentation/transport retry policy. Residual contract violations preserve a usable note.
These limits do not eliminate baseline provider errors or guarantee every meeting
finishes in 60s; they prevent additional long-context episode repair cost.

Claims are not rendered today. Compact keys only affect extraction, not client models.
List/search omit claims; detail returns filtered provenance when enabled. DEV
metadata-off reduced output and latency while retaining the coverage improvement;
wrong provenance still requires acceptance. Claim-dependent validation is skipped
when metadata is disabled; prose/presentation/vacuity safeguards remain.
Delayed revisit, evidence-aware relevance, expectation comparison
and thread linking remain later work.
