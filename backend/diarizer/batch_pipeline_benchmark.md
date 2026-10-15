# October 15 isolated dev L4 qualification

This measures ASR only, not the full VAD/STT/pyannote/storage chain or production
capacity. Dedicated pod `dev-omi-backend/batch-worker-b-1015` used the L4 freed by
`gpu-requal-1015`; the other L4's speedups pod was untouched. Image:
`gcr.io/based-hardware-dev/parakeet@sha256:09a340a0dea50005bfd2035471253a12e98ae505c74daddba8cb5d20f08983ff`.
Python 3.12, Torch `2.10.0a0+b558c986e8.nv25.11`, FP32 model weights, CUDA graphs
requested off once (effective post-timestamp state was not recorded). This differs from shipping Python 3.11 and is not an artifact release
gate. Model ID `nvidia/parakeet-tdt-0.6b-v3`; model weight revision was not pinned.

Public inputs: EN2002a, ES2004a, IS1009a, TS3003a AMI test headset mixes, each
original 240–540s crop, concatenated to 1200s; four speakers per meeting. Manual
XML words were midpoint-cropped, sorted by onset and normalized to 3165 tokens.
Overlap is included. This is a public multi-speaker diagnostic, not a direct
replay of the private five-speaker Qwen comparison. Artificial concatenation
boundaries limit inference about natural single-conversation length.

## Batch size and throughput

30-second core windows, two-second context, full attention. Single timed pass;
model loading and a 30s warmup excluded. Timing includes model transcription and
word extraction, excludes WER scoring, VAD, diarization, storage and scheduling.
GPU peak below is Torch allocated memory, not total device framebuffer.

| Model batch ceiling | RTF | Audio-h/GPU-h | Peak allocated GiB | WER |
| ---: | ---: | ---: | ---: | ---: |
| 1 | .004577 | 218.5 | 3.27 | 23.10% |
| 8 | .002827 | 353.7 | 4.75 | 23.10% |
| 32 | .002728 | 366.5 | 9.83 | 23.10% |

Batch 8 gives 1.62x batch-1 throughput. Batch 32 adds only 3.6% over batch 8 while
roughly doubling peak allocation. Keep ceiling 8; the dedicated padded budget
is 272 seconds to fit eight 34s context windows. Shared-live remains capped at
120 seconds and the local multi-model factory refuses live placement. These
are window-batching measurements; model inputs have no owner metadata, while
hermetic chain tests verify restoration to separate owner/item results.

## Word loss ablation

| First load / same public input | Tokens | WER |
| --- | ---: | ---: |
| Whole 1200s, local attention [256,256] | 2448 | 29.61% |
| 30s windows, no context | 2633 | 23.22% |
| 30s windows, 2s context | 2653 | 23.10% |

On a separate model load, whole-file yielded 2499 words at 28.44% WER; four
independent 300s meeting inputs yielded 2652 at 22.65% WER, **identical for full
and local attention**. 30s/full/context windows yielded 2696 at 22.09% WER.
Deletions fell from 687 to 496 (191 fewer); substitutions 192→176 and insertions
21→27. Run-to-run variation means counts are not a deterministic acceptance
oracle.

Whole-file token deficit versus short windows was **7.3–7.7%**, and WER improved
**6.35–6.51 percentage points**. The exact reported 17% vendor-relative deficit
was not reproduced. Even windowed output remains 14.8–16.2% below the manual
reference count; counts are not WER and this includes overlapping speech.

The controls locate a length-dependent long-form inference loss: VAD is absent
from these cells, shorter calls improve output rather than deleting words at
forced cuts, and changing full/local attention at fixed short duration does not
explain the gain. They do not identify a defective NeMo kernel or prove every
missing word is caused by chunking. The worker's bounded internal windows and
context mitigate the measured loss while keeping durable conversation units.
They do not establish parity with Soniox or Qwen; no vendor calls were made.

## VAD compaction: quality gate failed

Local Silero, 300ms onset/500ms tail padding, retained 1012.93/1200s (**15.6%
removed**); CPU VAD took 7.23s on the Mac, excluded from GPU RTF. The unguarded
compacted/windowed candidate measured .002470 RTF but WER **24.83%**, versus
22.09% for matched uncompressed windows on that model load. Deletions increased
496→617; 26 words crossed compacted timeline seams and could not be mapped
safely. Compact whole-file also worsened WER (29.79% versus 28.44%).

**Keep `TRANSCRIPTION_FINAL_PASS_VAD_COMPACTION_ENABLED=false`.** The implemented
wrapper abstains to original audio on VAD/mapping failure; these unguarded
candidate scores are not its post-fallback output. On this corpus, mapping
abstention can cause an extra ASR request, so no cost/latency saving is accepted.
Pyannote DER after compaction remains unmeasured. Improve segmentation/join
handling and repeat word/speaker quality gates before enabling the flag.

## Receipts and reproduction

Durable run record: `omi-workspace:data/run-2026-10-13-two-lane-nemotron/sol-pr1-B.md`.
Aggregate receipts beside it: `pr1-b-ami-ablation.json`, `pr1-b-ami-controls.json`,
`pr1-b-provenance.json`, `pr1-b-vad-receipt.json`; public preparation and paired
control sources: `pr1-b-ami-prepare.py`, `pr1-b-ami-controls.py`. Working assets,
logs and source staging: `/Volumes/Ephemeral/scratch/pr1-b-ami-20261015/`.
`batch_pipeline_benchmark.py` reproduces the 1/8/32 and attention/context matrix;
the paired control script adds separate 300s meetings and compacted inputs.
No generated audio/transcript/cache/model output is committed to the product PR.

## Graph-state qualification correction

The later GPU speedups lane reproduced NeMo re-enabling graphs on the first
`timestamps=True` call after a one-shot runtime disable. These older AMI receipts
do not record actual post-inference graph state. Their throughput may include
graph decoding and must not be labeled confirmed eager throughput or compared
as an eager baseline. The token/WER counts remain the recorded outputs; the
observed long-form deficit is still a bounded-window comparison, not proof of a
specific attention kernel cause or an exact reproduction of the vendor-relative
17% deficit. The benchmark now pins both timestamp and eager options in the
decoding configuration and asserts actual state, matching the new model factory.
No new GPU measurements are claimed by that code correction. The joint Python
3.11/BF16-ASR/FP32-segmentation image still needs separate GPU qualification.
