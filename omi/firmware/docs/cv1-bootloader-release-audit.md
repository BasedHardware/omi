# CV1 release HEX bootloader audit

Measured 2026-11-11 against downloaded GitHub release app-core HEX assets.
Hash is SHA-256 of addresses [0, 0x10000), filling absent bytes with 0xff,
not the HEX text or whole merged image. This is static evidence for the lead's
asset-retention decision; no release assets were changed by this audit.

| Version | Boot-region SHA-256 | Omi SD sequence | Evidence |
| --- | --- | --- | --- |
| 3.0.2 | `85ac576a9cd33da3e60c8732ac6cc7ca53c8c5b67d64317a4dac5c3fa9b835ab` | No | B: boot_go at 0x476, no SD prelude |
| 3.0.3 | `9baad287d7a6579c01e6e11c8249f26fcb7ec307b3fda255bdbd8c4b2f1e3277` | No | B: boot_go at 0x476, no SD prelude |
| 3.0.4 | `c38609f3caa3fe5215161c3d9176871839ecb4b7947e4015754532ef532cbf8d` | No | B: boot_go at 0x476, no SD prelude |
| 3.0.5 | `e03e1fa02712acbf91a1d818a569eded34e3035626862a0bff3fe3103f0e4c47` | No | B: boot_go at 0x476, no SD prelude |
| 3.0.6 | `98261d50cccb6cb80b357ab2b66b4fd4d523aa39456942c6a09ffe93134af9f0` | Yes | A: INIT 0x4b4 / DEINIT 0x4c8 |
| 3.0.7 | `c80cf2fd68b67328c9c7692391a21f87630b266698c2ae9e251967f3e43da086` | Yes | A: INIT 0x4b4 / DEINIT 0x4c8 |
| 3.0.8 | `c80cf2fd68b67328c9c7692391a21f87630b266698c2ae9e251967f3e43da086` | Yes | A: INIT 0x4b4 / DEINIT 0x4c8 |
| 3.0.9 | `8d2497fb0c70ab42e14384a287767040c313aff2aa0bade2bb37a669e2b9e239` | Yes | A: INIT 0x4b4 / DEINIT 0x4c8 |
| 3.0.11 | `8d2497fb0c70ab42e14384a287767040c313aff2aa0bade2bb37a669e2b9e239` | Yes | A: INIT 0x4b4 / DEINIT 0x4c8 |
| 3.0.12 | `8d2497fb0c70ab42e14384a287767040c313aff2aa0bade2bb37a669e2b9e239` | Yes | A: INIT 0x4b4 / DEINIT 0x4c8 |
| 3.0.13 | `8d2497fb0c70ab42e14384a287767040c313aff2aa0bade2bb37a669e2b9e239` | Yes | A: INIT 0x4b4 / DEINIT 0x4c8 |
| 3.0.14 | `8d2497fb0c70ab42e14384a287767040c313aff2aa0bade2bb37a669e2b9e239` | Yes | A: INIT 0x4b4 / DEINIT 0x4c8 |
| 3.0.15 | `8d2497fb0c70ab42e14384a287767040c313aff2aa0bade2bb37a669e2b9e239` | Yes | A: INIT 0x4b4 / DEINIT 0x4c8 |
| 3.0.17 | `674d627fc37db6fd12a5c60383cdb3f874548d9e42b59886cd3b0ce40300618a` | Yes | A: INIT 0x4b4 / DEINIT 0x4c8 |
| 3.0.18 | `df561c967fbef2da300b28a7308b815dd2324f48cfe94e8ac849739117a47f41` | Yes | A: INIT 0x4b4 / DEINIT 0x4c8 |
| 3.0.19 | `6cfd4a70a715c8885dd86db96eb97286590852dd4b0f28d9f7374faad235cad1` | Yes | A: INIT 0x4b4 / DEINIT 0x4c8 |
| 3.0.20 | `fb79eeff04fcb1a4b73b9d399180773c2abecfb1267cf6164c7925fce0587553` | No | B: boot_go at 0x476, no SD prelude |
| 3.0.21 | `239239dedc25287e45411dcae3ddd71d8e028a325bcc6481ec3a175bb43ab753` | No | B: boot_go at 0x476, no SD prelude |
| 3.0.23 | `239239dedc25287e45411dcae3ddd71d8e028a325bcc6481ec3a175bb43ab753` | No | B: boot_go at 0x476, no SD prelude |
| 3.0.24 | `239239dedc25287e45411dcae3ddd71d8e028a325bcc6481ec3a175bb43ab753` | No | B: boot_go at 0x476, no SD prelude |

3.0.10 and 3.0.16: no local asset and `gh release view Omi_CV1_v<version>`
returned "release not found" on the audit date. They are unclassified, not
assumed safe. The lead reported the app HEX assets for .21/.23/.24 removed;
the retained local copies were audited here. OTA ZIPs do not contain MCUboot.

## Method and limits

Parse Intel HEX with `scripts/ci/cv1_bootloader.py`, extract the padded boot
region, convert raw binary to ARM ELF using `llvm-objcopy -I binary -O
elf32-littlearm --rename-section .data=.text,alloc,load,readonly,code`, then
`llvm-objdump -d --triple=thumbv8m.main-none-eabi`. Inspect main at 0x424
through its `boot_go` call, rather than inferring behavior from an SD driver
string elsewhere in the binary.

**A (Omi main):** GPIO configure/set at 0x470–0x49a; sleep at 0x4a2;
PM RESUME at 0x4aa; `r1=6`, disk ioctl at 0x4b4; second sleep at 0x4be;
`r1=7`, same disk ioctl at 0x4c8; PM SUSPEND at 0x4d0;
heap init at 0x4d4 and `boot_go` at 0x4da. Both ioctl calls load the same
`SDMMC` string through the literal at 0x56c. Both sleeps use 0x8000 ticks,
which is one second at the factory 32768 Hz tick rate. Branch targets vary
by build, but this call order and the immediate arguments are the same in
all rows marked Yes. Factory disk ioctl target is 0x860a and PM target
is 0x1c34.

**B (stock main):** after watchdog register writes, heap init at 0x470 and
`boot_go` at 0x476. No GPIO/SD PM/sleep/ioctl prelude intervenes. In .20 and
.21/.23/.24, `SDMMC` is present in the linked driver data; that string alone
would give a false positive. In .2–.5 it is absent from the boot region.

All inspected boot regions contain the factory RSA public key with SHA-256
`fc5701dc6135e1323847bdc40f04d2e5bee5833b23c29f93593d00018cfa9994`.
No PEM content was inspected. .6 differs from the factory region in only
three bytes; its executable SD prelude is identical. .7/.8 match the pinned
factory region exactly. Other Yes rows are **not** thereby approved: layout,
configuration and physical behavior still need qualification. For example,
.9–.15 end at 0xce2c, .17 at 0xce3c, .18 at 0xceac and .19 at 0xcebc;
these differ from factory's 0xcddc end and the new-build 0xce00 size gate.

Recommendation for the lead: remove the app-core merged HEX assets marked
No, retain OTA ZIPs, and prefer regenerated app-only HEX for wire recovery.
Do not broaden the release hash allowlist based solely on this classification.
