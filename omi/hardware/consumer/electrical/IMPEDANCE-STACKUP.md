# Impedance & PCB Stackup — Omi Consumer Mainboard

↑ **[Build Guide](../BUILD-GUIDE.md)** | **[Consumer README](../README.md)**

**Sources:** KiCad PCB (`OMI.kicad_pcb`, `OMI-Charger.kicad_pcb`, `OMI-FPC.kicad_pcb`), gerber drill files (`OMI-front-in1.drl`, `OMI-in1-in2.drl`, `OMI-in2-back.drl`, `OMI-PTH.drl`), gerber job files

## Stackup (Design Intent — from KiCad 9 PCB Source)

4-layer HDI stackup, total thickness ~0.5934mm (including solder mask):

**⚠ This stackup is the design intent from KiCad.** The fab house will provide an approved stackup with their specific materials, glass styles, resin content, copper plating, and tolerances. Request the fab's impedance simulation report before build — do not assume the KiCad values are what the fab will deliver.

| Layer | Type | Thickness | Material | εr | Notes |
|-------|------|-----------|----------|-----|-------|
| F.SilkS | Silkscreen | — | — | — | Top silkscreen |
| F.Mask | Solder mask | 10µm | — | — | Top solder mask |
| **F.Cu** | **Copper** | **35µm (1 oz)** | Cu | — | Top signal + component layer |
| Dielectric 1 | **Prepreg** | **100µm** | FR4 | 4.5 | Between L1 and L2 |
| **In1.Cu** | **Copper** | **12µm (⅓ oz)** | Cu | — | Inner ground/power plane |
| Dielectric 2 | **Core** | **279.4µm** | FR4 | 4.5 | Central core |
| **In2.Cu** | **Copper** | **12µm (⅓ oz)** | Cu | — | Inner ground/power plane |
| Dielectric 3 | **Prepreg** | **100µm** | FR4 | 4.5 | Between L3 and L4 |
| **B.Cu** | **Copper** | **35µm (1 oz)** | Cu | — | Bottom signal + component layer |
| B.Mask | Solder mask | 10µm | — | — | Bottom solder mask |
| B.SilkS | Silkscreen | — | — | — | Bottom silkscreen |

**Surface finish:** ENIG (Electroless Nickel Immersion Gold) — required by the Omi design for WLCSP pad planarity. If using an alternative planar finish (OSP, immersion silver), verify wettability with Type 5 solder paste at 0.35mm pitch.

**Total copper thickness:** 35 + 12 + 12 + 35 = 94µm

**Total board thickness:** ~0.59mm (matches spec of ~0.6mm)

**Finished thickness tolerance:** 0.6mm ±0.1mm (verify with fab — some fabs quote ±10% or ±0.05mm for thin boards). The 0.5934mm sum includes solder mask; fabs may quote laminate thickness differently.

## Impedance Targets

### RF Traces (BLE/WiFi)

| Parameter | Target | Tolerance |
|-----------|--------|-----------|
| Single-ended RF trace | **50Ω** | ±10% |
| Reference layer | In1.Cu (ground plane, 100µm below F.Cu) | — |

For 50Ω microstrip on this stackup:
- εr = 4.5, h = 100µm (prepreg), t = 35µm (outer copper)
- Estimated trace width: ~130–150µm (5.1–5.9 mil)
- The actual trace width is set in the KiCad PCB — do not modify RF traces
- **Trace topology:** 50Ω microstrip referenced to In1.Cu ground. If there is ground pour on F.Cu adjacent to the RF trace (creating a CPWG — coplanar waveguide with ground topology), the gap between the trace and the adjacent copper also affects impedance. Check the KiCad layout for clearance to adjacent copper on RF nets.
- **Solder mask coverage:** Solder mask over the RF trace increases the effective εr of the surrounding medium, which **lowers** impedance (below the bare-board value). The preferred fix is to **strip solder mask from RF traces** (solder mask opening over the trace). If the fab applies mask over RF traces, the trace may need to be **narrower** to compensate and maintain 50Ω — request the fab's impedance simulation with and without mask modeled.
- **Ground plane continuity:** In1.Cu must be uninterrupted ground under all RF traces. No plane splits, voids, power islands, or signal routing under the antenna feed path. Verify in the KiCad PCB that In1.Cu is solid copper under the RF region.

### Differential Pairs (if present)

USB differential pairs (if routed) should target 90Ω differential impedance. This stackup was designed primarily for BLE/WiFi, not USB — verify if any differential pairs exist.

### General Signal Traces

General signal traces (SPI, I2C, GPIO) do not have strict impedance requirements at the edge rates typical on this board. The nRF5340 application core runs at 128MHz, but I/O edge rates are moderate. Standard trace widths (100–150µm) are adequate for most signals.

**Constrained signal nets** (require impedance control or short/matched routing):

| Net Group | Constraint | Reason |
|-----------|-----------|--------|
| RF feed (ANT pin to diplexer U3) | 50Ω ±10%, no stubs | Direct antenna performance impact |
| QSPI to flash (U7, CSNP4GCR01-DPW) | Short, well-referenced | High-speed data bus |
| SPI bus to nRF7002 (U2) | Short, well-referenced, matched | Inter-IC high-speed bus |
| 32MHz crystal traces (X2 to nRF5340) | Short, guarded | Sensitive to coupling |
| 40MHz crystal traces (X3 to nRF7002) | Short, guarded | Sensitive to coupling |

