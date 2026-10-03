# EXP-005 — Fleet conversation mentor prefilter shadow

**Owner:** dazheng. **Registered:** 2026-10-03. **Review by:** 2026-10-24.
**Decision:** measurement only; no Jev threshold is authorized for live filtering.

## Question and population

Can Jev skip Luna mentor gate evaluations while retaining at least 95% of
Luna-gate passes that led to sends? The mentor remains opt-in, now paid-only;
stored frequency is unchanged. Canonical subscription/managed-compute resolution
admits all paid plans, including mobile plans, without granting basic users
access through BYOK or a trial. Lookup errors fail open, counted by
`mentor_plan_admission outcome=fail_open reason=plan_lookup_unavailable` and
the shared fallback metric. Skips use the uid-less bounded log
`mentor_plan_admission outcome=skipped reason=basic_not_entitled`.

`MENTOR_GATE_DEBOUNCE_ENABLED=true` activates existing shared Redis admission
before context gathering and model calls in
`utils/app_integrations.py::_process_mentor_proactive_notification`. Coded
defaults remain 120 new user words AND 90 seconds, with 60 evaluations/user/day;
developers retain the existing daily-cap exemption. The code default remains
off; dev/prod declarations turn it on. Both changes affect notification
eligibility; Jev changes no decision.

Every reached Luna gate evaluation, including a gate failure, is eligible for
shadow measurement. The window is copied at the gate boundary, labelled User /
Other and truncated with the shared `truncate_state` (24,000 characters, head
and recent tail) for Jev's 32k context. It contains precisely the buffered
transcript messages seen by Luna, before truncation; user facts/goals, names,
past conversations and recent notifications are not sent to Jev. Version
`mentor_worthwhile_v1` in `utils/mentor_jev_shadow.py` freezes the typed noul
question and criteria. Model is `typesafe/jev-1.13`, through existing
`omi:auto:jev-decisions`, one attempt, no fallback. Changing wording/model
requires a new question version and calibration.

## Controls, spend and isolation

On dev/prod **backend-listen**, **pusher**, and Cloud Run **backend**, runtime
overlays and listen/pusher chart values declare:

| Flag | Value after deploy | Effect |
| --- | --- | --- |
| `MENTOR_GATE_DEBOUNCE_ENABLED` | `true` | Existing word/time/daily evaluation throttle; set false to disable. |
| `MENTOR_JEV_SHADOW_ENABLED` | `true` | Fleet measurement only; set false to stop new work. Unset means on only in dev. |
| `MENTOR_JEV_SHADOW_DAILY_CAP` | `1400` | Global admitted attempts per UTC day across these hosts within each stage's Redis; invalid/nonpositive admits none. |

