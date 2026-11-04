# Batch GPU worker: prepared flights and VAD segmentation reuse

Two ship-on GPU-efficiency levers for the dedicated batch worker, found by the
GPU-efficiency hill climb and ported onto main. Words, speaker turns, leases,
refunds and the decoded-memory bound are unchanged.

- **Prepared flights** (`BATCH_PIPELINE_PREPARE_FLIGHT_ENABLED`, Helm
  `worker.prepareFlightEnabled`). A lane waiting for the GPU now prepares every
  leading unit of its flight that fits the shared 1800-audio-second decode
  budget, not only the first. The chain returns finished preparations when its
  GPU section ends rather than after settlement and publication. A lost lease or
  stop while waiting cancels the whole prepared prefix and refunds those units
  without an attempt charge. `false` restores first-decode-only preparation.
- **Serial VAD segmentation reuse** (`BATCH_PIPELINE_VAD_SEGMENTATION_REUSE_ENABLED`,
  Helm `worker.vadSegmentationReuseEnabled`). A unit diarized at full length
  takes the raw segmentation scores its own VAD pass computed instead of a
  second segmentation forward. Compacted speech-only waveforms still segment
  themselves. `false` restores the second forward.

Both are worker-only kill switches, read once at startup. Readback after the
roll: `omi_batch_pipeline_stage_seconds` for `worker_flight` (GPU section) per
`fetch_decode` unit, and the `diarize` stage mean, against the pre-roll window.
See [runtime](../../../diarizer/batch_pipeline_runtime.md) and
[diarization adapter](../../../diarizer/batch_pipeline.md).
