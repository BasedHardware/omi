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

Conversation notes stay on GPT-5.6 Luna. The gateway `conv_structure` override
retains low reasoning; the direct/legacy profile and existing recovery behavior
are unchanged. There is one writer call, with the existing deadline and no added
retry or revision pass. L1 memory also stays on Luna, and the shared-prefix cache
optimization remains enabled when eligible.

The full conversation prefix, response schema, task/event extraction rules and
section-to-overview projection are preserved. Independent memory extraction
still receives the full transcript. When external text lacks segment markers,
the prompt explicitly requires empty citation lists rather than invented IDs.

`tests/unit/test_conversation_notes_v2.py` exercises the real writer with
controlled provider responses: multiline bullet projection, marked and unmarked
sources, action metadata, placeholders, shared-prefix construction and cache
compatibility against real gateway/direct routes. Prompt-text assertions verify
the contract, not whether a model obeys it. Run the backend selector and `test.sh`
for the component verification contract.

## Cost and diagnostic comparison

The model, reasoning setting, call count and cache behavior are unchanged from
the base branch. The prompt is longer, and generated-note length varies, so this
is not a promise of identical token usage. Published standard Luna pricing on
September 7, 2026 is $0.20 per million input tokens and $1.20 per million output
tokens; cached input has a separate lower rate. See the [official Luna model
documentation](https://developers.openai.com/api/docs/models/gpt-5.6-luna).

Seven previously inspected difficult conversations were replayed with the same
prompt at low and high reasoning on Chat Completions. Each arm used 33,585 input
tokens. Low used 4,165 output tokens; high used 12,223. At uncached standard rates,
that is approximately $0.0117 versus $0.0214 for all seven (about 1.83x). Median
direct-call time was 7.7 versus 15.3 seconds. These are diagnostic estimates,
including reported reasoning usage, not invoices or production forecasts.

A broader high-reasoning replay still conflated companies, inferred an unsupported
subject and added a currency. A draft/revision experiment corrected some errors
but retained others; one revision call timed out and was not retried. An
extract-quotes-then-write experiment also lost useful detail and made unsupported
claims despite valid quotes. None demonstrated enough consistent benefit to
justify adding its cost or complexity to this change. Their receipts remain
private; the shipped proposal adds neither higher reasoning nor another pass.

## Evidence boundaries

Offline replay uses the actual writer's prompt assembly and response parser,
replacing the provider seam with direct OpenAI calls and `store=false`. It does
not exercise a deployed gateway, endpoint or application rendering. Raw sources,
outputs and all failed or unresolved attempts remain private. Four exploratory
blind user comparisons informed the sentence-bullet style; later inspected
replays must not be described as an unseen holdout.

Valid citation IDs prove membership, not support for each clause. Prompt guidance
cannot guarantee attribution, coverage or formatting on
noisy transcripts. Review still needs to check whether fluent prose invents
relationships, normalizes uncertain names, adds units or loses meaningful detail.

## Final low-reasoning replay

The final prompt completed 14 inspected source conversations, five fictional
probes and one unmarked-source probe using Luna/low Chat Completions. All 20
responses parsed through the real writer. Emitted section IDs belonged to their
sources; the unmarked case emitted empty lists, and one unintelligible source
correctly returned an uncertainty overview with no sections. These are structural
checks, not an overall quality score.

The 14 source calls used 61,779 input and 8,678 output tokens, approximately
$0.0228 total at uncached standard rates. Median direct-call time was 7.2 seconds,
maximum 11.0 seconds. In four paired comparisons against the original prompt,
estimated cost was $0.00788 for the candidate versus $0.00831 for the control.
This small sample does not establish savings in production.

The candidate produced connected sentence bullets and removed incidental material
in some cases, but sometimes omitted useful everyday detail. Source review still
found a company conflation, added currency, garbled mechanics and a film-rating
attribution error. The PR does not claim that readability improvements solve
factual fidelity; higher-compute experiments are explicitly rejected, not hidden.
