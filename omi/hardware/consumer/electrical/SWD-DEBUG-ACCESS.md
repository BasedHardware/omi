# SWD Debug Access — Omi Consumer Mainboard

**Sources:** KiCad PCB (`OMI.kicad_pcb`), KiCad schematic (`nRF5340_mcu.kicad_sch`), factory BOM (`omi-bom.csv`)

## Overview

The nRF5340 SoC requires SWD (Serial Wire Debug) for **initial firmware flashing** on blank boards. OTA (Over-The-Air) update only works after the bootloader is programmed.

**Required equipment:**
- J-Link debug probe (SEGGER J-Link EDU Mini recommended, ~$20)
- Fine-tip probe wires or pogo pin jig
- Magnification (the test points are small — board is only 25.5mm diameter)

**nRF5340 dual-core architecture:** The nRF5340 has two independent processors — an application core (Cortex-M33, 128MHz) and a network core (Cortex-M33, 64MHz). Each has its own flash and must be programmed separately through the same SWD interface. The J-Link accesses both via separate debug access ports (DAPs).

## SWD Test Point Locations

All SWD signals are routed to test points on the mainboard PCB:

| Signal | Test Point | Net Name | Position (mm) | Side | Description |
|--------|-----------|----------|---------------|------|-------------|
| SWDIO | **TP3** | /nRF5340/SWDIO | (136.163, 111.829) | Bottom | Serial Wire Data I/O |
| SWDCLK | **TP8** | /nRF5340/SWDCLK | (154.028, 110.117) | Bottom | Serial Wire Clock |
| ~RESET | **TP14** | /nRF5340/~{RESET} | (139.044, 115.354) | Bottom | Active-low reset |
| GND | **TP18** | GND | (153.043, 112.395) | **Bottom** | Ground reference (recommended — same side as SWD signals) |
| GND (alt) | **TP12** | GND | (137.158, 113.116) | Top | Alternate ground (top side) |
| VBAT | **TP9** | VBAT | (144.317, 98.272) | Bottom | Battery voltage (3.0–4.2V) |

**Note:** SWDIO, SWDCLK, RESET, and GND (TP18) are all on the **bottom** side. Use TP18 for ground to enable single-side bottom probing. TP12 is on the top side — use only if a two-sided jig is available.

Coordinates use the drill/place file origin (same as gerber and CPL files). See board outline drawing for physical reference.

## J-Link Wiring

### Connector Types

**⚠ J-Link probes ship with different connectors.** Verify which one your probe uses:

| Connector | Pins | Common On |
|-----------|------|-----------|
| ARM 10-pin Cortex-M (2×5, 1.27mm pitch) | 10 | J-Link EDU Mini, J-Link BASE |
| JTAG/SWD 20-pin (2×10, 2.54mm pitch) | 20 | J-Link PLUS, J-Link ULTRA+ |

The pinouts below are for the **10-pin ARM Cortex-M connector** (J-Link EDU Mini). If using a 20-pin probe, see the 20-pin mapping at the end of this section.

### 10-Pin Connector — Minimum connections (3 wires + ground):

| J-Link 10-Pin | Signal | Connect To |
|---------------|--------|------------|
| Pin 1 (VTref) | Target voltage reference | **VDD_3V3 rail** (see "VTref Access" below) |
| Pin 2 (SWDIO) | Data | **TP3** |
| Pin 4 (SWDCLK) | Clock | **TP8** |
| Pin 3 or 5 (GND) | Ground | **TP18** (bottom-side, recommended) |

### Recommended (adds reset):

| J-Link 10-Pin | Signal | Connect To |
|---------------|--------|------------|
| Pin 10 (~RESET) | Reset | **TP14** |

### 10-Pin Connector Pinout (reference):

```
 ┌─────────────┐
 │  1  2  3  4  5 │   1 = VTref    2 = SWDIO
 │  6  7  8  9 10 │   3 = GND      4 = SWDCLK
 └─────────────┘   5 = GND      6 = SWO (unused)
                     7 = (reserved) 8 = (reserved)
                     9 = GND       10 = ~RESET
```

