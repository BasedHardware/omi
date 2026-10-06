# Draft connected-quiet AAD

This standalone draft starts at `6993ad4a22`. It targets CV1 HW5 / NCS 2.9.0,
`omi/nrf5340/cpuapp`. No shipping configuration enables the new policy:
`CONFIG_OMI_ENABLE_AAD_CONNECTED_QUIET=n` is the default and the explicit board
application setting. Hardware and first-word qualification must precede opt-in.
The devkit application has no new symbols or policy. Existing DT ownership is
unchanged: WAKE P1.02, CLK P1.01, THSEL P1.05, PDM_EN P1.04.

## Audio policy

| State (feature enabled) | Audio behavior | BLE / SD |
| --- | --- | --- |
| Disconnected | Existing amplitude threshold and `OMI_VAD_HOLD_MS` AAD sleep/wake | Advertising unchanged; existing SD sleep/remount |
| Connected + live mode + audio CCC + speech | PDM stays active; captured onset uses software pre-roll | Existing notifications |
| Connected + live mode + CCC + quiet | Software gate quiets codec after `OMI_VAD_HOLD_MS`; hardware AAD after `OMI_AAD_SILENCE_TIMEOUT_MS` (default 120000) | Link and CCC stay intact; SD stays powered for sync |
| Connected + continuous / Transcribe Later | No new software gate or hardware AAD sleep on battery, even through quiet | Subscribed frames reach the phone writer; unsubscribed frames go to the device SD writer |
| Connected + live mode without audio CCC | No hardware sleep; ownership is ambiguous | Existing live-mode unsubscribed behavior |
| Storage transfer active | Existing hardware sleep veto | Sync can continue while the mic is already asleep |
| Charging | Existing hardware AAD timeout and settle behavior; software gate bypassed | Charger, power, LEDs and BLE parameters unchanged |

Charging retains the base policy, which already permits quiet hardware sleep.
The on-battery batch protection therefore does not extend that guarantee to
charging; this is a deliberate boundary of the request to leave charging behavior
unchanged. An eventual product policy must reconcile these requirements.

There is **no live/batch flag at this base**. The transport's original pusher
writes SD only while disconnected, forwards subscribed connected frames, and
drops unsubscribed connected frames. CCC alone cannot distinguish a phone's
Transcribe Later writer from transcription. This draft defaults each session to
continuous capture and uses an explicit encrypted mode control. With the opt-in
feature, connected continuous capture also uses the existing SD writer when
unsubscribed; this is the only recording-routing change. No SD worker, raw ring
format, power queue, or WAL implementation changes.

## Draft mode control

Appended to the existing audio service (existing audio attribute indexes stay
unchanged): `19B10004-E8F2-537E-4F6C-D104768A1214`, encrypted read/write, one byte:

- `0`: continuous recording, session default. Use this for Transcribe Later.
- `1`: live capture; connected-quiet AAD additionally requires the audio CCC.

Offset/prepared writes, invalid lengths, and values other than 0/1 are rejected.
Mode is not persisted. Disconnect/reconnect resets it to 0; a future compatible
central must deliberately select 1 again. Mode/CCC/connection changes restart the
silence hold and notify the AAD worker. Switching a sleeping connection to mode 0
or removing CCC resumes PDM without waiting for sound. The existing app is
untouched, so it cannot activate this new policy automatically. Bench testing
uses a paired GATT client. UUID allocation and future app protocol adoption
require coordinator review before release.

## Wake and continuity

