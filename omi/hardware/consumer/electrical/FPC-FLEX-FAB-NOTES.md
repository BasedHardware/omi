# FPC Flex-Specific Fabrication Notes — Omi Consumer

↑ **[Build Guide](../BUILD-GUIDE.md)** | **[README](../README.md)**

**Sources:** KiCad PCB (`OMI-FPC.kicad_pcb`), KiCad schematic (`OMI-FPC.kicad_sch`), gerber job (`OMI-FPC-job.gbrjob`), factory BOM (`omi-bom.csv`)

## Overview

The Omi FPC (Flexible Printed Circuit) connects the mainboard to the charger board via the BTB connector. It carries **9 signals**: SWD debug (SWDCLK, SWDIO), UART (TXD, RXD), power (VIN+, VDD_3V3, bat+), reset (~RESET), and GND. It is a 2-layer flex with 2 components (~29.3 × 12.5mm per gerber).

## FPC Specifications

| Parameter | Value | Notes |
|-----------|-------|-------|
| **Layers** | 2 | Minimum for signal routing + ground |
| **Material** | Polyimide (Kapton or equivalent) | Standard flex base material |
| **Total thickness** | ~0.3mm (see stackup below) | Including coverlay; confirm with fab |
| **Copper type** | **RA (rolled annealed) preferred** | RA copper has superior bend fatigue life vs. ED (electrodeposited) copper. ED is acceptable for non-bend zones only. |
| **Copper weight** | **1 oz (35µm)** | Per KiCad PCB design (both layers). ½ oz is NOT in the design files. |
| **Surface finish** | ENIG recommended | KiCad design: unspecified. ENIG recommended for BTB connector (0.35mm pitch) soldering reliability. J1 charging contact ring may benefit from hard-gold plating (>10µ") if subject to repeated mating — specify separately if needed. |
| **Cover layer** | **Polyimide coverlay** (not solder mask) | Coverlay provides better flex life than liquid solder mask |
| **Board version** | v1.1 | Per factory BOM (gerber zip filename says v1.0 — BOM is authoritative) |
| **IPC class** | IPC-6013 Class 2 | Standard commercial flex; Class 3 for medical/aerospace only |

### FPC Stackup Breakdown

| Layer | Material | Thickness | Notes |
|-------|----------|-----------|-------|
| Top coverlay | PI 25µm + adhesive 25µm | ~50µm | Laser-cut openings for pads |
| Top copper | Cu (RA preferred) | 35µm (1 oz) | Signal layer (per KiCad design) |
| PI core | Polyimide | **203.2µm (8 mil)** | Base dielectric (per KiCad stackup) |
| Bottom copper | Cu (RA preferred) | 35µm (1 oz) | Ground/signal layer (per KiCad design) |
| Bottom coverlay | PI 25µm + adhesive 25µm | ~50µm | Laser-cut openings for pads |
| **Total (flex only)** | | **~0.37mm** | KiCad laminate stack reports 0.2932mm (copper + PI core), but IPC-2223C bend radius uses the **total flex thickness including coverlay**: 50 + 35 + 203.2 + 35 + 50 = 373.2µm ≈ 0.37mm. Stiffener adds 0.3mm in stiffened zones. |

**Note:** Bend radius calculations apply to the **total flex thickness including coverlay (~0.37mm)**, not the stiffened zones. Stiffened areas must not overlap with or extend into the bend zone.

## Components

Only 2 SMD components on the FPC:

| Ref | MPN | Description | Side | Notes |
|-----|-----|-------------|------|-------|
| J1 (FPC) | Custom charging contact ring | D9.9×H1.0mm, sourced by drawing/SKU | Top | Custom part — no standard MPN. **Not the same as mainboard J1.** |
| J3 (FPC) | ST-BTB-K3570606M | BTB male connector, 6+4P, **0.35mm pitch** (per KiCad PCB footprint pad spacing) | Bottom | Mates with mainboard J1 (ST-BTB-K3570606F, female). Mating height: 0.6mm. BOM says "0.25mm pitch" but KiCad footprint `BTB6_0d35` confirms 0.35mm — **resolve with Suntech before ordering**. |

## Stiffener

### What is the `Enhance` Gerber Layer?

The FPC gerber zip includes a file `OMI-FPC-Enhance.gbr`. This is the **stiffener area** — a rigid reinforcement bonded to the back of the flex in specific zones.

### Stiffener Specifications

| Parameter | Value | Notes |
|-----------|-------|-------|
| **Material** | FR4 or polyimide | FR4 is cheaper; polyimide is more flex-compatible |
| **Thickness** | **0.3mm** | Per KiCad annotation: "Total Thickness = 0.3mm" — this likely means stiffener alone (flex is 0.29mm, total with stiffener ~0.59mm). Confirm interpretation with fab. |
| **Applied to** | **Bottom side** (same side as J3 BTB connector) | Stiffener backs the connector for insertion force resistance |
| **Location** | **Defined by `OMI-FPC-Enhance.gbr`** — stiffener zones under BTB connector (J3) and charging ring (J1) areas | Fab must use the Enhance layer as stiffener outline; do not guess placement |
| **Adhesive** | 3M 467 or equivalent PSA (~50µm), pressure-laminated (not thermally cured — 3M 467 is a pressure-sensitive adhesive) | Standard FPC stiffener bonding. Adhesive adds ~0.05mm to stiffened zone thickness. |
| **Registration** | ±0.2mm to `Enhance` layer outline | Misregistered stiffener can overhang into bend zone or leave connector area unsupported |
| **Setback from bend zone** | ≥1.0mm from bend transition edge | Stiffener edge must NOT extend into or overlap the bend zone — abrupt stiffness transition causes stress concentration and cracking |

### Why Stiffeners Are Needed

The BTB connector (J3) requires a rigid backing for:
1. **Insertion force resistance** — without stiffener, the flex bends instead of the connector engaging
2. **Solder joint reliability** — flex movement at the connector pads causes fatigue cracking
3. **Mating alignment** — stiffener keeps the connector flat and coplanar

The charging contact ring (J1) may also need a stiffener to:
1. Maintain flat contact surface against the enclosure
2. Resist pogo pin insertion force from the charger dock

## Coverlay vs. Solder Mask

**Use polyimide coverlay, NOT liquid photoimageable solder mask (LPI/LPISM).**

| Property | Coverlay | LPI Solder Mask |
|----------|---------|-----------------|
| Flex life | **Excellent** — survives thousands of flex cycles | Poor — cracks after few flex cycles |
| Adhesion | Thermoset adhesive, permanent | Can delaminate under flex stress |
| Thickness | ~50µm (25µm PI + 25µm adhesive) | 10–25µm |
| Resolution | Lower (laser-cut openings) | Higher (photo-defined) |
| Cost | Standard for flex | Cheaper but unsuitable for repeated flexing |

For the Omi FPC, which bends during assembly and may flex slightly in use, coverlay is the correct choice.

## Minimum Bend Radius

These are **minimum design targets** per IPC-2223C (Sectional Design Standard for Flexible Printed Boards). Confirm with your fab for the actual stackup and copper type. Larger radii are always preferred.

**⚠ Semi-flex warning:** At ~0.29mm with 1oz copper on both sides, this FPC is relatively stiff. It behaves more like a semi-flex than a thin flex. The bend radii below account for this — do not assume thin-flex rules apply.

**Grain direction:** Specify RA copper with the grain direction **perpendicular to the bend axis**. RA copper's grain structure gives superior bend life when bent across the grain. If the fab cannot control grain orientation, increase bend radii by 25%.

| Condition | Minimum Bend Radius | Notes |
|-----------|---------------------|-------|
| **Static bend (installed)** | ≥6× total flex thickness = **~2.2mm** | Bend held permanently in the assembled device. Based on ~0.37mm total flex thickness (including coverlay per IPC-2223C §4.3.2). |
| **Dynamic bend (repeated)** | ≥12× total flex thickness = **~4.5mm** | If FPC is flexed during operation or service. With 1oz copper, 12× is the IPC minimum — 15-20× preferred for >1,000 flex cycles. |
| **Assembly bend** | ≥6× total flex thickness = **~2.2mm** | One-time bend during device assembly. IPC-2223 recommends ≥6× for 1oz copper; 3× is too aggressive and risks cracking. |

**⚠ These values are for 1 oz RA copper (per KiCad design).** RA copper is **required** in bend zones — ED (electrodeposited) copper has inferior bend fatigue and must not be used where the FPC flexes. If the fab substitutes ED copper, increase bend radii by 50% minimum or reject the substitution for bend zones. 1 oz copper is stiffer than ½ oz — verify bend fatigue life with fab for the installed bend radius.

### Bend Location
- The FPC must bend to route from the mainboard BTB connector to the charging contact ring
- **Do not place components or stiffeners in the bend zone** — this is handled in the KiCad layout
- **Traces should cross the bend zone perpendicular to the bend axis** — this distributes strain evenly. Traces running parallel to the bend axis concentrate stress and are more likely to crack. (This should already be handled in the design.)
- Copper traces in the bend zone should use curved routing, not right angles

### Copper in the Bend Zone

- **Avoid solid copper fills (ground pours) through the bend zone** — solid copper stiffens the flex and is prone to cracking
- Use **hatched or crosshatched copper** (25–50% fill) for ground continuity through the bend if required
- **Balance copper on top and bottom layers** in the bend zone — asymmetric copper causes the flex to curl and concentrates strain on one side
- If ground continuity is not required through the bend, use copper relief (no copper in bend zone) with ground vias on either side

## Ordering Notes for FPC Fabrication

### JLCPCB Flex PCB Order Settings

| Parameter | Value |
|-----------|-------|
| Base material | Polyimide (flex) |
| Layers | 2 |
| Board thickness | 0.3mm |
| Copper weight | **1 oz** (per KiCad design) |
| Coverlay color | Yellow (standard polyimide) |
| Surface finish | ENIG |
| Stiffener | Yes — FR4, 0.3mm, per `Enhance` gerber layer (KiCad annotation: "Total Thickness = 0.3mm, ±0.03mm") |
| Min trace/space | Standard (4/4 mil or better) |
| Via covering | Covered with coverlay |

### Key Files for FPC Ordering

| File | Purpose |
|------|---------|
| FPC gerber zip | Copper layers, drill, outline |
| `OMI-FPC-Enhance.gbr` | Stiffener placement area |
| `fpc-bom.csv` | BOM (2 components) |
| `fpc-cpl.csv` | Component placement (2 components) |

### DFM Notes for FPC Fab

| Item | Requirement | Notes |
|------|-------------|-------|
| Annular ring | ≥0.1mm | Standard; verify fab can hold for any vias present |
| Coverlay expansion | Allow 50–75µm for thermal expansion during lamination | Coverlay openings may shift — pad openings should be oversized by this margin |
| Paste reduction for J3 | 10–15% paste reduction on 0.35mm pitch BTB pads | Prevents bridging during reflow |
| Panelization | **Routed/laser-cut with breakaway tabs** (NOT V-score — V-score cracks flex) | FPC is small (~29×13mm) — panel multiple units |
| Fiducials | Add at least 2 global fiducials if not already in gerber | Required for machine-placed J3 connector |

### Assembly Notes

- J1 (charging contact ring) is a **custom part** — must be consigned to the PCBA house
- J3 (BTB connector) is also not on LCSC — must be consigned
- Due to only 2 components, manual soldering may be more practical than PCBA turnkey for small quantities
- If PCBA house assembles the FPC, request stiffener application and coverlay before component placement
- **J3 electrical check:** After assembly, verify continuity and shorts on all 10 pins (6 signal + 4 ground, 0.35mm pitch — adjacent shorts are the primary risk)

### J3 Pin-to-Net Mapping

| J3 Pin | Net Name | Function | Mainboard J1 Pin |
|--------|----------|----------|-----------------|
| 1 | bat+ | Battery positive | 1 |
| 2 | VIN+ | Charger input voltage | 2 |
| 3 | VDD_3V3 | 3.3V regulated supply | 3 |
| 4 | GND | Ground | 4 |
| 5 | SWDCLK | SWD clock (debug) | 5 |
| 6 | SWDIO | SWD data (debug) | 6 |
| 7 | TXD | UART transmit | 7 |
| 8 | RXD | UART receive | 8 |
| 9 | ~RESET | nRF5340 reset (active low) | 9 |
| 10 | GND | Ground (shield) | 10 |

**⚠ Pin mapping is from KiCad schematic — verify against the physical connector datasheet from Suntech before first assembly.** The 6+4P format means 6 signal pins + 4 ground/shield pins; pin numbering may differ between male (J3) and female (mainboard J1).

### BTB Mechanical Stack

| Parameter | Value |
|-----------|-------|
| Mating height | 0.6mm (per BOM description) |
| FPC-side connector (J3) | ST-BTB-K3570606M (male) |
| Mainboard-side connector (J1) | ST-BTB-K3570606F (female) |
| Pitch | **0.35mm** (KiCad footprint) — resolve BOM "0.25mm" discrepancy with supplier |
| Stiffener under J3 | Required — 0.3mm FR4, per `Enhance` gerber layer |
| Insertion force | TBD — verify with Suntech datasheet |

## Quality Checks

### Pre-Assembly (Bare FPC)

1. **Visual inspection:** No delamination, no exposed copper outside pad openings, no coverlay lifting at edges. **Pass:** zero visible defects under 10× magnification.
2. **Dimensional:** Outline matches gerber ±0.1mm. Stiffener edges align to `Enhance` layer outline within **±0.2mm**. **Fail:** any stiffener overhang into bend zone.
3. **Coverlay opening registration:** Pad openings in coverlay expose full pad area with ≥50µm clearance to adjacent copper. **Fail:** coverlay overlapping any solderable pad.
4. **Flex test:** Gently flex FPC to installed bend radius (~2.2mm). **Pass:** no cracking, no delamination, no white stress marks visible under 10× magnification. **Fail:** any visible damage.
5. **Continuity:** Test all 9 signal nets from J1 pads to J3 pads with multimeter (see pin-to-net table above): SWDCLK, SWDIO, TXD, RXD, VIN+, VDD_3V3, bat+, ~RESET, GND. **Pass:** resistance ≤2Ω per trace. **Fail:** open (>10Ω) or short between adjacent nets (<100KΩ).
6. **Peel strength:** Stiffener must not peel off with 1 kg/cm perpendicular pull force. **Fail:** any delamination under light finger pressure.

### Post-Assembly (Populated FPC)

7. **Connector coplanarity:** With J3 populated, place FPC on flat surface. **Pass:** pins coplanar within **0.1mm** (measure with feeler gauge or optical). **Fail:** visible tilt or >0.1mm gap at any pin.
8. **Connector fit:** J3 must mate with mainboard J1 (ST-BTB-K3570606F) smoothly. **Pass:** latch engages fully, connector sits flat, no visible angular offset. **Fail:** incomplete latch engagement or connector angle >2°.
9. **Post-bend continuity:** After bending FPC to installed position (~2.2mm radius), re-test continuity on all 9 nets. **Pass:** resistance ≤2Ω (same as pre-bend). **Fail:** any increase >1Ω from pre-bend value indicates cracked trace.
10. **Contact ring inspection:** J1 must sit flat and concentric. **Pass:** contact resistance to FPC pads ≤100mΩ, ring concentric within ±0.1mm. **Fail:** resistance >200mΩ or visible misalignment.
