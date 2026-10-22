# Batch speech language quality

Parakeet TDT v3 recognizes a fixed set of European languages. Its `multi`
capability means automatic selection within that set, not arbitrary-language
speech. A nonempty hypothesis is insufficient evidence that it understood the
audio: synthetic Thai, Arabic, Hindi, Japanese, Korean and Chinese speech was
rendered as Latin phonetics, and Vietnamese lost diacritics and words.

`STT_PRERECORDED_LANGUAGE_GUARD_ENABLED` defaults on. Only `false` restores the
ordinary prerecorded routing and disables new probes. The worker's frozen-language
barrier remains active for admitted audio across rollback. This switch does not alter live
streaming provider policy.

- Prerecorded `None`, blank, `und`, `unknown` and `multi` run an independent
  audio-language classification before dispatch. A supported code with
  confidence at least 0.9 for samples shorter than 10 seconds, or 0.8 for longer
  samples, retains configured Parakeet preference; unsupported,
  malformed, unavailable or low-confidence detection selects Modulate. Provider
  selection without audio proof conservatively returns Modulate. An unavailable
  allowed multilingual provider is a configuration failure. Named supported
  languages keep configured provider ordering without a probe.
- New batch sync intake resolves the effective legacy input from the user’s
  single-language preference. A primary app language alone does not constrain
  speech. Named unsupported inputs retain the legacy multilingual route before
  new batch custody. Unknown inputs are classified on the CPU intake host per
  decoded unit; the language, confidence and evidence are frozen in encrypted
  staging. Supported confident units use the cheap GPU path; other speech goes
  to fenced multilingual recovery. Existing receipts retain original ownership.
- The Parakeet worker checks its frozen intake language before any ASR or word
  reuse. Old primary-language hints without evidence do not establish support.
  Unknown/missing/unsupported metadata on speech produces
  `worker_failure={stage: vad_windows, reason: unsupported_language}`. No
  recognizer-empty evidence, result, silence or transcript is invented.
- Existing recovery policy still controls whether held audio may be processed.
  When permitted, a language-guard handoff must use Modulate even if the older
  empty-only multilingual flag is off. A valid-empty response may use the
  existing one-shot cloud Deepgram nova-3 second provider, with the same
  allowance, privacy and at-most-once intent fences. Two valid empty answers
  use `gpu_language_guard=unsupported_language` evidence; errors stay held.
  Recovery-off retains encrypted audio for later recovery.

