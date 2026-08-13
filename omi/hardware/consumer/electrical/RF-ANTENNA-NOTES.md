# RF & Antenna Notes — Omi Consumer Mainboard

**Sources:** KiCad PCB (`OMI.kicad_pcb`), KiCad schematic (`nRF7002.kicad_sch`, `nRF5340.kicad_sch`), factory BOM (`omi-bom.csv`)

## RF Architecture Overview

The Omi mainboard uses a **shared single antenna** for BLE and WiFi (both 2.4GHz and 5GHz bands):

```
                                          ┌─ RF Switch (U10) ─┐
nRF5340 (BLE 2.4GHz) ──► L3/L4 match ──► │   selects BLE     │
                                          │   vs WiFi 2.4GHz  ├──► Diplexer U3 ──► ANT
nRF7002 (WiFi 2.4GHz) ─────────────────► │                   │    (low port)
                                          └───────────────────┘
nRF7002 (WiFi 5GHz) ────────────────────────► Diplexer U3 ──► ANT
                                               (high port)
```

**How it works:** The diplexer (U3, Murata LFD182G45DCHD277) separates 2.4GHz from 5GHz bands. Its common port connects to the antenna. The 2.4GHz low-band port is shared between BLE (nRF5340) and WiFi 2.4GHz (nRF7002) via the RF switch (U10, FM8625H). The 5GHz high-band port connects directly to nRF7002's 5GHz path.

| Component | Ref | Function | Package |
|-----------|-----|----------|---------|
| nRF5340-CLAA | U1 | BLE transceiver (2.4GHz) | WLCSP-95 |
| nRF7002-CEAA-R7 | U2 | WiFi companion (2.4GHz + 5GHz) | WLCSP-81 |
| LFD182G45DCHD277 | U3 | Diplexer — splits BLE/WiFi bands | 1.6×0.8mm |
| FM8625H | U10 | SPDT RF switch — antenna path routing | DFN-6 (0.7×1.1mm) |
| CHQ0603T-2N2B-HU | L3, L4 | BLE matching inductors (2.2nH) | 0201 |
| CC0201BRNPO9BNR70 | C12, C15, C49, C50 | Matching/tuning caps (0.7pF) | 0201 |

### Signal Flow

1. **BLE TX/RX (2.4GHz):** nRF5340 ANT pin (D1) → L3/L4 radio-side match (2.2nH, brings ANT pin to 50Ω) → RF_LE net → RF Switch U10 (one port) → Diplexer U3 low-band (2.4GHz) port → Antenna
2. **WiFi 2.4GHz TX/RX:** nRF7002 2.4GHz pins → RF Switch U10 (other port) → Diplexer U3 low-band port → Antenna
3. **WiFi 5GHz TX/RX:** nRF7002 5GHz pins → Diplexer U3 high-band (5GHz) port → Antenna
4. **Coexistence:** BLE and WiFi 2.4GHz share the 2.4GHz low-band path through the RF switch. The switch (U10) is controlled by `SW_CTRL0` from the nRF7002 coexistence subsystem (verified from KiCad PCB — see truth table below). The coexistence interface (COEX_REQ, COEX_STATUS, COEX_GRANT) arbitrates access — it must prevent simultaneous 2.4GHz transmit and protect BLE RX from WiFi TX desense/saturation.

### RF Switch Control (U10, FM8625H)

**Verified from KiCad PCB (`OMI.kicad_pcb`) net assignments:**

| U10 Pin | Function | Net Name | Connected To |
|---------|----------|----------|-------------|
| Pin 3 (RF1) | Switch port 1 | `/nRF5340/RF_LE` | BLE 2.4GHz path (nRF5340) |
| Pin 1 (RF2) | Switch port 2 | `/nRF5340/nRF7002/TXRF0` | WiFi 2.4GHz path (nRF7002) |
| Pin 5 (ANT) | Common port | `Net-(U10-ANT)` | Diplexer U3 low-band port |
| Pin 6 (VCTL) | Control | `/nRF5340/nRF7002/SW_CTRL0` | Coexistence control from nRF7002 subsystem |

