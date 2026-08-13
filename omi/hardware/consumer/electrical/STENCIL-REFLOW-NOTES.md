# Stencil & Reflow Assembly Notes — Omi Consumer

## Assembly Complexity

The Omi mainboard uses advanced packages that **require professional PCBA assembly**:

| Component | Package | Pitch | Concern |
|-----------|---------|-------|---------|
| nRF5340-CLAA (U1) | WLCSP-95 | **0.35mm** ball pitch | Cannot be hand-soldered |
| nRF7002-CEAA-R7 (U2) | WLCSP-81 | **0.35mm** ball pitch | Cannot be hand-soldered |
| BQ25101YFPR (U15) | DSBGA-6 | 0.5mm ball pitch | Very difficult to hand-solder |
| TPS628438YKAR (U13) | DSBGA-6 | 0.5mm ball pitch | Very difficult to hand-solder |
| TPS22916CYFPR (U6, U11) | DSBGA-4 | 0.5mm ball pitch | Very difficult to hand-solder |
| TXS0104EYZTR (U4) | DSBGA-12 | 0.5mm ball pitch | Very difficult to hand-solder |
| Most passives | 0201 (0.6mm × 0.3mm) | N/A | Requires pick-and-place machine |

**Recommendation:** Order turnkey PCBA from JLCPCB (Standard assembly, not Economic), PCBWay, or equivalent. Do NOT attempt hand assembly.

## Stencil Specifications

### Mainboard Stencil

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| **Thickness** | **0.075mm (3 mil)** preferred; 0.10mm (4 mil) only with CM-proven process | Required for 0.35mm pitch WLCSP. Use step-down stencil if CM supports it (0.075mm in WLCSP/0201 regions, 0.10–0.12mm for larger parts). |
| Material | Stainless steel, **laser-cut + electropolished** | Electropolish/nano-coat required for reliable paste release at area ratio <0.66. |
| WLCSP aperture | Rounded-square or square, sized to match PCB land pattern | Typically 1:1 to 5–10% reduced from PCB pad. Validate by area ratio and SPI. |
| 0201 aperture | 10–20% reduction from pad, or home-plate/reverse-home-plate | Prevents bridging while maintaining adequate paste volume. |
| Fiducial openings | Yes — match PCB fiducials | Required for stencil-to-PCB alignment. |
| **SPI validation** | **Required** | Solder paste inspection for height/volume/alignment acceptance before placement. |

> **Why 0.075mm?** At 0.35mm pitch, the WLCSP pad aperture is approximately 200–230µm. On a 100µm foil, the area ratio is ~0.50–0.58 (below IPC ≥0.66 guideline for reliable paste release). A 75µm foil brings the area ratio to ~0.67–0.77. If the CM has demonstrated repeatable yield at 100µm with electropolish and SPI, that is acceptable — otherwise specify 75µm.

> **Placement tolerance:** WLCSP at 0.35mm pitch requires ±25µm placement accuracy. Confirm CM uses vision alignment with local fiducials and low placement force (~1N) for WLCSP packages.

> **Note on pitch:** The nRF5340-CLAA and nRF7002-CEAA-R7 WLCSP packages have a ball pitch of **0.35mm** per Nordic product specifications (e = 0.35mm). Some generic references cite 0.4mm — verify against the actual datasheet.

### Charger Board Stencil

| Parameter | Value |
|-----------|-------|
| Thickness | 0.12mm (5 mil) — standard |
| Material | Stainless steel, laser-cut |

Charger board uses 0402/0805 passives and SOT/DRV packages — no WLCSP. Standard stencil thickness is fine.

### FPC Stencil

FPC flex board has only 2 SMD connectors (J1, J3). Stencil may not be needed if assembled by hand or if PCBA house handles FPC assembly separately. If stencil is used: 0.10mm polyimide-compatible.

## Solder Paste

| Parameter | Requirement |
|-----------|-------------|
| **Type** | **Type 5 (15–25µm)** preferred for 0.35mm pitch WLCSP; **Type 4 (20–38µm)** acceptable if CM validates SPI results |
| Alloy | SAC305 (Sn96.5/Ag3.0/Cu0.5) — lead-free, RoHS |
| Flux | No-clean, halogen-free |
| Shelf life | Check expiration; paste must be refrigerated (2–10°C) |

