# Conversation Flex and outline cache replay

SCA-4247 uses the existing Luna lanes.
Cloud Tasks CAPTURE_END structure and L1 fanout opt in using the recording
close time. An admitted phase has at most 57 seconds of gateway time, with
Standard reserves of 40 seconds for structure and 24 for L1. A phase with a
positive budget too short for Flex uses Standard within that budget. V3 summary
uses Standard by default, following main commit `8b3cc87cef7`.
With the default-on switch, interactive, catch-up, pusher socket, sync
finalization, silent backfill, server recovery and derive calls use Standard
unless they enter an eligible durable scope with time remaining. Tool turns,
streaming requests, BYOK, and caller-selected tiers are excluded from scoped
Flex. The gateway can retry one receipt-free upstream Flex HTTP 429 when another
useful attempt fits. In scoped mode, only a confirmed receipt-free 429 can use
the Standard reserve. Any other Flex failure ends scoped dispatch. Standard
retries and failover share the caller's original deadline. Flex timeouts end
dispatch in both modes because the provider may bill the timed-out call.

Only an authenticated builder task can request nonstreaming Flex for a finished,
non-manual outline with headroom before close + 2 hours. It reserves 45 seconds
for Standard and 15 for publication, with at most 110 seconds of gateway time
per builder pass. A foreground open can take the existing lease during the
background model call. The old token cannot publish, although a provider call
already in flight can still charge. The Flex attempt has its own counter and
leaves both realtime attempts available. On a background gateway timeout the
builder can publish the deterministic outline within its publication budget.
The fallback stays out of the result cache so an open can try Standard.

Set `LLM_GATEWAY_BACKGROUND_FLEX_RETRY=off` in the gateway and backend to disable
scoped Flex and use legacy Flex-first for configured lanes. Legacy Flex-first
can fall back to Standard on non-timeout failures. To roll a lane back to
Standard, exclude it from `LLM_GATEWAY_FLEX_FIRST_LANES`. Set the lane list to
`off` to disable every listed lane and turn off the separate outline Flex arm
for an all-Standard rollback. The outline experiments default off.
Release owns enabling `LLM_GATEWAY_BACKGROUND_OUTLINE_FLEX=on` in the backend and
gateway and `OMI_OUTLINE_CACHE_PREFIX=on` in the backend after Margin GO and the
paired replay. Enable each arm independently, starting on the approved replay
cohort. Before expanding to eligible live outlines, confirm foreground p95/p99,
the close + 2h deadline, and net spend against matched Standard traffic. Margin
checks the first full 24-hour cohort window before authorizing expansion.
Set either key to `off` to roll its arm back.

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
The evaluator requires at least 30 distinct pairs per required stratum, with
at least 100 foreground outline pairs for the p95/p99 comparison. Tags can
overlap. It reports the counts, checks the paired noninferiority bound at one
percentage point, and prints weighted cache hit shares for both arms. Compare repriced cache reads and writes separately over
matched traffic at the same rate card before booking savings. The Nov 24 baseline
in SCA-4247 was 9.05% of outline input tokens reported as cache hits.

## Gateway readback

Use `sum by (lane_id) (increase(llm_gateway_flex_first_total{outcome="attempt"}[24h]))`
as the attempt denominator for both legacy and scoped Flex after this release.
Use provider-confirmed Flex usage to measure served share. The old
`flex + fallback_standard` proxy does not capture intermediate rejections or
terminal attempts and is only suitable for pre-change windows.

Release is contingent on the paired gate, SCA-3677 transcript access, SCA-3655
open promotion, and SCA-3657 chat/search freshness. The local deterministic
transport and concurrency checks do not measure model quality or served spend.

`OMI_V3_SUMMARY_FIRST_OPEN_GATING` defaults off. With it off, summary
reads keep the existing generation path, background enrichment proceeds
without waiting for a detail open, and the existing background processing
marker retains its queue semantics. Enable only after SCA-3677 preserves
full MCP and API agent read access to deferred conversations. Set the
switch back to `off` to restore the default behavior. The switch is
independent of the background Flex recovery and outline switches.
