# STT and LLM spend attribution

SCA-5424 adds aggregate counters for paid processing beyond VAD and for repeated notes generation.
The counters ship with the batch worker, live STT hosts, conversation backend, and LLM gateway.
They use bounded labels and the existing scrape paths.

- `omi_batch_asr_*` counts Parakeet model dispatches and windows, with CUDA stream elapsed time
  allocated equally across the windows in each dispatch. Windows with unavailable GPU timing
  retain their counts and allocated wall time under `timing="unknown"`. Compare allocations with
  dedicated-pool charges and report fixed or idle capacity separately.
- `omi_live_stt_spend_*` counts legs and submitted PCM seconds at transport close. Soniox also
  reports measured connection seconds as its billing basis. Modulate keeps billed time unknown.
  A response with no text is an outcome, and silence or duplication still requires separate evidence.
- `llm_gateway_margin_*` groups attempts and estimated cost by bounded cohort
  and retains attempts with indeterminate pricing. Foreground notes use already-loaded completion
  metadata. Missing or stale checkpoints keep the attempt in the unknown revision cohort.

The entire live leg lands on its UTC close day. A leg crossing midnight can therefore contribute
seconds to a different day than the vendor invoice or usage export. Reconcile across the vendor's
billing window and report the boundary difference before using close-day seconds to price a cohort.
For the first full UTC day after all components are serving, use midnight-anchored counter increases
and reconcile measured plus unknown coverage against the existing billing and accounting readers.

[Live STT observability](../../listen_pusher_pipeline.mdx#live-stt-observability) ·
[Batch STT PromQL and BigQuery billing reconciliation](https://github.com/BasedHardware/omi/pull/26603#batch-stt) ·
[Live STT reconciliation](https://github.com/BasedHardware/omi/pull/26603#live-stt) ·
[LLM reconciliation](https://github.com/BasedHardware/omi/pull/26603#llm)
