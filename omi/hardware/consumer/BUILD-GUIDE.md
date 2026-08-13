# Build Your Own Omi — Omi Consumer

↑ **[README](README.md)** | **[Kit Assembly](KIT-ASSEMBLY.md)** | **[Build Readiness](BUILD-READINESS.md)**

**This guide helps you pick the right build path based on your experience.**

The Omi Consumer device is an advanced wearable (nRF5340 + nRF7002, WLCSP packages, HDI PCB, CNC aluminium enclosure). The electronics **cannot be hand-soldered** — WLCSP at 0.35mm ball pitch requires professional pick-and-place and reflow. Choose the path that matches your skills.

---

## Choose Your Path

| Path | Who It's For | Time | Cost/Unit | Feasibility |
|------|-------------|------|-----------|-------------|
| **Kit Build** (recommended) | Makers, hobbyists, anyone | 1 evening | ~$80–120 | ⭐⭐⭐⭐⭐ |
| **DIY from Scratch** | Hardware engineers with PCBA sourcing experience | 5–6 weeks | ~$200–400 | ⭐⭐⭐ |
| **Design Fork** | Engineers modifying the design | 8+ weeks | Varies | ⭐⭐ |

---

## Path 1: Kit Build (Recommended)

**Buy pre-assembled electronics from the Omi factory, do final assembly yourself.**

The Omi factory already produces these boards at scale. Ordering pre-assembled subassemblies eliminates the hardest parts (HDI PCB fabrication, WLCSP assembly, consignment sourcing, X-ray inspection).

### What You Get in a Kit

| Item | Description |
|------|-------------|
| Mainboard PCBA | Fully assembled and tested. nRF5340, nRF7002, 144 placements soldered, X-ray verified. |
| Charger PCBA | Assembled. 8 placements. This is the **charging dock** — not installed in the wearable. |
| FPC | Assembled with BTB connector and charging contact ring. |
| Battery | 150mAh LiPo coin cell with protection circuit, pre-tested. |
| Enclosure | CNC AL6061-T6, anodized, laser-engraved (2 parts: case-a, case-b). |
| Internal parts | Wrapper (PC+ABS), silicone pad, frame, LED guide. |
| Hardware bag | Magnets (×4), screws (×3, M1.4×3mm), foam tape, Kapton tape, dust filters (×2), vibration motor, necklace cord. |

### What You Provide

