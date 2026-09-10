# Qualification benchmark

Evidence cutoff: 2026-09-10. The existing `parakeet_gpu_tests.yml` workflow now
builds the selected source into an immutable image and runs an isolated dev GPU
job. `backend/tests/container/test_parakeet_stream_capacity.py` qualifies the
actual `/v3/stream` protocol at increasing concurrency and tests admission
rejection above the configured cap. Artifacts record readiness, completion,
latency and VRAM. A completed run and its digest must be attached to the PR;
source code for a benchmark is not a measured result.

The stream model is pinned to Hugging Face revision
[`541d1f99c6b0c3cd0b11a95167540bb8edefd82b`](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3/tree/541d1f99c6b0c3cd0b11a95167540bb8edefd82b).
Silero is pinned to its official v6.2.1 commit. Runtime health and qualification
artifacts must agree on model family and revision. The public English fixture
contains long pauses; the sustained workload caps those pauses at 200 ms,
raising its measured speech duty from about 55% to 88%. The artifact records
the RMS recipe and source/workload hashes. Four phrase sentinels test basic
English content retention; they are not a substitute for WER or multilingual
quality evaluation.

This capacity fixture is not a representative quality corpus. Batch WER/DER
results use a different pipeline and do not qualify buffered-streaming accuracy or speakers.
The broader acceptance tests below remain necessary before production promotion.

## Candidate and comparator contract

Compare the actual Omi adapters end to end, not raw model leaderboards. Pin source SHA, model revision/weights hash, container digest, NeMo/CUDA versions, GPU/CPU/RAM, region, codec, audio sample rate, chunking, VAD, diarizer and concurrency settings. Candidates: TDT v3 buffered streaming/PTT and the separate TDT batch pipeline. The previous English RNNT stream model is not the migration candidate. Comparators: configured Modulate endpoint and Deepgram model/options on each supported surface. Deepgram batch helpers exist but are not admitted by the current batch selector/policy, while PTT has no Deepgram dispatcher. A direct API quality experiment must be labeled separately from the enabled production route.

NVIDIA's [TDT v3 model card](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3) describes 25-language ASR under CC-BY-4.0. It documents the same buffered streaming API used by this service (2-second chunks, 2-second right context and 10-second left context). That supports the implementation choice, while measured end-to-end latency, accuracy and speaker quality still require the actual deployed pipeline. Review licenses for the selected weights and diarizer dependencies before distribution.

## Corpus

Start with 20 hours of licensed public audio and newly consented test recordings, 200+ sessions, with at least 30 minutes in each critical slice. Use a held-out, manually corrected reference, blind provider labels and identical audio for paired comparisons. Keep tuning audio separate. Record dataset license, consent scope, checksums, slicing and normalization recipe. Keep audio, reference transcripts and identifiable results outside Git; publish only aggregate metrics and non-sensitive manifest IDs.

Cover quiet and far-field meetings, noisy pendant/BLE speech, mic/system capture, single and overlapping speakers, short PTT commands, long sessions, silence, accents, names/numbers/jargon, reconnect and codec boundaries. Include English, unsupported languages, auto-language and code-switching as explicit eligibility tests. Do not average an unsupported-language failure into an English pass. Use aggregate traffic metadata to weight slices only after its source/window is verified. Expand weak slices if confidence intervals remain too wide; corpus size is a starting budget, not proof of statistical power.

## Proposed gates — freeze before measuring

Thresholds below are planning proposals for product review, not existing Omi SLOs. Evaluate per critical slice and against both vendors; preserve the currently selected route as the migration baseline.

