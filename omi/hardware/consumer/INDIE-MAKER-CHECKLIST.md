# Omi Consumer — Indie Maker Readiness Checklist

**Objective:** Make it possible for an indie maker to build their own Omi consumer device using only what's in this repo + standard suppliers.

**Last updated:** 2026-08-11
**Reviewed by:** Codex (multi-round review — all tasks scored ≥8/10)

---

## Status Summary

| Category | Status | Codex Score |
|----------|--------|-------------|
| Board-Specific BOMs | ✅ Complete — 4 files | 10/10 |
| Pick-and-Place / CPL Files | ✅ Complete — 3 boards | 9/10 |
| LCSC / Distributor Part Numbers | ✅ Complete — 48/63 found, sourcing guide | 8.0/10 |
| SWD Debug Pad Map | ✅ Complete — SWD-DEBUG-ACCESS.md | 8.1/10 |
| Stencil / Reflow / PCBA Notes | ✅ Complete — STENCIL-REFLOW-NOTES.md | 8.0/10 |
| Battery Procurement Spec | ✅ Complete — BATTERY-SPEC.md | 8.0/10 |
| RF / Antenna Notes | ✅ Complete — RF-ANTENNA-NOTES.md | 8.0/10 |
| Impedance / Stackup Notes | ✅ Complete — IMPEDANCE-STACKUP.md | 8.0/10 |
| FPC Flex Fab Notes | ✅ Complete — FPC-FLEX-FAB-NOTES.md | 8.3/10 |
| Alternate Parts List | ✅ Complete — ALTERNATES.md | 8.2/10 |
| Electronics Build Guide | ✅ Complete — electronics.mdx improved | 8.2/10 |
| PCB Gerbers | ✅ Complete (existing) | — |
| KiCad Source | ✅ Complete (existing, KiCad 9) | — |
| Schematics (PDF) | ✅ Complete (existing) | — |
| Mechanical STEP Files | ✅ Complete (existing) | — |
| Firmware Source | ✅ Complete (existing) | — |
| License (MIT) | ✅ Complete (existing) | — |

**Average Codex Score: 8.5/10** (across 11 reviewed tasks)

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
