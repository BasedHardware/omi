# Fixed-bank target storage adapter — research only

This is the smallest concrete target slice: a Secure-only, serialized, fixed-bank
NOR read lease bound directly to the shared `cv1_source` interface. It is not an
activated target backend. Production does not include this directory; its optional
CMake switch defaults OFF. `cv1_target_storage_init` returns `-ENOTSUP` without
accessing hardware. It cannot silently return a simulator or ready lease.

The common implementation uses exact-length reads, a 256-byte/32-byte-aligned
Secure bounce, pre/post ownership predicates, poisoned I/O failures, and a fresh
trusted 32-bit boot epoch plus 32-bit lease counter. Counter exhaustion refuses.
Every pointer/context/binding must be trusted, Secure, nonaliasing and not mutable
by NS. One context must own the **entire** physical bus, not one per bank/client.
Any failed read invalidates the whole destination, including earlier chunks.
A successful callback snapshot is not continuous physical ownership enforcement.
Initialization is allowed only before publication or after reset, never concurrent
with existing readers. Reset must supply a genuinely new epoch; no provider is
implemented, and reusing an epoch is unsafe.

The private target hook compiles against retained NCS 2.9.0 Zephyr `flash_read`,
`device_is_ready`, DT `spi_flash` and Nordic SPU types/masks. Numeric bounds require the expected Secure window 0x20002000..0x20012000;
CMSE checks privileged read/write access and TT explicitly checks Secure
attribution for every touched 32-byte bounce granule. These are snapshots, not
proof of continuously locked attribution or DMA ownership.
It only normalizes a Zephyr zero-success result to the requested count; Zephyr
cannot report partial bytes. Driver errors poison the lease; authenticated image
hashes remain necessary for silent corrupt reads. The hook is retained for object
compilation but never invoked by the initializer or research application.

## Fixed map and constraints

| Resource | Bound / rule |
|---|---|
| NOR bank 0 | 0x130000..0x190000 |
| NOR bank 1 | 0x190000..0x1F0000 |
| Personal internal range | 0x54000..0xF0000, fixed relative policy only |
| Trial journal | 0xF0000..0xF2000, fixed relative policy only |
| Reference journal | excluded from this internal policy; separate trusted service needed |
| Internal erase/program | 4 KiB / 4-byte alignment; **no executing backend** |
| NOR erase policy | 4 KiB alignment; **no erase/write API exposed** |
| NS RAM numeric prefilter | 0x20012000..0x20070000; rejects Secure alias, zero/overflow/end crossing |

The NS numeric function is not a gateway, CMSE proof, copied-input snapshot or
permission to dereference NS memory. No NS pointers enter the actual read service.
Secure pointer nonaliasing and capacity remain trusted C caller requirements.

Pinned board `boards/omi/omi_nrf5340_cpuapp.dts` places NOR and SD on SPI3,
NOR CS P0.11, SD CS P1.11, NOR WP P0.19/HOLD P0.10. `omi-pinctrl.dtsi`
assigns SPI P1.7/9/8. Nordic MDK defines Secure SPI3 at 0x5000C000 (SPU ID 12),
PERIPHID offset 0x800, SECATTR 0x10, DMASEC 0x20, LOCK 0x100. Static assertions
bind these and DT's 2 MiB NOR size. Proposed flash boundaries align to 16 KiB SPU
regions; Secure/NS RAM boundary aligns to 8 KiB. Alignment is necessary, not proof
of attribution. No code writes attribution registers.

The hook reads SPI3 and both GPIO-port permission registers, but deliberately
returns unqualified: no continuous shared-SD/other-driver exclusion, GPIO locks,
DMA/master/debug ownership, quiescent driver state or boot-epoch provider has been
established. These are engineering gaps. Granting permission does not fix them.
Protection could require all shared bus access to be proxied through Secure code;
existing NS SD/NOR drivers cannot remain independent writers to recovery banks.
Target internal NVMC program/erase, upload mutation and recovery entry are not
implemented. Do not enable these hooks by merely changing the predicate to true.

## Verification and admission

Host contract test covers forbidden/end/alignment ranges, integer overflow and
Secure alias rejection, stale/released/reset token rejection, deterministic busy
contention and callback reentry, exact multi-chunk reads, short I/O, ownership loss
before/after I/O, poisoned-state persistence and actual `cv1_source` binding.
It does not exercise OS thread scheduling, actual DMA/SPU or physical reset.

The ARM build reuses the retained unsigned Secure research compile configuration
and real generated headers; C11 and `-Werror` compile all three implementation
objects, followed by an ARM relocatable `-r` link. This is not a final Zephyr
image/link or symbol-resolution proof, and is not flashable. No key/signing step,
SDK modification, target access or production configuration change occurs.
Build receipts/objects remain outside Git in the task evidence directory.

[Trusted owner confirmation](owner-confirmation.md) separates owner authorization,
health evidence and root/recovery changes. Current host ACKs are fixture-only.

## Whole-driver arbitration and boot epoch reservation

The [next bounded source slice](bus_epoch/README.md) adds fixed whole-driver NOR/SD arbitration and two-advance journal epoch reservation. Target completion still refuses without real DMA/lock ownership evidence; [remaining work](bus_epoch/remaining-work.md) separates local engineering, hardware trials and the existing owner batch.
