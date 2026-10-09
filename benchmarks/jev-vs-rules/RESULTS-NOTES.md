# JEV keep-rescue pilot

Offline Architecture 3 pilot approved 2026-10-09. Production rescue mode is **off**
when unset or invalid. No chart/workflow enables it. `shadow` scores R03/R08
rule discards and emits `omi_conversation_relevance_rescue_total{mode,rule,outcome}`
without changing the serialized decision. `on` rescues at P(discard) < 0.80 or
on missing/error/invalid scores; exactly 0.80 leaves the discard standing.
Calendar retention runs first and remains independent. Activation is separate
from this offline pilot; this PR does not authorize production scoring.

## Offline replay

```sh
python3 benchmarks/jev-vs-rules/generate_fixtures.py
python3 benchmarks/jev-vs-rules/harness.py
```

The frozen JSONL contains 90 synthetic families: 30 each for R03, R08 and R16.
IDs identify challenge strata, including protective cases that do not trigger
that rule. Rule expectations are asserted separately from the generated baseline.
`runpy` loads the real rules, processing policy, relevance decision and question
modules with scoped, offline-only import seams. Results include the baseline,
score, abstention, rescue, final verdict and label agreement; summary JSON includes
counts, rates, paired error-count deltas, source and fixture SHA256 pins.
Ambiguous baseline cases use a **KEEP model fake**, not measured nano predictions.
Outputs go to ignored `.outputs/results.jsonl` and `.outputs/summary.json`.
Use `--mock-scores scores.json` for an ID-to-score map (null or `"error"` abstains).
Default scores deliberately cycle 0.79/0.80/0.90/missing/error, independent of labels.

R16 results include an additional no-calendar counterfactual. Calendar coverage
is a fixture fake, not a calendar lookup; no calendar title reaches JEV. The
existing calendar override is never removed by rescue. Reuse the same score
when the effective and no-calendar baseline coincide, rather than paying twice.
The synthetic Friday Coffee and Cowork examples are invented; they do not copy
any account's original scrap.

## Labels and limits

`keep_label` is a proposed content label with a written reason, authored before
replay, **not an independently reviewed human label**. `label_status` explicitly
records `agent_proposed_unreviewed`. David must review/freeze labels before using
real results for an accuracy claim; non-English judgments need language review.
Uncertain labels are excluded from false-discard/false-keep denominators.
Boundary variants are correlated: 90 rows do not certify statistical independence
or population rates. Mock deltas verify matrix arithmetic, not JEV quality.
This small pilot does not meet the design's confirmatory sample/confidence gates.

## Real scoring, when David is ready

Use Python 3.11 with the existing backend environment and explicitly configured
non-production JEV gateway environment (`OMI_LLM_GATEWAY_URL` and existing gateway
auth). Do not source production account credentials. This script never loads
`.env`, reads account content, or fetches calendar data.

```sh
JEV_PILOT_LIVE=1 backend/.venv/bin/python benchmarks/jev-vs-rules/score_real.py --max-calls 100
```

The guard precedes client import. A missing gateway or insufficient explicit
call ceiling refuses the run. Each call prints latency, gateway-reported cost
when available, and outcome only. Missing billing and retry billing say
`COULD NOT DETERMINE`; never infer zero cost. The existing client can retry, so
the ceiling counts client invocations, not transport attempts or dollars.
Real outputs and accounting JSONL go under `.outputs/real/`. No real scoring
was run for this PR. The state uses a generic Speaker 0 label because raw fixtures
have no ownership metadata, preserving the shipped transcript/state shape.

## Source anchors

Baseline `7ba0b9a8e94093f553f902f24b74cff4e30a1558`:
`backend/utils/conversations/relevance_rules.py:233` (filler), `:255` (function
boundary); `backend/utils/conversations/relevance.py:164` (calendar override),
`:182` (rule dispatch); `backend/utils/conversations/relevance_jev.py:30`
(question), `:54` (state); `backend/config/jev_decisions.py:25` (pinned model).
The replay records hashes of the current branch implementation as well.
