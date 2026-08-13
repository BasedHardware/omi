# Battery Procurement Specification — Omi Consumer

**Sources:** Factory BOM (`omi-bom.csv` row 84), KiCad schematic (`WirelessCharger.kicad_sch` — U15 BQ25101 ISET circuit), KiCad PCB (`OMI.kicad_pcb` — R8/R28 positions), TI BQ25101 datasheet (K_ISET = 135 AΩ)

## Primary Battery

| Parameter | Value | Tolerance |
|-----------|-------|-----------|
| **Model** | GRP1654M1-1C-1S1P-3.7V-150mAh | — |
| **Manufacturer** | GERUIPU | — |
| **Chemistry** | Lithium polymer (LiPo) | — |
| **Nominal voltage** | 3.7V | — |
| **Capacity** | 150mAh | ≥140mAh acceptable |
| **Max diameter** | 16.0mm | **Must not exceed 16.0mm** — enclosure is 25.5mm OD with PCB and frame |
| **Max height** | 6.1mm | ≤6.5mm may fit; verify against mechanical clearance |
| **Form factor** | Cylindrical (coin cell style) | — |
| **Wire length** | 6mm | 5–10mm acceptable |
| **Wire gauge** | 32 AWG | 30–34 AWG acceptable |
| **Connector** | **Bare tinned wires (no connector)** | Soldered directly to PCB pads |
| **Protection circuit** | Built-in (over-charge, over-discharge, short circuit) | Required — BQ25101 handles charging only, not cell protection |
| **Charging IC** | BQ25101YFPR (on mainboard) | ISET = R8 = 1KΩ → charge rate ~135mA typ (K_ISET = 135 AΩ per TI datasheet) |
| **Max charge voltage** | 4.2V | Set by BQ25101 |
| **Discharge cutoff** | 2.75V (typical for protected cells) | GLF73910-BD01 provides additional board-level protection |

## ⚠ Critical Warnings

### Polarity
**Reversed polarity will destroy the BQ25101 charger IC and may cause thermal runaway.** The BQ25101 has no built-in reverse polarity protection.

- Verify polarity with a multimeter before soldering
- Red wire = positive (+), Black wire = negative (−) — verify, do not assume
- Mark polarity on the PCB silkscreen or assembly drawing before soldering

### Wire Routing
- Route battery wires to avoid pinching when the enclosure is closed
- Ensure wires do not cross over the IMU (LSM6DS3TR-C, U5) — vibration coupling
- Leave enough slack for the enclosure to open during service

### Soldering
- Solder battery wires to PCB pads (not a connector)
- Use a temperature-controlled iron at ≤350°C
- Minimize heat exposure to battery leads — LiPo cells are heat-sensitive
- Do not apply heat for more than 3 seconds per joint

## Acceptable Alternatives

Any LiPo cell meeting these criteria will work:

| Parameter | Minimum | Maximum | Critical? |
|-----------|---------|---------|-----------|
| Voltage | 3.7V nominal | 3.7V nominal | Yes — must be single-cell LiPo |
| Capacity | 100mAh | 200mAh | No — higher capacity = longer runtime |
| Diameter | 14mm | **16.0mm** | **Yes** — enclosure constraint |
| Height | 4mm | **6.5mm** | **Yes** — clearance against frame |
| Wire gauge | 34 AWG | 28 AWG | No — within reason |
| Wire length | 5mm | 15mm | No — longer can be trimmed |
| Protection circuit | Required | — | Yes — no cell-level protection on PCB |
| Termination | Bare tinned wires | — | Yes — no connector socket on PCB |

## Sourcing

### Direct from GERUIPU
- Alibaba: search "GERUIPU GRP1654M1" or "1654 lipo battery 150mah"
- MOQ: typically 10–100 pcs
- Lead time: 2–4 weeks for custom wire length/gauge

### Alternative Suppliers
- **AliExpress**: search "1654 lithium polymer battery 150mah" or "16mm round lipo battery"
- **Alibaba**: search "round lipo battery 16mm 150mah" — many manufacturers make this form factor
- **18650BatteryStore.com**: may have equivalents
- **Battery Space** (batteryspace.com): custom LiPo cells

### Key Search Terms
`round lipo 1654`, `coin cell lipo 16mm`, `D16 H6 lipo 150mah`, `cylindrical lithium polymer 3.7V 150mAh`

## Shipping & Customs

- **LiPo batteries are regulated dangerous goods** (Class 9)
- **Loose cells (not packed with equipment): UN3480 / PI965 Section IB** — cargo-aircraft-only by default under 2026 IATA DGR. Requirements:
  - Ship at ≤30% state of charge (SoC)
  - UN38.3 test summary must accompany the shipment
  - Dangerous Goods handling and documentation required
  - Maximum 2 cells per package under Section IB limits
- **Cells packed with equipment: UN3481 / PI966 Section II** — passenger aircraft permitted with restrictions
- This cell is ~0.56Wh (150mAh × 3.7V), well under the 100Wh limit
- **Request the supplier provide the UN38.3 test summary** — required for all lithium cell shipments
- Request seller ship via battery-approved carriers (SF Express, DHL with DG service)
- **Do not order batteries in the same package as assembled PCBs** — customs may flag the entire shipment
- Lead time for international battery orders: 2–4 weeks minimum

## Electrical Requirements

