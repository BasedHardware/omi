# LCSC / JLCPCB Part Sourcing Summary — Omi Consumer

**Last updated:** 2026-08-13
**Sources:** Factory BOM (`omi-bom.csv`), KiCad PCB/schematic (mainboard, charger, FPC), LCSC.com stock check 2026-08-11

## Coverage

| Metric | Count |
|--------|-------|
| Unique MPNs searched | 63 |
| Found on LCSC | 48 (76%) |
| Not on LCSC | 15 (24%) |
| LCSC but out of stock | 9 |
| JLCPCB Basic parts | 0 |
| JLCPCB Extended parts | 48 |

**All LCSC-available parts are JLCPCB Extended** — none are Basic. See "Cost Breakdown" below for full budget estimate including extended feeder fees, consignment handling, and assembly costs.

## Not on LCSC — Requires Consignment or Alternate Sourcing

These 15 MPNs must be sourced from authorized distributors or manufacturer direct, then consigned to the PCBA house. For each part: order 20% extra for attrition (JLCPCB minimum attrition policy). Ship components in original reels/tubes — loose parts are not accepted for machine placement.

### ICs (4 parts — highest sourcing risk)

| MPN | Ref | Package | Sourcing Plan | MSL |
|-----|-----|---------|---------------|-----|
| nRF7002-CEAA-R7 | U2 | WLCSP-81 (3.75×3.385mm) | **Critical.** Only QFAA-R (QFN) variant on LCSC — **wrong package**. Source from DigiKey ([945-CEAA-R7](https://www.digikey.com/)) or Mouser. Verify WLCSP-81 package code. Nordic authorized distributors: DigiKey, Mouser, Arrow, Avnet. | MSL-1 |
| CSNP4GCR01-DPW | U7 | LGA-8 (8×6×0.85mm) | Source from CS Semi (Changjiang Storage) authorized channel. **Do not use gray-market** — NAND flash requires firmware qualification and JEDEC ID verification. Contact CS Semi directly or use LCSC's sourcing request. | MSL-3 |
| P25Q16SH-UXH-IR | U12 | USON-8 (2×3mm) | Puya Semi P25Q16SH series. LCSC has `-SSH` (SOIC-8) variant — **wrong package**. Verify USON-8 package. Source DigiKey/Mouser or Puya authorized. Check SFDP table and QE bit behavior match the target suffix. | MSL-1 |
| GLF73910-BD01 | U14 | WLCSP (0.97×0.97mm) | Battery protection IC. Source from GLF (manufacturer) or DigiKey. **Do not substitute** without verifying OVP/UVP thresholds match BQ25101 charging profile. | MSL-1 |

### Passives (3 parts — RF-critical, do not substitute by value alone)

| MPN | Ref | Package | Sourcing Plan | RF Critical? |
|-----|-----|---------|---------------|-------------|
| CHQ0603T-2N2B-HU | L3, L4 | 0201 | 2.2nH RF matching inductor in nRF5340 antenna path. **DO NOT SUBSTITUTE by value alone** — Q factor, SRF, and DCR must match. Equivalent: Murata LQP03TN2N2B02D (LCSC C269798, verify stock). Must be high-Q (>15 at 2.4GHz), SRF >6GHz. | **Yes** |
| LQM18PN3R3MFRL | L5 | 0603 | 3.3µH power inductor for nRF7002 WiFi supply filter (L5). Equivalent: Murata LQM18PN3R3MGHD (higher current rating, same footprint). Source Murata direct or DigiKey. Match: 3.3µH ±20%, Isat ≥700mA, DCR ≤350mΩ. | No |
| MWSD1608FE100KT | L1, L2 | 0603 | 10µH power inductor for nRF5340 DCDC. Equivalent: Murata LQM18PN100MFRL (LCSC C307603 — but this is LQM18PN1R0, **1µH not 10µH**). Source Sunlord direct or find 10µH ±20% 0603, Isat ≥280mA, DCR ≤1Ω. | No |

### Connectors / Specialty (8 parts)

| MPN | Ref | Package | Sourcing Plan | Qty (incl. attrition) |
|-----|-----|---------|---------------|----------------------|
| ST-BTB-K3570606F | J1 (main) | 6+4P BTB female | Source Suntech direct or Alibaba. Must match mating height (0.6mm) with male connector. **⚠ BOM says 0.25mm pitch, KiCad footprint `BTB6_0d35` confirms 0.35mm** — verify with supplier before ordering. Order in tape/reel. | 2 |
| ST-BTB-K3570606M | J3 (FPC) | 6+4P BTB male | Source Suntech direct. Mating pair to J1 above. Same pitch conflict — see J1 note. | 2 |
| CA02-PG07 | PP1–PP6 (main) | WH1.5mm pogo | Source JINLANTIAN (Alibaba). 6 per board. Spring travel 1.5mm. | 8 |
| CA62-PG308 | PP1–PP2 (charger) | WH3.3mm pogo | Source JINLANTIAN (Alibaba). 2 per board. Spring travel 3.3mm. **Different from mainboard pogos.** | 3 |
| MMICT5838-00-012 | MIC1, MIC2 | SMD-7P (3.5×2.65mm) | TDK T5838 PDM MEMS microphone. **Bottom-port** — sound enters from PCB side (verify acoustic port alignment with enclosure). MMICT5848 variant on LCSC (C5176729) — verify pin-compatible and same sensitivity (-41dB). | 3 |
| MHPA0606RGBDT | D2, D7 | 0606 (0.69×0.69mm) | RGB LED. Larger 0808/1010 sizes available on LCSC but **will not fit footprint**. Source MEIHUA direct. | 3 |
| TS-1001S | K2 | 2.6×1.6×0.53mm | Ultra-low-profile tactile switch. Source JINBEILI direct or find equivalent with same footprint (163gf actuation). | 2 |
| 1S32000049 | X2 | 1.6×1.2mm 4-pad | 32MHz crystal, 8pF load, 10ppm. Source Faith Long direct or find equivalent: 32MHz, 8pF CL, 10ppm, ≤70Ω ESR, 1.6×1.2mm package. | 2 |

## Out of Stock on LCSC — Backup Sourcing

These parts have LCSC numbers but were out of stock at search time. For each, a backup source or equivalent is listed.

| LCSC PN | MPN | Ref | Description | Backup |
|---------|-----|-----|-------------|--------|
| C3606597 | nRF5340-CLAA | U1 | Main SoC, WLCSP-95 | **Critical.** DigiKey 5765-NRF5340-CLAA-R-ND. Mouser 949-NRF5340-CLAA-R. MSL-1. X-ray required post-reflow. Standard assembly only (not Economic) at JLCPCB due to WLCSP. |
| C2875272 | CJ17-400001010B20 | X3 | 40MHz crystal 4-pad | DigiKey or Mouser. Match: 40MHz, 10pF CL, 10ppm, 1.6×1.2mm, ≤80Ω ESR. |
| C93230 | DST1610A | X1 | 32.768KHz crystal | DigiKey. Match: 32.768KHz, 12.5pF CL, 20ppm, **1.6×1.0mm 2-pad** (not 2.05×1.2mm). No verified LCSC alternate — Epson FC-12M is wrong package (2.05×1.2mm). |
| C383245 | LN237N3T5G | Q1, Q2 | N-CH MOSFET SOT-883 | **No verified alternate.** Previously considered PMV65XNEA — rejected (MPN not found in Nexperia SOT-883 catalog). Source LRC direct. Match: N-CH, Vds≥30V, Id≥1.5A, SOT-883, verify D-G-S pinout. |
| C5152997 | SGM2036S-3.3XXDH4G/TR | U16 | 3.3V LDO | DigiKey. Equiv: any 3.3V 300mA LDO in XTDFN-4 (1×1mm). Check dropout and PSRR specs. |
| C5153132 | 74LVC1G00XC5G/TR | U9 | NAND gate SC70-5 | Equiv: TI SN74LVC1G00DCKR (LCSC C7468, SC70-5). Same function, same package. |
| C77131 | NCP15XH103F03RC | R28 | NTC 10K 1% 0402 | Equiv: TDK NTCG103JF103FT1 (10KΩ, 1%, 0402, B=3380K — verify B-value matches BQ25101 NTC profile). |
| C526951 | CC0201KRX7R6BB222 | C6 | 2.2nF 0201 X7R | Equiv: Samsung CL0201B222KK3NNND or Murata GRM033R71A222KA01. Verify X7R dielectric, 10V min rating. |
| C576685 | CC0201BRNPO9BNR70 | C12, C15, C49, C50 | 0.7pF 0201 NPO | **RF-critical** — nRF5340 antenna matching. Equiv: Murata GRM0335C1H0R7BA01. Must be NPO/C0G, ±0.1pF tolerance, 50V min. **DO NOT substitute with X7R.** |

## JLCPCB Turnkey Assembly — Detailed Guide

### Assembly Type Selection

| Board | Assembly Type | Reason |
|-------|--------------|--------|
| Mainboard | **Standard** (not Economic) | WLCSP-95/81 packages require Standard assembly line with X-ray inspection capability |
| Charger | Economic | Standard packages only (SOT, 0402, 0805) |
| FPC | Manual / consigned assembly | Only 2 components; some PCBA houses don't handle FPC |

### Cost Breakdown (estimated, 5-unit prototype run)

| Item | Estimated Cost | Notes |
|------|---------------|-------|
| Extended part feeder loading | ~$3 × 48 = $144 | One-time per unique part, per order |
| Standard assembly fee (mainboard) | ~$50–80 per board | Higher than Economic due to WLCSP |
| PCB fabrication (mainboard, 4L HDI) | ~$15–30 per board | 5-unit minimum |
| PCB fabrication (charger, 2L) | ~$5–10 per board | Standard 2-layer |
| Stencil (mainboard) | ~$15–25 | 0.075–0.10mm, electropolished |
| X-ray inspection | ~$10–20 per board | Required for WLCSP QC |
| Consigned parts shipping to JLCPCB | ~$30–50 | DHL/FedEx to Shenzhen |
| Component cost (LCSC parts) | ~$25–40 per board | Dominated by nRF5340 (~$8) and nRF7002 (~$6) |
| Component cost (consigned parts) | ~$30–50 per board | nRF7002 WLCSP, flash, mic, connectors |
| **Total per board (prototype)** | **~$150–250** | Decreases significantly at >50 units |

### Consignment Process

1. **Source consigned parts** from DigiKey/Mouser/manufacturer (authorized channels only for ICs)
2. **Ship to JLCPCB** — consignment address is provided when you place the order. International shipments may route through JLCPCB's import/handling workflow; follow their current consignment instructions.
3. **Extra quantity for attrition** — JLCPCB requires extra parts for machine loading losses. The required quantity varies by component type and package; check the order page for per-line minimum quantities. Budget ~10–30% extra depending on package.
4. **Packaging** — original reels/trays/tubes are preferred for machine placement. Loose parts may be accepted with extra handling but at higher risk of placement error.
5. **Label each bag/reel** with the JLCPCB order number and BOM designator
6. **Verify MSL handling**: nRF5340 and nRF7002 are MSL-1 (unlimited floor life, no bake required). CSNP4GCR01-DPW is likely MSL-3 — follow J-STD-033 or the component reel label for bake requirements. Check the moisture indicator card in each reel.

### BOM Format for JLCPCB Upload

JLCPCB expects these column names in the BOM CSV:

| JLCPCB Column | Our BOM Column | Notes |
|---------------|----------------|-------|
| `Designator` | `Designator` | Matches |
| `Qty` | `Qty` | Matches |
| `Comment` | `Description` or `MPN` | Use MPN for exact match |
| `Footprint` | (not in our BOM) | JLCPCB matches by LCSC PN, not footprint |
| `LCSC Part #` | `LCSC_PN` | Rename column when uploading |

For the upload: filter out non-component rows (pcba-reference, assembly-header, pcb-reference, custom-part, accessory) and rename `LCSC_PN` to `LCSC Part #`.

## Per-Board Summary

### Mainboard (56 component rows, 144 designators)
- 43 MPNs with LCSC PN (118 designators)
- 13 MPNs not on LCSC (26 designators — need consignment)

### Charger (6 component rows, 8 designators)
- 5 MPNs with LCSC PN (7 designators)
- 1 MPN not on LCSC (CA62-PG308 pogo pins, 2 designators)

### FPC (2 component rows, 2 designators)
- 0 MPNs with LCSC PN
- 1 MPN not on LCSC (ST-BTB-K3570606M connector)
- 1 custom part (J1 charging contact ring — sourced by drawing/SKU)

## Data Source

LCSC part numbers were searched via LCSC.com product search in August 2026. Stock status is a snapshot and changes frequently. **Always verify current stock and pricing before ordering.**

LCSC part numbers are in each board's BOM CSV (`LCSC_PN`, `JLC_Status`, `Stock_Note` columns). For JLCPCB upload, rename `LCSC_PN` → `LCSC Part #` and filter to component rows only.