> **Why Type 5 preferred?** At 0.35mm pitch with ~200µm apertures, the 5-ball rule (aperture ≥ 5 × largest particle) gives: 200µm / 5 = 40µm max particle. Type 4 max particle is 38µm (marginal). Type 5 max particle is 25µm (comfortable margin). If any aperture drops below ~190µm, Type 4 becomes unreliable.

## Reflow Profile

### Lead-Free SAC305 Reflow (recommended)

| Phase | Temperature | Duration | Notes |
|-------|------------|----------|-------|
| Preheat | Ramp 1–3°C/sec to 150°C | ~90 sec | Gentle ramp, avoid thermal shock |
| Soak | 150–200°C | 60–120 sec | Flux activation, volatile evaporation |
| Ramp to peak | 200–245°C | ~30 sec | |
| Peak | **240°C ±5°C** | 10–20 sec | **Do not exceed 260°C** (WLCSP absolute max) |
| Time above liquidus (>217°C) | | **45–90 sec** | Critical for joint formation |
| Cooling | **-3 to -4°C/sec** | | Controlled cooling prevents stress; -6°C/s is too aggressive for most WLCSP |

> **Important:** Peak temperature must be measured at component body/joint using thermocouples on the actual board, not just the oven setpoint. The oven setpoint is typically 5–15°C higher than the joint temperature. Run a profiling board with thermocouples at: (1) under U1 WLCSP, (2) near a 0201 pad, (3) board edge, (4) board center.

### Critical Notes

1. **Maximum peak temperature: 260°C absolute.** Nordic lists both nRF5340 WLCSP-95 and nRF7002 WLCSP-81 as rated for 260°C max reflow. Target 240°C ±5°C at the joint to maintain margin.

2. **Moisture sensitivity: MSL-1.** Nordic classifies both nRF5340 WLCSP and nRF7002 WLCSP as **MSL-1** (unlimited floor life, no bake required). However, always verify from the actual package label on received reels — classification can vary by package revision or supplier relabeling.
   - MSL-1: Unlimited floor life (no bake required)
   - If reel label shows MSL-3 (unlikely for WLCSP but possible for repackaged stock): Bake at 125°C for 24 hours before reflow, or use within 168 hours of opening dry pack
   - Check CSNP4GCR01-DPW (U7, NAND flash, LGA-8) — likely MSL-3; verify and handle accordingly
   - Check all other DSBGA parts (U4, U6, U11, U13, U15) for their MSL ratings

3. **Dual-side assembly required** — Mainboard has 24 bottom-side components. Assembly sequence:
   - **Pass 1:** Print paste on bottom, place bottom components, reflow
   - **Pass 2:** Print paste on top, place top components, reflow
   - Bottom components are held by surface tension during second reflow
   - **Bottom-side retention check:** All 24 bottom components are small passives and SOT/SOD packages (see list below). No heavy connectors or tall parts on bottom. Component weight is well within surface tension holding force.
   - Verify all bottom-side parts are rated for minimum 2× reflow cycles per their datasheets

4. **Bottom-side components (24 parts):**
   ```
   C14, C34, C36, C42, C48, C52, D3, D4, Q7, R4, R5, R6, R9, R10, R11,
   R24, R25, R26, R27, R34, R35, R36, R47, R48
   ```
   All are 0201 passives, SOD-523 diodes, or SOT-523 MOSFET — no adhesive needed.

5. **PCB land pattern:** WLCSP pads should be NSMD (Non-Solder Mask Defined) for best alignment. Verify solder mask registration is adequate. If via-in-pad is used under WLCSP, vias must be filled and capped (plated over) to prevent solder wicking.

## Post-Reflow Inspection

### SPI (Solder Paste Inspection) — BEFORE Placement

Run SPI after stencil printing, before component placement:

| Metric | Acceptance |
|--------|-----------|
| Paste height | Within ±20% of stencil thickness |
| Paste volume | Within ±30% of nominal |
| Paste position | Within ±50µm of pad center |
| Bridge detection | No paste bridging between adjacent pads |

Reject and re-print if SPI fails. Do not proceed to placement with marginal paste.

### X-Ray Inspection (REQUIRED for first builds)

WLCSP and BGA joints are hidden under the package — visual inspection cannot verify solder quality. Use 2D X-ray minimum; angled X-ray or laminography preferred for first articles to detect head-in-pillow defects.

| What to Check | Pass Criteria |
|---------------|--------------|
| U1 (nRF5340) ball joints | All 95 balls present, uniform spherical shape, no bridges. Voiding <25% of projected joint area. |
| U2 (nRF7002) ball joints | All 81 balls uniform, voiding <25% of projected joint area. |
| U15/U13/U6/U11 (DSBGA) | All balls connected, no opens, no solder wicking into vias. |
| Head-in-pillow defects | No partial reflow (balls sitting on paste without wetting — visible as double-outline in X-ray). |
| Shorts/bridges | No solder bridges between adjacent balls. |
| Package alignment | Package centered on land pattern, no skew >10% of pitch. |
| Via-in-pad wicking | No solder drawn into unfilled vias under WLCSP (if present). |

**First-article inspection:** 100% X-ray all WLCSP/BGA joints on first 3–5 boards. If yield is acceptable, reduce to statistical sampling for production.

### AOI (Automated Optical Inspection)

| Component Type | Check |
|----------------|-------|
| 0201 passives | No tombstoning, correct polarity (caps), adequate wetting, no side overhang |
| SOD-523 diodes (D1, D3, D4) | Polarity matches silkscreen, adequate end termination |
| RGB LEDs (D2, D7) | Correct pin-1 orientation, all pads wetted |
| Crystals (X1, X2, X3) | Flat against pads, no tilt, no solder beads |
| Pogo pins (PP1–PP6) | Vertical alignment, spring action, correct height |
| BTB connector (J1) | All pins soldered, no solder bridges, latch undamaged |
| MEMS mic (MIC1, MIC2) | Sound port unobstructed, no flux residue in port |
| IC markings | Verify part markings match BOM (spot-check for counterfeits) |

### Visual / Manual Checks

- No solder beads or splatter on board surface
- No flux residue in acoustic path (mic ports)
- Board cleanliness acceptable for no-clean process
- No PCB delamination or discoloration from reflow

## PCBA House Ordering Package

When ordering turnkey PCBA, provide the CM with this complete package:

### Required Files
1. **Gerbers** — from `gerbers/` directory (specify canonical mainboard zip)
2. **BOM** — per-board CSV from `bom/` directory, filtered to component rows only
3. **CPL** — per-board CSV from `bom/` directory (centroid/placement files)
4. **Assembly drawings** — annotated top/bottom views showing component placement, polarity marks, pin-1 indicators
5. **Stackup specification** — 4-layer, 0.6mm, ENIG (see `IMPEDANCE-STACKUP.md`)

### Specifications to Communicate
| Item | Value |
|------|-------|
| Assembly type | Standard (not Economic) — required for WLCSP |
| Sides | Dual-side (bottom first, top second) |
| Stencil thickness | 0.075mm mainboard (electropolished), 0.12mm charger |
| Solder paste | Type 5 SAC305, no-clean |
| IPC class | Class 2 (standard commercial) |
| SPI | Required before placement |
| X-ray | Required for U1, U2 (WLCSP), and all DSBGA packages |
| No-substitution list | See RF-critical and IC parts in BOM — marked DO NOT SUBSTITUTE |
| First-article report | Request photos, SPI report, X-ray images, and reflow profile plot |

### CM DFM Review
Request a DFM (Design for Manufacturability) review from the CM before build. Key items for CM feedback:
- Stencil aperture design for 0.35mm pitch WLCSP
- Via-in-pad handling under WLCSP footprints
- 0201 tomb-stoning risk assessment
- Dual-reflow thermal compatibility of bottom-side parts
- Component-specific thermal limits