No paid-only bypass flag is added. The default cap is also 1,400. At
[OpenRouter's published $0.042/M input-token rate, output free](https://openrouter.ai/blog/insights/what-is-jev/)
(checked 2026-10-03), even 1,400 full 32k inputs cost about $1.88/day. This is
a conservative list-price estimate, not invoice evidence. The 24k-character
state normally costs less. Failed attempts consume the cap; there are no
retries. Changing price, model or cap requires revisiting the estimate.

Submission occurs after the live pipeline's terminal outcome, on the existing
dedicated Jev shadow executor: no mentor thread waits for Jev or persistence.
Two queued/active tasks per process bound retained state; overload counts as
`dropped`. The 2.5s shadow deadline includes queue, Redis, vendor and persistence;
0.5s is reserved for recording provider failures. Admission reuses EXP-004's
attempt-owned, short-timeout, no-retry Redis client and atomic cap/claim Lua
with key `jev:shadow:mentor:<YYYYMMDD>`. Claims use a random evaluation ID so
repeated windows remain distinct evaluations. Redis failure admits nothing.
The kill switch is checked at submission and again at worker start. Already
running requests can complete. Usage context is `jev_shadow_mentor`, separate
from `proactive_notification`; shared metrics use static lane `mentor`.

This cap selects the first admitted evaluations until exhausted, with
process-overload drops: bounded fleet measurement is not a random census.
Report UTC-hour/frequency coverage and cap/drop rates. If cap exhaustion
concentrates early in the day, collect more days or revise sampling in a
separate change before claiming a representative fleet saving.

## Content-free records and send semantics

Records reuse `users/{uid}/jev_shadow/{id}`, EXP-004's first-write-wins
transaction, account-deletion marker fence and 60-day `expire_at` TTL. No new
collection group or TTL mutation is introduced. Record ID uses the existing
SHA256 `lane|evaluation_id|identity|question_version` convention; `uid_hash`
is SHA256(uid), using the shared shadow hashing helper. The parent user path
still contains the UID, as in EXP-004; hashes are pseudonyms, not anonymity.
Client rules deny this subcollection and account deletion recursively wipes it.

Stored fields: lane, env_stage (dev/prod/other), evaluation_id, uid_hash, evaluated_at, frequency,
question_version, state_chars, served_model, jev_score (nullable), jev_outcome,
luna_gate_verdict (raw boolean), luna_gate_score, luna_gate_passed (boolean
including frequency threshold), draft_passed, critic_passed, notification_sent,
dispatch_status, pipeline_failure, gate/pipeline/Jev/shadow latency in ms, plus
writer-owned created_at/expire_at. Not-reached stages are null; send starts
false. Pipeline failures use fixed stage labels, never exception text. Jev
provider failures persist a null score when persistence succeeds; admission,
deadline and persistence failures are visible in `omi_jev_shadow_total` and
`omi_jev_shadow_latency_seconds`, rather than fabricated rows. Existing metric
scrape coverage is limited to the exporter-enabled hosts.

`notification_sent=true` requires the existing dispatcher to report
`dispatched` with at least one successful FCM delivery. Zero/missing delivery
counts are excluded and `dispatch_status` remains available. This is transport
acknowledgment, not device rendering, opening or value. Legacy mentor return
values, rate limits and daily counts retain their behavior even on a dispatch
failure; the shadow merely observes the returned dispatch result.

No transcript, content hash, prompt, facts, name, reasoning, draft, notification
text or raw error is stored/logged by this experiment. Only the in-memory
bounded vendor state contains text. Failures and measurement scheduling never
change the Luna verdict, draft, critic or delivery path.

## Aggregate readout query

An authorized operator exports **only EXP-005 shape fields** from the server
shadow records to a private flattened NDJSON file, one row per document, adding
`record_id` and preserving the same ID on retries. No account documents or
transcripts are needed. This lane performs no production read/export. The
following DuckDB SQL runs locally on that export; no cloud index/table is
created. Include late commits and dedupe by `(uid_hash, record_id)`.

```sql
WITH rows AS (
  SELECT DISTINCT ON (uid_hash, record_id) *
  FROM read_ndjson('/secure/mentor-shadow.ndjson')
  WHERE lane = 'mentor' AND question_version = 'mentor_worthwhile_v1'
    AND env_stage = 'prod'
    AND evaluated_at >= '2026-10-03T00:00:00Z'
    AND evaluated_at < '2026-10-24T00:00:00Z'
  ORDER BY uid_hash, record_id, created_at
), thresholds AS (
  SELECT unnest([0.00, 0.01, 0.02, 0.05, 0.10, 0.15, 0.20, 0.30,
                 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 0.95]) AS t
), aggregate AS (
  SELECT t, count(*) AS measured_attempts,
    count(*) FILTER (WHERE jev_score IS NOT NULL) AS scored,
    count(*) FILTER (WHERE luna_gate_passed = true) AS gate_passes,
    count(*) FILTER (WHERE luna_gate_passed = true AND notification_sent) AS sends,
    count(*) FILTER (WHERE luna_gate_passed IS NOT NULL) AS gate_answers,
    count(*) FILTER (WHERE luna_gate_passed IS NOT NULL AND jev_score < t) AS skipped,
    count(*) FILTER (WHERE luna_gate_passed = true AND notification_sent
                    AND jev_score < t) AS lost_sends,
    count(*) FILTER (WHERE luna_gate_passed = true AND jev_score < t) AS lost_gate_passes,
    quantile_cont(jev_latency_ms, 0.95) AS jev_p95_ms
  FROM rows CROSS JOIN thresholds GROUP BY t
)
SELECT *, scored * 1.0 / measured_attempts AS score_coverage,
  skipped * 1.0 / nullif(gate_answers, 0) AS skip_rate,
  1.0 - lost_sends * 1.0 / nullif(sends, 0) AS send_recall,
  1.0 - lost_gate_passes * 1.0 / nullif(gate_passes, 0) AS gate_pass_recall
FROM aggregate ORDER BY t;
```

The hypothetical filter skips only `jev_score < t`; missing/error scores keep
the Luna call, so failure rows remain in the relevant denominators. Gate
failures have no verdict and are excluded from gate-answer denominators but
reported as coverage. Choose the largest measured skip rate with send recall
at least 0.95; zero sends cannot qualify. Report lost gate passes separately,
including passes that never produced a send. Break out the same aggregate by
frequency and UTC hour; report cap/drop/provider/persistence failure metrics
alongside it. Do not count attempt metrics as persisted rows or dedupe
distinct evaluation IDs by transcript text.

Tune on an initial window, confirm on a later held-out window, and report
uncertainty clustered by uid_hash. A 95% point estimate alone is not a live
filter approval. David chooses the threshold after sufficient send evidence;
any live Jev prefilter remains a separate PR. This shadow cannot establish
notification usefulness or mobile rendering/value.
