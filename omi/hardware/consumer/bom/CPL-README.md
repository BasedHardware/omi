# Component Placement List (CPL) — Omi Consumer

Pick-and-place / centroid files for PCBA ordering. Generated from KiCad 9 PCB source files using `kicad-cli pcb export pos --use-drill-file-origin`.

**Source PCBs:** `OMI.kicad_pcb` (mainboard v1.2), `OMI-Charger.kicad_pcb` (charger v1.0), `OMI-FPC.kicad_pcb` (FPC v1.1)
**Generation date:** 2026-08-11 | **Board revision must match gerber revision** — regenerate CPL if PCB changes.

## Files

| File | Board | Components | Sides |
|------|-------|-----------|-------|
| `mainboard-cpl.csv` | Mainboard (4-layer HDI) | 144 | 120 top, 24 bottom |
| `charger-cpl.csv` | Charger (2-layer) | 8 | 8 top |
| `fpc-cpl.csv` | FPC (2-layer flex) | 2 | 1 top, 1 bottom |

Test points are excluded from CPL files. See `mainboard-testpoints.csv` for test point locations (reference only).

## Format

JLCPCB-compatible CSV:

| Column | Description |
|--------|-------------|
| Designator | PCB reference (e.g., C1, U1) — board-scoped, see BOM README |
| Val | Component value (e.g., 100nF, nRF5340-CLAA) |
| Package | KiCad footprint package name |
| Mid X | Centroid X coordinate in mm (drill/place file origin) |
| Mid Y | Centroid Y coordinate in mm (drill/place file origin) |
| Rotation | Component rotation in degrees |
| Layer | `top` or `bottom` |

## ⚠ MANDATORY Before Ordering

### 1. Preview in JLCPCB Assembly Viewer

Upload BOM + CPL + Gerbers to JLCPCB. **Visually inspect every component** in their assembly preview before confirming the order. Pay special attention to:

### 2. Rotation Corrections

JLCPCB's component zero-degree orientation may differ from KiCad's for some packages. The assembly preview will show misaligned parts as rotated incorrectly. Correct rotations in the CPL file or in the JLCPCB editor.

Common rotation issues:
- **SOT-523, SOT-883**: Pin-1 orientation varies between KiCad libs and JLCPCB
- **Polarized caps**: Verify polarity mark aligns with PCB silkscreen
- **LEDs (D2, D7)**: Anode/cathode orientation

### 3. WLCSP Pin-1 Verification (CRITICAL)

| Ref | Part | Package | Risk |
|-----|------|---------|------|
| U1 | nRF5340-CLAA | WLCSP-95 (4.4×4.0mm) | **HIGH** — pin A1 must match PCB pad A1 |
| U2 | nRF7002-CEAA-R7 | WLCSP-81 (3.75×3.385mm) | **HIGH** — same concern |
| U15 | BQ25101YFPR | DSBGA-6 | Medium |
| U13 | TPS628438YKAR | DSBGA-6 | Medium |

Cross-reference with Nordic datasheet pin-1 ball marking and KiCad PCB pad numbering.

### 4. Bottom-Side Components (Mainboard)

24 components are on the bottom layer **including 5 ICs**. This requires **dual-side assembly** (two reflow passes). Bottom-side components (verified from KiCad PCB `OMI.kicad_pcb`):

```
Passives (0201):  C14, C34, C36, C42, C48, C52, R4, R5, R6, R9, R10, R11, R24, R26, R27
NTC (0402):       R28
Diodes (SOD-523): D3, D4
MOSFET (SOT-523): Q7
ICs:              U5  (LSM6DS3TR-C, IMU, LGA-14, 2.5×3mm)
                  U7  (CSNP4GCR01-DPW, NAND flash, LGA-8, 8×6mm)
                  U9  (74LVC1G00, logic, SC70-5)
                  U12 (P25Q16SH, SPI flash, USON-8, 3×2mm)
                  U14 (GLF73910-BD01, battery protection, WLCSP-4, 0.97×0.97mm)
```

**⚠ This is NOT a trivial bottom side.** U7 (NAND, 8×6mm) is the largest back-side part. Discuss bottom-side reflow capability with your CM before ordering. See `STENCIL-REFLOW-NOTES.md` for detailed assembly guidance.

Order dual-side assembly (Standard, not Economic). **Let the CM decide reflow order** based on component mass distribution — heavy bottom-side parts (U7 at 8×6mm) may influence whether bottom or top goes first. See `STENCIL-REFLOW-NOTES.md` for full dual-reflow guidance, X-ray requirements, and stencil specifications.

### 5. Package Name Mapping

CPL uses KiCad footprint library names (e.g., `C0201`, `R0402`, `WLCSP94-0.35-...`). Note: KiCad's footprint says `WLCSP94` but U1 has 95 pads — this is a footprint naming artifact, not an error. JLCPCB matches components by LCSC part number from the BOM, not by CPL package name. Ensure BOM has LCSC part numbers (see `LCSC-SOURCING.md`) for proper matching.

### 6. Bottom-Side Rotation

Bottom-side components are mirrored in the KiCad export. **Verify in the JLCPCB assembly preview** that bottom-side ICs (U5, U7, U9, U12, U14) have correct pin-1 orientation after mirroring. Some PCBA tools apply an additional rotation offset for bottom-side parts.

### 7. DNP / Fiducials / Test Points

- **Test points** (TP1–TP18) are excluded from CPL files. See `mainboard-testpoints.csv` for their locations (reference only, not placed by machine).
- **Fiducials** are included in the gerber files, not the CPL. The CM uses fiducials for stencil and placement alignment.
- **DNP parts** (if any): parts with `Populate = no` in the BOM are excluded from CPL. Verify BOM and CPL row counts match after filtering.

## Origin

Coordinates use the **drill/place file origin** set in KiCad (`--use-drill-file-origin`). This matches the origin used for Gerber drill files, ensuring CPL placement aligns with the PCB.

## Regeneration

To regenerate from KiCad source:

```bash
# Full export (includes test points)
kicad-cli pcb export pos --format csv --units mm --side both \
  --use-drill-file-origin <board>.kicad_pcb -o output.csv

# Then filter test points (TP1-TP18) from mainboard output
# and rename headers for JLCPCB upload if needed:
#   Ref → Designator, Val → Comment, PosX → Mid X, PosY → Mid Y, Side → Layer
```

### BOM/CPL Consistency Check

Before uploading, verify:
1. **Row count:** CPL designator count should match BOM component designator count (excluding test points, assembly headers, PCB/PCBA references)
2. **Designator match:** Every designator in CPL appears in BOM and vice versa (for placed parts)
3. **Side match:** Bottom-side designators in CPL match the list above (24 parts including 5 ICs)
4. **Origin match:** CPL coordinates use the same origin as gerber drill files (drill/place file origin)
