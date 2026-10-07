# Draft: connected-quiet T5838 AAD wake

## What changed and why

Connected live audio now has a durable destination before any BLE send attempt.
With `CONFIG_OMI_ENABLE_CONNECTED_RETENTION=y`, mode 1 frames (including speech
while unsubscribed, residual frames during AAD quiet, and CCC-on stalled sends)
commit to the same raw SD ring used by batch. Persisting even subscribed live
frames is required because a BLE completion cannot prove that the phone app read
or saved the audio. Mode 0 subscribed batch delivery and unsubscribed batch
packing/storage stay on their existing paths and record format; charging AAD
timing/power policy is unchanged.

Retention builds forward every sampled PCM block while PDM runs, including quiet
PCM; the old awake software gate must not discard sampled silence under INV-CAP-1.
There is no software wake debounce or onset gap in that path. Hardware AAD still
samples nothing while asleep, and its acoustic onset remains a bench release gate.
The shared #14156 pre-roll remains for retention-disabled builds. AAD now permits
explicit live mode with CCC off only when durable retention is configured; it
still vetoes continuous/batch on battery and active storage transfers.

The app is untouched. This is an unshipped draft, not permission to enable the
phone pause policy on current devices. The mode selection remains session-only,
resets to 0 on reconnect, and must be written deliberately by a compatible app.
The phrase "Never persist live mode" in the earlier transport comment meant the
**mode selection**, not license to discard live audio.

`OMI_ENABLE_AAD_CONNECTED_QUIET` defaults to **n**, also explicitly in `omi.conf`.
`OMI_AAD_SILENCE_TIMEOUT_MS` defaults to **120000 ms**. CV1 pins and devkit are
unchanged. Charging retains the legacy AAD policy, including its short timeout;
on-battery batch protection is not a new charging policy.

## Product invariants affected

INV-CAP-1 — pendant audio retention during automatic phone uplink pauses. The
binding locked document was read in the coordinator's `omi-inv-cap1` worktree;
`6993ad4a22` predates that document. Its product/UI/app-gating requirements still
apply when the app integration ships.

## Failure class (fixes)

Failure-Class: FC-durable-record-gated-on-delivery-reachability

## How it was verified

- `make setup`: passed; hooks and worktree-local backend prerequisites installed.
- `bash omi/firmware/omi/tests/aad/run.sh`: passed with C99, warnings as errors,
  ASan and UBSan. Exhausts 128 AAD policy states and 64 routing combinations;
  reuses #14156 VAD tests; executes production mic STOP/wake/mode transitions
  both with/without retention, including no-CCC first-wake routing and sampled
  quiet forwarding. Executes unedited production pusher/features handlers and
  the complete production SD module against a deterministic host disk seam:
  unsubscribe, CCC-on TX stall, AAD residual frames, retained-gap fragment IDs,
  uint16 wrap, capture timestamps, capability enabled/disabled/unready, SD
  write/sync failures with retry, RTC unset, bounded batch eviction and committed
  frame recovery after loss of all RAM/volatile disk cache. Syntax-checks mic
  feature-on/off with offline storage disabled. The host models media sync; it
  does not prove physical NAND power-loss behavior or concurrent Zephyr races.
- Target build attempts (from the repo root):

  ```sh
  west build -b omi/nrf5340/cpuapp omi/firmware/omi --sysbuild \
    -d /tmp/omi-retention-build -- -DBOARD_ROOT="$PWD/omi/firmware" \
    -DCONF_FILE=omi.conf -DCONFIG_OMI_ENABLE_AAD_CONNECTED_QUIET=y
  ```

  Failed before build: `west: command not found` (exit 127).

  ```sh
  cmake -S omi/firmware/omi -B /tmp/omi-retention-cmake-build -GNinja \
    -DBOARD=omi/nrf5340/cpuapp -DBOARD_ROOT="$PWD/omi/firmware" \
    -DCONF_FILE=omi.conf -DCONFIG_OMI_ENABLE_AAD_CONNECTED_QUIET=y
  ```

  Failed at `find_package(Zephyr)`: no `ZephyrConfig.cmake` (exit 1).
  No configured NCS 2.9.0 / Zephyr SDK or ARM compiler was found in the inspected
  tool locations; `ZEPHYR_BASE`, `ZEPHYR_SDK_INSTALL_DIR` and toolchain variant are
  unset. Docker CLI exists but cannot reach `/var/run/docker.sock`; the pinned
  CI container fallback was therefore unavailable. No board artifact was built.