### 20-Pin Connector Mapping (J-Link PLUS/ULTRA+):

| J-Link 20-Pin | Signal | Connect To |
|---------------|--------|------------|
| Pin 1 (VTref) | Target voltage reference | **VDD_3V3 rail** |
| Pin 7 (SWDIO/TMS) | Data | **TP3** |
| Pin 9 (SWDCLK/TCK) | Clock | **TP8** |
| Pin 4, 6, 8, 10, 12 (GND) | Ground | **TP18** |
| Pin 15 (~RESET) | Reset | **TP14** |
| Pin 19 (5V target supply) | **DO NOT CONNECT** | — (5V would damage VBAT path) |

## VTref Access

**VTref tells the J-Link what voltage level to use for SWD I/O.** It is a sense input, not a power output. It must be connected to the nRF5340 I/O rail (VDD_3V3, nominally 3.3V), **not** raw VBAT (3.0–4.2V).

**⚠ Do NOT connect VTref to VBAT (TP9).** VBAT is the raw battery voltage (3.0–4.2V nominal). The nRF5340 SWD I/O is referenced to its I/O supply rail (VDD_3V3), not VBAT. Connecting VTref to VBAT misrepresents the logic level and may cause communication failures or damage.

### How to access VDD_3V3

There is no dedicated VDD_3V3 test point on the PCB. Options (in order of preference):

1. **Probe the output side of U16 (SGM2036S-3.3V LDO)** — pin 3 is VOUT. Locate U16 on the PCB and solder a thin wire to its output pad or a nearby decoupling cap on the 3V3 net.
2. **Use a via or exposed pad on the VDD_3V3 net** — identify one by checking continuity from U16 output.
3. **Measure and verify:** Before connecting VTref, power the board and measure the candidate point with a multimeter. It should read **3.0–3.3V** relative to GND. If it reads 3.7–4.2V, you are on VBAT — do not connect.

## Power During Flashing

**Option A — Battery powered (recommended for assembled boards):**
- Connect the LiPo battery to power the board
- Wait for LDOs to stabilize (~10ms)
- J-Link VTref connects to VDD_3V3 (the nRF5340 I/O rail)
- VTref is a logic-level reference — it does NOT supply power to the board

**Option B — External bench supply (for bare boards without battery):**
- Set bench supply to **3.7V** (typical LiPo voltage), current limit **100mA**
- Connect to VBAT (TP9 positive) and GND (TP18 negative)
- Acceptable voltage range: **3.0V–4.2V** (matches LiPo operating range)
- **Do NOT exceed 4.2V** — the BQ25101 charger IC is rated for ≤6.4V input, but exceeding 4.2V on VBAT simulates an overcharged battery and may trigger the GLF73910 protection IC
- **Do NOT inject 5V** into VBAT — this is not a USB power input
- Wait for LDOs to stabilize, then connect VTref to VDD_3V3

**⚠ CAUTION:**
- Do NOT power from bench supply while battery is connected — the power paths may conflict
- Use a current-limited supply — if current exceeds 50mA before firmware is running, disconnect immediately (likely a short)
- TP18 (GND, bottom-side) is recommended for single-side probing
- Use a microscope and strain-relieved fine wires to avoid shorts on the 25.5mm diameter board
- Observe ESD precautions — wear a grounded wrist strap or touch a grounded metal surface before handling

## Flashing Procedure

1. **Connect SWD wires** to test points as described above
2. **Power the board** (battery or external supply)
3. **Verify VTref:** Measure VDD_3V3 with a multimeter — should read 3.0–3.3V
4. **Flash network core first**, then application core:

```bash
# Using nrfjprog (from Nordic nRF Command Line Tools v10.23+)

# Check J-Link connection first
nrfjprog -f NRF53 --ids
# If multiple probes, add --snr <serial> to all commands below

# For protected/factory devices, recover first:
nrfjprog -f NRF53 --recover --coprocessor CP_NETWORK
nrfjprog -f NRF53 --recover

# Flash network core FIRST (Bluetooth/802.15.4 firmware)
nrfjprog -f NRF53 --program net_core.hex --sectorerase --verify --coprocessor CP_NETWORK

# Flash application core (main firmware)
# CP_APPLICATION is the default if --coprocessor is omitted
nrfjprog -f NRF53 --program app_core.hex --sectorerase --verify --reset
```

