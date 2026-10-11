# Complete memory evidence in chat tools

The active memory list and search tools already returned full memory content.
The older 280-character chat adapter is not the active entrypoint. The issue
addressed here is the active list tool's final character slice: it could retain
a claim's beginning while dropping its trailing exception. REST list/search and
chat search also need a consistent response budget.

`utils/retrieval/memory_evidence.py` provides one renderer for the four active
entrypoints. Each record contains the complete JSON-quoted saved claim, its
recorded subject attribution, and the existing date/search metadata. A shared
notice distinguishes recorded attribution from verified identity and recorded
dates from current state. Quoting is an evidence delimiter, not a guarantee
against prompt injection or inaccurate source data.

The 60,000-character budget includes labels and continuation metadata. Claims
that cannot fit on this page are deferred whole. A claim too large for any page
is explicitly omitted whole; list pagination advances past it to avoid an
infinite loop. Source citations include only emitted claims. If the underlying
read reports an exhausted scan budget, the response reports the partial scan
without advertising a resumable list offset. The saved memory itself is untouched. Search omissions require
a narrower search; the list continuation offset applies to the same filters
and ordering and is not a snapshot-stable cursor under concurrent writes.

This changes the presentation of existing memories. It does not create a
profile or belief store, alter memory eligibility/ranking, or add model calls,
embeddings, database reads, or periodic jobs. It does not establish an increase
in end-to-end answer quality; that requires a paired online evaluation.

## Cost measurement

Compare actual baseline and changed tool outputs with identical retrieved rows,
query, limits, dates, and feature flags. Count the strings with the same token
estimator. Count each subsequent model request containing that result, including
later tool rounds and retries; a tool result is not necessarily read only once.
The local `cl100k_base` tokenizer matches the repository's existing `gpt-4`
counting proxy. It is not a GPT-5.6 Luna billing-token receipt.

For short-context GPT-5.6 Luna, the configured rate card
`openai.gpt-5.6-luna.2026-07-30` uses $0.20 per million uncached input tokens and
$0.02 per million cached input tokens, matching the
[official model pricing](https://developers.openai.com/api/docs/models/gpt-5.6-luna)
checked on 2026-09-21. Cache writes cost $0.25 per million. These are list-rate
estimates, not invoice amounts or proof of the deployed route.

For unchanged tool-call and output behavior:

```
monthly_delta_usd = mean_added_tokens_per_result
                  * retrievals_per_day * days * model_reads_per_result
                  * input_usd_per_million / 1_000_000
```

Use provider-reported cached/write counts for observed spend; do not assume
cache hits. If the complete input crosses 272,000 tokens, the rate tier changes
for the whole request, so the marginal formula above is insufficient. Additional
pagination, changed generated output, different model routes, and changed tool
selection also require a full-turn comparison. A smaller bounded page is not
a guaranteed cost saving if the agent fetches another page.

Existing gateway attempt accounting and `llm_gateway_user_days` rollups support
per-user measured follow-up without collecting memory text. Group by recorded
model/rate-card and include all attempts. `scripts/chat_agent_cost_report.py`
provides the existing accounting report; actual invoice reconciliation remains
separate from token-rate estimates.

## Offline replay, 2026-09-21

Replayed an owner-authorized saved snapshot through both baseline and changed
production functions with fake service dependencies and outbound network
blocked. Baseline: `a8d22af3aa7c4d506d7f320eac80e15cd9ae8feb`.
The canonical converter accepted all 1,426 eligible processed rows. Search used
18 frozen top-five result sets from an earlier offline retrieval experiment;
this measures formatting cost, not live search quality. Each result set ran
through both chat and REST search; each list entrypoint ran at limits 50 and
300, giving 40 paired cases. No model or embedding call was made.

| Retrieval | Added proxy tokens per result | Added USD/user/month at 100/day, 30 days, one uncached model read |
| --- | ---: | ---: |
| Five-result search, mean of 18 cases on each surface | 65.2 | $0.039 |
| 50-memory list, chat / REST | 436 / 485 | $0.262 / $0.291 |
| 300-memory list, chat / REST | 2,440 / 2,489 | $1.464 / $1.493 |

Search median was 65 added tokens; its p95 was about 69. The arbitrary mix of
all 40 cases averaged 204.95 added tokens; it is **not** an observed traffic mix
or a fleet average. That mix implies $0.012/$0.061/$0.123 per user per month at
10/50/100 retrievals a day and one uncached read, or three times those amounts
for three uncached reads. An assumed cache hit uses 10% of the uncached input
rate for that read; no cache hits were observed in this offline experiment.

All replay cases fit the new response limit. Therefore these measurements do
not claim savings from clipping or measure the extra calls caused by paging.
Synthetic regression tests exercise the oversized/boundary cases separately.
Input hashes, exact edited-code hashes, the executable replay, and aggregate
case receipts remain with the owner outside the public repository. Raw memory
text, identifiers, and queries are not published.
