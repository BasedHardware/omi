# CV1 owner OTA: bootstrap and ownership review contract

Status: proposed, not implemented. No signing, keys, target operations, firmware
compile/link, or Library transfer. Source baseline e86cda5abb0ea7ff942ac1bcd07261140953812c;
MCUboot 12e5ee106034972b0f1074d6f2261b2b39d1501b. Companion model executes the exact isolated C
version comparator; all flash/control-flow behavior is explicitly a faithful
Python characterization, not the whole loader or flash HAL.

## Bootstrap cut matrix and admission

Relevant loader order: raw headers (`swap_scratch.c:976–993`), update selection
(`loader.c:2340–2400`), secondary downgrade comparison before authentication
(`loader.c:1169–1229`), ascending primary erase/copy, destination magic, secondary
header/trailer cleanup (`loader.c:1812–1975`), final primary validation before
jump. `boot_copy_region` writes ascending 1024-byte chunks; linked
`zephyr/drivers/flash/soc_flash_nrf.c:480–512` writes ascending four-byte words.
`bootutil_public.c:102–132` selects TEST/PERM from good secondary magic and
UNSET/SET image_ok; BAD image_ok selects neither. Retained overwrite path does
not set copy_done. No bootstrap fallback, BLE recovery or serial recovery is
configured in this loader.

| Cut class | State after power returns | Conventional candidate | Maximum comparison version |
|---|---|---|---|
| Upload/request magic or flags incomplete | Primary unchanged; source may not be pending | Existing primary usable | Same |
| First primary erase in flight | Primary version/magic can be partly erased | Raw inflated version can erase source | No representable version exceeds candidate |
| Later primary erase / trailer erase | Primary first header erased | Retry source preserved when magic all FF | Retry source preserved |
| Copy first 20 bytes | Magic non-FF; version still all FF; primary invalid | Source erased as downgrade, no boot | Retry source preserved |
| Version word partly written | Raw primary may exceed intended version | Same hazard | No greater raw comparison tuple exists |
| Body/TLV incomplete | New header complete; primary not authentic yet | Equal comparison permits retry | Equal comparison permits retry |
| Signed copy complete / padding / primary magic write | Authentic new primary; source intact | Retry or boot new primary | Same |
| Secondary header/trailer cleanup interrupted | New primary complete; source may be lost | Boot primary, or recopy if source still valid/pending | Same |
| App confirmation flag write | Copy already completed; no overwrite revert | Does not restore old image | Same |

The canonical counterexample is a cut after byte20 at primary offset0: source
version1.0.0 compares below raw255.255.65535; non-erased magic makes
`boot_check_header_erased()` return -1 (truthy). The loader erases the source
before authenticating the incomplete primary. Equal-version conventional updates
have the same counterexample. Padding/header-size tricks do not change this
ordering or the fixed version offset.

Maximum major/minor/revision (255.255.65535) survives the modeled image-availability
cut classes because the candidate cannot compare below any raw primary tuple.
Build numbers are ignored. Equal maximum versions are accepted, including a
future supervisor with a smaller semantic generation. A lower outer version is
rejected before primary modification. No maximum-version image was produced or
adopted. This is a candidate mitigation with a substantial tradeoff: the retained
root loader no longer enforces meaningful supervisor version ordering; it also
has no configured hardware rollback counter. An inner supervisor generation
floor is not a substitute for root enforcement of supervisor rollback.

The repeated-cut argument is conditional: before complete destination copy the
valid pending retry source remains; after that point destination integrity is
available before source cleanup. It assumes healthy readable flash after reboot,
compatible geometry, app-only update, stable radio, authentic source, and an
initial normal overwrite trailer (copy_done UNSET). The tests reduce equivalent
body-word cuts to the same header/authentication predicates; arbitrary partial
header states are bounded by the unsigned maximum argument. They do not simulate
analog torn writes, correlated corruption, crypto, actual erases, or every shipped
trailer state. Erase failure, permanent faults and unknown cohorts are excluded.

**No general safe OTA bootstrap is established.** Even with this mitigation, a
validly signed but nonfunctional first supervisor overwrites the only working
application and the old loader has no independent phone recovery. That once-only
migration hazard is different from the protected post-migration recovery below.
Without a proven first supervisor and accepted maximum-version policy, current
Option A remains on hold. Option B replaces the root loader/protection and has no
established trusted application-OTA installation route; it does not remove this
legacy bootstrap problem by assertion.

