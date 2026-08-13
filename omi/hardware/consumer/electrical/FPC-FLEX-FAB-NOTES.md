# FPC Flex-Specific Fabrication Notes — Omi Consumer

## Overview

The Omi FPC (Flexible Printed Circuit) connects the mainboard to the charging contact ring. It is a simple 2-layer flex with minimal components.

## FPC Specifications

| Parameter | Value | Notes |
|-----------|-------|-------|
| **Layers** | 2 | Minimum for signal routing + ground |
| **Material** | Polyimide (Kapton or equivalent) | Standard flex base material |
| **Total thickness** | ~0.3mm (see stackup below) | Including coverlay; confirm with fab |
| **Copper type** | **RA (rolled annealed) preferred** | RA copper has superior bend fatigue life vs. ED (electrodeposited) copper. ED is acceptable for non-bend zones only. |
| **Copper weight** | ½ oz (18µm) or 1 oz (35µm) | ½ oz preferred for flexibility, especially through bend zone |
| **Surface finish** | ENIG | Required for BTB connector soldering |
| **Cover layer** | **Polyimide coverlay** (not solder mask) | Coverlay provides better flex life than liquid solder mask |
| **Board version** | v1.1 | Per gerber files |

### FPC Stackup Breakdown

| Layer | Material | Thickness | Notes |
|-------|----------|-----------|-------|
| Top coverlay | PI 25µm + adhesive 25µm | ~50µm | Laser-cut openings for pads |
| Top copper | Cu (RA preferred) | 18µm (½ oz) | Signal layer |
| PI core | Polyimide | 50µm | Base dielectric |
| Adhesive | Acrylic or epoxy | 25µm | Bonds copper to PI core |
| Bottom copper | Cu (RA preferred) | 18µm (½ oz) | Ground/signal layer |
| Bottom coverlay | PI 25µm + adhesive 25µm | ~50µm | Laser-cut openings for pads |
| **Total (flex only)** | | **~0.26mm** | Stiffener adds 0.2–0.3mm in stiffened zones |

**Note:** Bend radius calculations apply to the **flex-only thickness (~0.26mm)**, not the stiffened zones. Stiffened areas must not overlap with or extend into the bend zone.

## Components

Only 2 SMD components on the FPC:

| Ref | MPN | Description | Side | Notes |
|-----|-----|-------------|------|-------|
| J1 (FPC) | Custom charging contact ring | D9.9×H1.0mm, sourced by drawing/SKU | Top | Custom part — no standard MPN. **Not the same as mainboard J1.** |
| J3 (FPC) | ST-BTB-K3570606M | BTB male connector, 6+4P, 0.25mm pitch | Bottom | Mates with the BTB female connector on the mainboard (mainboard ref may differ — verify against mainboard schematic) |

## Stiffener

### What is the `Enhance` Gerber Layer?

The FPC gerber zip includes a file `OMI-FPC-Enhance.gbr`. This is the **stiffener area** — a rigid reinforcement bonded to the back of the flex in specific zones.

### Stiffener Specifications

| Parameter | Value | Notes |
|-----------|-------|-------|
| **Material** | FR4 or polyimide | FR4 is cheaper; polyimide is more flex-compatible |
| **Thickness** | 0.2–0.3mm | Typical for FPC stiffeners |
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
| **Static bend (installed)** | ≥6× flex thickness = **~1.6mm** | Bend held permanently in the assembled device. Based on ~0.26mm flex-only thickness. |
| **Dynamic bend (repeated)** | ≥12× flex thickness = **~3.2mm** | If FPC is flexed during operation or service |
| **Assembly bend** | ≥3× flex thickness = **~0.8mm** | One-time bend during device assembly. Aggressive — verify with fab for 1oz copper. |

**⚠ These values assume ½ oz RA copper.** If the fab substitutes 1 oz or ED copper, increase bend radii by 50% or request fab confirmation.

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
| Copper weight | ½ oz (or 1 oz if ½ oz unavailable) |
| Coverlay color | Yellow (standard polyimide) |
| Surface finish | ENIG |
| Stiffener | Yes — FR4, 0.2mm, per `Enhance` gerber layer |
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
