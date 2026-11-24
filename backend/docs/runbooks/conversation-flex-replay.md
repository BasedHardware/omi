# Conversation Flex and outline cache replay

SCA-4247 uses the existing Luna lanes.
Cloud Tasks CAPTURE_END structure and L1 fanout opt in using the recording
close time. An admitted phase has at most 57 seconds of gateway time, with
Standard reserves of 40 seconds for structure, 24 for L1, and 42 for V3 summary.
A phase with less than its full Standard reserve uses its existing realtime
deadline. Summary opts in only during the existing background model call.
Interactive, catch-up, and pusher socket finalization use Standard with their
existing transport deadlines. Tool turns, streaming requests, BYOK, and
caller-selected tiers are excluded. The shared gateway retries one Flex 429 if the provider
delay and another useful attempt fit. Timeouts go directly to Standard because
the first provider attempt may have charged.

Only an authenticated builder task can request nonstreaming Flex for a finished,
non-manual outline with headroom before close + 2 hours. It reserves 45 seconds
for Standard and 15 for publication, with at most 110 seconds of gateway time
per builder pass. A foreground open can take the existing lease during the
background model call. The old token cannot publish, although a provider call
already in flight can still charge. The durable outline attempt count reserves a
second slot for the realtime path.

Set `LLM_GATEWAY_BACKGROUND_FLEX_RETRY=off` in the gateway and backend to restore
the previous Flex behavior. The gateway's `LLM_GATEWAY_FLEX_FIRST_LANES` can exclude
one of the three existing lanes from Flex. Set
`LLM_GATEWAY_BACKGROUND_OUTLINE_FLEX=off` in the backend and gateway to restore
streamed Standard outlines, and `OMI_OUTLINE_CACHE_PREFIX=off` in the backend to
restore the original prompt and cache policy.

## Offline gate

Use approved fixture transcripts or synthetic fixtures. Run the baseline and each
candidate independently on the same model with isolated result caches. Include
standard streaming versus nonstreaming Flex, legacy versus stable prefix, and a
write-opt-out control using explicit cache options with no marked breakpoint.
Blind output graders to the variant. Replay open and append races, and chat and
search both before and after the existing extraction deadline.

For each lane and comparison arm, record at least 300 paired cases in a JSONL file
with no prompt or response text. Provide:

- `id`, `lane`, and `tags` for the case and `expected_boundaries` for outlines.
- `baseline` and `candidate` objects with `model`, `schema_ok`, `grounded`,
  `critical_errors`, `missed_promotions`, `duplicate_publications`,
  `due_extractions_pending`, and `deadline_met`. Count critical timeline,
  factual or ownership errors during blind review.
- For outlines, add each arm's `boundaries` (numbered starts, excluding the mandatory
  first line), `title_ok`, and `foreground_ms` in foreground cases.
- Attach provider `usage.prompt_tokens` and
  `usage.prompt_tokens_details.{cached_tokens,cache_write_tokens}` for each arm.
  Sum usage across attempts when measuring cost, including fallback and retries.
  Record a zero only when the corresponding usage field is known to be zero.

Run `python backend/scripts/evaluate-conversation-flex.py <lane> <receipts.jsonl>`.
The evaluator rejects missing strata, checks the paired noninferiority bound at
one percentage point, compares foreground latency, and prints weighted cache
hit shares for both arms. Compare repriced cache reads and writes separately over
matched traffic at the same rate card before booking savings. The Nov 24 baseline
in SCA-4247 was 9.05% of outline input tokens reported as cache hits.

Release is contingent on the paired gate, SCA-3677 transcript access, SCA-3655
open promotion, and SCA-3657 chat/search freshness. The local deterministic
transport and concurrency checks do not measure model quality or served spend.
