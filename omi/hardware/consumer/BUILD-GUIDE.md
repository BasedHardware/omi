# Build Your Own Omi — Step-by-Step Guide for Indie Makers

**Last updated:** 2026-08-13
**Estimated build time:** 5–6 weeks (mostly waiting for parts and PCBs)
**Estimated cost:** ~$200–310 per unit at 5-unit prototype scale
**Difficulty:** Advanced — requires PCBA ordering experience, not hand-solderable

---

## Before You Start

**What you need:**
- A computer with a web browser (for JLCPCB ordering)
- A credit card for ~$800–1,500 total (5 boards + components + shipping)
- A J-Link debug probe (~$20 for EDU Mini, ~$400 for BASE commercial)
- A multimeter
- Basic soldering iron (for battery wires only — everything else is machine-assembled)
- A phone with the Omi app

**What you do NOT need:**
- A pick-and-place machine (JLCPCB does this)
- A reflow oven (JLCPCB does this)
- RF test equipment (unless you change the enclosure)
- KiCad (unless you want to modify the design)

**Key constraint:** This board uses WLCSP packages (0.35mm ball pitch) that **cannot be hand-soldered**. You must use a professional PCBA service.

---

## Phase 1 — Review & Budget (Day 1)

### Step 1: Clone the Repo

```bash
git clone https://github.com/BasedHardware/omi.git
cd omi/hardware/consumer
```

### Step 2: Understand What You're Building

The Omi consumer device has **3 PCBs + 1 battery + 1 enclosure**:

| Board | Type | Components | Assembly |
|-------|------|-----------|----------|
| **Mainboard** | 4-layer HDI, 25.5mm round, 0.6mm | 144 parts (WLCSP, 0201) | JLCPCB Standard |
| **Charger** | 2-layer, standard | 8 parts (SOT, 0402, 0805) | JLCPCB Economic |
| **FPC** | 2-layer flex (polyimide) | 2 parts (BTB connector, charging ring) | Hand-solder or PCBA |
| **Battery** | LiPo coin cell, ≤16mm dia | — | Solder wires to mainboard |
| **Enclosure** | CNC aluminium (2 parts) | — | CNC machining service |

### Step 3: Budget Check

| Item | Estimated Cost (5 units) |
|------|--------------------------|
| PCB fabrication (all 3 boards) | $140–275 |
| JLCPCB setup fees (stencil, feeders) | $200–230 |
| LCSC components (39 in-stock parts) | $125–200 |
| Consigned components (24 parts from DigiKey/Mouser) | $200–350 |
| Consignment shipping to JLCPCB | $30–50 |
| X-ray inspection | $50–100 |
| Battery (×5) | $25–50 |
| CNC enclosure (×5) | $150–500 (depends on vendor) |
| J-Link debug probe | $20–400 |
| **Total** | **$940–2,155** |
| **Per unit** | **$188–431** |

Costs drop significantly at >50 units. At 100+ units, expect ~$80–120/unit for electronics only.

---

## Phase 2 — Order PCBs (Week 1)

### Step 4: Order Mainboard PCB