| Parameter | Requirement | Notes |
|-----------|-------------|-------|
| **Max continuous discharge** | ≥250mA | nRF7002 WiFi TX draws 191mA at 2.4GHz / 260mA at 5GHz max power (Nordic PS), plus nRF5340, sensors, and regulator losses |
| **Max pulse discharge** | ≥500mA for 100ms | Boot-up inrush, WiFi TX bursts at max power with concurrent BLE |
| **Internal resistance** | ≤500mΩ | High IR causes voltage sag during TX bursts — may trigger brown-out reset |
| **Protection board trip current** | ≥800mA | Must not trip during WiFi 5GHz TX peaks (260mA radio + system overhead) |
| **Charging current** | ~135mA typ (ISET = R8 = 1KΩ; K_ISET = 135 AΩ, range 129–145mA) | ~0.9C for 150mAh cell — cell must be rated for ≥150mA charge current |
| **NTC thermistor** | Not required on battery | BQ25101 TS pin is configured on-board (R28, 10K NTC near cell) |

**⚠ WiFi current is higher than typical BLE wearables.** Nordic's nRF7002 product spec lists 191mA (2.4GHz) and 260mA (5GHz) TX current before system overhead. Verify the cell's protection PCB does not trip during WiFi operation. If the cell's protection trips below 300mA, it is unsuitable.

**⚠ Thermal sensing caveat:** The on-board NTC (R28, 10K) drives the BQ25101 TS pin for charge temperature monitoring. R28 is positioned ~1mm from U15 (BQ25101 charger IC) per KiCad PCB — it senses charger IC temperature, not cell temperature directly. Thermal coupling to the battery is indirect. For effective cell protection during charging, verify the cell's built-in protection circuit handles temperature independently.

### Protection PCB Requirements

The built-in protection circuit inside the cell must meet these thresholds:

| Parameter | Minimum | Maximum | Notes |
|-----------|---------|---------|-------|
| Overcharge cutoff | 4.25V | 4.35V | Must be below or at BQ25101's 4.2V charge voltage with margin |
| Overcharge release | 4.05V | 4.15V | Hysteresis prevents cycling |
| Overdischarge cutoff | 2.4V | 2.7V | GLF73910-BD01 provides additional board-level protection at ~2.9V |
| Overdischarge release | 2.9V | 3.1V | Must resume when charging begins |
| Overcurrent trip | ≥800mA | — | Must not trip during WiFi TX peaks |
| Short-circuit protection | Required | — | Must disconnect within 50µs |
| Quiescent current | — | ≤5µA | Minimizes self-discharge during storage |
| PCM resistance | — | ≤150mΩ | Adds to cell IR; included in 500mΩ total IR budget |

**⚠ Confirm that the cell dimensions (diameter, height) INCLUDE the protection PCB, tape, tabs, and wire exit.** Some suppliers quote bare-cell dimensions; the protection PCB adds 0.5–1.5mm to height.

## Compliance & Acceptance Requirements

Request from the cell supplier before ordering:

| Document | Required? | Notes |
|----------|-----------|-------|
| **UN38.3 test summary** | **Yes** | Required for all lithium cell shipments. Ask for the summary, not just a declaration. |
| **IEC 62133-2 or UL1642** | Recommended | Cell safety certification. Required for any product certification (CE, FCC, UL). |
| **MSDS / SDS** | **Yes** | Material Safety Data Sheet — required by customs and shipping carriers. |
| **RoHS / REACH declaration** | Recommended | Required for EU sale. Most reputable LiPo cells are compliant. |
| **Lot / date code traceability** | **Yes** | Each cell must have a traceable lot code for warranty and recall tracking. |

### Incoming Quality Control (IQC)

Before assembly, verify each incoming cell:

1. **Open-circuit voltage (OCV):** 3.7–3.9V for a fresh cell; reject <3.5V or >4.1V
2. **Polarity:** Red = +, Black = − — verify with multimeter, do not assume
3. **Dimensions:** Measure diameter and height with calipers — reject if >16.0mm diameter or >6.5mm height (including protection PCB)
4. **Capacity (sample):** Charge to 4.2V, discharge to 2.75V at 0.2C — capacity should be ≥140mAh
5. **Internal resistance (sample):** Measure with AC milliohm meter at 1kHz — should be ≤500mΩ total (cell + protection PCB)
6. **Protection trip (sample):** Apply increasing load; protection should NOT trip below 800mA

## Mechanical Installation

| Requirement | Value | Notes |
|-------------|-------|-------|
| **Swelling allowance** | ≥0.5mm clearance around cell at end-of-life | LiPo cells swell 5–10% over lifespan |
| **Compression** | None permitted | Do not mechanically compress the cell — risk of internal short and thermal runaway |
| **Insulation from frame** | Required | Insulate cell from CNC aluminium enclosure with Kapton tape or foam pad |
| **Adhesive/retention** | Double-sided foam tape (3M VHB or equivalent) | Secure cell to prevent rattle; foam absorbs swelling |
| **Wire strain relief** | Required | Hot-melt or RTV silicone at solder joints to prevent fatigue |
| **Reject criteria** | Bulging, discoloration, damaged wrap, corroded terminals | Do not use visibly damaged cells |

## Capacity vs. Runtime Estimate

| Usage Mode | Current Draw | Runtime (150mAh) |
|------------|-------------|-------------------|
| BLE advertising only | ~5mA | ~30 hours |
| BLE connected + recording | ~15mA | ~10 hours |
| BLE + WiFi idle (associated) | ~40mA | ~3.5 hours |
| WiFi 2.4GHz TX (active upload) | ~200mA | ~45 minutes |
| WiFi 5GHz TX (max power) | ~270mA | ~33 minutes |

These are rough estimates. WiFi TX currents are from Nordic nRF7002 product specification (191mA at 2.4GHz, 260mA at 5GHz) plus system overhead (~10–15mA). Actual runtime depends on firmware power management, WiFi duty cycle, TX power setting, and ambient temperature. Firmware may limit TX power or duty cycle to extend battery life.
