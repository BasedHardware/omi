# FPC Flex-Specific Fabrication Notes — Omi Consumer

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
| **Surface finish** | Specify ENIG when ordering | KiCad design: unspecified. ENIG needed for BTB connector soldering. |
| **Cover layer** | **Polyimide coverlay** (not solder mask) | Coverlay provides better flex life than liquid solder mask |
| **Board version** | v1.1 | Per factory BOM (gerber zip filename says v1.0 — BOM is authoritative) |

### FPC Stackup Breakdown

| Layer | Material | Thickness | Notes |
|-------|----------|-----------|-------|
| Top coverlay | PI 25µm + adhesive 25µm | ~50µm | Laser-cut openings for pads |
| Top copper | Cu (RA preferred) | 35µm (1 oz) | Signal layer (per KiCad design) |
| PI core | Polyimide | **203.2µm (8 mil)** | Base dielectric (per KiCad stackup) |
| Bottom copper | Cu (RA preferred) | 35µm (1 oz) | Ground/signal layer (per KiCad design) |
| Bottom coverlay | PI 25µm + adhesive 25µm | ~50µm | Laser-cut openings for pads |
| **Total (flex only)** | | **~0.29mm** | Matches KiCad 0.2932mm. Stiffener adds 0.3mm in stiffened zones. |

**Note:** Bend radius calculations apply to the **flex-only thickness (~0.29mm)**, not the stiffened zones. Stiffened areas must not overlap with or extend into the bend zone.

## Components

Only 2 SMD components on the FPC:

| Ref | MPN | Description | Side | Notes |
|-----|-----|-------------|------|-------|
| J1 (FPC) | Custom charging contact ring | D9.9×H1.0mm, sourced by drawing/SKU | Top | Custom part — no standard MPN. **Not the same as mainboard J1.** |
| J3 (FPC) | ST-BTB-K3570606M | BTB male connector, 6+4P, **0.35mm pitch** (per KiCad PCB footprint pad spacing) | Bottom | Mates with the BTB female connector on the mainboard (mainboard ref may differ — verify against mainboard schematic). BOM description says "0.25" but KiCad footprint `BTB6_0d35` confirms 0.35mm. |

## Stiffener

### What is the `Enhance` Gerber Layer?

The FPC gerber zip includes a file `OMI-FPC-Enhance.gbr`. This is the **stiffener area** — a rigid reinforcement bonded to the back of the flex in specific zones.

### Stiffener Specifications

| Parameter | Value | Notes |
|-----------|-------|-------|
| **Material** | FR4 or polyimide | FR4 is cheaper; polyimide is more flex-compatible |
| **Thickness** | **0.3mm** | Per KiCad annotation: "Total Thickness = 0.3mm" — ambiguous whether this means stiffener alone or stiffener + FPC combined. Confirm interpretation with fab. |
| **Location** | **Defined by `OMI-FPC-Enhance.gbr`** — stiffener zones under BTB connector (J3) and charging ring (J1) areas | Fab must use the Enhance layer as stiffener outline; do not guess placement |
| **Adhesive** | 3M 467 or equivalent PSA (pressure-sensitive adhesive) | Standard FPC stiffener bonding |
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

These are **minimum design targets** — confirm with your fab for the actual stackup and copper type. Larger radii are always preferred.

| Condition | Minimum Bend Radius | Notes |
|-----------|---------------------|-------|
| **Static bend (installed)** | ≥6× flex thickness = **~1.8mm** | Bend held permanently in the assembled device. Based on ~0.29mm flex-only thickness. |
| **Dynamic bend (repeated)** | ≥12× flex thickness = **~3.5mm** | If FPC is flexed during operation or service |
| **Assembly bend** | ≥3× flex thickness = **~0.9mm** | One-time bend during device assembly. Aggressive — verify with fab for 1oz copper. |

**⚠ These values are for 1 oz RA copper (per KiCad design).** If the fab substitutes ED copper, increase bend radii by 50% or request fab confirmation. 1 oz copper is stiffer than ½ oz — verify bend fatigue life with fab for the installed bend radius.

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

### Assembly Notes

- J1 (charging contact ring) is a **custom part** — must be consigned to the PCBA house
- J3 (BTB connector) is also not on LCSC — must be consigned
- Due to only 2 components, manual soldering may be more practical than PCBA turnkey for small quantities
- If PCBA house assembles the FPC, request stiffener application and coverlay before component placement

## Quality Checks

### Pre-Assembly (Bare FPC)

1. **Visual inspection:** Check coverlay adhesion, no delamination, no exposed copper outside pad openings.
2. **Dimensional:** Verify outline matches gerber. Check stiffener registration — stiffener edges should align to the `Enhance` layer outline within ±0.2mm.
3. **Coverlay opening registration:** Pad openings in coverlay must not overlap copper traces. Misregistered coverlay blocks soldering.
4. **Flex test:** Gently flex the FPC to its installed bend radius. It should not crack, delaminate, or show white stress marks.
5. **Continuity:** Test all traces from J1 pads to J3 pads with a multimeter — verify every signal path.
6. **Peel strength:** Stiffener should not peel off with light finger pressure. If it does, the adhesive is inadequate.

### Post-Assembly (Populated FPC)

7. **Connector coplanarity:** With J3 populated, place FPC on a flat surface — connector pins should be coplanar within 0.1mm. Non-coplanar connector causes intermittent contact.
8. **Connector fit:** J3 must mate with the mainboard BTB connector smoothly with the latch. Stiffener alignment is critical — if misaligned, the connector sits at an angle.
9. **Post-bend continuity:** After bending the FPC to its installed position, re-test continuity on all traces. Cracked traces may pass flat but fail under bend.
10. **Contact ring inspection:** J1 (charging contact ring) must sit flat and concentric. Verify contact resistance to FPC pads ≤100mΩ.
