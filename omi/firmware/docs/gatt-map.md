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
incompatible 16-byte format. This candidate moves that recovery prefix to
`19B10042`, appended after telemetry in the same service. Recovery readers written
for 3.0.22 must discover `42` on 3.0.23; never decode `41` as recovery state.

## SAFE subset

SAFE registers only `19B10040` with recovery characteristic `19B10042`, plus
Zephyr's static services (DIS, SMP, configured BAS). Device telemetry `41` and all
other application services, capture callbacks and workers are absent. A minimal
connection callback invalidates only the recovery read cache. This avoids normal
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

96 bytes, version 2, little endian. The original 16-byte prefix keeps its
field offsets and meaning; only its format-version byte changes. Version 1
readers must recognize version 2 before parsing the prefix. New readers accept
both lengths/versions. Offset reads use a per-connection snapshot, refreshed
on an offset-zero read and invalidated at disconnect/reconnect. `19B10041`
remains the unchanged 25-byte version 1 packet.

| Offset | Size | Meaning |
| --- | --- | --- |
| 0 | 1 | Format version: 2 |
| 1 | 1 | Currently running safe mode (0/1) |
| 2 | 1 | Next-boot latch set (0/1); clears on completed DFU |
| 3 | 1 | Cached persistent bootstate: 0 unknown, 1 SAFE, 2 GOOD, 3 TRIAL |
| 4 | 4 | Retained boot attempt count; clears after healthy self-test/DFU |
| 8 | 4 | Raw Nordic RESETREAS captured before clear |
| 12 | 4 | Latch reason: 0 none, 1 crash loop, 2 held button, 3 simulation |

The appended 80-byte boot record is also the `omi/boot_telemetry` settings value:

| Offset | Size | Meaning |
| --- | --- | --- |
| 16 | 1 | Boot-record encoding version: 1 |
| 17 | 1 | Flags: bit 0 current record valid; bit 1 boot selected SAFE; bit 2 current header version valid; bit 3 previous header version valid; bit 4 previous identity valid |
| 18 | 1 | This boot's update outcome: 0 unknown/first observation, 1 unchanged, 2 updated, 3 not installed |
| 19 | 1 | Completed app upload was marked pending in the previous saved boot (0/1) |
| 20 | 4 | Cumulative boot count, saturating at `0xffffffff` |
| 24 | 4 | Raw Nordic RESETREAS for this boot (captured before clear) |
| 28 | 4 | Last fatal signal: 0 none observed, 1 observed; existing retained fatal indication, not a Zephyr fatal reason code |
| 32 | 4 | Why this boot selected SAFE: 0 none, 1 crash loop, 2 held button, 3 simulation |
| 36 | 4 | Cumulative NOR read-check failures, saturating |
| 40 | 4 | Cumulative SD init failures, saturating |
| 44 | 16 | Running DIS firmware string, NUL-terminated and zero-padded |
| 60 | 8 | Running MCUboot header version: major U8, minor U8, revision LE16, build LE32 |
| 68 | 16 | Previous saved boot's firmware string |
| 84 | 8 | Previous saved boot's MCUboot header version, same encoding |
| 92 | 1 | Completed app upload marked pending during this boot (0/1) |
| 93 | 3 | Reserved zero |

The boot fields describe entry, even if DFU later clears the live latch in the
prefix. Identity is read only from the internal primary slot with
`boot_read_bank_header()`. A changed firmware string or valid header version
means updated (including downgrade). Equal identities mean unchanged, or not
installed when the previous boot marked an upload pending. With equal strings
and a missing header, outcome is unknown. Rebuilds sharing both identities
cannot be distinguished without a hash; an identical reinstallation therefore
also reports not installed when pending. No cryptographic verification claim
is made by this comparison. Native simulation has no image header.

Pending means the existing image-0 `DFU_PENDING` completion callback accepted
an app-slot upload. It does not prove a MCUboot swap/trailer was armed. No extra
NOR/trailer query is issued. Interrupted uploads never mark completion.

Normal mode opens this isolated key before deferred devices; SAFE opens it only
after advertising, without app/bond loading. Boot records are saved once on open,
and once on the first completed upload per boot. Normal mode checkpoints dirty
health counters at most every ten minutes; failed writes use the same throttle.
SAFE captures its initial SD/NOR checks in its boot write and does not poll NVS.
Increment/read callbacks never write flash. Each failed SD init stage/attempt
counts (including each normal SD retry), not each failed mount. NOR checks count
slot-open/read errors or unequal repeated 32-byte slot reads, plus optional
flash-shell read/ID errors. `spi_flash.c` has no production verify/read-back path;
SD ring errors remain in `19B10041`'s existing volatile storage-error count.

A CRC-protected retained guard skips telemetry backend access on subsequent
warm SAFE boots if an earlier telemetry open hung. Telemetry also skips backend
access while interrupted-DFU resolution is outstanding, preserving its bypass boots. The live boot record remains
readable with previous-identity flags clear; durable counters may then be
unavailable. A returning backend error permits another attempt on a later boot.
Counters since the last checkpoint can be lost on power loss/reset. Cumulative
boots/fatal history survive CRC-valid warm resets (including pre-settings
crashes) and merge with NVS on open; cold/invalid RAM loses any uncheckpointed
history. Without an accessible settings backend, cold-power persistence is not
guaranteed. These are diagnostic records, not a transaction journal.

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
