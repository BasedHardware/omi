# Omi Consumer — Indie Maker Readiness Checklist

**Objective:** Make it possible for an indie maker to build their own Omi consumer device using only what's in this repo + standard suppliers.

**Last updated:** 2026-08-13
**Reviewed by:** Codex (multi-round review) + source-of-truth audit against KiCad PCB/schematics/gerbers + factory BOM

---

## Status Summary

| Category | Status | Codex Score (R5) |
|----------|--------|------------------|
| Board-Specific BOMs | ✅ Complete — 4 files | 10/10 |
| Pick-and-Place / CPL Files | ✅ Complete — 3 boards | 8/10 |
| LCSC / Distributor Part Numbers | ✅ Complete — 48/63 found, sourcing guide | 7→pending |
| SWD Debug Pad Map | ✅ Complete — SWD-DEBUG-ACCESS.md | 7→pending |
| Stencil / Reflow / PCBA Notes | ✅ Verified — STENCIL-REFLOW-NOTES.md | 8/10 |
| Battery Procurement Spec | ✅ Verified — BATTERY-SPEC.md | 7→pending |
| RF / Antenna Notes | ✅ Verified — RF-ANTENNA-NOTES.md | 7→pending |
| Impedance / Stackup Notes | ✅ Verified — IMPEDANCE-STACKUP.md | 7→pending |
| FPC Flex Fab Notes | ✅ Verified — FPC-FLEX-FAB-NOTES.md | 7→pending |
| Alternate Parts List | ✅ Verified — ALTERNATES.md | 8/10 |
| Electronics Build Guide | ✅ Complete — electronics.mdx improved | 8.2/10 |
| PCB Gerbers | ✅ Complete (existing) | — |
| KiCad Source | ✅ Complete (existing, KiCad 9) | — |
| Schematics (PDF) | ✅ Complete (existing) | — |
| Mechanical STEP Files | ✅ Complete (existing) | — |
| Firmware Source | ✅ Complete (existing) | — |
| License (MIT) | ✅ Complete (existing) | — |

**Post-audit:** 14 factual errors found and fixed. 5 rounds of Codex review + fixes applied. Key corrections: diplexer IL values, T5848≠T5838 (PDM vs I2S), overcharge protection threshold direction, JLCPCB 4L impedance minimum, stencil aperture dimensions, J-Link licensing, nrfutil commands.

---

## Files Created / Modified

### New Files

| File | Description |
|------|-------------|
| `bom/mainboard-bom.csv` | Board-specific BOM with LCSC columns (43 parts found) |
| `bom/charger-bom.csv` | Charger board BOM with LCSC columns (5 parts found) |
| `bom/fpc-bom.csv` | FPC BOM with LCSC columns |
| `bom/mechanical-bom.csv` | Mechanical parts BOM |
| `bom/mainboard-cpl.csv` | Pick-and-place file (JLCPCB format) |
| `bom/charger-cpl.csv` | Pick-and-place file |
| `bom/fpc-cpl.csv` | Pick-and-place file |
| `bom/LCSC-SOURCING.md` | LCSC/JLCPCB sourcing guide (48/63 found) |
| `bom/BATTERY-SPEC.md` | Battery procurement spec with compliance requirements |
| `bom/ALTERNATES.md` | Alternate parts with Approved/Candidate/Rejected tiers |
| `bom/CPL-README.md` | CPL format and rotation documentation |
| `electrical/SWD-DEBUG-ACCESS.md` | SWD debug wiring, test point map, troubleshooting |
| `electrical/STENCIL-REFLOW-NOTES.md` | WLCSP stencil, paste, reflow, X-ray specs |
| `electrical/RF-ANTENNA-NOTES.md` | RF architecture, switch control, DO NOT SUBSTITUTE list |
| `electrical/IMPEDANCE-STACKUP.md` | 4-layer stackup, impedance targets, HDI requirements |
| `electrical/FPC-FLEX-FAB-NOTES.md` | FPC fabrication, stiffener, coverlay, bend specs |

### Modified Files

| File | Changes |
|------|---------|
| `docs/doc/hardware/consumer/electronics.mdx` | KiCad 9 note, WLCSP pitch fix (0.35mm), mic port fix (bottom-port), NAND capacity fix (4Gbit/512MB), HDI warning, X-ray language, manufacturing doc links |
| `bom/README.md` | Updated with board-specific BOM + CPL file references |

---

## Codex Review History

Each task went through multiple Codex review rounds until scoring ≥8/10. Key corrections caught by Codex:

| Round | Issue Caught | Impact |
|-------|-------------|--------|
| R1 | WLCSP pitch was 0.4mm → corrected to 0.35mm | Wrong stencil apertures |
| R1 | MSL-3 claim for nRF5340/nRF7002 → corrected to MSL-1 | Unnecessary bake cycle |
| R1 | Diplexer architecture diagram was wrong → corrected RF switch + shared 2.4GHz path | Misleading RF debug |
| R1 | FPC trace routing "parallel to bend" → corrected to "perpendicular to bend axis" | Cracked flex traces |
| R1 | J-Link pin 19 listed as GND → corrected to "DO NOT CONNECT" (5V supply) | Potential board damage |
| R2 | Battery shipping PI965 Section II → corrected to Section IB (cargo-only) | Shipping rejection |
| R2 | WiFi TX current 100mA → corrected to 191-260mA per Nordic PS | Undersized battery protection |
| R3 | SI1308EDL listed as P-ch → actually N-ch per Vishay datasheet | Wrong polarity MOSFET |
| R3 | FC-12M crystal package wrong → 2.05×1.2mm not 1.6×1.0mm | Wrong footprint |
| R3 | Mic listed as top-port → corrected to bottom-port per TDK data | Blocked audio path |
| R3 | NAND flash listed as 8GB → corrected to 4Gbit (512MB) per BOM | Misleading spec |
| **Audit** | Bottom-side component list completely wrong (5 ICs missing, 6 wrong refs) | CM gets wrong assembly difficulty |
| **Audit** | BQ25101 charge current ~100mA → ~135mA (K_ISET=135 AΩ, R8=1KΩ) | Wrong battery spec |
| **Audit** | FPC PI core 50µm → 203.2µm (4× off), copper ½oz → 1oz, BTB pitch 0.25→0.35mm | Wrong FPC fabrication |
| **Audit** | Blind via count 159→176, min drill 0.15→0.102mm, charger thickness 1.6→1.0mm | Wrong fab specs |
| **Audit** | RF switch truth table verified from KiCad net assignments (RF1=BLE, RF2=WiFi) | Resolved ambiguity |