| Dimension | Measurement | Proposed pass threshold |
| --- | --- | --- |
| Text accuracy | WER/CER, paired session bootstrap 95% CI; raw and normalized text | Upper bound on WER regression ≤1 absolute percentage point against current route for each qualified slice |
| Names/numbers | Manually labeled entity exact-match error | ≤1 pp absolute error regression; inspect all high-impact command errors |
| Speaker quality | DER, speaker-attributed WER, named-speaker identity continuity; disclose overlap/collar policy | DER regression ≤2 pp, no cross-session identity leakage; no invented named speaker |
| Formatting | Blind readability and punctuation review, plus downstream summary/action extraction checks | ≥95% acceptable sessions and ≤2 pp regression; evaluate the actual TDT streaming output rather than inheriting batch-formatting claims |
| Realtime latency | First valid audio → first nonempty transcript; speech end → final; client receipt/render separately | record first-transcript and end-to-final p95/p99; the executable capacity gate allows ≤4 s segment-end-to-text because the selected model reserves 2 s of right context; compare receipt/render against vendors before product promotion |
| PTT | Speech end → complete final text | p95 ≤2 s and ≤300 ms regression; no lost final word |
| Batch | Queue wait + inference to final, by audio length | p95 completion ≤current route +10%; report real-time factor and queue-age tail |
| Continuity | Accepted voiced sessions with durable nonempty final transcript | ≥99.9%, no more than 0.1 pp regression; failures and empty outputs included in denominator |
| Capacity | Sustainable concurrent streams while all quality/latency gates pass | Before load tests, freeze an absolute concurrency target from the verified 28-day baseline: ceil(1.3 × peak eligible live concurrency), while one replica is lost/draining; batch contention included |
| Failure recovery | Injected faults and replayed boundary audio | Every enumerated fault yields correct fallback or explicit recoverable terminal state; no silent loss or duplicate committed text |

Report observed failures and confidence intervals, not just a pass label. At least 3,000 independent voiced sessions with zero failures are needed even for an approximate one-sided 95% upper bound near 0.1%; a 200-session quality corpus cannot substantiate 99.9% reliability. Load repeats can validate mechanics but do not create independent real-world quality samples. Insufficient samples mean inconclusive.

## Load and fault experiments

Run in a dedicated test deployment with test identities and no production data dependencies. Sweep 1, 5, 10, 20 streams and onward only inside the isolated resource limit until a quality/latency gate fails; do not treat the historical cap of 25 as certified capacity. Mix batch jobs and streaming, cold start, long sessions, burst arrival, rolling drain, replica loss and reconnect. Record safe per-replica capacity, load-balancer skew, GPU memory/utilization, queue depth, admission rejects and fallback starts. A throughput-only benchmark does not qualify realtime concurrency.

Exercise connection refusal, handshake/readiness rejection, timeout, model failure, capacity denial, midstream close, send failure, cancellation, exhausted vendor quota, both fallbacks unavailable, finalize and drain timeout. Include repeated fallback attempts and speaker/timestamp reconciliation across provider boundaries. Establish bounds for retained replay audio and exactly which acknowledged audio can be retried.

Run three repeatable load trials and a 24-hour isolated soak after focused fault tests. Stop on unexpected cost, resource cap breach, data-plane escape or any silent loss. No load/stress tests against production. This task authorizes an isolated one-L4 qualification run bounded by the workflow timeout. Larger corpus runs, a 24-hour soak and vendor API comparison require a separately scoped budget. Public API tests require a bounded funded test account; do not export user recordings to a new provider by assumption.

## Deliverable

One dated aggregate report contains command/config manifests, dataset provenance, completed/failed counts, per-slice quality with intervals, latency distributions, capacity curves, full cost per accepted audio hour, fault outcomes, and a pass/fail/inconclusive verdict for each surface. Blank result fields remain explicitly unmeasured. Neither the source README's unqualified WER claim nor a fixed-output stack stub is a benchmark result.

## Existing harnesses to reuse

Inspect `omi:backend/scripts/stt/u_benchmark_parakeet_prerecorded.py`, `v_benchmark_parakeet_streaming.py`, `w_benchmark_parakeet_multilang.py` and `x_benchmark_parakeet_der.py` before building another runner. Reuse `omi:backend/tests/container/test_parakeet_wer_gate.py`, `test_parakeet_der_gate.py` and concurrency/VRAM tests where their corpus and execution contract fit. These were inventoried, not executed here; inspect endpoints and data dependencies before running them. Add speaker-sample verification (word counts from segment text, expected-text containment, speaker dominance) and sample-rate conversion to the paired suite.