## JLCPCB Stackup Selection

When ordering PCBs from JLCPCB, select the closest standard stackup:

| Parameter | Specify |
|-----------|---------|
| Layers | 4 |
| Board thickness | **0.6mm** |
| Outer copper | 1 oz (35µm) |
| Inner copper | ⅓ oz (12µm) — design intent; JLCPCB standard inner copper is 0.5 oz (17.5µm), so specify ⅓ oz explicitly or accept 0.5 oz and request updated impedance simulation |
| Material | FR4 (standard) |
| Surface finish | **ENIG** |
| Impedance control | **Yes** — specify 50Ω single-ended microstrip |

**⚠ JLCPCB does not offer a standard 0.6mm 4-layer impedance-controlled stackup.** Their standard controlled-impedance offerings start at 0.8mm (as of 2026). Options:
- **Request a custom stackup** matching the design (100µm prepreg L1–L2) — JLCPCB supports custom stackups but with longer lead time and higher cost.
- **Use 0.8mm with adjusted prepreg** — if 0.6mm is not critical for the enclosure, a 0.8mm stackup with controlled impedance may be easier to source. Verify mechanical clearance.
- **Do NOT let the CM adjust RF trace widths without agreement** — antenna matching depends on the original trace geometry. Request an impedance report with the order and review before build.

### HDI Requirements

| Feature | Value | Notes |
|---------|-------|-------|
| Minimum trace/space | 3/3 mil (76.2/76.2µm) | Required for WLCSP breakout |
| Minimum via drill | **0.102mm (4 mil)** — laser-drilled microvias | Blind vias L1–L2 and L3–L4 |
| Via-in-pad | **Yes** — resin-filled + copper-capped (IPC-4761 Type VII) | Required under WLCSP footprints |
| Blind vias L1–L2 | **159** (0.102mm drill, laser) | WLCSP breakout, outer-layer routing |
| Blind vias L3–L4 | **17** (0.102mm drill, laser) | Bottom-side breakout |
| Buried vias L2–L3 | **55** (0.152mm drill, mechanical) | Inner-layer routing |
| Through-hole vias L1–L4 | **183** (0.152mm drill) | Signal and power vias |
| Annular ring | ≥0.1mm | Standard |
| Sequential lamination | **Required** | Blind + buried vias require at least 3 lamination cycles |
| HDI type | **Type II** (1+ N +1 with buried vias) | Blind vias L1–L2 and L3–L4, plus buried L2–L3 |
| Lamination cycles | **3** | (1) Core L2–L3 with buried vias, (2) add L1 prepreg+copper with blind L1–L2, (3) add L4 prepreg+copper with blind L3–L4 |

**Note:** HDI PCBs with via-in-pad, blind/buried vias, ENIG, and impedance control at 0.6mm are not a standard product. Not all fabs support HDI Type II — verify the fab handles sequential lamination with 3 cycles. Request a quote — pricing depends heavily on capabilities and panel utilization. Expect 2–3× cost and 1–2 week longer lead time vs standard 4-layer boards.

**⚠ JLCPCB ordering note:** JLCPCB's standard service does **not** support blind/buried vias. You must select their **HDI** or **Advanced** PCB service to get blind/buried via capability. When uploading gerbers with blind/buried drill files, JLCPCB will prompt you to upgrade to the HDI process — confirm this and verify the via stack (L1–L2 blind, L3–L4 blind, L2–L3 buried) is correctly recognized. The annular ring minimum of 0.1mm applies to through-hole vias; for 0.102mm laser-drilled microvias (blind L1–L2 and L3–L4), JLCPCB's HDI process has its own annular ring rules — confirm with their HDI DFM check.

## Charger Board Stackup

| Parameter | Value |
|-----------|-------|
| Layers | 2 |
| Thickness | ~1.0mm (KiCad design: 0.9mm core + copper + mask) |
| Copper | 1 oz outer |
| Material | FR4 |
| Surface finish | Specify HASL or ENIG when ordering (KiCad design: unspecified). ENIG recommended for pogo pin pads. |
| Impedance control | Not required |

## FPC Stackup

| Parameter | Value |
|-----------|-------|
| Layers | 2 |
| Thickness | 0.3mm |
| Material | Polyimide |
| Copper | 1 oz (35µm) both layers |
| Surface finish | Specify ENIG when ordering (KiCad design: unspecified) |
| Cover layer | Polyimide coverlay (not solder mask) |

See `FPC-FLEX-FAB-NOTES.md` for flex-specific fabrication details.

## Design Notes

### Dielectric Constraints

The KiCad PCB has `dielectric_constraints no` set, meaning the PCB editor does not enforce impedance during routing. The designer used manual trace width control for RF traces. This is common for designs where impedance was calculated externally or verified by the fab house.

### Loss Tangent

FR4 dielectric loss tangent is set to 0.02 in the design — standard value for generic FR4. For 2.4GHz RF performance, this is adequate. Higher-frequency designs (>6GHz) would benefit from low-loss materials (e.g., Megtron 6), but that is not necessary for BLE/WiFi at 2.4–5GHz.

### Grid Origin

The PCB drill/place file origin is set at (144.780, 107.571) mm. This is the reference point for all gerber, drill, and CPL coordinates. It is set via `(grid_origin 144.780155 107.571157)` in the KiCad PCB file.
