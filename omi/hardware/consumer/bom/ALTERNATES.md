# Alternate Parts List — Omi Consumer

**Last updated:** 2026-08-13
**Sources:** Factory BOM (`omi-bom.csv`), KiCad PCB/schematic (mainboard, charger, FPC)

## How to Use This Document

Parts are classified into three tiers:

| Tier | Meaning | Action Required |
|------|---------|-----------------|
| ✅ **Approved drop-in** | Verified package, pinout, and key electrical parameters | Order directly |
| ⚠️ **Candidate (EE review)** | Plausible alternate but unverified — package/electrical delta or incomplete data | Do NOT order without engineer sign-off |
| 🚫 **Do not substitute** | No pin-compatible alternate, or requires RF/firmware re-validation | Use exact MPN only |

## Substitution Policy

| Category | Tier | Rule |
|----------|------|------|
| RF passives (L3, L4, C12, C15, C49, C50) | 🚫 | Exact MPN only unless RF retuned and measured. See `RF-ANTENNA-NOTES.md`. |
| RF ICs (U3 diplexer, U10 RF switch) | 🚫 | No pin-compatible alternate; redesign/revalidation required. |
| Main SoC (U1 nRF5340) | 🚫 | No pin-compatible alternate. Nordic-only. |
| WiFi companion (U2 nRF7002) | 🚫 | No pin-compatible alternate. Nordic-only. |
| Crystals (X1, X2, X3) | ⚠️ | Must match load capacitance, ESR, tolerance, and package exactly. |
| MEMS microphone (MIC1, MIC2) | 🚫 | No verified pin/port-compatible alternate. Use exact MPN. |
| Battery protection (U14 GLF73910) | 🚫 | OVP/UVP thresholds must match BQ25101 charge profile. No verified alternate. |
| Connectors (J1, J3, PP1–PP6) | ⚠️ | Must match mating height, pitch, and pin count exactly. |
| Power ICs (U8, U16 LDO) | ⚠️ | Must match voltage, current, package, pinout. Very few share XTDFN-4 footprint. |
| Power ICs (U13 buck, U15 charger) | 🚫 | TI DSBGA-6 packages. No verified alternate; use exact MPN. |
| IMU (U5 LSM6DS3TR-C) | ⚠️ | LGA-14 (2.5×3mm), back side. Other 6-axis IMUs exist in same package but require firmware driver and I2C/SPI address verification. |
| SPI Flash (U12 P25Q16SH) | ⚠️ | USON-8 (3×2mm), back side. Other **16 Mbit** SPI NOR flash may be pin-compatible but require SFDP table and QE bit behavior matching for firmware. |
| RGB LED (D2, D7 MHPA0606RGBDT) | 🚫 | 0606 (0.69×0.69mm) — no LCSC alternate in this footprint. Use exact MPN from MEIHUA. |
| Tactile switch (K2 TS-1001S) | ⚠️ | 2.6×1.6×0.53mm ultra-low-profile. Must match footprint and profile height exactly for enclosure fit. |
| MOSFETs (Q1, Q2, Q7) | 🚫 | No verified alternate. Use exact MPN; see details below. |
| Logic (U9 NAND gate) | ✅ | 74LVC1G00 in SC70-5 — any manufacturer (SGMICRO, Nexperia, TI). Note: TI version lacks Schmitt-trigger inputs (see details below). |
| General passives (R, C not in RF path) | ✅ | Any equivalent value/tolerance/package from major vendor. |
| 0Ω resistors | ✅ | Any 0Ω jumper in same package. |

## ✅ Approved Drop-In — Passives (Non-RF)

General-purpose 0201 resistors and capacitors can be substituted with equivalents from any major manufacturer (YAGEO, Samsung, Murata, Vishay, Panasonic) as long as:

- Same value and tolerance (1% for resistors, 10–20% for caps)
- Same or better voltage rating
- Same dielectric (X5R/X7R for caps — **never substitute NPO with X5R or vice versa**)
- Same package (0201 = 0603 metric = 0.6×0.3mm)
- Same or lower height (max 0.3mm for 0201)

