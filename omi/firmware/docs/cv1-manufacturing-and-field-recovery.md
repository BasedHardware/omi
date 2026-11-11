# CV1 qualified manufacturing bootloader and stock-loader field recovery

Evidence date: 2026-11-11. Gettop's report that .19 and .21 were factory
shipment versions, and that .21 units were programmed with the GitHub HEX
as-is, is a **manufacturer claim relayed by David**, not an audited shipment
record. It matches the reproduced stock-loader/shared-SPI mechanism. Do not
assume all fielded pendants have the same bootloader based on app version.

## Manufacturing: 3.0.19 MCUboot with the 3.0.24 app

**Static compatibility and the lead-run manufacturing pairing trial passed on 2026-11-11.**
The 3.0.19 boot region is
`6cfd4a70a715c8885dd86db96eb97286590852dd4b0f28d9f7374faad235cad1`.
It contains the Omi power/sleep/resume/INIT(6)/sleep/DEINIT(7)/suspend sequence
before `boot_go`. The two sleeps and call sites match the factory prelude:
INIT at 0x4b4, DEINIT at 0x4c8, PM at 0x4aa/0x4d0 and `boot_go` at 0x4da.
The public RSA key has SHA-256
`fc5701dc6135e1323847bdc40f04d2e5bee5833b23c29f93593d00018cfa9994`,
the same key embedded in factory 3.0.8 and the 3.0.24 loader and derived from
the release signing key. No PEM contents are part of this evidence.

The compiled `flash_area` tables in .19 and .24 match all 13 entries after
normalizing device pointers to internal/ram/external device identity:

| Area ID | Device | Offset | Size | Role |
| --- | --- | --- | --- | --- |
| 0 | Internal | 0 | 0x10000 | MCUboot reservation |
| 1 | RAM | 0 | 0x40000 | Network update region |
| 2 | External NOR | 0 | 0xf0000 | App secondary |
| 3 | Internal | 0x10000 | 0x200 | MCUboot pad/header |
| 4 | Internal | 0x10000 | 0xf0000 | App primary slot |
| 5 | Internal | 0x10200 | 0xe5e00 | App image allocation |
| 6 | Internal | 0x10200 | 0xefe00 | Primary app span |
| 7 | RAM | 0x40000 | 0 | Remaining RAM flash |
| 8 | External NOR | 0xf0000 | 0x40000 | Network secondary |
| 9 | Internal | 0xf6000 | 0x6000 | Storage |
| 10 | Internal | 0xfc000 | 0x2000 | Settings |
| 11 | Internal | 0xfe000 | 0x2000 | Empty |
| 12 | External NOR | 0x130000 | 0xd0000 | Remaining external flash |

The .24 release HEX contains a valid MCUboot header at 0x10000, a 0x200-byte
header, a 0x406c4-byte application payload and signed version 3.0.24+0. Its
payload and signature fit well before storage. Offline RSA-PSS/SHA-256
verification of the released OTA signed image with the public key extracted
from .19 passed; its signed SHA-256 is
`b92ef865d865ad47242a4f70d050225cc65f42705b9d9c2931d4402a0c852978`
and its length is 264724 bytes (ending at 0x50a14 when placed at 0x10000). Key and slot compatibility
therefore support pairing the .19 loader with that app; the app version need
not be changed merely to use a different compatible bootloader.

Compared with factory .8 (`c80cf2fd...da086`), .19 differs in 39,957 padded
region bytes and initialized data ends at 0xcebc rather than 0xcddc. Much of
this is shifted code/data, not 39,957 independent behavior changes. The SD
prelude is the same, but the table grew from 10 to 13 areas: .8 has an app
allocation of 0xefe00 and no separate storage/settings entries. The OTA app
primary/secondary offsets and 0xf0000 sizes are unchanged. .19 fits inside
its 0x10000 reservation. The lead retired the 0xce00 heuristic: CI checks the
actual reservation, exact build hash, production slots, public key and SD sequence.

