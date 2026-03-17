# Omi Consumer — Open Source Hardware

Complete hardware design files for the Omi Consumer, the world's leading open-source AI wearable.

Licensed under MIT (see [LICENSE](LICENSE)).

## What's Inside

### Electrical (`electrical/`)
- **Mainboard** (nRF5340 + nRF7002): Altium source, Gerber files, schematics (v1.2)
- **Charger Board**: Altium source, Gerber files, schematic (v1.0)
- **FPC (Flexible PCB)**: Altium source, Gerber files, schematic (v1.0)

### Bill of Materials (`bom/`)
- 88 components with manufacturer part numbers (MPN)
- Available in CSV and XLSX formats

### Mechanical (`mechanical/`)
- Full device + charger STEP assembly
- Individual parts organized by manufacturing process:
  - **CNC**: Aluminium covers (Case A, Case B), copper touch pins
  - **Injection Molding**: Wrapper/shell (PC+ABS)
  - **Silicone**: Internal pad (50A/80A durometer)
  - **SLA**: Frame, LED guide, charger cases, enhance plate
- 2D technical drawings (PDF)

### Assembly (`assembly/`)
- Exploded view photos
- Component identification photos
- Materials labelled reference images

### Packaging (`packaging/`)
- 3D CAD models: foam inserts, case, sheet metal, full assembly
- Package drawings and reference photos

## Technical Specifications

| Component | Specification |
|-----------|---------------|
| Processor | nRF5340 dual-core Bluetooth LE SoC |
| Wi-Fi | nRF7002 Wi-Fi 6 chip |
| Audio | 2x TDK T5838 top-port PDM microphones |
| Storage | CSNP4GCR01 8GB NAND Flash |
| IMU | LSM6DS3TR-C 6-axis accelerometer/gyroscope |
| Battery | 3.7V 150mAh LiPo (custom, D16xH6.1mm) |
| Charging | BQ25101 Li-Ion charger IC, magnetic pogo pins |
| Motor | 3V vibration motor (D5.0xH2.5mm) |

## Firmware

The firmware is open source and lives at [`omi/firmware/`](../../firmware/). Built on Zephyr RTOS with nRF Connect SDK.

## Getting Started