| Item | Where to Get | Cost |
|------|-------------|------|
| J-Link debug probe | [SEGGER](https://www.segger.com/products/debug-probes/j-link/models/j-link-edu-mini/) — EDU Mini ~$20 | $20 |
| Soldering iron | Any temperature-controlled iron | You probably have one |
| Multimeter | Basic DMM | You probably have one |
| Phone with Omi app | iOS or Android | Free |

### Build Steps (Kit)

**See [KIT-ASSEMBLY.md](KIT-ASSEMBLY.md) for the detailed guide.** Summary:

1. **Solder motor** — solder vibration motor wires (board unpowered)
2. **Connect FPC** — mate BTB connector from FPC to mainboard
3. **Flash firmware** — temporarily power board, connect J-Link to SWD test points, flash both cores
4. **Solder battery** — verify polarity first (⚠ reversed polarity destroys the charger IC), insulate with Kapton
5. **Test** — BLE scan, microphone, IMU
6. **Assemble** — place internal parts and PCB in case-b, route FPC, close case-a
7. **Final test** — BLE range, charging, pair with app

**Time:** 1–2 hours. **Difficulty:** Moderate (soldering 4 wires, careful assembly).

### How to Order a Kit

Contact the Omi team:
- **Email:** hardware@omi.me
- **Discord:** [discord.gg/omi](https://discord.gg/omi) — #hardware channel
- **GitHub:** Open an issue with tag `hardware-kit`

Pricing depends on quantity. Expect ~$80–120/unit at 10+ units.

---

## Path 2: DIY from Scratch

**Order PCBs, source components, and use a PCBA service (JLCPCB, PCBWay, etc.).**

⚠ **This path is for hardware engineers with PCB sourcing experience.** If you've never ordered an HDI PCB or managed a consignment BOM, start with the Kit path.

### Why This Is Hard

| Challenge | Detail |
|-----------|--------|
| **HDI PCB** | 4-layer, 0.6mm, blind/buried vias, impedance-controlled. Custom quote required — JLCPCB doesn't stock this as standard. |
| **WLCSP assembly** | 0.35mm pitch requires Standard/Advanced tier PCBA, Type 5 solder paste, X-ray inspection. |
| **15 consigned parts** | Not on LCSC. Must source from DigiKey, Mouser, CS Semi, Puya Semi, Suntech, and others — then ship to JLCPCB for consignment assembly. |
| **No reverse polarity protection** | One wrong battery wire → dead BQ25101 → board scrapped. |
| **CNC enclosure** | Custom machining. Laser engraving on case-a is designed to improve RF (surface current disruption) — no final-enclosure VNA data available yet. |

### Estimated Cost (5 units)

| Category | Cost |
|----------|------|
| PCB fabrication (3 board types ×5 each) | $140–275 |
| PCBA setup (stencils, feeders, X-ray) | $200–230 |
| LCSC components (48 MPNs in stock) | $125–200 |
| Consigned components (15 MPNs not on LCSC) | $200–350 |
| Consignment shipping | $30–50 |
| Battery (×5) | $25–50 |
| CNC enclosure (×5) | $150–500 |
| J-Link probe | $20–400 |
| **Total (5 units)** | **$890–2,055** |
| **Per unit** | **$178–411** |

### DIY Steps

1. Clone this repo and read the engineering reference docs (see table below)
2. Order mainboard PCB — HDI specs in [IMPEDANCE-STACKUP.md](electrical/IMPEDANCE-STACKUP.md)
3. Order charger PCB and FPC — flex specs in [FPC-FAB-NOTES.md](electrical/FPC-FAB-NOTES.md)
4. Source components — 63 unique MPNs total: 48 available on LCSC, 15 must be consigned. See [LCSC-SOURCING.md](bom/LCSC-SOURCING.md)
5. Order PCBA — select Standard or Advanced assembly tier for WLCSP capability (PCB fabrication is separate; HDI service is required for mainboard). Use [COMPONENT-PLACEMENT.md](bom/COMPONENT-PLACEMENT.md) for rotation/pin-1
6. Specify stencil and reflow — [STENCIL-REFLOW-NOTES.md](electrical/STENCIL-REFLOW-NOTES.md)
7. Order battery — [BATTERY-SPEC.md](bom/BATTERY-SPEC.md) (dangerous goods shipping, allow 2–4 weeks)
8. Order CNC enclosure from a machining service
9. Receive boards → inspect → X-ray verify WLCSP joints
10. Flash firmware via J-Link SWD — [SWD-FLASHING.md](electrical/SWD-FLASHING.md)
11. Solder battery, connect FPC, assemble into enclosure
12. Test (BLE, Wi-Fi, mic, IMU, charging)

### Engineering Reference Docs

| Doc | Audience | What It Covers |
|-----|----------|---------------|
| [LCSC-SOURCING.md](bom/LCSC-SOURCING.md) | Sourcing engineer | Part-by-part availability, JLCPCB ordering, cost breakdown |
| [COMPONENT-PLACEMENT.md](bom/COMPONENT-PLACEMENT.md) | PCBA engineer | Pick-and-place format, rotation corrections, WLCSP pin-1 |
| [STENCIL-REFLOW-NOTES.md](electrical/STENCIL-REFLOW-NOTES.md) | CM / process engineer | Stencil specs, paste type, reflow profile, X-ray criteria |
| [IMPEDANCE-STACKUP.md](electrical/IMPEDANCE-STACKUP.md) | PCB fab engineer | 4-layer stackup, impedance targets, HDI requirements |
| [FPC-FAB-NOTES.md](electrical/FPC-FAB-NOTES.md) | Flex fab engineer | FPC fabrication, stiffener, bend radius, quality checks |
| [RF-ANTENNA-NOTES.md](electrical/RF-ANTENNA-NOTES.md) | RF engineer | RF architecture, switch control, enclosure RF strategy |
| [BATTERY-SPEC.md](bom/BATTERY-SPEC.md) | Everyone | Battery selection, safety, shipping compliance |
| [SWD-FLASHING.md](electrical/SWD-FLASHING.md) | Everyone | Debug probe wiring, test points, firmware flashing |
| [ALTERNATE-PARTS.md](bom/ALTERNATE-PARTS.md) | Sourcing engineer | Substitute parts (approved, candidate, rejected) |

---

## Path 3: Design Fork

**Modify the hardware design for a different form factor, feature set, or manufacturing process.**

Start with Path 2. Additionally:
- Open the KiCad 9 source files (in `electrical/*/altium/` zips — labeled "altium" but actually KiCad 9 format)
- Read [RF-ANTENNA-NOTES.md](electrical/RF-ANTENNA-NOTES.md) — any antenna or enclosure change requires VNA re-tuning and invalidates FCC/CE
- Read [IMPEDANCE-STACKUP.md](electrical/IMPEDANCE-STACKUP.md) — trace widths depend on the stackup
- Budget $5–15K for FCC/CE re-testing if you change the RF path

---

## Common to All Paths

### Firmware Flashing

Get firmware hex files from:
- **Pre-built releases:** [github.com/BasedHardware/omi/releases](https://github.com/BasedHardware/omi/releases) — download `net_core.hex` and `app_core.hex` matching your hardware revision (v1.2)
- **Build from source:** Follow the [firmware build guide](https://docs.omi.me/doc/developer/firmware/Compile_firmware) — requires nRF Connect SDK

See [SWD-FLASHING.md](electrical/SWD-FLASHING.md) for complete instructions. Quick summary:

```bash
# Download nrfutil from nordicsemi.com, then:
nrfutil install device

# Flash network core FIRST (BLE controller)
nrfutil device program --firmware net_core.hex --core Network --verify

# Flash application core (app logic + nRF7002 Wi-Fi host driver)
nrfutil device program --firmware app_core.hex --core Application --verify --reset

# If program fails with access-protection error, recover first:
# nrfutil device recover --core Network
# nrfutil device recover --core Application
# Then re-run the program commands above
```

### Battery Safety

- ⚠ **Verify polarity with a multimeter before soldering.** Reversed polarity destroys the BQ25101.
- Use only protected LiPo cells with an integrated protection circuit
- Inspect for swelling or damage before use — do not use a damaged cell
- Solder at ≤350°C, ≤3 seconds per joint
- Insulate solder joints and wires with Kapton tape
- Insulate battery from aluminium enclosure with foam tape
- Do not short, puncture, or charge unattended during initial bring-up
- Use a current-limited supply for first power-up if available (100mA for BLE-only bring-up; raise to 500mA before Wi-Fi testing — nRF7002 TX draws up to 260mA)
- See [BATTERY-SPEC.md](bom/BATTERY-SPEC.md) for full safety and shipping requirements

### Testing

| Test | Method | Pass |
|------|--------|------|
| Power-on | Apply 3.7V to VBAT, measure current | 1–5mA (sleep) or 10–20mA (BLE advertising only) |
| BLE | nRF Connect app scan | RSSI > -70 dBm at 1m |
| Wi-Fi | Firmware log | Connects to 2.4 GHz AP (note: Wi-Fi TX draws 191–260mA) |
| Microphone | Record via app | Non-zero audio signal |
| IMU | Read WHO_AM_I | Returns 0x69 |
| Charging | Connect to dock | LED indicates charging |
| BLE range | Walk away | ≥10m line-of-sight |
