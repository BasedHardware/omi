# EXP-003 — Jev capture shadow

**Owner:** David. **Registered:** 2026-09-27. **Decision deadline:** 2026-10-18T00:00:00Z.
**State:** code only, default off. Production vendor use requires David's explicit privacy decision.

## Hypotheses and fixed treatment

The deterministic cross-source, overlap and shared-trigram rule misses same
scenes, particularly same-source captures. A Jev B score at or above **0.675**
may recover these without an unsafe false-fold rate. On a later capture joining
an existing group, Jev A at or above **0.725** may identify material missing
facts that justify visible re-summary. Both questions use the exact wording and
criteria in `capture_jev_shadow.py`, model `typesafe/jev-1.13`, and input schema
version `capture_same_b1` / `capture_resummary_a1`. Changing any of those or the
thresholds requires a new benchmark and protocol version.

The work is shadow only: no grouping, summary, split, deletion, attribution,
entitlement, or data shape changes. Candidate pairs are overlapping completed
captures returned by the current bounded finalization query. This includes
same-source and below-threshold pairs; it does not cover nonoverlapping near
misses or candidates past the query page. At most six overlapping pairs are
submitted per finalization, with a process-wide queue bound of two and a
2.5-second decision deadline including queue time. The worker rereads
decrypted captures in the trusted backend and sends bounded 3,000-character
excerpts through the existing Jev gateway. It never retries. Timeout, absent
gateway, malformed response, Redis failure, or any other error leaves the
committed behavior intact.

## Admission and stop

`CAPTURE_JEV_SHADOW_ENABLED` defaults off. `CAPTURE_JEV_SHADOW_UID_ALLOWLIST`
admits explicit UIDs; `CAPTURE_JEV_SHADOW_PERCENT` defaults to zero and uses
a stable UID hash. Set a positive percentage only on David's go. Redis admits
at most 20,000 global and 100 per UID calls per UTC day by one atomic Lua
operation; failure is closed. Pair/decision IDs are deduplicated in Redis for
30 days, including failed attempts. Caps count admitted calls even if the vendor
fails. A process semaphore bounds queued and active work. On or after
**2026-10-18T00:00:00Z**, the code is a no-op even if the flag remains on,
and logs expiry once per process. `CAPTURE_JEV_SHADOW_EXPIRY` can only shorten
that date. The flag should also be removed at the decision deadline.

## Data and metrics

Static-label Prometheus metrics report calls, skip reasons, latency, scores,
and the four-cell same-scene agreement matrix by source/device category.
Same-source pairs without both `client_device_id` values are reported as
`same_source_unknown_device`, rather than being misclassified as different-device.
Structured `jev_capture_shadow` logs carry UID, pair IDs, category, shipped
group result, score/would-decision when available, outcome, version, served
model, and timestamps for every admitted attempt.
They contain **no transcript or summary text**. Only allowlisted UIDs also
get an identifier-only `users/{uid}/jev_capture_shadow/{record_id}` document
for David's prospective labeling; the readout uses logging exports so it adds
no fleet Firestore reads. A successful Separate or manual Merge action emits
an identifier-only `jev_capture_shadow_outcome` log after the action. Those
outcomes are proxies: other reasons can drive a split or merge, and delayed
actions have censoring. Logs and label docs must follow the customer-data
retention/access policy; no transcript text belongs in either.

## Go/no-go

This is a **prospective** decision; the enriched, single-user pilot is only
threshold selection. David labels at least 30 independent true-join cases and
enough proposed folds, including hard negatives, for the one-sided exact 95%
upper false-fold bound to be **below 1%**. With zero observed false folds this
requires at least 299 independent proposed folds. Report missed true joins
against all labeled same-scene cases, by source category, and require an
improvement over the shipped rule at the same safety bound. For re-summary,
David labels materiality on at least 50 prospective joins; require at least
90% precision on would-revise and review proposed summary changes for actual
fact coverage before any visible rollout. Require p95 call latency at or below
2.5 seconds, vendor error/timeout under 5%, estimated spend under $2/day,
and no split/privacy/entitlement violation. If these are unmet by the
deadline, turn the experiment off. No automatic product promotion follows a
positive readout.

## Readout

Export the two structured log event types as JSONL using a read-only Cloud
Logging query over the experiment window. Run:

```bash
python3 backend/scripts/jev_capture_shadow_readout.py logs.jsonl \
  --allowlist UID1,UID2 --export prospective.jsonl \
  --labels david-labels.jsonl
```

Label rows are `{"id":"<shadow record id>","truth":true}` for same-scene
or materiality, separately interpreted by decision. The script prints volumes,
agreement, score/latency distributions, estimated vendor cost, outcome proxies,
and the exact false-fold bound; compare actual cost with the gateway accounting
metric. Review all exported prospective items against the authorized capture
data, especially near-cutoff scores and user splits. Record David's decision in
this protocol or its successor before any percentage rollout or visible gate.