**If connection is unstable with flying wires**, reduce SWD clock speed:
```bash
nrfjprog -f NRF53 --clockspeed 1000 --program app_core.hex --sectorerase --verify --reset
```

Or use the J-Link scripts in `firmware/FLASH_3.0.8/`:
```bash
JLinkExe -device nRF5340_xxAA -if SWD -speed 4000 -CommandFile program_net.jlink
JLinkExe -device nRF5340_xxAA -if SWD -speed 4000 -CommandFile program_app.jlink
```

5. **Verify** — LED should blink after successful flash
6. **After initial flash**, subsequent updates can use OTA via the nRF Connect app

## Programming Jig (for multiple boards)

For production or multiple boards, a custom pogo pin jig is recommended:

### Design Parameters
- **Board diameter:** 25.5mm (circular)
- **Test point pad diameter:** ~1.0mm (typical)
- **Recommended pogo tip:** P75-B1 or equivalent (0.74mm tip, 1.02mm body)
- **Required signals (all bottom-side):** TP3 (SWDIO), TP8 (SWDCLK), TP14 (RESET), TP18 (GND) — 4 probes minimum
- **Optional (for VTref):** Probe a VDD_3V3 via on the bottom side — 5 probes
- **Board orientation:** Align using the edge of the PCB outline or a mechanical feature (BTB connector J1 position)

### Jig Construction
1. 3D-print a fixture plate with holes at the test point coordinates
2. Press-fit pogo pin probes (spring-loaded)
3. Wire probes to a 10-pin ribbon cable connector (matches J-Link EDU Mini)
4. Add alignment pins or a circular recess matching the 25.5mm board diameter

### Alternative: Tag-Connect TC2030-NL
The current PCB does not have a Tag-Connect footprint. If a future revision adds one, Tag-Connect TC2030-NL (no-legs, 6-pin) is ideal — but requires a PCB layout change.

### Manual Probing (1–5 units)
Fine-tip spring probes held by hand with magnification. Use strain-relieved wires. One person holds probes on pads while another runs the flash commands. Adequate for small quantities but slow and error-prone.

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| J-Link doesn't detect target | No power, wrong VTref, or no GND | Measure VDD_3V3 with multimeter. Verify GND continuity. Check J-Link LEDs. |
| "Cannot connect to target" | SWDIO/SWDCLK reversed, or probe not making contact | Swap TP3 and TP8. Apply firm pressure. Use magnification to verify pad contact. |
| "Cannot connect" intermittently | SWD clock too fast for flying wires | Add `--clockspeed 1000` to nrfjprog commands. Keep SWD wires short (<10cm). |
| VTref reads 0V | VDD_3V3 not powered, or wrong probe point | Check VBAT is applied. Verify U16 LDO output. Board may have assembly defect. |
| VTref reads 3.7–4.2V | Probing VBAT instead of VDD_3V3 | Wrong probe point. Move to U16 output or a verified VDD_3V3 pad. |
| Erase/recover fails | Access port protection enabled | Run `nrfjprog -f NRF53 --recover --coprocessor CP_NETWORK` first, then `--recover` for app core. |
| Flash succeeds but no boot | Wrong firmware file or missing network image | Ensure using `omi/nrf5340/cpuapp` target build. Flash network core first. |
| "Multiple J-Links detected" | More than one probe connected | Add `--snr <serial>` to specify which probe. Find serial with `nrfjprog --ids`. |
| App flashed but BLE not working | Network core not programmed | Network core firmware is required for BLE. Flash with `--coprocessor CP_NETWORK`. |
| Intermittent connection drops | Loose probe contact or long wires | Use spring probes. Keep wires <10cm. Add ferrite bead on SWD lines if EMI suspected. |