Go to [JLCPCB](https://jlcpcb.com) → Order Now → Upload gerbers from `electrical/mainboard/gerbers/` (the mainboard zip).

| Setting | Value | Why |
|---------|-------|-----|
| Layers | 4 | Design is 4-layer HDI |
| Board thickness | **0.6mm** | ⚠ Non-standard — requires custom quote |
| Copper weight | 1oz outer / ⅓oz inner | Per design |
| Surface finish | **ENIG** | Required for WLCSP pad planarity |
| Impedance control | **Yes — 50Ω single-ended** | Required for RF traces |
| Via-in-pad | **Yes** | Required under WLCSP footprints |
| Min via drill | 0.102mm (laser) | Blind/buried vias |

**⚠ Important:** JLCPCB's standard 4-layer impedance-controlled stackup starts at **0.8mm, not 0.6mm**. You must request a **custom stackup**. This adds cost ($15–30/board vs $2–5 for standard) and lead time (7–10 days vs 3–5). See `IMPEDANCE-STACKUP.md` for the full stackup specification to provide to JLCPCB.

**Alternative:** If 0.6mm is not critical for your enclosure, ask JLCPCB for a **0.8mm impedance-controlled stackup** instead — much easier to source, same electrical function, just thicker.

### Step 5: Order Charger PCB

Upload charger gerbers. Standard settings:

| Setting | Value |
|---------|-------|
| Layers | 2 |
| Board thickness | 1.0mm |
| Surface finish | ENIG (recommended for pogo pin pads) |

### Step 6: Order FPC

Upload FPC gerbers + the `OMI-FPC-Enhance.gbr` file (stiffener layer).

| Setting | Value |
|---------|-------|
| Base material | **Polyimide (flex)** |
| Layers | 2 |
| Thickness | 0.3mm |
| Copper weight | 1oz |
| Cover layer | **Polyimide coverlay** (not solder mask) |
| Surface finish | ENIG |
| Stiffener | **Yes** — FR4, 0.3mm, per Enhance gerber layer |

See `FPC-FLEX-FAB-NOTES.md` for complete flex fabrication specs.

---

## Phase 3 — Source Components (Week 1–2, parallel with PCBs)

### Step 7: LCSC Cart — 39 In-Stock Parts

Open `bom/mainboard-bom.csv` and `bom/charger-bom.csv`. Filter to rows with an `LCSC_PN` value and `Stock_Note` = "In Stock". Add these to your JLCPCB/LCSC cart.

**All LCSC parts are Extended** (not Basic) — each costs ~$3 extra feeder loading fee. Budget ~$144 for feeder fees alone (48 unique parts × $3).

### Step 8: DigiKey/Mouser — 24 Consigned Parts

These parts are **not on LCSC** or **out of stock**. You must buy them separately and ship to JLCPCB. See `LCSC-SOURCING.md` for exact MPNs, package warnings, and sourcing guidance.

**Critical ICs (order first — longest lead times):**

| Part | Ref | Where to Buy | ⚠ Watch Out |
|------|-----|-------------|-------------|
| nRF5340-CLAA | U1 | DigiKey, Mouser | **WLCSP-95** — verify package |
| nRF7002-CEAA-R7 | U2 | DigiKey, Mouser | **WLCSP-81** — LCSC has QFN variant (WRONG package) |
| CSNP4GCR01-DPW | U7 | CS Semi direct | NAND flash — no gray market |
| P25Q16SH-UXH-IR | U12 | Puya Semi direct | **USON-8** — LCSC has SOIC-8 variant (WRONG package) |

**RF parts (exact MPN only — do NOT substitute):**

| Part | Ref | Where to Buy |
|------|-----|-------------|
| CHQ0603T-2N2B-HU | L3, L4 | Sunlord direct or DigiKey |
| LQM18PN3R3MFRL | L5 | Murata / DigiKey |
| MWSD1608FE100KT | L1, L2 | Sunlord direct |

**Connectors & specialty (various suppliers):**

| Part | Ref | Where to Buy |
|------|-----|-------------|
| ST-BTB-K3570606F | J1 (main) | Suntech / Alibaba |
| ST-BTB-K3570606M | J3 (FPC) | Suntech / Alibaba |
| MMICT5838-00-012 | MIC1, MIC2 | TDK / DigiKey |
| CA02-PG07 | PP1–PP6 | JINLANTIAN / Alibaba |
| MHPA0606RGBDT | D2, D7 | MEIHUA / Alibaba |

**Order 10–30% extra** for machine loading attrition. Ship in **original reels/tubes** to JLCPCB.

### Step 9: Order Battery

Search Alibaba/AliExpress: `"GERUIPU GRP1654M1"` or `"1654 lipo 150mah"`

| Requirement | Value |
|-------------|-------|
| Chemistry | LiPo, 3.7V nominal |
| Capacity | 100–200mAh (150mAh is BOM spec) |
| Max diameter | **≤16.0mm** (enclosure constraint) |
| Max height | **≤6.5mm** (including protection PCB) |
| Protection circuit | **Required** (over-charge, over-discharge, short) |
| Termination | Bare tinned wires (no connector) |

⚠ **Dangerous goods shipping** — allow 2–4 weeks. Request UN38.3 test summary from supplier. See `BATTERY-SPEC.md` for full spec.

---

## Phase 4 — PCBA Assembly at JLCPCB (Week 3–4)

### Step 10: Submit Mainboard Assembly Order

1. Go to JLCPCB assembly page
2. Upload **gerbers** + **BOM** (`mainboard-bom.csv`) + **CPL** (`mainboard-cpl.csv`)
3. Select **Standard assembly** (NOT Economic — required for WLCSP)
4. Rename BOM column `LCSC_PN` → `LCSC Part #` for JLCPCB
5. Select "Consign parts" and follow JLCPCB's consignment instructions

### Step 11: Preview & Verify (CRITICAL)

**Before confirming the order**, visually inspect every component in JLCPCB's assembly preview:

- [ ] **U1 (nRF5340) pin-1/A1 orientation** — must match PCB pad A1
- [ ] **U2 (nRF7002) pin-1/A1 orientation** — same concern
- [ ] **All bottom-side ICs** (U5, U7, U9, U12, U14) — check rotation after mirroring
- [ ] **LED polarity** (D2, D7) — anode/cathode correct
- [ ] **Diode polarity** (D1, D3, D4) — cathode band matches silkscreen
- [ ] **All 24 bottom-side parts** listed correctly on bottom layer

See `CPL-README.md` for rotation correction guidance.

### Step 12: Request Inspection

- [ ] Request **X-ray inspection** for U1, U2 (WLCSP joints are hidden)
- [ ] Request **first-article report** with photos, SPI data, X-ray images

### Step 13: Charger Assembly

Upload charger BOM + CPL + gerbers. **Economic** assembly tier is fine (no WLCSP).

### Step 14: FPC Assembly

Only 2 components. Options:
- **Hand-solder** J3 (BTB connector) yourself — practical for small quantities
- **Consign to PCBA house** — some fabs handle FPC with fixtures
- J1 (charging contact ring) is a custom part — always consigned

---

## Phase 5 — Receive & Inspect (Week 5)

### Step 15: Inspect Boards

When boards arrive, before powering anything:

1. **Visual check**: No obvious shorts, missing parts, or tombstoned components
2. **X-ray report**: Review U1/U2 WLCSP joints — all balls present, no bridges, voiding <25%
3. **Resistance check**: Measure between VBAT and GND — should be >10KΩ (not shorted)

See `STENCIL-REFLOW-NOTES.md` for full inspection criteria.

### Step 16: Smoke Test — Power On

1. Connect bench supply to TP9 (VBAT+) and TP18 (GND−): **3.7V, 100mA limit**
2. Current should be **1–5mA** (sleep, no firmware)
3. If current >50mA → **disconnect immediately** (likely a short)
4. Measure U16 output (VDD_3V3): should read **3.0–3.3V**

---

## Phase 6 — Flash Firmware (Week 5)

### Step 17: Connect J-Link to SWD Test Points

All SWD pads are on the **bottom** side of the mainboard:

| Signal | Test Point | J-Link Pin |
|--------|-----------|------------|
| SWDIO | **TP3** | Pin 2 |
| SWDCLK | **TP8** | Pin 4 |
| GND | **TP18** | Pin 3 or 5 |
| ~RESET | **TP14** | Pin 10 |
| VTref | **VDD_3V3 rail** (U16 output) | Pin 1 |

**⚠ VTref goes to VDD_3V3 (3.3V), NOT VBAT (3.7V).** There is no dedicated 3V3 test point — probe U16 output pin or a nearby decoupling cap on the VDD_3V3 net. See `SWD-DEBUG-ACCESS.md`.

### Step 18: Flash Firmware

```bash
# Install Nordic tools
pip install nrfutil
nrfutil install device

# Flash NETWORK core FIRST (BLE/802.15.4)
nrfutil device recover --core Network
nrfutil device program --firmware net_core.hex --core Network --verify

# Flash APPLICATION core (main firmware)
nrfutil device recover --core Application
nrfutil device program --firmware app_core.hex --core Application --verify --reset
```

Build firmware from `omi/firmware/` following its README. The hex files come from the nRF Connect SDK build.

---

## Phase 7 — Final Assembly (Week 5–6)

### Step 19: Connect FPC

1. Mate FPC J3 (male) into mainboard J1 (female) BTB connector
2. Latch should click — connector sits flat
3. **Check continuity** on all 9 signals with multimeter (see `FPC-FLEX-FAB-NOTES.md` pin table)

### Step 20: Solder Battery

1. **Verify polarity with multimeter** — Red wire = +, Black wire = −
2. Solder to mainboard battery pads: **≤350°C, ≤3 seconds per joint**
3. Route wires away from IMU (U5) to avoid vibration coupling

**⚠ Reversed polarity destroys the BQ25101 charger IC. There is no reverse polarity protection.**

### Step 21: Functional Test (before enclosure)

| Test | How | Expected Result |
|------|-----|-----------------|
| BLE | Open nRF Connect app, scan | Device appears with RSSI > -70 dBm within 1m |
| WiFi | Check firmware log | Connects to 2.4GHz AP within 5m |
| Mic | Record 1s audio via app | Non-zero audio signal |
| IMU | Read WHO_AM_I register | Returns 0x69 |
| Charging | Connect to charger dock (or apply 5V to charger pogo pins) | LED indicates charging |

### Step 22: Assemble into Enclosure

1. Place mainboard in case-b (back cover)
2. Insulate battery from aluminium with **Kapton tape** — prevent shorts
3. Secure battery with **foam tape** (3M VHB or equivalent)
4. Bend FPC to route from mainboard to charger position (≥1.8mm bend radius)
5. Place charger board in position, connect FPC
6. Close case-a (front cover)
7. Verify microphone ports align with enclosure acoustic holes

### Step 23: Final Test

1. Verify BLE range: ≥10m line-of-sight
2. Verify charging works from dock
3. Pair with Omi app on phone
4. **You have a working Omi!** 🎉

---

## Troubleshooting

| Problem | Likely Cause | Fix |
|---------|-------------|-----|
| No power (0mA at 3.7V) | Open circuit, bad solder joint | Check VBAT continuity, inspect U16 LDO |
| High current (>50mA, no firmware) | Short circuit on board | Disconnect! X-ray inspect. Check for solder bridges. |
| J-Link won't connect | Wrong VTref, no power, SWD reversed | See `SWD-DEBUG-ACCESS.md` troubleshooting table |
| BLE not advertising | Network core not flashed | Flash network core first with `--core Network` |
| Weak BLE signal (<-90 dBm at 1m) | Antenna issue, enclosure blocking RF | Check antenna trace, verify RF window in enclosure |
| WiFi won't connect | nRF7002 not initialized | Check firmware config, verify 40MHz crystal X3 |
| No audio | Mic port blocked by enclosure | Verify acoustic port alignment |
| Battery won't charge | Reversed polarity, dead BQ25101 | Measure polarity. If reversed, BQ25101 is destroyed — board may need rework. |

---

## Reference Documents

| Document | What It Covers |
|----------|---------------|
| `INDIE-MAKER-CHECKLIST.md` | Overview of all deliverables and Codex review scores |
| `LCSC-SOURCING.md` | Part-by-part sourcing guide, JLCPCB ordering, cost breakdown |
| `CPL-README.md` | Pick-and-place file format, rotation corrections, WLCSP pin-1 |
| `STENCIL-REFLOW-NOTES.md` | Stencil specs, paste type, reflow profile, X-ray criteria |
| `BATTERY-SPEC.md` | Battery dimensions, electrical requirements, shipping compliance |
| `ALTERNATES.md` | Substitute parts (approved, candidate, rejected) |
| `RF-ANTENNA-NOTES.md` | RF architecture, switch control, antenna considerations |
| `IMPEDANCE-STACKUP.md` | PCB stackup, impedance targets, HDI requirements |
| `FPC-FLEX-FAB-NOTES.md` | FPC fabrication, stiffener, bend radius, quality checks |
| `SWD-DEBUG-ACCESS.md` | Debug probe wiring, test points, flashing procedure |
