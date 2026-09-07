# Conversation note style

`get_conversation_notes` in `utils/llm/conversation_processing.py` owns the
section-based conversation note prompt. Section bodies use readable sentence
bullets: related details belong together, while a distinct proposal, tradeoff,
response, or social experience can have its own bullet. Short headings group the
main threads. The note should be easy to follow without adding causal or temporal
connections that the source does not support.

The density guides apply to the **entire note**, not each section: roughly 80
words for short transcripts, 200 for medium transcripts, and 400 for long ones.
They are flexible guides, not output truncation or quotas. Select meaningful
threads and retain their concrete details; do not inventory every number, name,
playback command, or unclear fragment. Social experiences and personal boundaries
are meaningful content too.

The prompt distinguishes proposals, intentions, reported actions, and completed
work; separates past anecdotes from current plans and different entities from
one another; and forbids completing clipped quantities or reconstructing unclear
mechanics. Existing identity-metadata spelling rules still apply. Source segment
IDs belong in `source_segment_ids`, not the visible prose.

## Integration and verification

The gateway `conv_structure` override selects GPT-5.6 Sol with medium reasoning.
Repeated diagnostic replays on Luna still merged unrelated entities and completed
ambiguous quantities; the Sol comparison improved those cases. This is a quality
tradeoff, not a demonstrated population-wide win. Legacy/direct routing remains
Luna, including the existing recovery path, so its output may differ.

Notes and L1 memory no longer share an OpenAI model cache in gateway mode.
`shared_conversation_cache_supported()` therefore disables their cross-task cache
optimization there. Direct mode retains it when the configured profiles match.
The full conversation prefix, call count, response schema, task and event
extraction rules, and section-to-overview projection are preserved. Independent
memory extraction still receives the full transcript.

Sol costs materially more. At the September 7, 2026 published standard rates,
input/output cost per million tokens is $4/$20 for
[Sol](https://developers.openai.com/api/docs/models/gpt-5.6-sol) versus $0.20/$1.20
for [Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna), before
caching or other discounts. Actual cost also depends on reasoning/output length
and losing cross-model cache reuse. The gateway's dated accounting rate cards
remain unchanged; their estimates are not an invoice. No timeout or retry budget
was increased. Reverting the model override also requires revisiting the cache
compatibility decision and its test.

`tests/unit/test_conversation_notes_v2.py` exercises the real writer with a
controlled provider response, including multiline bullet projection, action
metadata, placeholder removal, shared-prefix construction, and cache compatibility
for the gateway and direct routes. Its prompt-text assertions
are contract checks; they do not prove that a model follows the instructions.
Run the backend selector and `test.sh` for the component verification contract.

Quality evidence comes from offline model replay through the real writer's prompt
assembly and response parser, with the provider seam replaced by direct OpenAI
calls. Raw sources and generated notes remain private. This measures note
construction and source fidelity; it does not measure a deployed gateway, app
rendering, endpoint latency, or population-wide user preference. Four exploratory
blind comparisons informed the style; they do not establish a statistical win.

Prompt guidance cannot guarantee perfect attribution, coverage, or formatting on
noisy transcripts. Exact-ID membership is only a structural check: reviewers must
check what the cited segments actually support and whether important content was
lost. Do not treat fluent wording or valid citations as proof of correctness.

## September 7 diagnostic replay

The final prompt and Sol/medium completed 14 previously inspected conversations
and five fictional adversarial cases using Chat Completions with `store=false`.
All 19 responses passed the real writer parser; all emitted section IDs existed
in their source and all section bodies started with bullets. The fictional cases
preserved past/current separation, unfinished quantities, joke status, population
scope, and distinct companies. They are diagnostic examples, not a held-out
benchmark or a statistical score.

For the 14 conversation calls, reported usage totaled 61,485 input and 15,268
output tokens. Median direct-call wall time was 15.9 seconds, maximum 33.8 seconds;
these are neither gateway latency nor a production SLA. Final notes ranged from
27 to 310 words. Targets are intentionally soft.

Source review still found limitations: an inferred currency in one cost fragment,
an ambiguous family relationship resolved too specifically, normalization of an
uncertain game name, and some peripheral detail retained. Citation membership
does not establish clause-level support. Do not characterize this candidate as
hallucination-free or automatically approved for deployment. Earlier unsuccessful
candidates and unresolved transport attempts remain in the private experiment
ledger rather than being discarded from accounting.
