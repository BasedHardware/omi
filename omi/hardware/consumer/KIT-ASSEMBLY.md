# Kit Assembly Guide

**Assemble an Omi device from a pre-built electronics kit.**

This guide is for Kit Build buyers. You received assembled PCBAs, battery, enclosure, and hardware — all you need to do is flash, connect, and assemble.

**Time:** 1–2 hours | **Skill:** Basic soldering (2 wires) | **Tools:** J-Link, soldering iron, multimeter

---

## Before You Start

### Required Tools

| Tool | Notes |
|------|-------|
| J-Link debug probe | EDU Mini (~$20) or any SEGGER J-Link |
| Soldering iron | Temperature-controlled, fine tip |
| Solder wire | 0.5mm or thinner, lead-free or leaded |
| Multimeter | For polarity check |
| Tweezers | For placing small parts |
| Phone | iOS or Android with Omi app installed |

### Kit Contents Checklist

Open the kit and verify all items are present:

- [ ] Mainboard PCBA (round, ~24mm diameter)
- [ ] Charger PCBA (small board with pogo pin pads)
- [ ] FPC (thin flex cable with BTB connector and charging ring)
- [ ] Battery (coin cell, 2 wires — red and black)
- [ ] Case-A (aluminium top cover, laser-engraved)
- [ ] Case-B (aluminium bottom shell)
- [ ] Magnets ×4 (for charger alignment)
- [ ] Screws ×3 (M1.2 or M1.4)
- [ ] Foam tape strip (for battery insulation)
- [ ] Dust filters ×2 (for mic ports)
- [ ] Vibration motor (coin type, 2 wires)
- [ ] Necklace cord

⚠ **If any item is missing or damaged, contact the Omi team before proceeding.**

---

## Step 1: Flash Firmware

Flash the firmware before assembly — it's much easier to access the SWD test points on a bare board.

### Connect J-Link

The mainboard has exposed SWD test points. Connect 4 wires:

| J-Link Pin | Mainboard Pad | Wire Color (suggested) |
|------------|---------------|----------------------|
| VTref | VDD (3.3V) | Red |
| SWDIO | SWDIO | Yellow |
| SWDCLK | SWCLK | Green |
| GND | GND | Black |

Use pogo pins, test clips, or solder temporary wires. The test points are labeled on the board silkscreen.

See [SWD-DEBUG-ACCESS.md](electrical/SWD-DEBUG-ACCESS.md) for a photo of test point locations and detailed wiring.

### Flash

