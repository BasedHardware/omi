# R3.2 Plan — Call-Site Cutover (updated per David 2026-07-02)

## Origin (David's feedback)

> - First real cutover should still be chat-structured / extraction-style work
> - I don't mind shadowing other lanes, but shadowing cannot affect user latency or behavior

## First cutover: `omi:auto:chat-structured`

**Why chat-structured first**:
- It's the only `prod_ready` lane in the catalog (per R0.5)
- It has a real surface (openai.chat_completions) + provider (openai) + eval (R0's `chat_extraction.requires_context` feature bundle)
- It's the R0 pilot — already in production
- It's an "extraction-style" task per David's preference

## Shadow latency invariant

**P1: shadowing cannot affect user latency or behavior.**

R3.1's design already enforces this:
- `ShadowCutover` runs both paths in parallel
- Returns the control response (NOT the gateway response) to the caller
- The gateway response is recorded + observed in the background

The R3.2 implementation must include a test that asserts:
- The control response is returned to the caller in the same wall-clock time regardless of gateway behavior
- Specifically: a slow gateway (e.g., 5-second delay) must NOT delay the control response

This is testable: a `FakeGatewayClient` with a 5-second delay, and assert the call returns within ~10ms (control's own latency, not gateway's).

## Implementation (planned)

### Where to wire `ShadowCutover`

The chat-structured call site is in `backend/utils/llm/gateway_client.py::invoke_chat_structured_gateway`. But that function ALREADY calls the gateway directly. We need to find the original direct-provider call (the "control path") and wrap it with `ShadowCutover`.

Looking at the codebase, the direct-provider call for chat-structured is in `backend/utils/llm/clients.py` or similar. The wiring would be:

1. Find the existing direct-provider call for chat-structured
2. Wrap it with `ShadowCutover(control=existing_call, gateway=invoke_chat_structured_gateway, ...)`
3. The cutover returns the control response (existing behavior)
4. The gateway response is observed in the background

### Changes per file

- `backend/utils/llm/clients.py` (or wherever the direct-provider call lives): wrap with `ShadowCutover`
- `backend/utils/llm/gateway_observability.py` or new `backend/utils/llm/shadow_observability.py`: wire real `AlertSink` + `MetricsSink` (R3.1's Protocol-based design makes this easy)
- `backend/llm_gateway/gateway/resolver.py` already updated for R0.5 — no further changes

### PR structure (per PLAN.md §R3: "One PR per backend domain for reviewability")

- **PR-1 (this)**: chat-structured + chat-extraction (extraction-style) — bundle for atomic rollback
- **PR-2 (later)**: retrieval + post-processing (different domain)
- **PR-3 (later)**: realtime-ptt (requires Anthropic provider registration — R3 scope)

The first PR (this one) targets the extraction-style work per David's preference.

## Tests (planned)

- Unit: `ShadowCutover` returns control within 10ms even when gateway delays 5s
- Unit: control path latency is independent of gateway path latency
- Unit: gateway failure (timeout / exception) returns control response
- Unit: gateway success does NOT change the returned response (control is always returned in R3.1)
- Integration: chat-structured end-to-end against the local gateway
- Integration: 14-day shadow metric collection (in production, observed by Prometheus + Sentry)

## Acceptance criteria (planned)

1. The existing direct-provider call for chat-structured is wrapped with `ShadowCutover`
2. The control response is returned in the same wall-clock time as before (latency invariant)
3. The gateway response is recorded into `ShadowMetrics` (real sinks wired in R3.2)
4. The chat-extraction lane is also wrapped (bundle for atomic rollback per PLAN.md)
5. The shadow metric dashboard shows the dual-path per-call + 24h aggregate per lane
6. Tests assert the latency invariant (control in <10ms even when gateway delays 5s)

## Out of scope (planned)

- Other lanes (realtime-ptt, retrieval, etc.) — separate R3.2 PRs
- The "drop the control path" follow-up — gated on 14 days of <1% divergence
- Internal eval set design — separate work, "table for later"

## Reference

- `.aidlc/spec.md` (R0.5 spec — updated with the catalog split)
- `.aidlc/migration_plan.md` (R0.5 migration plan)
- `backend/utils/llm/shadow_cutover.py` (R3.1's `ShadowCutover`)
- `backend/utils/llm/shadow_metrics.py` (R3.1's `ShadowMetrics`)
- `PLAN.md` §R3 (original R3 plan)
- David's 2026-07-02 feedback