Method: strict Intel HEX parsing and 0xff-padded boot extraction; Thumb
disassembly of main; embedded 270-byte PKCS#1 public DER digest; decode the
16-byte `flash_area` records (id/padding, offset, size, device pointer) at
0xbec4 in .19 and 0xbd44 in .24. The .8 table starts at 0xbe14. Compare
against the pinned SDK [flash-area structure](https://github.com/nrfconnect/sdk-zephyr/blob/v3.7.99-ncs2/include/zephyr/storage/flash_map.h)
and `tools/cv1/pinned-partitions.yml`.

**Manufacturing decision:** build and ship the exact .19 boot hash with the
intended signed app. Two independent pristine production CI builds at source
`eec9bff0be368557cde464f9e43b62b47c28a98e`, run `42986142335`, attempts 1 and 2,
reproduced that historical boot region byte-for-byte. The lead then proved
.21 app -> released .24 BLE installation with those same boot bytes and
restored the factory loader and .21 app. See the
[jig receipt](cv1-bootloader-release-audit.md#jig-qualification-2026-11-11).
The old size heuristic alone rejected those CI attempts; it is replaced by
reservation/layout/key/SD checks and the exact pinned hash.

The policy approves .19 for manufacturing and retains factory .8 as an
approved installed/restoration state. New CI builds must equal .19. Release
app-core HEX combines that loader with the exact staged OTA signed app bytes,
excluding storage, UICR and network-core addresses. Extract `omi.signed.bin`
from the matching OTA ZIP and validate it with:
`python3 omi/firmware/scripts/ci/cv1_bootloader.py --require-bootloader --signed-app omi.signed.bin manufacturing-app.hex`.
Do not substitute the old .19 app or its whole historical merged HEX. Normal
BLE OTA remains app-only and preserves the installed loader. This physical
trial supports the pairing; it does not verify Gettop's shipment counts.

## Fielded stock 3.0.21 units

**Recommend a controlled wired bootloader reflash; offer RMA when that cannot
be done. No safe, durable OTA-only repair has been established.**

### Retry and SD state

The jig establishes corruption under a particular uninitialized-card state;
it does not establish a failure probability or prove every warm retry must
fail. A warm restart while SD remains powered and initialized could behave
differently. That is a bench hypothesis, not an approved customer recovery
procedure or a reason to run repeated fleet updates. Even a lucky app update
leaves the stock bootloader installed and the next cold update vulnerable.

In the .21 source, `sd_worker_thread()` mounts the disk and `_transport_connected()`
requests SD power-on. Disconnect while the microphone is in AAD sleep queues
power-off. `REQ_POWER_OFF` flushes/deinitializes, cuts the rail and parks SD CS
low. `turnoff_all()` calls `app_sd_off()` and enters System OFF; that function
also disconnects SD CS and suspends shared SPI3. These are not reliable ways
to make stock MCUboot read with SD off:

- The board has a P1.10 `gpio-hog` with `output-high`, applied again during
  boot initialization. An application GPIO-off setting does not govern
  MCUboot's later rail state, irrespective of whether a particular reset
  retains that setting.
- The SD SPI slot has no `pwr-gpios` link to that rail. Stock MCUboot does
  not execute the Omi power/protocol handshake before reading slot1.
- SDK SMP reset schedules `sys_reboot(SYS_REBOOT_WARM)` directly. The .21
  application has no DFU reset hook that initializes SD and keeps it in a
  verified bus-safe state across MCUboot entry. Phone disconnect timing,
  idle shutdown and reset/power history can change the card's state.

A useful **lead-only** experiment is a bounded warm-reset trial after a
verified SD mount, with the BLE connection maintained through the SMP reset,
compared against idle-disconnect and cold-power trials. Measure rail/CS/MISO
and slot1 read integrity. No one has run that experiment as part of this
mission. A pass would show a temporary install path, not bootloader repair.

### An app cannot safely rewrite this bootloader

The actual stock `239239de` binary calls its flash-protection routine at
0x492 with start 0 and length 0x10000. At 0x4904–0x4932 it writes value 0x115
to the four 16 KiB SPU flash-region permission registers at peripheral base
0x50003000, before app entry. This is locked secure read/execute access
without write permission, matching pinned NCS
[`fprotect_spu.c`](https://github.com/nrfconnect/sdk-nrf/blob/v2.9.0/lib/fprotect/fprotect_spu.c)
and Nordic's [SPU specification](https://docs.nordicsemi.com/r/bundle/ps_nrf5340/page/spu.html).
The app cannot unlock those registers; reset clears locks but MCUboot reapplies
them before handing control back. This is application-core SPU protection,
not the network core's ACL and not a reason to change UICR/APPROTECT.

Even without that protection, in-place erase/rewrite of the sole bootloader
has a power-loss window: loss after erasing its vectors and before finishing
would leave no working reset path or BLE recovery. There is no demonstrated
transactional alternate bootloader. A special app also faces the same initial
slot1-read failure before its code could run. The existing image-management
path writes OTA secondary slots, not the boot region. Do not bypass protection,
ship a boot-writing app or treat possession of the signing key as a solution.

### Aggregate sizing, without per-user reads

Ask Gettop for **lot-level totals**: exact programmed boot hash/HEX asset,
units shipped, unsold stock, replacements and units reworked to a qualified
hash. Start with **units actually shipped with the exact stock boot hash**,
excluding unsold stock. Subtract mutually exclusive dispositions for those
shipped units: returned and still held, or reworked to a qualified hash and
returned to service. A unit must appear in only one disposition, so returns
and reworks cannot be subtracted twice. Count replacements separately by
their own programmed boot hash. This is the best route to an affected
field-inventory count; the shipment claim remains unverified until those
records arrive.

For observed impact, request only aggregate analytics outputs over CV1:
from-version, target/observed-version, upload-finished, install-requested,
completed and `not_installed`/`no_reconnect` failures, grouped by app build and
time window. Count distinct attempts separately from aggregate distinct
installed devices where the owning analytics system supports that dimension;
never export identifiers or inspect individual Firestore/customer records.

The current `FirmwareUpdateTelemetry` funnel records attempt IDs and firmware
versions, **not boot hashes**. `Device Connected` is sampled and firmware events
need a verified ingestion keep-list/coverage check (`app/lib/services/telemetry/EMISSION.md`).
Do not extrapolate raw sampled event counts into an affected-unit total.
Version 3.0.21 alone cannot distinguish .19-origin OTA-updated devices from
stock-.21 factory devices. Repeated failures are supporting evidence, not a
bootloader census. Report unobserved inventory and statistical uncertainty;
an exact installed count needs manufacturer provisioning evidence or a future
read-only boot-hash diagnostic, which cannot itself reach a stuck unit by OTA.