**Exclusions — do NOT substitute without EE review:**
- RF matching caps: C12, C15, C49, C50 (0.7pF NPO) — see RF-ANTENNA-NOTES.md
- Crystal load caps: verify CL value if any are changed
- PMIC input/output caps: check ESR/ESL requirements in TPS628438, BQ25101, SGM2036 datasheets
- Antenna-adjacent decoupling: check layout placement and SRF

### Resistor Alternates (0201, 1%, 1/20W)

| Original MPN (YAGEO) | Value | Murata/Vishay Equiv | Notes |
|----------------------|-------|---------------------|-------|
| RC0201FR-0710KL | 10KΩ | CRCW020110K0FKED (Vishay) | Same value/package |
| RC0201FR-07100KL | 100KΩ | CRCW0201100KFKED (Vishay) | Same value/package |
| RC0201FR-071KL | 1KΩ | CRCW02011K00FKED (Vishay) | Same value/package |
| RC0201FR-070RL | 0Ω | Any 0201 0Ω jumper | — |

### Capacitor Alternates (0201)

| Original MPN | Value/Dielectric | Murata Equiv | Samsung Equiv |
|-------------|------------------|--------------|---------------|
| CC0201KRX5R6BB104 | 100nF X5R 10V | GRM033R61A104KE15 | CL0201B104KO3NNND |
| GRM033R61A105ME44D | 1µF X5R 10V | (same) | CL0201A105KQ3NNND |
| 0201X225M6R3NT | 2.2µF X5R 6.3V | GRM033R60J225ME47 | CL0201A225MQ3NRND |
| CC0201KRX5R5BB474 | 470nF X5R 6.3V | GRM033R60J474KE90 | — |

**⚠ Do NOT substitute C12, C15, C49, C50 (0.7pF NPO) with X5R/X7R — these are RF matching caps.**

## ✅ Approved Drop-In — ICs

### U9: NAND Gate (74LVC1G00XC5G/TR → any 74LVC1G00)

| Alternate MPN | Manufacturer | LCSC | Package | Verified |
|--------------|--------------|------|---------|----------|
| 74LVC1G00GW,125 | Nexperia | C12078 | SC70-5 | ✅ Drop-in. Nexperia datasheet shows Schmitt-trigger inputs. Verify your circuit tolerates the hysteresis if switching thresholds are critical. |
| SN74LVC1G00DCKR | TI | C7468 | SC70-5 | ✅ Drop-in. TI version has standard CMOS inputs (no Schmitt-trigger hysteresis) with input transition-rate limits (20ns/V at 1.8V, 10ns/V at 3.3V). Safe if input edges are clean. |

## ⚠️ Candidate — Requires EE Review

### U8: 1.8V LDO (SGM2036S-1.8, XTDFN-4 1×1mm)

**No verified drop-in alternate exists.** The SGM2036S uses XTDFN-4 (1×1mm) — very few LDOs share this footprint and pinout.

| MPN | Status | Issue |
|-----|--------|-------|
| XC6206P182MR (Torex) | ❌ **Rejected** | Wrong package (SOT-23-3), only 80mA (vs SGM2036S 300mA class) |
| AP7354D-18FS4-7 (Diodes Inc) | ⚠️ **Unverified** | DFN-4 1×1mm but only 150mA, VIN min 2.0V. Requires review: pinout, enable polarity, output discharge behavior, dropout at actual load, PSRR/noise, required Cout ESR/type for stability. |

**If OOS:** Contact SGMICRO directly for lead time rather than substituting. LDO substitution requires matching: output voltage, dropout, PSRR, noise, quiescent current, enable polarity, output discharge, Cout stability range, AND package/pinout.

### U16: 3.3V LDO (SGM2036S-3.3, XTDFN-4 1×1mm)

Same situation as U8. The XTDFN-4 (1×1mm) package limits alternatives. If OOS, contact SGMICRO directly.

### U13: DC-DC Buck Converter (TPS628438YKAR, DSBGA-6)

🚫 **No alternate.** TI TPS628438 in DSBGA-6 (1.8×1.8mm). No other buck converter shares this exact package, pinout, and integrated compensation. Source from TI authorized distributors (DigiKey LCSC C18197908).

### U15: Battery Charger (BQ25101YFPR, DSBGA-6)

🚫 **No alternate.** TI BQ25101 single-cell Li-Ion/LiPo charger in DSBGA-6 (1.6×0.9mm). Charge current set by external resistor. No pin-compatible alternate. Source from TI authorized distributors (DigiKey, LCSC C478468).

