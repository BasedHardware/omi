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

## Persistence and reads

`database.usage_units` projects units into the same `hourly_usage` set/merge
writes and the existing `llm_gateway_user_days` rollup writes. Sync's content
marker remains in its existing transaction. Gateway attempt identity remains
the canonical deduplication boundary, and each immutable attempt includes its
v1 unit annotation. LLM retries are separate cost attempts; duplicate attempt
IDs do not add units. Provider counters are never copied into request content.

Live provenance follows the provider serving at flush time. A Deepgram BYOK
key only excludes cloud Deepgram; Parakeet/Modulate remain Omi-funded, and
self-hosted Deepgram retains its provider identity with the explicit unlisted-rate compute proxy.
Custom STT is zero for transcription while funded downstream LLM calls still
consume units. Current listen, sync and proxy counters are estimated as counter
seconds × 0.32; no producer falsely declares these accepted speech. Sync's
counter is already initial VAD duration, so its mandated ratio proxy can
particularly underestimate accepted speech; that basis is recorded. The
optional accepted-speech hook preserves fractional quantities when available.
On-device/PTT/import paths without these writers remain coverage gaps.

Firestore write counts are unchanged: ordinary hourly writes 1→1, sync content
marker transactions 2→2, gateway attempt+day rollup 2→2. There are no new per-event
write calls or subscriptions reads for projection. MCP/API-only requests have
no existing durable usage write on cache hits, so strict zero additional writes
means their request quantities remain explicitly incomplete. Web synthesis
attempts piggyback the provisional web-tool infra charge on the existing rollup;
vendor search request fees remain unmeasured.

`get_usage_units(uid, period)` takes a timezone-aware datetime selecting a UTC
calendar month; annual plans also reset monthly. It reads one projected hourly
query, at most 31 direct hashed day-rollups, and subscription metadata. It never
scans attempts or reads user content. Outputs include used units, the price-
resolved version's budget (legacy has none), feature/funding totals, status
counts, and coverage gaps. It remains an internal helper with no route/client
surface. Missing old projections are counted as incomplete lower-bound data;
no historical document is rewritten or backfilled. Attempt delivery and
rollups retain their existing best-effort failure contract; complete capture
cannot be asserted from the rollup alone.

Hourly plan attribution now uses the existing nested-field expansion primitive
before set/merge. Reporting adds disjoint historical literal dotted fields to
new nested increments. Root meter/finops counters are unchanged, so monthly
allowance and finops extraction remain on their existing quantity. Tests use
the real Firestore protobuf serializer to verify unquoted nested field paths
and preserve the root-counter readers across both stored shapes.
