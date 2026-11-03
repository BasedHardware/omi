# CV1 GATT allocation map (3.0.23 candidate)

The `19B100xx` UUID suffix is `-E8F2-537E-4F6C-D104768A1214`.
Each characteristic has one owner and one wire layout in every mode.

## Normal-mode order

Zephyr owns the static services, including DIS, SMP and configured BAS. Dynamic
application services register in this order for `omi.conf`: button, haptic,
audio, settings, features, time sync, storage, diagnostics. Optional accelerometer
and speaker services retain their existing conditional registration sites.
Every characteristic expands to a declaration followed by its value; CCC entries
below follow their owning value. Relative to fielded 3.0.21, which has no
diagnostics service and registers storage last, existing attributes keep their
relative order. Backlog settings additions follow the original charging CCC, and
diagnostics registers once, after storage. That is a change from the unreleased
07f3866 candidate, which placed diagnostics before storage. Absolute handles can
change; discover by UUID.

| Service | Characteristic / descriptor order |
| --- | --- |
| Button `23BA7924-0000-1000-7450-346EAC492E92` | `23BA7925` with same suffix, CCC |
| Haptic `CAB1AB95-2EA5-4F4D-BB56-874B72CFC984` | `CAB1AB96` with same suffix |
| Audio `19B10000` | Data `01`, CCC; codec `02`; optional speaker `03`, CCC |
| Settings `19B10010` | Dim ratio `11`; mic gain `12`; charging `13`, CCC; capture mute `15`; power control `16`; device name `14` |
| Features `19B10020` | Bitmask `21` |
| Time sync `19B10030` | Write `31`; read `32` |
| Storage `30295780-4301-EABD-2904-2849ADFEAE43` | `30295781`, CCC; `30295782`, CCC (same suffix) |
| Diagnostics `19B10040` | Device telemetry `41`; recovery state `42`; both read-only, no CCC |

The backlog's 25-byte telemetry remains at `19B10041`, including its coherent
per-connection long-read cache and single-ATT-bearer requirement. A new offset-zero
read refreshes that snapshot. The safe-mode release also claimed `41` for an
incompatible 16-byte format. This candidate moves that recovery format intact to
`19B10042`, appended after telemetry in the same service. Recovery readers written
for 3.0.22 must discover `42` on 3.0.23; never decode `41` as recovery state.

## SAFE subset

SAFE registers only `19B10040` with recovery characteristic `19B10042`, plus
Zephyr's static services (DIS, SMP, configured BAS). Device telemetry `41` and all
other application services, callbacks and workers are absent. This avoids normal
telemetry claiming initialized capture/battery/storage state. SAFE uses the default
`CONFIG_BT_DEVICE_NAME`, without loading application settings, identities or bonds;
normal mode retains the persisted name in the scan response. Both advertise the
existing audio-service UUID, which alone does not establish capture availability.

## Device telemetry (`19B10041`)

Exactly 25 bytes, version 1, little endian. Normal offset reads are supported.

| Offset | Size | Meaning |
| --- | --- | --- |
| 0 | 1 | Format version: 1 |
| 1 | 4 | Zephyr reset-cause flags, captured before early raw-register clearing |
| 5 | 4 | Uptime seconds |
| 9 | 2 | Uncorrected battery ADC millivolts; `0xffff` unavailable |
| 11 | 1 | Charging state; `0xff` unavailable |
| 12 | 1 | Reserved zero |
| 13 | 4 | Microphone overrun count |
| 17 | 4 | BLE TX drop count |
| 21 | 4 | Storage error count |

Reset cause defaults to `0xffffffff` if unavailable. Counters start at zero.

## Recovery state (`19B10042`)

Exactly 16 bytes, version 1, little endian; normal offset reads are supported.
This retains main's snapshot encoding and state-machine meaning.

| Offset | Size | Meaning |
| --- | --- | --- |
| 0 | 1 | Format version: 1 |
| 1 | 1 | Currently running safe mode (0/1) |
| 2 | 1 | Next-boot latch set (0/1); clears on completed DFU |
| 3 | 1 | Cached persistent bootstate: 0 unknown, 1 SAFE, 2 GOOD, 3 TRIAL |
| 4 | 4 | Retained boot attempt count; clears after healthy self-test/DFU |
| 8 | 4 | Raw Nordic RESETREAS captured before clear |
| 12 | 4 | Latch reason: 0 none, 1 crash loop, 2 held button, 3 simulation |

No phone repair UI is implemented here. Consumers must check UUID, version and
payload size. See [safe mode](safe-mode.md) for lifecycle, test plan and limits.

## Allocations and reserved claims

Device name `14` uses feature bit 9; capture mute `15` uses bit 10; power control
`16` uses bit 11. Device-name duplicates #14289, #23938 and #13704 must converge;
#10604 cannot reuse these slots. #20483 contributes battery behavior, with no
additional diagnostics characteristic.

Power control byte 0 resumes capture, 1 queues orderly power-off, and 2 pauses
through the persistent mute owner used by `15`. Disconnect and hardware AAD wake
do not clear pause. Sampling may continue while paused; TX and offline storage
stay gated. Pending shutdown reads as 1 and rejects pause/resume writes. Shutdown
uses a dedicated thread after a 50 ms grace period; the write ACK promises queued
shutdown, not completed shutdown.

`19B10004` remains reserved for the unselected connected-retention alternative
#20838; the selected #20450 custody implementation adds no UUID. `19B10005` and
`06` belong to image characteristics. The app also uses `19B10010`–`12` for
omiGlass OTA; do not reuse image slots on CV1. Future additions must allocate a
free UUID here and append attributes after existing members.