The language-only probe uses the existing Modulate key and
[`velma-2-language-detection-batch`](https://docs.modulate.ai/api-reference/language-detection/batch).
Only the first 30 seconds of canonical PCM16 WAV are sent, with an 8-second
timeout and no retries. Sync execution selects and pins the actual provider
before per-segment accounting; intake rechecks funded dispatch before a probe.
The key remains on CPU hosts. Native record admission already requires a fully
supported declared profile and freezes that profile in its reference manifest.
The detector is sampled evidence: later code switching or a confident wrong
classification can escape it. Soak003's six-second synthetic Chinese clips
were labeled English at confidence 0.804–0.839 across PCM16, PCM8 and Opus.
Their decoded 16kHz mono format was correct. The short-sample floor rejects those
observed false permissions without changing declared languages or the longer
probe threshold. Probe duration comes from actual PCM frames, never the
provider's duration metadata. The worker applies the same floor to admitted
audio-LID evidence using its validated unit duration, including after rollback.
`STT_PRERECORDED_SHORT_LID_GUARD_ENABLED` defaults on; only `false` restores the
prior 0.8 floor on the runtime where it is applied. CPU selection and worker
custody read it independently, so a CPU-only override does not disable the
worker floor. The original language guard and unsupported-language barrier
remain independent of this narrower kill switch.
This is a bounded regression fix, not a universal language-ID accuracy claim.
A multilingual soak remains necessary.

Previously pinned dispatch intents remain pinned: changing their provider after
an uncertain call would violate at-most-once billing/custody. Operator minimal
redrive also retains its explicitly selected Parakeet contract; it requires its
separate audio-language qualification. This guard governs ordinary provider
selection and new Parakeet worker calls, not historical transcript repair.

The `omi_batch_pipeline_language_route_total` counter has static `surface`
(`prerecorded`, `intake`, `worker`), `language_class` (`supported`, `unknown`,
`unsupported`) and `route` (`parakeet`, `multilingual`, `blocked`) labels. Worker
logs emit the same decision as `event=batch_language_route`, with an existing
opaque segment ID for an in-memory cohort join. Shadow work emits no serving
route log. No transcript, language string or user ID is logged by this signal.
`omi_batch_pipeline_language_detection_total{detected_language,decision}` counts detected
ISO codes through a closed policy vocabulary (other/und otherwise); its
`parakeet` decision means eligible, while the route counter records the provider
selected after configured ordering. The
`omi_batch_pipeline_language_probe_audio_seconds_total{outcome}` counts sent samples.
The published language-only rate is $0.01/sample-hour; multilingual batch STT
is $0.03/audio-hour ([provider pricing](https://platform.modulate.ai/pricing)).
These are list estimates, not invoice measurements or guaranteed GPU savings.

The private rollout `fleet_gate.sh` requires language-route coverage for every
since-T0 completed cohort unit and rejects any unknown/unsupported Parakeet
attempt, including with the kill switch off. Missing logs are unknown, not zero.
The signal detects this routing failure class; it is not a general language-ID
or transcript-correctness score. A serving-SHA synthetic multilingual soak is
still required for product acceptance.

Regression fixtures in `tests/unit/fixtures/batch_wrong_script.json` are seven
synthetic TTS cases from `hardcases-e653-002`, with no user data. Tests assert
that the provider that returned nonempty Latin phonetics is never called and
that multilingual responses preserve the native text. They do not claim a new
vendor replay or production-quality measurement.

## Self-hosted language gate (P58)

Parakeet serves `POST /v2/language`: Whisper-base's language-token head (fp16,
on the GPU worker queue; Apache-2.0) scores at most the first 30 s of the probe
and returns `p_supported`, the summed probability of the 25 Parakeet languages,
with the top language and a route. MMS-LID scored better offline but is
CC-BY-NC, so it cannot serve a commercial product. Parakeet needs
`p_supported >= 0.95` for at least 6 s of audio, `>= 0.985` below 6 s, and never
below 1 s. The backend re-derives that rule
(`config/prerecorded_language.self_lid_confidence_floor`) instead of trusting the
service's `route`, and also requires the top language to be supported. The model
never sees recognizer text. `PARAKEET_LID_MODEL` defaults to `whisper-base`;
`off` (the kill switch) makes the endpoint return 503.

Offline, through this serving code (FLEURS 15 languages x 60 clips as full,
6 s, 3 s and 8 kHz copies, plus the owned synthetic corpus; not prod audio), the
highest `p_supported` Whisper-base gave an unsupported clip was 0.922 at >=6 s
and 0.978 for a 3 s crop, so 0 of 2,349 unsupported clips clear the thresholds
(2 did at 0.90/0.97). The cost is leakage of supported speech to the paid
multilingual vendor: 6/420 full clips, 21/420 6 s crops, 189/420 3 s crops and
100/420 8 kHz copies. It scores the staging Arabic 6 s canary that
Modulate called `en` 0.9258 as `ar` (`p_supported` < 0.01), and the soak003
Chinese 6 s cases as `zh`.

Shadow (`STT_PRERECORDED_LANGUAGE_GATE_SHADOW`, default on): every
unknown-language probe also calls the gate and counts
`omi_stt_language_gate_shadow_total{surface,self_route,vendor_route,self_bucket,vendor_bucket,vendor_conf,dur_bucket}`.
Routing is unchanged. When the gate says Parakeet but the vendor said an
unsupported language, the backend logs `event=language_gate_shadow_disagreement`
with bounded codes and scores only. Call outcomes are counted in
`omi_stt_language_gate_self_total{surface,outcome}`.

Enforcement (`STT_PRERECORDED_LANGUAGE_GATE_PERCENT`, default 0): a stable uid
cohort on legacy sync, or an audio-hash cohort for voice messages, uses the gate
instead of the Modulate probe, which no longer runs for that cohort. Any gate
failure (503, timeout, malformed body, no `HOSTED_PARAKEET_API_URL`) falls back
to the vendor probe path, counted as `route=vendor_fallback` in
`omi_stt_language_gate_enforced_total`. Batch intake stays shadow-only at any
percent until the GPU worker accepts `self_lid` evidence.

Wrong-language alarm: Parakeet counts the text language of every `/v2`
transcript with at least 24 letters in `parakeet_output_language_total{bucket}`.
TDT always emits Latin script, so this is an alarm, not a router.
