# Omi Consumer — Indie Maker Readiness

**Can an indie maker build their own Omi device?** Yes — with the right path.

**Last updated:** 2026-08-13
**Reviewed by:** Codex (6 rounds) + source-of-truth audit against KiCad PCB/schematics/gerbers + factory BOM

---

## Honest Assessment

The Omi consumer is **not a weekend project**. It uses WLCSP packages at 0.35mm ball pitch, a 4-layer HDI PCB with blind/buried vias, and a CNC aluminium enclosure. The electronics cannot be hand-soldered.

But you don't need to build it from scratch. The Omi factory already produces these boards — ordering pre-assembled subassemblies makes indie building realistic.

| Build Path | Feasibility | Who It's For |
|-----------|-------------|--------------|
| **Kit Build** (recommended) | ⭐⭐⭐⭐⭐ 9/10 | Anyone with basic soldering skills |
| **DIY from Scratch** | ⭐⭐⭐ 6/10 | Hardware engineers with PCBA sourcing experience |
| **Design Fork** | ⭐⭐ 4/10 | Engineers with RF/HDI PCB experience |

**Start here → [BUILD-GUIDE.md](BUILD-GUIDE.md)** — detailed instructions for all three paths.

**Kit assembly → [KIT-ASSEMBLY.md](KIT-ASSEMBLY.md)** — step-by-step guide for Kit buyers.

---

## What's in the Repo

Design files and manufacturing references for the Omi consumer device are open-source (MIT license). Some components must be obtained separately — see "What's NOT in the Repo" below.

### For Kit Builders

| What You Need | File | Status |
|--------------|------|--------|
| Assembly steps | [KIT-ASSEMBLY.md](KIT-ASSEMBLY.md) | ✅ Documented |
| Firmware flashing | [SWD-DEBUG-ACCESS.md](electrical/SWD-DEBUG-ACCESS.md) | ✅ Documented |
| Battery safety | [BATTERY-SPEC.md](bom/BATTERY-SPEC.md) | ✅ Documented |
| Build path selection | [BUILD-GUIDE.md](BUILD-GUIDE.md) | ✅ Documented |

### For DIY Builders (Engineers)

| What You Need | File | Status |
|--------------|------|--------|
| Component sourcing | [LCSC-SOURCING.md](bom/LCSC-SOURCING.md) | ✅ 48/63 parts on LCSC |
| Pick-and-place data | [CPL-README.md](bom/CPL-README.md) | ✅ 3 boards, rotation corrections |
| Stencil & reflow specs | [STENCIL-REFLOW-NOTES.md](electrical/STENCIL-REFLOW-NOTES.md) | ✅ WLCSP, dual-side, X-ray |
| PCB stackup & impedance | [IMPEDANCE-STACKUP.md](electrical/IMPEDANCE-STACKUP.md) | ✅ 4-layer HDI, impedance targets |
| FPC fabrication | [FPC-FLEX-FAB-NOTES.md](electrical/FPC-FLEX-FAB-NOTES.md) | ✅ Bend radius, stiffener, quality |
| RF & antenna | [RF-ANTENNA-NOTES.md](electrical/RF-ANTENNA-NOTES.md) | ✅ RF paths, switch control, enclosure strategy |
| Alternate parts | [ALTERNATES.md](bom/ALTERNATES.md) | ✅ Approved/candidate/rejected tiers |
| PCB Gerbers | `electrical/*/gerbers/` | ✅ Mainboard, charger, FPC |
| KiCad source | `electrical/*/altium/*.zip` | ✅ KiCad 9 format |
| Schematics (PDF) | `electrical/*/schematic.pdf` | ✅ All 3 boards |
| Mechanical STEP | `mechanical/` | ✅ Full device + charger assembly |
| Firmware source | `../../firmware/` | ✅ Zephyr RTOS / nRF Connect SDK |

### What's NOT in the Repo (Must Obtain Separately)

| Item | Where | Notes |
|------|-------|-------|
| J-Link debug probe | [SEGGER](https://www.segger.com/products/debug-probes/j-link/) | ~$20 for EDU Mini |
| Battery (150mAh LiPo coin cell) | Battery supplier | See [BATTERY-SPEC.md](bom/BATTERY-SPEC.md) — dangerous goods shipping |
| CNC enclosure | Machining service | AL6061-T6, STEP files in `mechanical/` |
| Consigned components (24 parts) | DigiKey, Mouser, etc. | See [LCSC-SOURCING.md](bom/LCSC-SOURCING.md) |

---

## Known Constraints

Things to be aware of that these docs cannot solve:

- **No VNA measurements** in the final enclosure yet — RF antenna notes are based on design analysis, not measured S-parameters
- **No PCB photos** with test point locations labeled — SWD doc describes locations from silkscreen only
- **JLCPCB pricing changes** — component costs and consignment quotes are estimates, not live quotes
- **Suntech BTB connector pitch** — listed as 0.35mm from KiCad, not independently confirmed by datasheet

---

## Appendix: Review History

<details>
<summary>These docs went through 6 rounds of automated review (Codex) + a source-of-truth audit against the KiCad PCB/schematic files and factory BOM. 20+ corrections found and fixed. Click to expand.</summary>

| Round | Issue Caught | Impact |
|-------|-------------|--------|
| R1 | WLCSP pitch was 0.4mm → 0.35mm | Wrong stencil apertures |
| R1 | MSL-3 → MSL-1 for nRF5340/nRF7002 | Unnecessary bake cycle |
| R1 | Diplexer architecture diagram wrong → corrected RF switch + shared 2.4GHz path | Misleading RF debug |
| R1 | FPC trace routing "parallel to bend" → "perpendicular to bend axis" | Cracked flex traces |
| R1 | J-Link pin 19 listed as GND → "DO NOT CONNECT" (5V supply) | Potential board damage |
| R2 | PI965 Section II → Section IB (cargo-only) | Shipping rejection |
| R2 | WiFi TX current 100mA → 191–260mA per Nordic PS | Undersized battery protection |
| R3 | SI1308EDL listed as P-ch → actually N-ch | Wrong polarity MOSFET |
| R3 | FC-12M crystal package wrong → 2.05×1.2mm not 1.6×1.0mm | Wrong footprint |
| R3 | Mic listed as top-port → corrected to bottom-port | Blocked audio path |
| R3 | NAND flash listed as 8GB → 4Gbit (512MB) | Misleading spec |
| Audit | Bottom-side component list completely wrong (5 ICs missing, 6 wrong refs) | CM gets wrong assembly |
| Audit | BQ25101 charge current ~100mA → ~135mA | Wrong battery spec |
| Audit | FPC PI core 50µm → 203.2µm (4× off) | Wrong FPC fabrication |
| R6 | RF window strategy undocumented → added | Indie maker couldn't assess RF risk |
| R6 | DSBGA pitch values all 0.5mm → 0.35/0.4mm | Wrong stencil apertures |
| R6 | FPC total thickness 0.29mm → 0.37mm | Wrong bend radius |
| R6 | FM8625H switching time <100ns → 2–20µs | Misleading coexistence timing |
| R6b | TPS628438 package 1.8×1.8mm → 1.05×0.70mm | Wrong package dimensions |
| R6b | W25Q16JW → W25Q16JV (1.8V → 3.3V family) | Would destroy flash IC |
| R6b | PI965 Section II cargo-only for UN3480 | Shipping rejection |
| R6b | Max discharge ≥250mA → ≥300mA | Battery protection trips |

</details>
