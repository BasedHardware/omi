# Omi Consumer — Open Source Hardware

Complete hardware design files for the Omi Consumer, the world's leading open-source AI wearable.

Licensed under MIT (see [LICENSE](LICENSE)).

## What's Inside

### Electrical (`electrical/`)
- **Mainboard** (nRF5340 + nRF7002): Altium source, Gerber files, schematics (v1.1 and v1.2)
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

## Questions?

- [GitHub Issues](https://github.com/BasedHardware/omi/issues) for bugs and feature requests
- [Discord](https://discord.gg/omi) for community discussion
