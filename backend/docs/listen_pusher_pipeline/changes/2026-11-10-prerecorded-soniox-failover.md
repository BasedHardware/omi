# Pre-recorded Modulate credit refusals fail over once to Soniox

The [pre-recorded failover contract](../../listen_pusher_pipeline.mdx#pre-recorded-modulate-credit-refusal-failover)
adds a bounded resilience hop for the 2026-11-10 Modulate credit outage. Ordinary
selection still has no Soniox model token. Only a selected Modulate provider's
credit/quota refusal or open breaker sends the same audio once through the existing
Soniox batch client, subject to its language and two-hour bounds. There is no
Deepgram path and no retry after the Soniox attempt.

Empty results, validation/client errors, plain Modulate rate limits, other transient
failures and timeouts of a posted request with unknown billing state keep existing
behavior. Soniox 429 and other Soniox failures return the original Modulate failure
class. The voice-message response shape is unchanged; its provider/model values
identify Soniox only when Soniox served the result. Shared fallback telemetry uses
`component=stt_prerecorded`; the existing vendor burn counter records Soniox audio
seconds with bounded labels.

`PRERECORDED_SONIOX_FAILOVER_ENABLED` is default-on and declared on all pre-recorded
Cloud Run and GKE co-hosts. Rollback sets it to `false` on those same hosts. This PR
does not change production configuration or call a live vendor.

Evidence: `tests/unit/test_prerecorded_soniox_failover.py`, existing pre-recorded,
voice-message, Soniox batch and STT-policy suites, generated runtime-env validation,
and the repository preflight/pre-push contracts.

Held-piece recovery and prompt-verification coordinators retain their existing single-provider attempt budgets. A prior failed Modulate POST suppresses cross-vendor failover even if a later retry receives a credit refusal. Direct authentication/client refusals do not fail over; a request refused locally by an open breaker can fail over as specified.

The voice HTTP boundary accepts the existing `(text, language)` adapter result as
well as the opt-in serving-metadata result. Default helper calls preserve the
single-language provider's existing keyword contract; language detection and
provider metadata are requested only when needed. These contracts are covered by
the full desktop-transcription and messaging-modality suites.