The software VAD and its five 100 ms pre-roll blocks are reused from
[PR #14156](https://github.com/BasedHardware/omi/pull/14156), head
`1cd8afbf6ff9bbf38f06d489df03731735257a4d`. No second VAD algorithm is introduced.
Three above-threshold frames open the awake software gate and replay oldest-first.
After hardware wake, the first captured block bypasses that debounce immediately.
Mic context owns all pre-roll state and drops stale pre-sleep PCM on wake, rather
than replaying already delivered frames or joining old quiet to new speech.

**AAD has no PCM capture during sleep. Software pre-roll cannot recover speech
before WAKE/PDM restart. First-word preservation remains unproven.** A semaphore
wakes the mic worker immediately instead of adding a 100 ms idle poll. Connected
wake avoids the SD request queue's possible 500 ms delay; SD was kept on. Live
entry arms WAKE without the legacy 800 ms masked settle interval, accepting
possible false wakes. Configuration still bit-bangs with PDM stopped. Hardware
must bound both sound-to-WAKE and WAKE-to-first-PDM-block; target for the latter
is **<300 ms**, not a measured guarantee. With logs enabled, first-block latency
is reported from the ISR's uptime32 timestamp (wrap-safe subtraction).

The final read before STOP is forwarded and checked for speech or policy changes.
A stale request is canceled; a cooperative-pause timeout leaves capture running.
A pending first wake prevents re-sleep before its timer has been reset.
STOP, timeout cancellation and START share a mutex so cancellation cannot leave
an unacknowledged delayed STOP. Reconnect publishes its policy event after the
connection pointer and SD power request are ready, before the existing BLE
negotiation delays.

`packet_next_index` advances only when the pusher sends real fragments, wraps as
uint16, and is not reset by AAD or reconnect. Codec/TX rings drain normally; no
synthetic silence packets or reinitialization are added. SD `buffer_offset` keeps
partial packet assembly; raw `read_seq`/`write_seq` and the WAL remain owned by
`sd_card.c`. SD timestamps use `get_utc_time()` when writing; the live wire has no
last-frame timestamp to rewrite. Sleep introduces wall-clock gaps, not fake
captured duration. Offline SD power-off still drains pending writes and commits
the batch; wake still queues power-on before offline audio resumes. These are
code-inspection findings; SD recovery and queue-pressure behavior need bench QA.

## Stacking

- #14156 directly conflicts with this policy: its `!is_connected` sleep veto
  must be replaced by the explicit live/continuous decision. Keep one shared
  `software_vad.c/.h`; its optional `main.c` VAD gate must not double-gate this
  mic path or gate continuous/batch capture. Retain immediate hardware-wake
  forwarding. No PR branch was merged or cherry-picked into this draft.
- [#12943](https://github.com/BasedHardware/omi/pull/12943), head
  `7582728f200545910912807e3c383fa856d68b53`, replaces button/SD polling with
  event/deadline waits. This draft retains its SD APIs and remount/drain ordering;
  compatible by inspection, not verified as a combined build.
- [#10604](https://github.com/BasedHardware/omi/pull/10604), head
  `0258c7204793cab40418126cb74f02248bf73488`, adds opt-in system-off/idle controls.
  System-off must not treat connected AAD quiet as idle. Its audio subscription
  helper overlaps this draft's atomic snapshot API: reconcile to one helper and
  preserve its connection-reference contract when stacking. Its idle feature is
  disabled for offline-storage builds. No connection-interval changes here.

## Local and target verification

Run `bash omi/firmware/omi/tests/aad/run.sh` from the repository root for the host
policy and reused VAD tests. Host tests cannot establish PDM/CLK or BLE behavior.
There is no existing Twister `testcase.yaml`, `native_sim` application, or CV1
simulation target under `omi/firmware`; do not mistake the physical `test/`
application for a simulator. Use NCS 2.9.0 for target build coverage:

```sh
west build -b omi/nrf5340/cpuapp omi/firmware/omi --sysbuild \
  -d /tmp/omi-aad-build --pristine always -- \
  -DBOARD_ROOT="$PWD/omi/firmware" -DCONF_FILE=omi.conf \
  -DCONFIG_OMI_ENABLE_AAD_CONNECTED_QUIET=y
```

Also build the default flag-off board configuration and a feature-on build with
`-DCONFIG_OMI_ENABLE_OFFLINE_STORAGE=n` to verify the sync guard compiles out.
The existing firmware release workflow/container uses NCS 2.9.0 sysbuild plus
MCUboot; this draft does not dispatch that workflow or publish artifacts.
