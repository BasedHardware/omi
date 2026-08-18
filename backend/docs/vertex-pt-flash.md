# Vertex Provisioned Throughput for Gemini 2.5 Flash

We bought **5 GSU Provisioned Throughput** for `gemini-2.5-flash` in
`us-central1` so company-paid Flash text is reserved and cheaper than Gemini
API list price.

**Vertex PT: 5 GSU gemini-2.5-flash us-central1, expires ~2027-05-28.**

- SKU: `Vertex AI: Provisioned Throughput 1 Year`
- Cap: 13,450 tok/s
- First billing row: 2026-05-28
- **Expires ~2027-05-28** (1-year SKU; confirm in Cloud Console → Vertex →
  Provisioned Throughput — Commerce API was disabled, so do not invent a more
  precise date)
- Flat ~$290.32/day even when traffic is elsewhere

PT and EDP apply **only on Vertex publisher**, not AI Studio
(`generativelanguage.googleapis.com`).

## Never send company-paid Flash to AI Studio

Server-paid `gemini-2.5-flash` `generateContent` / `streamGenerateContent` must
go to:

`{location}-aiplatform.googleapis.com/v1/projects/{project}/locations/{location}/publishers/google/models/gemini-2.5-flash:generateContent`

using ADC / Workload Identity. **Never** `generativelanguage.googleapis.com`
and **never** `?key=` for that path. Missing `GOOGLE_CLOUD_PROJECT` must fail
closed — that omission is what moved Flash off Vertex on 2026-08-04 and
double-paid (reservation + API list).

The model pin is `VERTEX_PT_MODEL` in `backend/routers/desktop_proxy.py`,
sourced from `ptr.PT_MODEL_CURRENT` in
`backend/utils/llm/vertex_pt_routing.py`. Changing the company-paid Flash
default without updating that pin, this note, and the contract tests in the
same commit is the regression.

BYOK Gemini stays on the user's key / AI Studio, and is never remapped: the
user pays for the model they asked for.

## Model prices (Vertex list, captured 2026-08-18)

| Model | Input $/1M | Output $/1M |
| --- | ---: | ---: |
| `gemini-2.5-flash-lite` | 0.10 | 0.40 |
| `gemini-3.1-flash-lite` | 0.25 | 1.50 |
| `gemini-2.5-flash` | 0.30 | 2.50 |
| `gemini-2.5-pro` | 1.25 | 10.00 |

**`gemini-3.1-flash-lite` is not the same price class as
`gemini-2.5-flash-lite`** — it is 2.5x input and 3.75x output. It is cheaper
than `gemini-2.5-flash` and far cheaper than `gemini-2.5-pro`, which is why it
absorbs overflow and Pro. Promoting the client-pinned Lite lanes
(`ModelQoS.lightweight`, Windows `memory/goals/insight`) onto it would be a
large cost regression, not a saving. Those pins are deliberately untouched and
`test_client_pinned_flash_lite_is_never_promoted` holds that boundary.

## Migrating the reservation to `gemini-3.1-flash-lite`

Requested 2026-08-18; PT orders provision in ~10 business days. **No deploy is
needed when it lands.** The proxy detects it and promotes itself:

1. Company-paid text asks the reservation for `dedicated` capacity via the
   `X-Vertex-AI-LLM-Request-Type` header. Without that header Vertex silently
   spills over-cap requests onto pay-as-you-go; with it, an over-cap request
   returns 429 `Exceeded the Provisioned Throughput` instead.
2. On that 429 the proxy overflows to `gemini-3.1-flash-lite`. If a capacity
   probe is due (`_PT_PROBE_TTL_SECONDS`, 600s) the first overflow attempt asks
   for `dedicated`. That single request **is** the auto-detection: if the new
   order exists it succeeds, and if it does not it 429s and falls through to
   the on-demand call the proxy would have made anyway. Detection therefore
   costs nothing and only happens when the old reservation is already full.
3. A successful probe latches `_pt_target_ready` and logs
   `desktop_proxy pt_promotion`. From then on `gemini-2.5-flash` requests are
   served by `gemini-3.1-flash-lite` on prepaid capacity.

The positive observation is latched rather than TTL'd on purpose: a PT purchase
is long-lived, and expiring it would flap the serving model every time overflow
stopped re-probing. A vanished order still degrades safely — requests 429 and
overflow absorbs them.

The latch is **per Cloud Run instance**, held in process memory. Promotion
therefore rolls out gradually: each instance switches the first time it
overflows and probes successfully, so expect a mixed fleet for a while rather
than a single cutover instant. Grep the logs for
`desktop_proxy pt_promotion` to see how far it has spread, and set
`OMI_VERTEX_PT_MODEL` if you need every instance on one model immediately.

**Retire the old order when promotion happens.** The `gemini-2.5-flash` order
bills a flat ~$290.32/day until ~2027-05-28 whether or not traffic uses it, so
once traffic moves to `gemini-3.1-flash-lite` the old reservation is paid-for
and idle. Promotion is a code-side cutover; converting or cancelling the 5 GSU
`gemini-2.5-flash` order is a separate commercial action that has to be done in
Cloud Console, and until it is, both are billed.

## Never move dedicated traffic off a reservation early

Moving `gemini-2.5-flash` onto an on-demand model *before* the replacement
order is live pays the flat reservation fee for idle capacity **and** full
on-demand for every token — strictly worse than either alone. This is why the
flash remap is gated on observed capacity rather than shipped as a constant.
`test_flash_stays_on_the_current_reservation_until_target_capacity_exists`
holds that gate.