| SW_CTRL0 State | Active Path | Notes |
|----------------|-------------|-------|
| LOW (default) | RF1 → BLE 2.4GHz (nRF5340 → switch → diplexer) | Default state after reset — BLE active |
| HIGH | RF2 → WiFi 2.4GHz (nRF7002 → switch → diplexer) | Set by coexistence logic when WiFi needs antenna |

- Control signal is `SW_CTRL0` from the nRF7002 coexistence interface, not a direct nRF5340 GPIO
- Switching time: typically <100ns for SPDT RF switches — fast enough for packet-level coexistence
- During WiFi 5GHz operation, the 2.4GHz switch position does not matter (5GHz bypasses U10)

### RF Path Loss Budget

| Path | Components in Chain | Estimated Insertion Loss | Notes |
|------|---------------------|--------------------------|-------|
| BLE 2.4GHz | L3/L4 match + RF switch (U10) + diplexer (U3) low-band | ~1.5–2.5 dB total | Highest loss — three components in chain |
| WiFi 2.4GHz | RF switch (U10) + diplexer (U3) low-band | ~1.0–2.0 dB total | nRF7002 has internal matching; no external matching network on this path |
| WiFi 5GHz | Diplexer (U3) high-band only | ~0.5–1.0 dB | Shortest path, lowest loss |

**⚠ These are estimates.** Request S-parameter data from Murata (U3) and FUMAN (U10) for accurate link budgets. Measure actual insertion loss with a VNA on populated boards.

## RF-Critical Components — DO NOT SUBSTITUTE

The following components are part of the RF matching network and antenna path. **Do not substitute by value alone** — Q factor, SRF (self-resonant frequency), ESR, parasitic inductance, and frequency response must match.

| Ref | MPN | Value | Role | Substitution Risk |
|-----|-----|-------|------|-------------------|
| L3, L4 | CHQ0603T-2N2B-HU | 2.2nH | BLE radio-side match (nRF5340 ANT → 50Ω) | **HIGH** — Q >15 at 2.4GHz, SRF >6GHz required |
| C12, C15 | CC0201BRNPO9BNR70 | 0.7pF | BLE matching/tuning | **HIGH** — NPO/C0G only, ±0.05pF absolute tolerance, 50V min |
| C49, C50 | CC0201BRNPO9BNR70 | 0.7pF | RF matching/tuning (same value as C12/C15 — verify placement in schematic for BLE vs WiFi path) | **HIGH** — same as C12/C15 |
| U3 | LFD182G45DCHD277 | Diplexer | Band splitting | **CRITICAL** — no equivalent; must use exact part |
| U10 | FM8625H | RF switch | Antenna selection | **CRITICAL** — no equivalent; must use exact part |
| R34–R37 | RC0201FR-070RL | 0Ω | RF path configuration | **LOW** — standard 0201 0Ω jumper; population determines RF configuration |

### If substitution is unavoidable (L3, L4):
- Must be 0201 package (0.6mm × 0.3mm)
- 2.2nH ±0.1nH
- Q factor ≥15 at 2.4GHz
- SRF ≥6GHz
- DCR ≤500mΩ
- Candidates: Murata LQP03TN2N2B02D, TDK MLG0603P2N2BT000