### Q1, Q2: N-CH MOSFET (LN237N3T5G, SOT-883)

🚫 **No verified alternate.** Source LN237N3T5G from LRC (Leshan Radio Company) or authorized distributors. If seeking an alternate, an EE must verify: exact SOT-883 (XDFN3) pinout (D-G-S mapping), Vds≥30V, Id≥1.5A, Rds(on) at actual gate drive voltage, body diode orientation, Vgs(max), and gate charge.

**Previously considered alternates — all rejected:**
- ~~PMV65XNEA (Nexperia)~~ — **Rejected:** MPN not found in Nexperia's SOT-883 catalog. Closest match PMV65XP is P-channel SOT-23, wrong type and package.
- ~~2N7002BKS (Nexperia)~~ — **Rejected:** Dual N-channel MOSFET in SOT-363 (SC-88), NOT single SOT-883. Wrong package.

### Q7: P-CH MOSFET (CJE3139K, SOT-523)

🚫 **No verified alternate.** CJE3139K is a P-channel MOSFET in SOT-523 package (per BOM: "SMD MOSFET P-CH 20V-660mA;SOT-523"). Source from JCET/CJ Semi directly. If seeking an alternate, an EE must find a SOT-523 P-CH MOSFET matching: Vds≥20V, Id≥660mA, Vgs(th), Rds(on) at actual gate drive, body diode orientation, and exact pinout.

## 🚫 Do Not Substitute — Single Source

These parts have no pin-compatible alternate. Plan inventory accordingly.

| Ref | MPN | Why No Alternate | Sourcing Fallback |
|-----|-----|------------------|-------------------|
| U1 | nRF5340-CLAA | Only Nordic makes this SoC. No pin/function equivalent. | DigiKey, Mouser, Nordic direct |
| U2 | nRF7002-CEAA-R7 | Only Nordic makes this WiFi companion. No pin-compatible alternate (works with nRF52/53/91 and non-Nordic hosts, but no other IC replaces it). | DigiKey, Mouser, Nordic direct |
| U3 | LFD182G45DCHD277 | Murata diplexer for 2.4/5GHz band splitting. Other diplexers have different band edges, port impedance, and insertion loss. | Murata direct, DigiKey |
| U7 | CSNP4GCR01-DPW | CS Semi 4Gbit SD NAND. No qualified alternate — other SD NAND ICs may be pin-compatible (LGA-8) but require firmware qualification, JEDEC ID verification, power-loss behavior testing, and endurance validation. | CS Semi (Changjiang Storage) direct, Alibaba |
| U10 | FM8625H | FUMAN SPDT RF switch. Other SPDT switches may work but require RF path re-validation (insertion loss, isolation, P1dB). | FUMAN direct, LCSC sourcing request |
| U14 | GLF73910-BD01 | GLF battery protection IC. Other protection ICs require OVP/UVP threshold matching to BQ25101 charge profile. | GLF direct |
| MIC1, MIC2 | MMICT5838-00-012 | TDK T5838 PDM MEMS mic. Other PDM mics differ in sensitivity, SNR, pinout, and port direction (this mic is bottom-port per TDK distributor data — sound enters from PCB side). | TDK direct, DigiKey |

### U5: IMU (LSM6DS3TR-C, LGA-14 2.5×3mm — back side)

⚠️ **Candidate only.** The LSM6DS3TR-C is a mature ST 6-axis IMU. Pin-compatible alternates exist but require:
- Same LGA-14 (2.5×3mm, 0.5mm pitch) package and pinout
- I2C address match (SA0 pin determines 0x6A/0x6B)
- Firmware driver compatibility (register map)
- Vibration motor coupling qualification (U5 is on back side near motor mount)

| MPN | Manufacturer | Status | Notes |
|-----|-------------|--------|-------|
| LSM6DSO (LCSC C2849283) | STMicroelectronics | ⚠️ **Unverified** | Drop-in successor to LSM6DS3, same LGA-14, but register map differs. Firmware driver change required. |
| ICM-42688-P (TDK) | TDK InvenSense | ❌ **Rejected** | Different package (LGA-14 but 2.5×3×0.73mm, different pinout). Not pin-compatible. |

