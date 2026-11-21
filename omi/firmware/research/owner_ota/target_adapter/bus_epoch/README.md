# Shared storage bus and reset epoch — disabled research

This bounded source slice adds whole-operation arbitration and boot epoch
reservation to the existing fixed-bank adapter. No target initializer succeeds;
no device function was executed, and no SPU/flash/power/protection was changed.
CMake compilation is opt-in/default OFF and not referenced by production.

## Exact pinned driver route

`boards/omi/omi_nrf5340_cpuapp.dts:201–238` and `omi-pinctrl.dtsi:67–82` bind NOR
and SD to SPI3 (Secure address 0x5000C000), NOR CS P0.11 and SD CS P1.11,
SPI P1.7/9/8; NOR WP P0.19/HOLD P0.10. These are source facts, not live readback.

In retained NCS 2.9.0 Zephyr:

- `drivers/flash/spi_nor.c:371–428` uses its private `spi_dt_spec` for
  `spi_write_dt`/`spi_transceive_dt`. Its own lock is per NOR device, not an
  immutable NOR-bank/whole-SD-command ownership guarantee.
- `drivers/sdhc/sdhc_spi.c:640–690` holds an entire command/data/retry sequence
  and calls `spi_release` with its retained exact configuration, propagating
  release errors. `:833` sets LOCK_ON/HOLD_ON_CS. SD is not an interchangeable
  one-shot raw SPI request.
- `include/zephyr/drivers/spi.h:1090–1113` requires the exact last config to
  release held CS/lock. A wrapper cannot safely invent that pointer.
- `drivers/spi/spi_nrfx_spim.c:490–526` has timeout/uninit/CS cleanup paths;
  `finalize_spi_transaction` controls CS. The public flash/disk APIs do not
  expose one authoritative common DMA/lock-idle observation to this adapter.

`zephyr_bus.c` calls actual whole `flash_read` or `disk_access_read("SD",...,0,1)`
interfaces, with typed fixed services only. NOR accepts reads inside either
0x130000..0x190000 or 0x190000..0x1F0000 bank, without crossing a bank. SD accepts
only sector zero, exactly 512 bytes, as a future diagnostic service; no arbitrary
LBA, raw SPI config or mutating command exists. This code has never read an SD
sector on the device. Actual SD namespace readiness is also unqualified.

The only transfer buffer is aligned, bounded Secure bounce memory: numeric Secure
RAM window, MPU access check and TT Secure attribution at each touched 32-byte
granule precede any target hook. These are snapshots; hardware lock and continuous
DMA/master ownership are still mandatory. No NS pointer enters these hooks.

## Arbitration and failure contract

One Secure context covers both drivers and all bus users. Atomic service ownership
spans each whole driver call and cleanup; interleaved/reentrant requests reject.
The read output cannot overlap the context/bounce and must have trusted Secure
capacity. No bytes are copied to the caller until complete exact-length success,
cleanup, epoch and ownership checks succeed. Any partial I/O, timeout detection,
cleanup error, clock reversal or boot-epoch change poisons the context. New calls
cannot clear that uncertainty. Reset/reinitialization is only before publication
or after an actual reset, never concurrently with an old caller.

The 100 ms check is **post-call detection**, not cancellation or a bound on a hung
synchronous driver. A driver lifecycle/cancellation hook is needed before target
use. Cleanup always runs after an attempted whole operation, including errors.
The target cleanup reads both CS levels (active-low logical zero means inactive),
but always refuses: CS alone cannot prove DMA/driver lock quiescence. It does not
force pins, reset a peripheral or call `spi_release` with a fabricated config.

`cv1_bus_nor_io` fits the existing storage I/O signature. No target ops table is
installed. The target initializer remains ENOTSUP; host callbacks are explicitly
fixtures, not capability flags claiming target ownership.

## Non-reused boot epochs within the stated model

`boot_epoch.c` reuses the real shared dual-page journal C codec. A **separate,
pre-provisioned, Secure boot-only 8 KiB ledger view** is required. No physical
placement, provisioning or target write backend is assigned/implemented here.
This must never alias the application or confirmed-reference journals.

A role-marked record is required; erased/corrupt/unknown journals never auto-seed.
A single boot authority, guarded against concurrent reservation in this image,
reserves **two advancing records with exact readback** before issuing the final
32-bit epoch. A newest-record fallback loses at most one sequence, so the next
two-step reservation ends above the last issued epoch. Exhaustion refuses before
there is insufficient room for both writes. The existing lease counter occupies
the other 32 token bits and refuses wrap. `cv1_storage_boot` invalidates old RAM
state before reservation; failed reservation cannot leave an old service enabled.

Secure boot provides 32 bytes of nonzero entropy evidence, stored in the reserved
record. It is not a key/credential and was only supplied by public deterministic
host fixtures. It is **not the uniqueness argument**: tests deliberately repeat
it. Durable monotonic reservation supplies uniqueness under the codec's monotonic
partial-program/erase model and one-record loss/corruption. Both-invalid metadata
fails closed. Whole-ledger rollback, malicious Secure writers, unapproved erasure,
provisioning reset and analog flash retention faults are outside that guarantee.
No API silently repairs or reseeds. Secure storage allocation, write endurance,
boot provenance/entropy provider and anti-rollback lifecycle remain engineering.

## Verification

One native C driver, UBSan, uses actual arbitration/epoch/journal code: a real
pthread NOR/SD contention test with bounded condition waits and joined worker,
callback reentry, busy/stale handle, range crossing/overflow/context alias,
partial transfer, timeout, cleanup failure and reset identity changing mid-call.
Its existing NOR journal test backend explores 2,177 mutation cut prefixes across
both reservation writes; no previously issued epoch is returned after restart.
Corruption of each individual persisted record is tested separately. This is host
fault simulation, not physical reset, DMA exclusion or a new device emulator.

Example from this directory with existing compiler, output outside Git:

```sh
cc -std=c11 -pthread -O1 -Wall -Wextra -Werror -fsanitize=undefined \
  -fno-sanitize-recover=all -I.. -I../../shared \
  ../storage_adapter.c ../../shared/secure_store.c ../../shared/secure_image.c \
  boot_epoch.c secure_bus.c test_bus_epoch.c -o /tmp/cv1-bus-test-UNIQUE
/tmp/cv1-bus-test-UNIQUE
```

In the Omi workspace, run builds/tests through `bin/omi-heavy`. Existing ARM
Secure generated headers/config compile the real Zephyr hooks and all common
objects with C11/-Werror; ARM `-r` link succeeds. This is not final Zephyr symbol
resolution, runtime RAM/stack measurement or a signed/deployable image.

See [remaining work](remaining-work.md). Prior owner-confirmation boundary remains
in force; owner personal-app authority never grants recovery/key/radio privileges.