Download `nrfutil` from [nordicsemi.com](https://www.nordicsemi.com/Products/Development-tools/nrf-util) (standalone binary — do NOT use `pip install nrfutil`, that's the deprecated v6).

```bash
# Install the device command
nrfutil install device

# 1. Flash network core FIRST (BLE/WiFi stack)
nrfutil device recover --core Network
nrfutil device program --firmware net_core.hex --core Network --verify

# 2. Flash application core
nrfutil device recover --core Application
nrfutil device program --firmware app_core.hex --core Application --verify --reset
```

**Verify:** After reset, the LED should blink. Open the **nRF Connect** app on your phone and scan — you should see the device advertising.

If flashing fails, check:
- VTref must be connected (J-Link needs to sense the target voltage)
- Try lowering speed: add `--jlink-speed 1000` (check `nrfutil device program --help` for flag availability in your version)
- Make sure SWDIO and SWDCLK aren't swapped

---

## Step 2: Solder Battery

⚠ **CRITICAL: Verify polarity with a multimeter before soldering. Reversed polarity destroys the BQ25101 charger IC. There is no reverse-polarity protection.**

### Check Polarity

1. Set multimeter to DC voltage
2. Touch probes to battery wires: red = positive, black = negative
3. Confirm voltage reads ~3.7V (positive reading)
4. Match to mainboard pads: B+ (positive), B– (negative)

### Solder

1. Tin the B+ and B– pads on the mainboard with a small amount of solder
2. Hold red wire to B+, solder at ≤350°C for ≤3 seconds
3. Hold black wire to B–, solder at ≤350°C for ≤3 seconds
4. Verify: measure voltage across B+ and B– pads — should read ~3.7V

The board should power on. LED blinks = firmware is running.

---

## Step 3: Connect FPC

The FPC (Flexible Printed Circuit) connects the mainboard to the charger board's charging contacts.

1. **Locate the BTB connector** on the mainboard (small, low-profile, one side)
2. **Align the FPC connector** with the mainboard BTB connector
3. **Press down firmly and evenly** until it clicks — the connector latches mechanically
4. **Do not force** — if it doesn't align, rotate the FPC 180° and try again

⚠ The FPC has a minimum bend radius of 2.2mm (static). Do not crease or fold sharply — it will crack the traces.

---

## Step 4: Solder Vibration Motor

1. Tin the motor pads on the mainboard
2. Solder the vibration motor's two wires to the motor pads
3. Polarity doesn't matter for the motor — it vibrates in either direction

---

## Step 5: Test Before Assembly

Run these tests before closing the enclosure — fixing problems after assembly is much harder.

| Test | How | Pass |
|------|-----|------|
| **BLE** | Open nRF Connect on phone, scan | Device appears, RSSI > -70 dBm at arm's length |
| **Microphone** | Open Omi app, start recording | You can hear audio playback |
| **IMU** | Tilt the board while connected | Accelerometer data changes |
| **Motor** | Trigger vibration from app | Motor vibrates |
| **Charging** | Place on charger dock (if you have one) | LED indicates charging |

If any test fails, debug now. See [SWD-DEBUG-ACCESS.md](electrical/SWD-DEBUG-ACCESS.md) for troubleshooting via J-Link RTT.

---

## Step 6: Assemble into Enclosure

### Prepare

1. Place dust filters over the two mic port holes in case-b (press to stick)
2. Insert 4 magnets into case-b magnet slots (check polarity — they should attract the charger)
3. Cut a small piece of foam tape for battery insulation

### Place Components

1. **Mainboard** — seat the mainboard PCBA into case-b. It fits in one orientation only.
2. **Battery** — place foam tape on top of battery, then place battery in the cavity. The foam insulates it from the aluminium case.
3. **FPC routing** — fold the FPC around the edge of the mainboard. Maintain ≥2.2mm bend radius.
4. **Vibration motor** — place in its pocket in case-b
5. **Necklace cord** — thread through the loop slot in case-b

### Close

1. Place case-a (top cover) onto case-b
2. Align the 3 screw holes
3. Insert and tighten 3 screws — snug, not overtightened (aluminium threads strip easily)

---

## Step 7: Final Test

| Test | How | Pass |
|------|-----|------|
| **BLE range** | Walk 10m away from phone | Still connected |
| **Charging** | Place on charger dock | LED indicates charging, stays aligned (magnets) |
| **App pairing** | Open Omi app → Add Device | Pairs and streams audio |
| **Physical** | Shake gently | No rattling, case is solid |

---

## Troubleshooting

| Problem | Likely Cause | Fix |
|---------|-------------|-----|
| No LED after power | Battery not connected or reversed | Check solder joints, verify polarity |
| BLE not advertising | Firmware not flashed | Re-flash both cores |
| No audio | Mic dust filter blocking, or firmware issue | Check dust filter placement, re-flash |
| Won't charge | FPC not connected, or charger board issue | Re-seat BTB connector |
| Weak BLE signal | Case-a not laser-engraved, or wrapper missing | Ensure proper case-a and wrapper installed |
| Case won't close | FPC routed wrong, or component misplaced | Open, re-route FPC with ≥2.2mm bend radius |

---

## What's Next

- **Firmware updates:** Future firmware can be flashed OTA via the Omi app, or via J-Link SWD
- **Community:** Join [Discord](https://discord.gg/omi) #hardware channel
- **Issues:** Report hardware problems on [GitHub](https://github.com/BasedHardware/omi/issues)
- **Modify:** Want to change something? See [BUILD-GUIDE.md](BUILD-GUIDE.md) Path 3 (Design Fork)
