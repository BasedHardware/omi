# LIFECYCLE: permanent

# Episode notes rollout

Owner: David. No production enablement in this PR. David completed v3 held-out
acceptance on 35 conversations, two judge samples, at b89a11c1be with production
gateway effort parity (2026-10-06). Do not rerun or tune against that split.
Sharing remains a decision about the whole note. Hold at 0% until David starts the ramp.

The locked configuration supersedes C8. C7 uses deterministic selection, claims off and no request effort
override. Universal volume routing selects C6/xhigh when admitted speech has at
least 1500 words and at least two source kinds; other captures use C7. This rule
has no UID, allowlist or situation category. DEV routing share is not a production
traffic estimate without matching kept-capture/source distributions.

Writer configuration (episode cohort only, read at each call):

- `MEETING_NOTES_EPISODE_SELECTION=deterministic` (default), `jev`, or `luna`.
- `MEETING_NOTES_EPISODE_CLAIMS_ENABLED=false` (default).
- `MEETING_NOTES_EPISODE_EFFORT=default`; high/xhigh are explicit experiments.
  Default means no request override: the shared gateway's `conv_structure` route
  currently supplies low. C6's explicit xhigh overrides that route setting.
- `MEETING_NOTES_EPISODE_TIERED_ENABLED=true` inside the admitted episode cohort.
- `MEETING_NOTES_EPISODE_TIER_MIN_WORDS=1500` (David 2026-10-06: about 10 min of speech; 250 was too low) and `..._TIER_MIN_SOURCE_KINDS=2`.
- `MEETING_NOTES_EPISODE_WRITER_TIMEOUT_SECONDS=120`, `..._C6_TIMEOUT_SECONDS=180`.
  The existing gateway route clamps C6 to 115s; synchronous requests remain
  C7/60s. Only already-leased durable finalizers get extended budgets.
- `MEETING_NOTES_EPISODE_THINKING_MAX_INPUT_BYTES=0`: optional experimental guard
  disabled by default; setting 4k–240k retains the previous baseline size policy.
- Luna selector effort defaults low, timeout 30s (bounded 1–30).
- Jev threshold defaults 0.70, the best measured experimental cutoff; it is NOT an accepted
  shipping cutoff. DEV sweeps 0.70/0.80/0.90 did not justify replacing deterministic
  selection. The selector flag stays deterministic unless renewed acceptance does.

Invalid selectors/efforts retain deterministic/no override; invalid tier controls
fall back to C7 or documented bounded values. Jev errors/oversize use deterministic
selection. Jev receipts use the existing `episode_evidence` decision metric lane,
and report actual selector, calls, usage/cost when returned; never source text.
Read the [outer deadline audit](EPISODE_DEADLINES.md) before increasing a budget.
A full 180s C6 serving deadline is blocked by the existing shared gateway route;
no outer request, lease, shutdown or client limit changes here. C7 timeout/oversize
remains an ordinary provider failure. C6 gets one C7 rewrite only for timeout or
context-limit failure; auth/quota/refusal errors are not retried as C7. After that
fallback all further model repair is disabled. The worst requested writer time is
115s + 120s, plus bounded selection/transport overhead, inside the 1500s job lease at the level of requested timeouts.
Completed calls exceeding a socket deadline log `writer_deadline_overrun` and
disable paid repair. This is not a hard guarantee against process termination or the rest of enrichment.

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
`baseline_long`, `baseline_budget`), fixed violation classes, vacuity, best-note fallback and errors.
Logs contain no note/evidence text. Usage is provider input/output/cache-read metadata;
missing usage is unknown, not zero. Existing fallback counters retain each violation.
Receipts also record reasoning tokens, effort, selection mode/effort/deadline,
claims enabled, selection calls, requested/actual effort, estimated input bytes,
configured byte ceiling and model errors, tier/route reason, configured/effective writer deadline,
actual selector, Jev calls/cost and tier fallback. Retry count excludes selection.
Recoverable selector/repair errors are separate from processing errors. Known
BYOK models outside the supported reasoning family retain their own options;
`effort_unsupported_model` records the downgrade without model/key/content logs.
Count retrieval reads with the existing Firestore read-site instrumentation. Billing,
LLM gateway routing, cache writes and physical attempts need separate dashboards;
these receipts count model invocations, not gateway/direct transport hops.

Hold or abort a step if, relative to the simultaneous baseline control:

- Processing errors rise >0.5 percentage points for 30 min, or p95 note latency
  exceeds the accepted configuration's latency ceiling for 30 min.
- Mean billed note cost exceeds **2.0× the simultaneous baseline control**.
  The held-out parity mean ratio was 1.4×. Count failed attempts, rewrites and
  repairs in billing. Monitor writer deadline overruns separately: the 115s C6
  clamp is a per-writer limit, not the total note latency including C7 fallback.
- Vacuity rises >1 percentage point or repair rate exceeds 10%.
- Overall best-note/tier fallback exceeds **10% of all episode notes** for 30 min.
  Count receipts with `fallback_to_best_note OR tier_fallback` once, not their sum.
- Audited unsupported/wrong-provenance rates rise >2 percentage points; unrelated
  content exceeds baseline. Review a consented random sample, not logs of note text.
- Kept/discarded counts or per-kept retrieval reads change unexpectedly. Episode
  admission does not alter relevance/discard; discarded conversations have no new reads.

Do not advance on improved information coverage alone. Confirm cache-hit share,
source inclusion, routing share and long-meeting completion. Speech above 240k
transcript-prefix bytes stays on rich baseline. Episode repair needs at least
15s remaining tier budget, skips inputs above 120k message bytes, and never follows
a C6→C7 fallback. Default deterministic notes buy at most two writers total;
optional selectors add their own calls (Jev splits only for context overflow).
Baseline long/budget paths retain their existing transport/presentation policy.
Monitor C6 fallback rate separately. C6→C7 timeouts are expected until a dedicated
long gateway route exists: 3/8 routed held-out writers exceeded 115s, or 3/35
(8.6%) of all notes. Do not apply a 5% threshold to only routed C6 captures;
use the overall 10% fallback guard above. Direct-provider acceptance omits the
paid C7 fallback for those overruns, so ramp billing/latency must be measured.
**Next step: a dedicated long gateway route**, with its own audited deadline and
gateway acceptance, rather than raising unrelated shared/request/lease limits.

Claims are not rendered today. Compact keys only affect extraction, not client models.
List/search omit claims; detail returns filtered provenance when enabled. DEV
metadata-off reduced output and latency while retaining the coverage improvement;
wrong provenance still requires acceptance. Claim-dependent validation is skipped
when metadata is disabled; prose/presentation/vacuity safeguards remain.
Delayed revisit, evidence-aware relevance, expectation comparison
and thread linking remain later work.
