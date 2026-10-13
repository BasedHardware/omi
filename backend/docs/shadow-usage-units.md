# Shadow usage units

The subscription version is price-keyed; legacy APIs continue to own admission.
`config.plan_catalog.entitlement_budget_units` evaluates dormant ladder budgets.
`config.rate_card` prices inputs from immutable `rate_card_v1.json` at $0.001/unit.
The v1 SHA-256 is pinned in the loader and its unit test; changes require a new
version file. No vendor feed or environment variable changes the rate card.

The loading factor is the ratio of summed fully loaded variable costs to summed
vendor list costs in `omi_finops.unit_cost_user_day`, September 22–October 9,
2026: 24450.274588023036 / 11812.180030023044 = 2.069920584166319783906855281.
Numerator: fully_loaded + stt_vendor_low - shared_headcount. Denominator:
llm_openai_measured + llm_direct_residual + llm_gemini_list_memo + stt_vendor_low.
These are allocation/model proxies, not audited provider invoices. The numerator
retains the reservation, while Gemini inputs are priced at list rates. The flat
request placeholder overlaps some infrastructure already loaded by L; treat it
as provisional until request-level allocation is available.

Calls use cached/uncached input, cache-write and billable output tokens, including
reasoning exactly once. Flex and reserved capacity do not discount shadow units.
Realtime modality rates and image output rates are pinned separately. Missing
modality counts can use an exact matching pinned legacy realtime card amount,
with estimated completeness. Unknown models/rates or funding are incomplete,
never a complete zero. BYOK, custom and on-device provider usage is zero; Omi-paid
extraction of a customer-funded transcript still draws LLM units independently.

Transcription consumes fractional accepted Omi-funded speech seconds. In paths
without that quantity, elapsed duration × 0.32 is explicitly estimated. The
Parakeet compute card ($0.02/hour) and provider-unknown proxy are provisional.
Provider routing may change without changing these pinned input prices.

Free's dormant mix uses Parakeet and a standard chat of 3 uncached input +
11667 cached input + 49 output gpt-6-luna tokens. These are componentwise
medians over 215 Omi-funded confirmed first-attempt chat_agent calls in a
read-only metadata sample of 36000 UUID-ordered attempt documents (4000/day,
October 1–9). First attempts use retry ordinal <=1. No user identifiers or
content were projected. A preceding 36000-document scan incorrectly filtered
first attempts as ordinal 0 and returned no matches; total reads were 72000.
Five speech hours = 206.992058 units; 30 standard chats = 9.089220;
ceil(216.081278) = **217 units/month**. The Luna rate is an operator card
pending official pricing, so these dollar equivalents remain provisional.
This does not switch Free accounts to ladder v1. Display equivalents use the
card plus supplied recent-mix overhead per recording hour/chat; these remain
internal helpers with no API/client surface.