### If substitution is unavoidable (C12, C15, C49, C50):
- Must be 0201 package
- 0.7pF ±0.05pF absolute tolerance (at 0.7pF, ±0.05pF is ~7% — tighter than standard ±10% which would be ±0.07pF)
- NPO/C0G dielectric ONLY — X7R/X5R capacitance shifts with frequency and is unusable at 2.4GHz
- Rated ≥50V
- Candidates: Murata GRM0335C1H0R7BA01 (verify actual tolerance on Murata's parametric search)

### Matching Network Boundary

**L3/L4 are the radio-side match**, not antenna tuning. They transform the nRF5340 ANT pin impedance to the 50Ω reference expected by the RF switch and diplexer. Antenna tuning for a different enclosure is a separate concern — it may require additional components or trace modifications at the antenna feed point, not changes to L3/L4. Do not conflate the two: changing L3/L4 to compensate for enclosure detuning will simultaneously degrade the radio match and the antenna match.

## Antenna Considerations

### PCB Antenna / External Antenna

The mainboard uses a PCB trace antenna (no external antenna connector). The antenna trace geometry is part of the gerber files and **must not be modified**.

### Antenna Keepout Zone

**No copper pour, ground plane, or components should be placed within the antenna keepout area.** The KiCad PCB should have a keepout zone defined around the antenna area. Verify this is preserved in fabrication.

### Enclosure Effect

The Omi device uses a **CNC aluminium enclosure** (front cover case-a, back cover case-b). Metal enclosures significantly affect antenna performance:

- **Detuning:** Metal near the antenna shifts the resonant frequency. The antenna feed was tuned for the production enclosure geometry.
- **Absorption:** Aluminium absorbs and reflects RF energy, reducing antenna efficiency.
- **Acoustic ports as RF windows (hypothesis — not measured):** The microphone holes in the enclosure may serve as RF apertures — do not block them with conductive material. A CNC aluminum enclosure needs a verified RF window/slot strategy; this assumption should be confirmed with VNA measurement in the final enclosure.

**⚠ If using a different enclosure:** The RF matching network may need re-tuning. This requires a VNA (Vector Network Analyzer) and expertise in antenna matching. Without re-tuning, expect degraded BLE range and WiFi throughput.

**⚠ Regulatory:** Any change to the antenna, enclosure, or RF matching network invalidates the original FCC/CE/IC certification (if one exists). A modified design requires re-testing per FCC Part 15.247 (2.4 GHz), Part 15.407 (5 GHz UNII), and ETSI EN 300 328 / EN 301 893. Budget $5–15K for a pre-scan at an accredited test lab before production.

### Antenna Testing

After assembly, verify RF performance:

**Smoke tests (bring-up):**

1. **BLE range test:** Device should maintain connection at ≥10m line-of-sight with phone
2. **WiFi connectivity:** Should connect to a standard 2.4GHz access point within 5m
3. **nRF Connect app:** Shows RSSI (Received Signal Strength Indicator) — typical values:
   - -30 to -50 dBm: Excellent (within 1m)
   - -50 to -70 dBm: Good (1-5m)
   - -70 to -90 dBm: Fair (5-10m)
   - Below -90 dBm: Poor — check antenna/matching

**Recommended qualification tests:**

4. **VNA S11 measurement** in the final enclosure — strongly recommended. Measure return loss at the antenna feed point; target S11 < -10 dB across 2.4–2.5 GHz and 5.15–5.85 GHz bands.
5. **Conducted TX power** — measure with a spectrum analyzer or power meter via a test coupler if available. Required if doing a regulatory pre-scan (FCC/CE).
6. **WiFi EVM/throughput** — verify on both 2.4 GHz and 5 GHz bands to confirm diplexer and switch path integrity.
7. **BLE sensitivity** — use nRF Connect SDK's DTM (Direct Test Mode) for conducted or radiated measurements.

## Reference Documents

- [Nordic nRF5340 Antenna Design Guide](https://infocenter.nordicsemi.com/topic/com.nordic.infocenter.nrf5340/dita/nrf5340/hw_description/antenna.html)
- [Nordic nRF7002 Wi-Fi Design Guide](https://infocenter.nordicsemi.com/topic/nrf7002_ps/keyfeatures_html5.html)
- [Murata Diplexer LFD182G45 Datasheet](https://www.murata.com/products/productdetail?partno=LFD182G45DCHD277)
- IPC-2221B: Generic Standard on Printed Board Design (impedance/trace guidance)