**If OOS:** Source from DigiKey (497-LSM6DS3TR-C) or Mouser. ST makes this part in high volume.

### U12: SPI Flash (P25Q16SH-UXH-IR, USON-8 3×2mm — back side)

⚠️ **Candidate only.** The P25Q16SH is a **16 Mbit** (2 MB) SPI NOR flash. Other 16Mbit SPI NOR flash in USON-8 may work but require:
- Exact USON-8 (3×2mm) package and pinout match
- **16 Mbit capacity** (not 128 Mbit — firmware expects 2 MB)
- SFDP (Serial Flash Discoverable Parameters) table compatibility
- QE (Quad Enable) bit behavior matching for firmware
- Same or better read/erase performance

| MPN | Manufacturer | Status | Notes |
|-----|-------------|--------|-------|
| W25Q16JWUXIQ (Winbond) | Winbond | ⚠️ **Unverified** | 16Mbit USON-8 (3×2mm). **Use -UXIQ suffix (USON-8), NOT -SSIQ (SOIC-8 — wrong package).** Verify LCSC availability and SFDP/QE compatibility. |
| GD25Q16CEIGR (GigaDevice) | GigaDevice | ⚠️ **Unverified** | 16Mbit USON-8. Verify package is 3×2mm (not 4×4mm WSON). |

**If OOS:** Source Puya P25Q16SH from Puya Semi direct. LCSC has `-SSH` variant (SOIC-8) — **wrong package**, do not use.

### D2, D7: RGB LED (MHPA0606RGBDT, 0606 0.69×0.69mm)

🚫 **No verified alternate.** The 0606 RGB LED footprint (0.69×0.69mm) is uncommon. Larger 0808/1010 sizes are widely available but **will not fit the PCB footprint**. Source MHPA0606RGBDT from MEIHUA direct or Alibaba.

### K2: Tactile Switch (TS-1001S, 2.6×1.6×0.53mm)

⚠️ **Candidate only.** Ultra-low-profile SMD tactile switch. Must match:
- Footprint: 2.6×1.6mm
- Profile height: ≤0.53mm (enclosure clearance critical)
- Actuation force: ~163gf (similar feel)
- 4-pin SMD configuration

Source JINBEILI TS-1001S direct if OOS. Check C&K/Alps for ultra-low-profile equivalents, but verify all four dimensions match.

## ⚠️ Crystal Alternates (USE WITH CAUTION)

Crystals require exact matching of load capacitance, frequency tolerance, and ESR. The matching capacitors in the nRF5340/nRF7002 designs are tuned for specific crystal parameters. **Substituting a crystal with different CL or ESR can cause startup failure or poor radio performance.**

### X1: 32.768KHz (DST1610A, 1.6×1.0mm 2-pad)

**No verified alternate.** Previously listed FC-12M removed — Epson FC-12M is 2.05×1.2×0.6mm, NOT 1.6×1.0mm. Wrong package.

Source DST1610A from Daishinku or authorized distributors.

### X2: 32MHz (1S32000049, 1.6×1.2mm 4-pad)

No common alternate identified. The 32MHz crystal with 8pF load capacitance and ≤70Ω ESR in 1.6×1.2mm 4-pad package is uncommon. Source Faith Long directly.

### X3: 40MHz (CJ17-400001010B20, 1.6×1.2mm 4-pad)

**No verified alternate.** Previously listed XRCGB40M000F3A1BR0 removed — Murata XRCGB series is 2.0×1.6×0.7mm, NOT 1.6×1.2mm. Wrong package.

Source CJ17 from CJ Semi or authorized distributors.

**⚠ After substituting any crystal:**
1. Verify crystal startup over voltage range (2.9–4.2V) and temperature (-20 to +60°C)
2. Confirm firmware load-capacitance / trim settings match the new crystal's CL specification
3. Measure frequency error with a counter or spectrum analyzer — Nordic requires ±40ppm for BLE, WiFi 802.11 requires ±20ppm
4. Run BLE DTM (Direct Test Mode) and WiFi conducted TX to confirm output power and spectral mask
5. At minimum: confirm BLE advertising with nRF Connect and WiFi scan results at room temperature
6. The nRF7002 40MHz crystal has tight Wi-Fi EVM implications — validate with Wi-Fi throughput test
