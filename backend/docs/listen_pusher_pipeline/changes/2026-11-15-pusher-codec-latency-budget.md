# Pusher codec latency: one child and a shared optional budget

SCA-2302 follow-up. Listen's compression canary passed, but pusher's did not:
`histogram_quantile(0.99, omi_audio_pcm_storage_seconds_bucket{job="prod-omi-pusher"})`
read 3.30–3.62 s across four consecutive five-minute windows on the 0714 build.
The pusher pod has a 1 vCPU limit (listen has 2) and its windows are a full 60 s
of PCM, so two process-local encoder slots each got roughly half a core, and a
call could spend the full two-second encode cap plus a two-second decode cap.
Custody failure fraction and raw-read integrity stayed clean; this was optional
work latency only.

## Change

`utils/other/audio_pcm_storage.compact_pcm` now bounds the whole optional step
instead of only each child:

- **One codec child per process** (`_ENCODERS = BoundedSemaphore(1)`). The
  second concurrent candidate reports `busy` and keeps PCM immediately instead
  of competing for the same vCPU. This supersedes the earlier two-slot bound.
- **0.4 s shared budget** for encode plus decode, with 0.08 s reserved for the
  decode check. Each child keeps its own two-second cap, but receives
  `min(2 s, remaining budget)`, so a starved child is killed by our budget
  rather than running the full cap.
- **New closed-set outcome `deadline`** for a pack that does not fit the budget.
  A child killed at the two-second cap remains `encoder_error`; a child killed
  by the shared budget is `deadline`, so a slow surface is not reported as a
  codec fault. Each `deadline` also calls the shared
  `utils.observability.fallback.record_fallback` once
  (`component="audio_custody"`, `from_mode="flac"`, `to_mode="pcm16"`,
  `reason="timeout"`, `outcome="degraded"`) while the domain `DECISIONS`
  counter is retained.

Unchanged: eligibility (32,000 bytes–16 MiB mono PCM16 with a complete PCM
identity proof), the 5% saving floor, byte-exact decode verification before the
FLAC representation is used, every fallback to original PCM, custody commit/ACK
barriers, encryption, consent, frame gaps, readers and object lifecycle.

## Rollout and rollback

Compression stays **off** on pusher (`AUDIO_CUSTODY_PCM_COMPRESSION_ENABLED=false`)
until this change is reviewed, merged, deployed and requalified with fresh
production numbers. Listen may keep compression on. Turning compression off
still writes new custody PCM uncompressed and deletes nothing; image rollback
and compression rollback remain independent.

The kill switch is unchanged. The 30-minute acceptance and the 0.5 s p99 /
custody-failure guards are in
[the custody runbook](../../runbooks/audio-durable-outbox.md#lossless-pcm-storage-new-writes).
Note that a disabled surface still times every call, so its p99 measures the
disabled path and cannot requalify encoding.

## Verification

`tests/unit/test_audio_pcm_storage.py` covers the exhausted budget (no child
launched), the budget-limited child timeout labelled `deadline`, the full
two-second cap still labelled `encoder_error`, the encode/decode split of the
shared budget, the no-budget-left-after-encode fallback, the single-slot
bound, and the shared fallback record (exactly one per `deadline`, none for a
verified FLAC or the disabled switch). Existing real-FFmpeg, writer, receipt,
gapped-frame and rollback tests are unchanged.
