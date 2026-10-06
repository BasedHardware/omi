# Draft: connected-quiet T5838 AAD wake

## What changed and why

Explicit live capture can quiet codec/notifications and later stop PDM while
keeping BLE connected and audio CCC subscribed. Hardware WAKE restarts capture
with no software debounce. The standalone draft reuses #14156's bounded pre-roll
and requires an explicit encrypted live/continuous mode selection because this
base has no batch signal. Sessions default to continuous recording, protecting
phone-side Transcribe Later; unsubscribed continuous capture uses the existing
SD writer. The app is untouched and cannot automatically opt in yet.

`OMI_ENABLE_AAD_CONNECTED_QUIET` defaults to **n**, also explicitly in `omi.conf`.
`OMI_AAD_SILENCE_TIMEOUT_MS` defaults to **120000 ms**. CV1 pins and devkit are
unchanged. Charging retains the legacy AAD policy, including its short timeout;
on-battery batch protection is not a new charging policy.

## Product invariants affected

none

## Failure class (fixes)

Failure-Class: none

## How it was verified

- `make setup`: passed; hooks and worktree-local backend prerequisites installed.
- `bash omi/firmware/omi/tests/aad/run.sh`: passed with C99, warnings as errors,
  ASan and UBSan. Exhausts 64 policy states, reuses #14156 VAD tests, executes
  production mic STOP/wake/mode transitions through a deterministic host seam,
  and syntax-checks feature-on/off with offline storage disabled.
- Target build attempts (from the repo root):

  ```sh
  west build -b omi/nrf5340/cpuapp omi/firmware/omi --sysbuild \
    -d /tmp/omi-aad-review/build -- -DBOARD_ROOT="$PWD/omi/firmware" \
    -DCONF_FILE=omi.conf -DCONFIG_OMI_ENABLE_AAD_CONNECTED_QUIET=y
  ```

  Failed before build: `west: command not found` (exit 127).

  ```sh
  cmake -S omi/firmware/omi -B /tmp/omi-aad-review/cmake-build -GNinja \
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
   with the wake recording. Verify the five-block awake pre-roll is oldest-first,
   the first post-WAKE block has no three-frame debounce, and no stale/duplicate
   PCM is replayed. Sound while PDM is off is unrecoverable; any clipped first
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
   timeout periods. Switch live-sleep → continuous and live-sleep → CCC-off
   without sound; verify immediate PDM resume, no gate, ordered SD records and
   correct timestamps. Verify switching back to live starts a fresh hold.
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

## Interplay and draft gaps

- #14156 (`1cd8afbf6ff9`): reuse its software VAD; reconcile its connected sleep
  veto and optional main-level gate. No branch stack was applied.
- #12943 (`7582728f2005`): compatible SD event/deadline APIs by inspection; no
  SD worker edits here. Combined build/hardware evidence remains required.
- #10604 (`0258c7204793`): reconcile subscription helper/reference API; keep
  connected AAD separate from system-off and subscribed live capture busy.
- BLE IDs, codec/TX rings, SD partial assembly and raw WAL are not reset by AAD.
  SD packet timestamp is assigned at actual write time; there is no live
  last-frame timestamp field. These continuity findings are from inspection.
- No app change: live opt-in requires a paired bench client or later coordinator
  work. Review draft UUID allocation and mode ownership with that work.
- <300 ms and no first-word clipping are **targets, not verified properties**.
  The T5838 has no PCM pre-roll while sleeping. The existing 75 dB sensitivity,
  two-channel mix/second mic behavior, live entry transients, thread races,
  PDM driver queue semantics and SD recovery all need physical qualification.
