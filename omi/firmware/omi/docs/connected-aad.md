# Draft connected-quiet AAD and durable retention

This standalone lane starts at `6993ad4a22` and targets CV1 HW5 / NCS 2.9.0,
`omi/nrf5340/cpuapp`. AAD connected quiet stays opt-in:
`CONFIG_OMI_ENABLE_AAD_CONNECTED_QUIET=n` in defaults and `omi.conf`.
`CONFIG_OMI_ENABLE_CONNECTED_RETENTION=y` is independent, requires SD storage,
and enables the advertised retention contract in this unshipped 3.0.22 draft.
Devkit/pins are unchanged: WAKE P1.02, CLK P1.01, THSEL P1.05, PDM_EN P1.04.

The binding contract is INV-CAP-1: an automatic phone subscription/socket pause
must not leave sampled pendant audio without a durable destination. Full wire
layout, version/capability admission, eviction, app handoff, verification and bench
release gates live in [PR_DRAFT_NOTES.md](PR_DRAFT_NOTES.md).

## Audio policy

| State | Audio / storage behavior |
| --- | --- |
| Connected live + CCC | Retention-enabled: commit every real frame to raw SD before attempting notify; stalled TX cannot block forever |
| Connected live without CCC | Same durable SD writer; configured retention permits long-hold AAD on battery |
| Connected live + AAD quiet | No PDM samples while hardware sleeps; any queued residual frames go to SD; acoustic wake immediately forwards first PCM without CCC/debounce |
| Connected continuous / Transcribe Later + CCC | Existing continuous phone delivery, no new on-battery sleep; failed-send fallback stores audio |
| Connected continuous without CCC | Existing batch packing/SD writer; continuous PDM on battery |
| Disconnected | Existing offline SD/batch capture and AAD policy; WAL record cursors stay continuous |
| Storage sync | Existing hardware-sleep veto; retained data is reclaimed only by explicit app ADVANCE |
| Charging | Existing hardware timeout/settle, power, LED and BLE policy unchanged; storage ownership never licenses phone-pause frame loss |

Retention-enabled builds forward **all sampled awake PCM**; the old software
silence-discard gate cannot comply with the locked invariant. No increased RAM
frame capacity substitutes for persistence. The SD worker acknowledges retained
writes only after raw batch + metadata WAL + media sync. The new CQ01 padding
trailer carries boot-scoped frame sequence, reserved live fragment range and
codec-output timestamp. Existing Opus record decoding remains compatible.

The ring is the existing bounded raw-card layout. Wrapping evicts the oldest
unread whole batch and journals read/write/dropped counters. This requested finite
retention exception must be visible via INFO, never called gap-free recovery.
The per-frame commit throughput, wear/current and physical power-loss safety still
require target qualification; a host media model cannot establish them.

## Mode, capability and drain

Capture mode remains `19B10004-E8F2-537E-4F6C-D104768A1214`, one encrypted byte:
0 continuous (safe session default), 1 live. It is available with retention OR
AAD enabled. Disconnect/reconnect resets mode to 0. Invalid/prepared writes are
rejected; connection/CCC/mode changes restart the silence hold. Removing CCC can
remain asleep only with configured retention; selecting mode 0 wakes immediately.

The app must require **DIS firmware >=3.0.22 AND features byte 4 bit 0 / 0x01**,
then verify mode 1 and establish a tested ring drain before any silence-pause.
Features bytes 0..3 retain the original LE mask; bytes 5..8 expose boot ID LE.
Bit 0 is clear when disabled or SD is unready/failed. The current app parses only
the original mask, so this firmware draft alone cannot enable its pause policy.

Use the existing storage service and INFO/READ/DATA/DONE/ADVANCE commands;
`RingStorageSyncImpl` already handles 3.0.20+ ring WAL discovery/reassembly and
explicit advance after local persistence. It needs CQ01-aware live overlap dedup
and splice handling before claiming gap recovery. No second drain protocol.

## Wake and stacking

Shared #14156 VAD/pre-roll stays in retention-disabled builds. Retention builds
bypass its sampled-frame discard gate and immediately forward every wake block;
there is no stale pre-sleep PCM replay. Hardware AAD has **no sleeping PCM
pre-roll**. Sound before WAKE/PDM restart is unrecoverable: first-word preservation
and <300 ms WAKE-to-first-PDM-frame are bench targets, never host-proven promises.

The final read before STOP is delivered and checked for speech/policy changes.
A stale request is canceled; cooperative-pause timeout leaves capture running.
STOP/cancel/START share a mutex; WAKE signals a semaphore instead of an idle poll.
Connected sleep keeps SD powered. Only offline idle cuts SD power; wake queues
power-on before offline frames. Hardware entry skips the legacy 800 ms masked
settle on connected live mode; charging/offline keep it.

- #14156 (`1cd8afbf6ff9`): replace its `!is_connected` veto with live ownership
  and CCC-or-retention admission. Do not stack a second main/software VAD gate
  that discards captured PCM in retention builds. Keep immediate hardware wake.
- #12943 (`7582728f2005`): preserves SD event/deadline APIs but this fixup extends
  write requests with durable completion. Reconcile its worker batching and
  ordered commit/remount paths; combined build/bench remains required.
- #10604 (`0258c7204793`): reconcile subscription/connection-reference helpers;
  connected AAD is not system-off idle. The pusher owns a connection reference
  across SD commits and disconnect detaches it under the same lock.

## Verification

`bash omi/firmware/omi/tests/aad/run.sh` runs C99/-Werror/ASan/UBSan production
mic, pusher/features and SD/WAL host seams plus routing and shared VAD coverage.
The seam cannot qualify scheduler races, board drivers, physical NAND, current,
acoustic thresholds or first-word clipping. Target attempts fail because west
and Zephyr/NCS SDK configuration are absent here; no board artifact was built.
No firmware flashed, CI dispatched, push, PR, merge or release performed.