- Formatting, diff hygiene and repository preflight results are recorded in the
  coordinator handoff/session report; host passing results are not NCS or physical
  acceptance. No firmware flashed, no CI dispatched, no push/PR/merge/release.

## App gate and pause/drain contract (retention v1)

Minimum firmware: **3.0.22**, advertised by Device Information Firmware Revision
String (DIS UUID `0x2A26`), configured in `omi/omi.conf` as
`CONFIG_BT_DIS_FW_REV_STR="3.0.22"`. Version alone is insufficient.

Read features service `19B10020-E8F2-537E-4F6C-D104768A1214`, characteristic
`19B10021-E8F2-537E-4F6C-D104768A1214`. Its 9-byte value is:

| Bytes | Contract |
| --- | --- |
| 0..3 | Existing feature flags, uint32 LE, unchanged; `performGetFeatures` currently reads only these |
| 4 | New independent capability enum: **bit 0 / 0x01 = connected retention v1**; other bits reserved zero |
| 5..8 | uint32 LE boot/session identity; stable over reconnect and natural sequence wrap, changes on reset |

Bit 0 means: connected live frames survive CCC unsubscribe and a stalled central
in durable SD, use the existing ring WAL drain, and carry continuous frame and BLE
fragment identity. It is present only with retention compiled in AND a ready ring
(no mount/startup, shutdown, pause or observed write/sync fault). The build symbol
is `CONFIG_OMI_ENABLE_CONNECTED_RETENTION`, depends on offline storage, defaults
to y for storage builds and is explicitly y in `omi.conf`; it is independent of
the opt-in AAD flag. Missing/short features, bit clear or older/invalid firmware
means **keep the audio uplink open**. Before enabling silence-pause, the app must
read the complete payload, check semantic version >=3.0.22 AND byte 4 bit 0, sync
RTC, write/read back encrypted capture mode 1 (`19B10004-...`), and have a tested
ring drain/dedup integration. Repeat the admission after reconnect (mode resets to
0), and recheck readiness before each pause. No legacy feature bit is reused.

Pause only transmission/socket consumption; sampled quiet and speech while
paused are retained. Keep the pendant connected; AAD wake speech does not wait for
a CCC subscriber. The app must show the invariant's suspended-uplink state while
paused, then actually drain retained audio on resume/reconnect before reporting
gap recovery. This draft changes no phone UI or automatic pause admission.

Use the **same** SD ring sync path as batch: `WalSyncs` routes firmware >=3.0.20
to `RingStorageSyncImpl` (rather than the old `SDCardWalSyncImpl`). Those sources
were inspected, including the phone's explicit ADVANCE after local WAL proof.
Storage service is `30295780-4301-EABD-2904-2849ADFEAE43`; subscribe to the
write/control notify characteristic `30295781-...`, and read status on
`30295782-...`. Commands/multibyte fields remain unchanged:

1. `0x10 INFO`: discover `[read_seq:u64 BE][write_seq:u64 BE][capacity:u32 BE]
   [dropped:u64 BE][record_size:u16 BE]` in the existing 31-byte `0x02` response.
2. `0x11 READ + start_seq:u64 BE [+ count:u32 BE]`: start at read_seq; count 0 or
   omitted drains the available snapshot. `0x05 READ_BEGIN` anchors the implicit
   per-record ring sequence. Reassemble unaligned `0x03 DATA` bytes into **444-byte
   records**, as `RingRecordReassembler` already does. `0x04 DONE` reports status
   and next_seq. Poll INFO again to discover frames recorded during the drain.