## Erase-aligned external bank alternatives

App NOR driver advertises 64KiB layout pages, but pinned spi_nor.c:900–982
requires4KiB-aligned ranges and chooses an erase no larger than the remaining
range, falling back to4KiB. It does NOT round a400KiB caller request upward.
Use64KiB boundaries as a conservative layout policy, not a driver requirement. Both alternatives
preserve legacy official app `[0,0xF0000)` and radio `[0xF0000,0x130000)` staging.
All intervals below are half-open, bytes relative to the2MiB NOR.

| Region | Two-bank option A1 | Three-bank option A2 |
|---|---|---|
| Candidate | 0x130000–0x190000 (384KiB) | 0x130000–0x170000 (256KiB) |
| Previous | 0x190000–0x1F0000 (384KiB) | 0x170000–0x1B0000 (256KiB) |
| Authenticated stock cache | Phone-provided, not a third NOR bank | 0x1B0000–0x1F0000 (256KiB) |
| Non-authoritative metadata/spare | 0x1F0000–0x200000 (64KiB) | Same |

A1 gives growth room; A2 fits the observed248516-byte stock container with only
13628 raw bytes remaining before inner-format overhead. Neither proves the new
owner NS app fits or that residual NOR is blank on shipped devices. Protected
owner/trial journals are internal; external metadata alone never authorizes boot.
The prior400KiB sketch is withdrawn in favor of this conservative policy. If a
future layout-based caller rounds its end0x194000 to0x1A0000 it would cross the
next bank by48KiB; this is a conditional caller risk, not retained driver behavior.

## Proposed internal map and signed extent

Root MCUboot `[0,0x10000)` unchanged. Supervisor/guard `[0x10000,0x50000)`;
container at most252KiB leaves4KiB erase/copy guard. Owner journal
`[0x50000,0x54000)`; owner personal slot `[0x54000,0xF0000)` (624KiB);
trial journal `[0xF0000,0xF4000)`; gap `[0xF4000,0xF6000)`; existing littlefs
`[0xF6000,0xFC000)` and settings `[0xFC000,0xFE000)` preserved;
legacy trailer/tail `[0xFE000,0x100000)` reserved. Protection granularity and
actual generated linker/partition boundaries must be verified before linking.

MCUboot must authenticate only the immutable S supervisor container including all
S vectors, executable code, read-only policy and NSC veneers, with all authenticated
bytes within its declared size/TLV extent. Owner journal and mutable NS image are
outside that hash. A separate owner container authenticates board, ABI, digest,
role=app and generation; it cannot authorize S/radio changes. No executable S
section or veneer may land in mutable regions. On reset, authenticated S code
validates the inner header, NS vector/MSP/entry bounds and alignment, configures
NS VTOR/MSP and branches nonsecure only after attribution locks. Stock combined
S+NS signing is **not** evidence this separated artifact exists. Existing keys
may not trust any future maintainer key; migration must use actual installed
trust, not new-key possession alone.

## Secure/nonsecure ownership contract

This table is a required implementation contract, not present stock behavior.
Stock TF-M defaults expose many of these resources and GPIOs to NS. Applicable
source: TF-M `tfm_peripherals_config_nrf5340_application.h:14–28,94–96,142–148,
238–260`, `target_cfg.c:1490–1515,1617–1626`.