## Overflow is resolved against the live reservation

`OVERFLOW_PREFERENCE` is a ladder, not a pin, and
`resolve_overflow_model()` never returns the model that currently holds prepaid
capacity. Once `gemini-3.1-flash-lite` *is* the reservation, overflow steps
past it to `gemini-2.5-flash-lite` automatically. Pinning overflow to
`gemini-3.1-flash-lite` would, after promotion, dump degraded traffic onto the
budget the quota exists to protect — that is
`FC-degraded-fallback-consumes-protected-budget` (PR #10686), and the guard is
`test_overflow_never_targets_the_live_reservation`.

## Gemini 3.x changed the thinking contract

2.5 models take an integer `thinkingConfig.thinkingBudget`. 3.x models take
`thinkingConfig.thinkingLevel`, and **thinking cannot be disabled** — the floor
is `minimal`. Thinking tokens bill as *output*, so sending a 2.5-style budget
to a 3.x model risks an uncapped reasoning trace at $1.50/1M: the field is
schema-valid, so it is accepted and then ignored.

`ptr.thinking_config_for()` picks by family prefix rather than exact model name,
matching how `_CACHE_KEY_MODEL_PREFIXES` handles prompt caching, and
`_retarget_thinking()` rewrites the body when overflow crosses families.

**Unverified:** whether 3.x hard-errors on `thinkingBudget` or silently ignores
it could not be settled from this host — `aiplatform.endpoints.predict` is
denied to the read-only service account, and no human ADC was live. The code is
correct either way, but the observed token counts are still worth capturing:

```
python3 backend/scripts/probe_gemini_thinking_contract.py
```

Run it with credentials that can call `generateContent` and paste the output
into this section.

## Operator overrides

All three are read per request, so a bad promotion can be corrected without
shipping code.

| Env | Effect |
| --- | --- |
| `OMI_VERTEX_PT_MODEL` | Pins the reservation model, beating auto-detection in both directions. |
| `OMI_GEMINI_OVERFLOW_MODEL` | Pins the overflow model. Rejected at resolution time if it equals the reservation. |
| `OMI_GEMINI_OVERFLOW_ENABLED` | `false` disables overflow entirely; a full reservation then returns 429 to the client. |

## Keeping the reservation for work that must be Flash

The 13,450 tok/s cap is oversubscribed, so the proxy actively keeps low-value
work off `gemini-2.5-flash`:

- **Server-paid Pro is served by `gemini-3.1-flash-lite`** ($10.00 -> $1.50 per
  1M output). The remap happens after metering, so the two Pro paths stay
  distinct: within quota a request gets `gemini-3.1-flash-lite`, and over quota
  it still demotes to `gemini-2.5-flash-lite` and keeps the cheap tier for
  heavy users.
- **Over-quota demotion targets `gemini-2.5-flash-lite`**
  (`_QUOTA_DEMOTION_MODEL`), which is `shared`/on-demand on Vertex and never
  burns the PT. Demoting to `gemini-2.5-flash` instead was the 2026-08-17
  defect that silently dumped the Insight tool loop (~11% of the reservation)
  onto the saturated PT lane.
- **Server-paid requests are capped at 2048 output tokens**
  (`_SERVER_PAID_MAX_OUTPUT_TOKENS`). No shipped desktop client sends
  `maxOutputTokens`, so everything used to inherit the 8192 default while
  output burns down the reservation at 9x. Realistic per-lane budgets are
  64–1024 visible tokens plus a thinking budget of up to 1024 (thinking counts
  toward the output limit on 2.5 models). BYOK requests keep the 8192
  default/clamp.

The desktop clients pin the low-value lanes (memory extraction, LiveNotes,
goals, task dedup/prioritization, home suggestions, Windows insight) to
`gemini-2.5-flash-lite` directly — see `ModelQoS.Gemini.lightweight`
(macOS) and the Windows assistant model pins. Task extraction stays on
`gemini-2.5-flash`: Flash-Lite measurably fails its prompt contract there
(omi-knowledge-base, vertex-pt-flash-spend, 2026-08-17 overflow bakeoff).

## Durable runtime env

`desktop-backend` compose (`backend/deploy/runtime_env/_base.yaml` →
`desktop_backend`) and the Cloud Run deploy workflows must keep:

- `USE_VERTEX_AI=true`
- `GOOGLE_CLOUD_PROJECT` = `based-hardware` (prod) / `based-hardware-dev` (dev)
- `GCP_LOCATION=us-central1`

`GEMINI_API_KEY` remains only for BYOK / emergency leftover surfaces.

## Out of scope leftovers

Realtime token mint (`desktop_realtime.py`) and the omni Live websocket
(`omni_relay.py`) still use AI Studio. Vertex Live is not wired. Those are not
the high-volume Flash text bill.

Single `embedContent` uses Vertex `:predict` when a project is set.
`batchEmbedContents` stays on AI Studio (incompatible Vertex batch shape).

## How to verify after deploy

- Cloud Monitoring `consumed_token_throughput{request_type=dedicated, model=gemini-2.5-flash}` should move
- Gemini API Flash daily $ should drop
- PT SKU stays flat (~$290/day)
- Proxy logs: `provider_route=vertex_ai`, not `ai_studio`, for server-paid Flash

Incident: 2026-08-04 cutover. GitHub #6935 / SCA-323.
