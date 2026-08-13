# Component Placement List (CPL) — Omi Consumer

Pick-and-place / centroid files for PCBA ordering. Generated from KiCad 9 PCB source files using `kicad-cli pcb export pos --use-drill-file-origin`.

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

24 components are on the bottom layer. This requires **dual-side assembly** (two reflow passes). Bottom-side components:

```
C14, C34, C36, C42, C48, C52, D3, D4, Q7, R4, R5, R6, R9, R10, R11,
R24, R25, R26, R27, R34, R35, R36, R47, R48
```

Order dual-side assembly. Bottom side goes through reflow first, then top side.

### 5. Package Name Mapping

CPL uses KiCad footprint library names (e.g., `C0201`, `R0402`, `WLCSP94-0.35-...`). JLCPCB matches components by LCSC part number from the BOM, not by CPL package name. Ensure BOM has LCSC part numbers (Task 3) for proper matching.

## Origin

Coordinates use the **drill/place file origin** set in KiCad (`--use-drill-file-origin`). This matches the origin used for Gerber drill files, ensuring CPL placement aligns with the PCB.

## Regeneration

To regenerate from KiCad source:

```bash
# Full export (includes test points)
kicad-cli pcb export pos --format csv --units mm --side both \
  --use-drill-file-origin <board>.kicad_pcb -o output.csv

# Then filter test points (TP1-TP18) from mainboard output
```