1. **Build one**: Use the Gerber files to order PCBs, the BOM to source components, and the STEP files to manufacture the enclosure.
2. **Modify the design**: Open Altium source files to customize the electronics, or edit STEP files to redesign the enclosure.
3. **Flash firmware**: Follow the [firmware guide](https://docs.omi.me/doc/developer/firmware/Compile_firmware).
4. **Documentation**: Visit [docs.omi.me](https://docs.omi.me/doc/hardware/consumer) for detailed guides.

## File Checksums (SHA-256)

Use these checksums to verify file integrity after cloning.

```
sha256sum -c checksums.sha256
```

### Electrical

| File | SHA-256 |
|------|---------|
| `electrical/mainboard/altium/omi2-mainboard-v1.2-altium.zip` | `025c79effcebaa63de9a4adbf59cfb15b5adfe8f3d61d4c21d268320acf5c133` |
| `electrical/mainboard/gerbers/omi2-mainboard-v1.2-gerbers.zip` | `54e126a1aa4e3174eed50e099c7b930646abad261b7f73421ca1526d39dcee49` |
| `electrical/mainboard/gerbers/omi-gerber-files-main-pcb.zip` | `b2c00ffe2e2483daa9871c45a98f38f49896cbc6b4022a4bbbbffe28217259b3` |
| `electrical/mainboard/schematic.pdf` | `0c09fc65f7c191f6d1ec03932042f78a56688b21bb57b9810204640d6e5f527a` |
| `electrical/charger-board/altium/omi2-charger-v1.0-altium.zip` | `7b15cb87102f177e3feaaeaa8315e3f75bd3790b0cf0c68b0caa763b25ac049c` |
| `electrical/charger-board/gerbers/omi2-charger-v1.0-gerbers.zip` | `e7227b24c951c77fd9a1db11d1249fdf2f6db26cf416fa2ef0cf1816f12c4169` |
| `electrical/charger-board/schematic.pdf` | `282e1c469a0cc73f349fbe4fe050f6e1fdc2a86c1dee61c175a50bb6f247a8ad` |
| `electrical/fpc-board/altium/omi2-fpc-v1.0-altium.zip` | `5f30a4a8ef9d21ca5010f039e791a7845486af58db85bce77637518b146a610b` |
| `electrical/fpc-board/gerbers/omi2-fpc-v1.0-gerbers.zip` | `5a8d56466101ef77fd83dc5bd6016d56542443a865142d23864b07aac712ab2b` |
| `electrical/fpc-board/schematic.pdf` | `31d5c900f54dc586440c8d29093e501bde532c45db455b96ac7c552af102919d` |

### BOM

| File | SHA-256 |
|------|---------|
| `bom/omi-bom.csv` | `01b27487469ddb8ff7b59258959277e3976d6a150b120a643943505c8f892256` |
| `bom/omi-bom.xlsx` | `1445b549f72a37939be9a38401404e8da7ed45a2029204739dac2733b038987b` |
| `bom/omi-bom-original.xlsx` | `a8744d573bc02b62952e164776f72f30ee7929874666da7b452fbc5e8dde6764` |

### Mechanical

| File | SHA-256 |
|------|---------|
| `mechanical/assemblies/omi-device-charger-assembly.step` | `d7df1b004e159365b69ef57995a21f49e17dbe18d863b359ef611c6f84e473d1` |
| `mechanical/parts/cnc/case-a.step` | `6a23a0693e3d0e0c3068474cb46931f32e7850d6e22266a902060762f165eb1b` |
| `mechanical/parts/cnc/case-b.step` | `ddeba686dd58d06fc5f3b7934e32dd6d720d037b2a4c1828ee44973795fb7a11` |
| `mechanical/parts/cnc/cnc-brass-copper-zinc-polished.zip` | `d19352e101c9c4bb35c6ccba0e71500f06a0023629ec3a303e3cb3ec4a8192bd` |
| `mechanical/parts/cnc/touchpin-1.step` | `8b9941c24fac07849c3b521528be928ec9fcf8f4f7446e2ea78f02263595e4d0` |
| `mechanical/parts/cnc/touchpin-1-v2.step` | `b26275c3c9857e23c46e0ff133d78fd6c8d8b6d4c82b9c0ef77608e720df142a` |
| `mechanical/parts/cnc/touchpin-2.step` | `260945fac51f3c291ced064b37615027997412f226171bc0815a3425d03e4062` |
| `mechanical/parts/cnc/touchpin-2-v2.step` | `7ac7843fc1616f044c74a0b36d6227394d9abb75b93552982b2965906a684471` |
| `mechanical/parts/injection-molding/wrapper.step` | `4a0c2e9494f973fd6e37deea6c30ded2b52af40364d6e357b15f69722eb4cac8` |
| `mechanical/parts/injection-molding/wrapper-drawing.pdf` | `333f625787012c8eb50a4e3f02a31ef9775dd306811b8f620f5891127021413b` |
| `mechanical/parts/silicone/pad.step` | `e47a7ac6076ca5f99ef911499ea609f04d7efe2fb0d346827ed44e172f3f457b` |
| `mechanical/parts/silicone/pad-drawing.pdf` | `714b057e4f0b508212b27c9fcb55bf80e428468fca3fb14ce970fbdf4ac9b815` |
| `mechanical/parts/sla/charger-case-a-ceramic.step` | `9d0fea420fd38bbe7cfb325e5a3b770150ed9efd02239240b8c14abc075f0ebc` |
| `mechanical/parts/sla/charger-case-b-ceramic.step` | `64296a2503a0b70ac032f7f511de47a7274e6af856bb19faef06a2a72104ce67` |
| `mechanical/parts/sla/enhance-plate-black.step` | `e3c0fb9b6a44966e969fc66fe0ce1a2dc0ac410bb00a3932fdfec307d214c7b6` |
| `mechanical/parts/sla/frame-white-translucent.step` | `a0d96a3dcf0e3b7f85885ee5876ddfd58ce187faea3bd3c10ea4a8f5339b0e86` |
| `mechanical/parts/sla/led-guide-white-translucent.step` | `40f1e31e55e18c5f6df762c69b6b705b651f534851b4defb9bf2ef17e5739bfa` |
| `mechanical/parts/sla/pad-ppt-grey.step` | `1df8786beef2a028c1576c3715eb84aef701804750d9ad90eccee1e989fce6ef` |
| `mechanical/parts/sla/touchpin-2-sla-test.step` | `260945fac51f3c291ced064b37615027997412f226171bc0815a3425d03e4062` |
| `mechanical/drawings/omi-2d-drawings.pdf` | `3eb768218947591cea0ae115219fddd1ae40cc9df332d935681289bb778e8861` |
| `mechanical/drawings/manufacturing-specifications.png` | `13ebd6b23de37919f457b96734538ff36be70ec7d6d5f1e94d7a9826393641fb` |

### Packaging

| File | SHA-256 |
|------|---------|
| `packaging/cad/packaging-full-assembly.step` | `95298ba059e96c83456d7396db0f50328eaa3931776e65ccbc60e1698b4fa2e4` |
| `packaging/cad/case-packaging.step` | `cd9e71389791b07a10fb84378a1437f069d26292cc4a977ef2fb76296c7ba28d` |
| `packaging/cad/sheet-metal-packaging.step` | `53259fb0dc6f3a382c1ef16fce84c39a410fb7c9486a35b23282382ea4abb1cd` |
| `packaging/cad/foam/foam-assembly.step` | `06ea31b64fc4ab1a18713a98984cb4200caba8c115ee40ff4204a0fe293d8b19` |
| `packaging/cad/foam/foam-bottom.step` | `7c86f3eca98b3a08b582023cf71148322247ecba5e6482e962646e0d80a5bf0d` |
| `packaging/cad/foam/foam-circle.step` | `d0152f117c1f1968c75fb126f8eb92022194266e44e93af73d75c061aaf38f71` |
| `packaging/cad/foam/foam-top.step` | `89df594615bb795ad6e67a9053b61f468d3617c7edee994ee78692c1e632e5fe` |
| `packaging/cad/foam/foam-packaging.step` | `649380aae5dc56b151604301cd7e0c8223e6055c4f8814643e3c49b76fd06c9a` |
| `packaging/cad/foam/foam-drawing.pdf` | `6b1686aa8c1d89c2dc5d511c2abb55b1f456d508b9485d78f037599c10ac2671` |
| `packaging/package-drawing.pdf` | `f9b64171b32a1c432ecd3949f5fc51a28b339b52336c23ef70b2f9e335c173f9` |

### Assembly Photos

| File | SHA-256 |
|------|---------|
| `assembly/photos/components-disassembled.jpg` | `880e774b49f56a8ec7bf4f4075483f5c0bcf7c0e39962d874d54deb0428b5b71` |
| `assembly/photos/materials-labelled-exploded-view.jpg` | `0cb3e22f08dceaa5cce9c569510985251c2b6c580718ad8d2559987019c2fd00` |
| `assembly/photos/materials-labelled.jpg` | `7857e7b6f7e1686899dd51ec9d11196905ff1f539f09aff08ae2b724904a9555` |
| `assembly/photos/outer-aluminium-covers.jpg` | `0ce99ecfffba3b11a91e754c90c9f4b8c1a14c779b1124cbe6c8b6a69ce71ab1` |

### Packaging Photos

| File | SHA-256 |
|------|---------|
| `packaging/photos/disassembly-exploded-view.png` | `bfc5a0fa7ed8997aa882cefcff1b7a750578aa6e323e63b720de7ea64d3d54a4` |
| `packaging/photos/package-overview.png` | `2556dd78a18397aa58ed8cb27edd48de5536ce08168a2db371de3e7564f476ad` |
| `packaging/photos/package-render.png` | `2556dd78a18397aa58ed8cb27edd48de5536ce08168a2db371de3e7564f476ad` |
| `packaging/photos/packaging-1.jpg` | `6bf951f71209730e5e031fd28e1e7dc192c86e2b3a5cfdaacd80d8efff77ae38` |
| `packaging/photos/packaging-2.jpg` | `4104233eb7f29c6560d2bfcfbc60bfeea79bc3a1877fb97c0fd19447a350feb1` |
| `packaging/photos/packaging-3.jpg` | `c3ab8314c2465191edaf23849f7da921058b2773add5b372a2891126229362fd` |
| `packaging/photos/packaging-4.jpg` | `6821e45eefc5d4557b88b6282887abebaa9658a7b9f12883f3ca42f4b9e5d2c8` |
| `packaging/photos/packaging-5.jpg` | `f1cd74ab68fbfde7d149bd36ec4f3a5186740af792470c9f2417c561e02404ab` |
| `packaging/photos/packaging-6.jpg` | `a2288a15cb8e9ac8dfc074fed6a6e61a060ff09cecffc6939a92948bfa8dccb5` |
| `packaging/photos/packaging-7.jpg` | `5d0ceae15ed4191c43319c450d89e9a3fcd9ae35db05f605336dd9c8e6d1ca70` |

## Questions?

- [GitHub Issues](https://github.com/BasedHardware/omi/issues) for bugs and feature requests
- [Discord](https://discord.gg/omi) for community discussion
