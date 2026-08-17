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

The model pin is `VERTEX_PT_MODEL = 'gemini-2.5-flash'` in
`backend/routers/desktop_proxy.py`. Changing the company-paid Flash default to
Lite / 3.1 without updating that pin, this note, and the contract tests in the
same commit is the regression.

BYOK Gemini stays on the user's key / AI Studio.

## Keeping the reservation for work that must be Flash

The 13,450 tok/s cap is oversubscribed, so the proxy actively keeps low-value
work off `gemini-2.5-flash`:

- **Over-quota Pro demotes to `gemini-2.5-flash-lite`**
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
