# Conversation summaries outside v3 leave the Flex-first list

Conversations that are not on v3 get their title, summary and tasks from one
call on `omi:auto:conv-structure` (`gpt-6-luna`, low reasoning). Until this
change the LLM gateway treated that lane as Flex-first: it tried OpenAI's Flex
tier (half the token price) for up to 15 seconds and called the Standard tier
only after Flex failed or ran out of time. The lane is now removed from
`DEFAULT_FLEX_FIRST_LANES`, so the summary goes straight to Standard.
`omi:auto:memory-l1` stays Flex-first.

## Why

Flex times out on about half of this lane's attempts, and each timeout holds
the summary for the whole cap.

Production gateway attempt ledger (`llm_gateway_attempts`), seven days
2026-11-18 to 2026-11-24, 8,000 sampled rows a day:

| Outcome of the Flex attempt | Share of attempts |
|---|---|
| Flex answered | 39% |
| Timed out at the 15 s cap, then Standard | 52% |
| Refused quickly (429), then Standard | 9% |

By day, Flex answered 26% to 38% of attempts on weekdays and 58% to 65% at the
weekend; timeouts were 49% to 64% on weekdays.

- **What Flex saved.** Flex answers the smaller requests (about 300 output
  tokens on average against about 500 for the ones that fell back), so its
  share of cost is below its share of calls. The discount came to 13% of what
  the Flex-eligible calls would cost on Standard and 4% of the lane's total.
  The rest of the lane is the notes agent's tool turns, which never try Flex.
  That is what this change gives up.
- **What Flex cost.** About one summary in two waited 15 seconds before its
  Standard call began. Callers of this lane give up at 60 seconds, so the wait
  also comes out of the time Standard has to answer.

The ledger records no cost for a failed attempt, so whether the provider bills
a Flex attempt that timed out is not visible here.

On a local stack with production settings, the summary of a 6,100-token request
was re-run through `POST /v1/conversations/{id}/reprocess`:

| Case, same transcript | Discarded Flex attempt | Summary answered after |
|---|---|---|
| Flex-first, 15 s cap, 3 of 4 runs | 15.2 s | 21.9 to 22.3 s |
| Flex-first, 15 s cap, 1 of 4 runs | 0.7 s (refused) | 5.7 s |
| Standard only, 4 of 4 runs | none | 5.6 to 9.2 s |

## What it changes for people

A conversation outside v3 gets its title and summary without the Flex wait.
Summary text, prompt, model and reasoning effort are unchanged.

## Rollout and rollback

The gateway reads the list at request time. `LLM_GATEWAY_FLEX_FIRST_LANES`
overrides the default: to put the lane back, name it there together with the
other lanes to keep. Its 15-second cap is still in `FLEX_FIRST_LANE_TIMEOUT_MS`
and applies when the lane is named. Production does not set the variable
today, so the new default applies when the gateway deploys.

## Reading it after deploy

- `llm_gateway_flex_first_total{lane_id="omi:auto:conv-structure"}` and
  `llm_gateway_conv_structure_flex_fallback_reason_total` stop increasing.
- Ledger rows for the lane carry `traffic_type` `default` and
  `retry_ordinal` 1.
