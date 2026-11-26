# v3 builder summaries leave the Flex-first list

The v3 builder writes each conversation summary through
`omi:auto:conversation-v3-summary`. Until this change the LLM gateway treated
that lane as Flex-first: it tried OpenAI's Flex tier (half the token price) for
up to 10 seconds and called the Standard tier only after Flex failed or ran out
of time. The lane is now removed from `DEFAULT_FLEX_FIRST_LANES`, so the summary
goes straight to Standard. `omi:auto:conv-structure` and `omi:auto:memory-l1`
stay Flex-first.

## Why

Flex almost never serves this lane, so the list entry bought a small discount
and a long wait.

Production gateway cache receipts, 66 hours ending 2026-11-24 04:15 UTC (the
receipts are sampled, so these are shares, not totals):

| Outcome on `conversation-v3-summary` | Share of summaries |
|---|---|
| Served on Flex | 5.1% |
| Served on Standard | 94.9% |
| Served on Standard after a discarded first attempt was logged | 92.6% |

- **What Flex saved.** Flex-served summaries carried 4.1% of the lane's prompt
  tokens, and Flex is a 50% discount, so the lane saved about 2% of its token
  cost. That is what this change gives up.
- **What Flex cost.** A Flex attempt that times out holds the summary for the
  whole 10-second cap before Standard starts. On a local stack with production
  settings every discarded attempt ended at 10.0 s, and the same 145-word
  transcript took 20.0 s from End to stored summary on the Flex-first lane
  against 8.7 s on a Standard lane.
- **Why a longer cap does not help.** With the cap raised to 30 s locally, Flex
  answered 3 of 12 summaries, each in 25 to 30 s. The other 9 fell back after
  losing 12 to 30 s and took 36 to 44 s in all. Standard answers this request
  in about 7 s at the median and about 11 s at the 90th percentile (estimated
  from the gap between the discarded attempt and the Standard receipt on the
  same gateway pod).

The receipts do not record why a first attempt was discarded, so the split
between Flex timeouts and fast Flex refusals in production is not known. A
refusal returns quickly and costs little time; a timeout costs the cap.

## What it changes for people

A person who taps End, or whose conversation closes after five minutes of
silence, gets the title and summary without the Flex wait. Summary text,
prompt, model (`gpt-6-luna`, low reasoning) and task extraction are unchanged.

## Rollout and rollback

The gateway reads the list at request time. `LLM_GATEWAY_FLEX_FIRST_LANES`
overrides the default: to put the lane back, set it to
`omi:auto:conv-structure,omi:auto:memory-l1,omi:auto:conversation-v3-summary`
on the gateway. Production does not set the variable today, so the new default
applies when the gateway deploys.

## Reading it after deploy

- `llm_gateway_flex_first_total{lane_id="omi:auto:conversation-v3-summary"}`
  stops increasing.
- `omi_conversations_v3_end_to_summary_seconds` should drop by up to the old
  cap for most summaries.
- Usage for the lane stays under feature `conversation_v3_summary`; its
  `traffic_type` becomes `default` for every row.

Memory extraction (`omi:auto:memory-l1`) runs after the summary in the same
builder pass and is still Flex-first. Its Flex serve rate was not measured for
this change.