3. Persist/reconcile decoded records into phone WAL, then send `0x12 ADVANCE +
   next_seq:u64 BE`. Retained records disable transport-TX auto-reclaim; STOP,
   unsubscribe, incomplete transfers and disconnect do not remove them. Legacy
   all-batch transfers retain their existing checkpoint behavior. No new drain
   command or second storage service is introduced.

Ring layout version stays 1. Inspection confirmed the raw batch header already
has `start_seq:u64` and the metadata journal has read/write/dropped u64 counters;
**the old 444-byte record did not contain a BLE fragment sequence**. Retained
records keep `[capture_timestamp_s:4 BE][payload:440]`, with one real Opus frame
`[size:1][frame:size]` then zero padding. At payload offset 408, append CQ01:

| Offset in payload | Value |
| --- | --- |
| 408 | `0xFF`, impossible remaining frame length; current phone parser stops here |
| 409..412 | ASCII `CQ01` |
| 413..414 | First live BLE fragment ID, uint16 BE |
| 415 | Fragment count, uint8; same reservation used by subscribed sends |
| 416..423 | Codec-frame sequence, uint64 BE; advances for sent AND retained frames |
| 424..431 | Codec-output timestamp, uint64 BE milliseconds, captured before TX queuing |
| 432..435 | Boot/session ID, uint32 BE |
| 436 | Flags: bit 0 = timestamp is uptime rather than UTC; other bits zero |
| 437..439 | Zero reserved |

The current phone Opus parser ignores this trailer safely, but the app team must
parse it to splice/deduplicate against live fragment ranges; the current app does
not do that automatically. Ring sequence is durable and implicitly reconstructed
from READ_BEGIN plus record ordinal; CQ01 identifies the frame/fragment range
within its boot session, including wrap and partially delivered retries. It is
not a new audio codec. Frame and fragment counters never reset on AAD or reconnect;
reset starts a new boot session. Unsynced RTC cannot veto retention: timestamp
prefix bit 31 denotes uptime seconds (already recognized by phone RingProtocol),
and CQ01 retains uptime ms. Hardware sleep creates real wall-clock gaps with no
invented audio duration. Ordinary legacy offline/batch records stay unchanged.

Durability: `sd_ring_write_retained` uses the existing SD worker's ordered write
queue, writes the raw batch plus metadata WAL and requires successful media sync
before returning success. The pusher holds/retries a failed frame with the same
identity; it never reports a RAM enqueue as durable. This deliberately chooses
per-frame commits for correctness; SD latency, write amplification, wear/current
and queue pressure must be qualified on the target before shipping.

Eviction: reuse the existing fixed raw-card ring, not accumulating FAT files.
`capacity_packets = floor((sector_count - 64)/32) * 36`; each raw 32-sector batch
contains up to 36 records. Wrapping overwrites the **oldest unread whole batch**,
advances read_seq and persists cumulative dropped_packets in the existing 64-slot
metadata WAL. INFO exposes capacity/read/write/dropped. Continuous multiday wear
cannot grow beyond these fixed sectors. Overflow is an explicit bounded-retention
exception requested in this fixup; the app must surface dropped-count deltas and
must not call an evicted span a recovered gap.

## INV-CAP-1 compliance boundary

Automatic phone pause is no longer a destination-less connected live path. Every
successfully committed retained frame exists on SD after reset; no increased RAM
frame capacity substitutes for that. Regression tests cover pause routes, and the
advertised admission is tied to the enabled/ready implementation.

The requested oldest-data eviction is a deviation from literal indefinite "every
frame survives" wording: finite capacity necessarily loses an undrained old span.
It is measured/exposed, never represented as gap-free recovery. Persistent failed
media or commits slower than production can still exhaust existing codec/TX
buffers; readiness drops and the app must reopen the uplink. Frames in flight
before commit are not guaranteed against an instantaneous power cut. These are
unqualified failure limits, not a claim that the invariant has a hardware waiver.
App capability/version gate, suspended UI, trailer-aware dedup and real-device
validation remain release prerequisites; firmware host success is not shipped
and verified phone/pendant acceptance.

## Required testing on hardware

