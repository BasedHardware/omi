# Chat provenance

A provenance claim is a conjunction of three independent witnesses. Any two
agreeing without the third is how a stub ships for a week.

## The three witnesses

1. **Rendered label.** Chat reads the latest `capability_receipt` on the
   assistant message and prints it in `.chat-agent-capability`.
   - Canned gateway (`tier: "unknown"`, adapter `omi.local-test-gateway.v1` or
     the legacy `omi-llm-gateway` names) → `Local test gateway`.
   - Real proxy (`tier: "real-provider"`, adapter
     `omi.local-model-gateway.v1/<model>`) → `External model response (<model>)`.
2. **`service.boot`.** The service probes the configured gateway's `/ready` at
   boot and records the gateway's own `schema` as `gateway_kind` (and `model` as
   `gateway_model` when present). Values: `none` (no gateway), the schema id, or
   `unknown`. A socket that does not answer `/ready`, or answers without a
   schema, is `unknown`. It is never guessed and never defaulted to real.
   Reachability is not provenance.
3. **Declared intent.** `OMI_CHAT_MODEL=real` selects the real-model proxy;
   unset/`test` selects the canned local test gateway. This is the operator's
   claim about which process should be listening. It is not evidence that a
   model produced the tokens.

`tier: "real-provider"` is derived **only** when `/ready` declared
`real_model_proxy: true` on a body that also carried a schema. The closed
`capability_receipt` field set (`adapter`, `capabilityId`, `deterministic`,
`tier`) carries that identity in `adapter` (`schema` or `schema/model`) and
`tier`. `capability-tier-report.ts` still refuses to let that receipt claim
real agent success: gateway-routed is not provider-observed.

## How to read them

```bash
bun run logs --event service.boot
# gateway_kind=omi.local-test-gateway.v1          canned
# gateway_kind=omi.local-model-gateway.v1 gateway_model=glm-4.7   real proxy
# gateway_kind=unknown                           configured but /ready silent
# gateway_kind=none                              no gateway
```

Open Chat, expand "How Omi handled this response", and read the capability
chip. Compare it to `gateway_kind` and to `OMI_CHAT_MODEL`. All three must
agree.

## How a test asserts agreement

Negative control (required): boot against the canned gateway
(`integration/local-test-gateway.mjs`). Assert:

- persisted assistant text equals `Local test gateway answered.`
- `capability_receipt.tier` is not `real-provider`
- the rendered chip equals `Local test gateway` and does **not** contain
  `External model response`

Happy path (real proxy): assert the chip names the model, `tier` is
`real-provider`, and the text is **not** the canned string. Do not assert the
model's exact words; they are nondeterministic.

The pair of tests is `apps/service/chat/chat-provenance.test.ts` (boot +
persisted text + receipt) and the ChatProduction cases in
`frontend/packages/surfaces/test/chat-live-rendering.test.mjs` (the label the
user reads). The headed control-acceptance harness (`integration/control-acceptance/`)
joins all three witnesses before it will print `CONTROL chat=streamed-and-persisted`:
the chip from the page, `service.boot` from the telemetry JSONL, and
`OMI_CHAT_MODEL`. Canned-while-declaring-real is `provenance-mismatch`.
