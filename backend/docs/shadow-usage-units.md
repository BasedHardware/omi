# Shadow usage units

The subscription version is price-keyed; legacy APIs continue to own admission.
`config.plan_catalog.entitlement_budget_units` evaluates dormant ladder budgets.
`config.rate_card` prices inputs from an immutable, hash-pinned card at
$0.001/unit. `RATE_CARD_VERSION` selects `v1` or `v2`; unset defaults to `v1`,
so existing behavior remains unchanged. The loader checks each file against
`config.rate_card_versions`; independent literals in `test_rate_card.py` pin
the registry and file bytes. Updating the registry alone cannot approve a
changed card. A later revision requires another version file.

`rate_card_v1.json` remains byte-identical. `rate_card_v2.json` corrects
Gemini 2.5 Flash to the Vertex AI Gemini 2.5 Standard tab rates verified
2026-10-18 (https://cloud.google.com/vertex-ai/generative-ai/pricing; $0.30
input, $0.03 cached, $2.50 output per million tokens), matching the Flash
rates v1 already carries, and adds Gemini 3.8 Flash at its standard rate
effective 2027-01-01 ($1.50 / $0.15 / $7.50). Other v1 entries carry forward.
No vendor feed changes either card. Selecting v2 changes the units charged for
features using those model rates; it does not alter any plan budget number or
admission behavior.

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
reasoning exactly once (missing inclusion metadata defaults to extra reasoning).
Gemini audio without a modality price, and Gemini tool-use prompt tokens, remain
estimated with explicit missing-rate reasons, including realtime tool tokens. Flex and reserved capacity do not discount shadow units.
Realtime modality rates and image output rates are pinned separately. Missing
or empty modality counts can use an exact matching pinned legacy realtime card amount,
with estimated completeness. Unknown models/rates or funding are incomplete,
never a complete zero. BYOK, custom and on-device provider usage is zero; Omi-paid
extraction of a customer-funded transcript still draws LLM units independently.

Transcription consumes fractional accepted Omi-funded speech seconds. In paths
without that quantity, elapsed duration × 0.32 is explicitly estimated. The
Parakeet compute card ($0.02/hour) and provider-unknown proxy are provisional.
Provider routing may change without changing these pinned input prices. Deepgram
streaming includes Nova-3 multilingual $0.0058/min plus always-on diarization
$0.0020/min = $0.468/hour (https://deepgram.com/pricing); conditional keyterm
fees are outside this flat rate. Modulate uses the multilingual transcription
WebSocket SKU `velma-2-stt-streaming`, $0.06/hour
(https://platform.modulate.ai/pricing), distinct from Velma Triage.

Free's dormant speech basis uses the conservative maximum Free-routable managed
provider, Deepgram. origin/main routing config has no fixed accepted-speech
shares: language, requested provider, ramps, capacity and health affect selection.
The standard chat uses 3 uncached input +
11667 cached input + 49 output gpt-6-luna tokens. These are componentwise
medians over 215 Omi-funded confirmed first-attempt chat_agent calls in a
read-only metadata sample of 36000 UUID-ordered attempt documents (4000/day,
October 1–9). First attempts use retry ordinal <=1. No user identifiers or
content were projected. A preceding 36000-document scan incorrectly filtered
first attempts as ordinal 0 and returned no matches; total reads were 72000.
Five speech hours = $0.468 × 5 × L / $0.001 = 4843.614167 units;
30 standard chats = 9.089220; ceil(4852.703387) = **4853 units/month**. The Luna rate is an operator card
pending official pricing, so these dollar equivalents remain provisional.
This does not switch Free accounts to ladder v1. Display equivalents use the
user-routed accepted-speech `speech_provider_shares` (nonnegative, summing to one),
or a known single `speech_provider`, plus supplied recording/chat overhead.
Without a supplied mix they use the same conservative Deepgram maximum; these remain
internal helpers with no API/client surface.

## Persistence and reads

`database.usage_units` projects units into the same `hourly_usage` set/merge
writes and the existing `llm_gateway_user_days` rollup writes. Sync's content
marker remains in its existing transaction. Gateway attempt identity remains
the canonical deduplication boundary. Each immutable attempt has a
`usage_units_v1` or `usage_units_v2` annotation with its explicit card version;
hourly documents and user-day rollups likewise keep separate `shadow_v1` and
`shadow_v2` projections. The default reader sums their stored units across card
versions because both cards keep the same $0.001 unit; it reports the active
`RATE_CARD_VERSION` and the versions present in the total. Passing an explicit
version reads that card's projection alone. Neither path reprices historical
data, so v1 history retains its original meaning. LLM retries are separate cost
attempts; duplicate attempt IDs do not add units. Provider counters are never
copied into request content.

Live provenance follows the provider serving at flush time. A Deepgram BYOK
key only excludes cloud Deepgram; Parakeet/Modulate remain Omi-funded, and
self-hosted Deepgram retains its provider identity with the explicit unlisted-rate compute proxy.
Custom STT is zero for transcription while funded downstream LLM calls still
consume units. Current listen, sync and proxy counters are estimated as counter
seconds × 0.32; no producer falsely declares these accepted speech. Sync's
counter is already initial VAD duration, so its mandated ratio proxy can
particularly underestimate accepted speech; that basis is recorded. The
optional accepted-speech hook preserves fractional quantities when available.
Invalid or nonfinite accepted quantities fail open inside pricing: the legacy
write proceeds and the shadow leaf records missing coverage.
Sync v1 currently stamps Omi-funded/unknown-provider estimates without successful
segment funding provenance. Deepgram BYOK work can therefore be overstated in
shadow units; do not use that projection for admission or billing. Correcting
this requires carrying successful segment provider/funding through aggregation.
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