1. **Silence-entry timing and current.** Use a paired CV1 HW5 on battery, feature
   enabled, mode byte 1 and audio CCC subscribed. Measure from last qualifying
   speech to PDM stop against 120000 ms (allow the 100 ms PCM boundary and entry
   work). Measure current before/after, separately isolating the mic/rail from
   BLE/LED/SD current. Expected sleeping mic current is approximately **20 µA**;
   report the measured active-to-AAD delta, not a claim that the whole pendant
   draws 20 µA. Verify no audio notifications in hardware quiet and the link/CCC
   remain intact. Repeat with feature off and the existing offline hold.
2. **Wake-to-first-audio latency.** Scope P1.02 WAKE and PDM CLK plus timestamp
   the first valid DMA/PCM block and first BLE audio notification. Enable logs
   for the first-block diagnostic. Target **<300 ms from WAKE to first PDM
   frame**; measure worst case and distribution over repeated trials, not only
   an average. Separately measure sound-to-WAKE, transport delay and false wakes.
3. **First-word clip and pre-roll.** Replay phrases with quiet consonants and
   abrupt onsets at different levels/distances, including normal speech below
   the driver's fixed 75 dB AAD threshold. Compare a continuous-capture reference
   with the wake recording. Retention builds forward every awake PCM block;
   verify no software discard, debounce, stale or duplicate replay. With retention
   disabled, verify the five-block awake pre-roll is oldest-first and first
   post-WAKE PCM has no three-frame debounce. Sound while PDM is off is unrecoverable; any clipped first
   word blocks release and requires threshold/hardware redesign or a revised
   policy. Test sound during bit-bang entry and immediately after entry.
4. **Reconnect during sleep.** Walk the phone out of range while the pendant
   sleeps, then return. Verify advertising/link restoration and CCC re-enable;
   mode resets to continuous, wakes capture without sound, and resumes streamed
   frames. Select live again and repeat acoustic wake. Check uint16 BLE fragment
   sequence continues without an AAD/reconnect reset (including natural wrap),
   SD remount ordering and storage read/write sequences for new offline audio.
5. **Batch / Transcribe Later regression.** Sync the RTC first. Mode 0 with audio CCC must deliver
   continuous speech **and quiet** to the phone's batch writer. Mode 0 without
   CCC must continuously record to device SD on battery through multiple live
   timeout periods. Switch live-sleep → continuous without sound; verify immediate
   PDM resume, no gate, ordered SD records and correct timestamps. CCC-off live
   sleep may remain asleep only with retention enabled; with retention disabled
   it must wake immediately. Verify switching back to live starts a fresh hold.
6. **Charging unchanged.** Compare base/flag-off and feature-on current, charging
   status, LEDs, legacy short AAD hold/800 ms settle, wake and streamed audio.
   Plug/unplug before timeout, during entry and while sleeping. The charging
   legacy policy can sleep during quiet even in continuous mode; explicitly
   review that existing limitation before claiming batch coverage on a charger.
7. **24-hour connected + quiet soak.** Keep mode 1, CCC and the connection alive,
   inject periodic speech, and check no watchdog resets or unexpected BLE drops,
   stable RAM/slab use, no spurious PDM errors, wake storms or lasting silence
   after mode changes. Log reset reasons, wake latency maxima, link state and
   notification/sequence counts; measure duty-cycle/current for the full run.
8. **SD/ring/WAL continuity and sync.** Begin with a partially assembled SD
   packet and dirty raw batch; cross offline sleep/wake, connection/CCC/mode
   changes and simultaneous storage sync. Verify power-off drains queued writes,
   power-on precedes offline writes, raw sequence/WAL checkpoints remain valid,
   and sleep produces wall-clock gaps without invented captured duration.
   Exercise queue pressure, reconnect power races and restart/power-loss recovery;
   compare recovered packets with the captured reference. AAD must not reset
   packet IDs, partial assembly or ring cursors.