| Resource | Secure authority / permitted owner NS access |
|---|---|
| Internal flash programming, NVMC/UICR, SPU/attribution, reset/regulators/VMC/DCNF | Programming/control authority S only; no generic NS address/write/register API. Root/S/journals S-only. Personal slot NS read/execute, not write, after validation; S copies it with NS stopped before final RX lock/handoff. A later update resets into S mode, never unlocks a locked live attribution. |
| NOR and SD shared SPIM3 | Entire peripheral and pins S. SCKP1.7,MOSIP1.9,MISOP1.8,SDCSP1.11,NORCSP0.11,WPP0.19,HOLDP0.10. NS gets range-checked SD/file operations, no raw SPI/CS/PSEL/power or DMA addresses. |
| NOR candidate/previous/metadata and legacy staging | S broker owns all erases/reads/writes. NS upload opaque chunks to broker-selected candidate; cannot address previous/recovery or legacy app/radio stage. |
| SD and settings/littlefs | Bounded broker validates offsets/lengths/overflow and copies NS buffers after CMSE checks. Crash-consistent metadata and file namespace policy required; raw NS SD driver prohibited. |
| ButtonP0.26, powerP0.5, reset/wake | S only. Trusted timer/IRQ recognizes recovery gesture independent of NS event loop; NS cannot reassign pins or disable recovery wake. |
| Watchdog and recovery deadline | S owned; NS cannot stop/reconfigure/feed indefinitely without trusted health policy. S faults/reset handler returns to S selector. |
| Microphone and ordinary app peripherals | Explicit whitelist only after cross-checking S pin, DMA and peripheral routing; unrestricted GPIO/PSEL forbidden. No claim stock app runs unchanged. |
| CPUAPP normal RAM | PCD8KiB0x20000000–0x20002000 kept locked NS read-only; S64KiB0x20002000–0x20012000; NS376KiB0x20012000–0x20070000; HCI64KiB0x20070000–0x20080000 NS shared. |
| Recovery RAM | Reset-exclusive recovery, NS never started. Proposed S arena0x20002000–0x20070000 (440KiB), same PCD/HCI exclusions. Configure once per reset, not mutation of locked runtime attribution. Real BLE recovery link/stack budget unproved. |
| Network core | Stable reviewed image initially, NW-origin access stays NS and locked. CPUAPP cannot directly access CPUNET peripheral/NVMC or flash; PCD is separate privileged path. NS cannot reset/relaunch NW, alter attribution or PCD staging/mailbox. |
| HCI | Owner privileged NS has raw writable NS vrings, not an enforceable S opcode filter. Stock IPC/controller/library remains TCB. Visible source-selected62 standard+22 vendor handlers expose no flash/UICR/PCD command; binary implementations are not audited. Vendor key-hierarchy-root read is exposed; no secrecy promise. |

Network topology evidence: pinned `nrf/doc/nrf/libraries/dfu/pcd.rst:15–26`,
`pcd.c:159–189,236–272`, `pcd_common.h:44–60`, TF-M target_cfg above;
`nrf5340_cpuapp_ipc.dtsi:7–18`, HCI ipc.c248–329 and
ipc_radio bt_hci_ipc.c226–271. Nordic product specification says CPUAPP cannot
access CPUNET peripherals. DCNF is the opposite network-to-application direction,
not an invented application-to-network firewall. Network UICR’s NS address in its
own domain does not establish CPUAPP programming access. Controller compromise
could execute arbitrary NW code: raw HCI is an explicit privilege/TCB risk, not
proof of isolation against malicious radio-stack exploitation.

## Recovery independent of a broken or self-confirmed app

S boot selector checks protected journals and trusted gesture before any NS code.
S IRQ/timer/watchdog must remain usable when NS masks its interrupts, loops,
crashes, changes its VTOR, or confirms its own health. NS cannot self-confirm:
owner confirmation is bound to digest/generation and trusted supervisor checks.
A held trusted gesture must latch recovery and reset into reset-exclusive BLE
recovery; this must work after a bad candidate is already confirmed. Recovery
accepts authenticated stock from a phone, revokes owner enrollment only through
explicit physical owner reset, and can repair the personal slot without SWD.
System-off entry/wake and power control are S policy. Shared-data corruption
cannot corrupt S journals/recovery banks. No whole external flash erase API.

Required negative tests before any implementation clearance: NS attempts erase of
S/NOR previous/legacy slots through every exposed driver; DMA/PSEL alias attacks;
NS IRQ masking/systemoff/watchdog abuse; raw HCI reset/malformed traffic; power cuts
in S journals/candidate copy/previous restore; button with NS wedged and already
confirmed bad app; lost phone enrollment reset and stock restore. These are
acceptance contracts, not results. Host models cannot prove hardware attribution.

## Review gate

No compile/link spike until independent source review accepts bounded bootstrap
conclusion and this privilege contract. A later key-free spike must use real S
monitor/recovery code, show vector/NSC/signed extents and map budgets, and cannot
substitute dummy BLE stubs for a recovery implementation. Parent/user approval
of personal OTA requirement is not adoption of maximum-version policy or a
promise that legacy devices can migrate without a one-time recovery risk.