9. **Entry/control races.** Speak in the final read before STOP: it must be
   delivered and cancel sleep. Change mode, CCC, connection and charger while
   entry is stopping/programming. Force a slow PDM pause, an already-HIGH WAKE
   at arm time, and repeated noise transients; check no CLK ownership overlap,
   deadlock, lost wake or rapid re-sleep before the first wake frame.
10. **Unrun target/CI qualification.** Build NCS 2.9.0
    `omi/nrf5340/cpuapp` sysbuild + MCUboot with the connected feature **off**,
    **on**, and **on with offline storage off**; inspect resolved `.config`,
    compile/link and RAM/stack usage, and validate OTA/dual-image artifacts.
    Existing `.github/workflows/firmware_release.yml` / `scripts/ci/build-cv1.sh`
    own that build; do not publish this draft. No existing Twister testcase or
    native_sim firmware application was found, so neither was runnable here and
    no fictional build-only simulator coverage is claimed. Devkit is unchanged;
    its distinct board configurations need the coordinator's normal build
    regression coverage if stacked changes touch shared code. Repeat with the
    coordinator's combined #14156/#12943/#10604 stack before hardware sign-off.

11. **Speak while phone-paused and drain.** Read DIS 3.0.22 and byte 4 bit 0,
    select mode 1, then cancel audio CCC/socket after silence. Speak immediately,
    during long quiet, at hardware WAKE and across reconnect. Drain via INFO/READ
    into durable phone WAL and ADVANCE only afterward. Compare every decoded
    speech frame/fragment range and timestamp with a reference. Test CCC still
    enabled with a central not consuming; capture must continue into SD without
    indefinite TX blockage. Reconcile live overlap without duplicate transcripts.
12. **Raw ring overflow and recovery.** Use a bounded test card/volume to wrap
    several times. Verify whole-oldest-batch eviction, durable read/write/dropped
    after reset, INFO deltas surfaced, and no claimed recovery for evicted spans.
    Cut power before/during/after raw batch, WAL metadata and media sync operations;
    qualify physical atomicity and reconstruction, not only clean-reset recovery.
13. **Capability truthfulness.** Retention-on/off builds and startup/remount,
    paused/shutdown SD, injected write/sync errors and absent/unreadable features:
    bit 0 must reflect ready enabled retention. Older version or bit clear must
    keep phone uplink open. Verify boot ID remains stable on reconnect and changes
    on reset, mode resets to 0, and app verifies mode 1 before another pause.
14. **Commit throughput/current.** Measure worst-case per-frame SD commit latency
    and sustained 50 frames/s with live audio plus concurrent storage sync, charging
    edges and multi-day wear. Bound codec/TX/SD queues and NAND wear/write-amplification;
    no queue overflow or silently discarded speech is acceptable. Run both AAD
    opt-in states; retained speech latency/current and SD cost require measurement.

## Interplay and draft gaps

- #14156 (`1cd8afbf6ff9`): replace its connected-sleep veto with explicit live
  ownership, including CCC-off only with durable retention. Retention builds must
  bypass its software/main sampled-frame discard gate; keep the shared pre-roll
  for non-retention builds, and never double-gate or delay hardware wake. No
  branch stack was applied.
- #12943 (`7582728f2005`): compatible SD event/deadline APIs by inspection; no
  SD worker edits here. Combined build/hardware evidence remains required.
- #10604 (`0258c7204793`): reconcile subscription helper/reference API; keep
  connected AAD separate from system-off and subscribed live capture busy.
- BLE IDs, codec/TX rings, SD partial assembly and raw WAL are not reset by AAD.
  CQ01 retained frames use codec-output clock before queuing, not delayed SD-write
  clock; legacy batch keeps write-time timestamps. Host tests cover retained-gap
  continuity/reset recovery; physical acceptance remains outstanding.
- No app change: live opt-in requires a paired bench client or later coordinator
  work. Review draft UUID allocation and mode ownership with that work.
- <300 ms and no first-word clipping are **targets, not verified properties**.
  The T5838 has no PCM pre-roll while sleeping. The existing 75 dB sensitivity,
  two-channel mix/second mic behavior, live entry transients, thread races,
  PDM driver queue semantics and SD recovery all need physical qualification.
