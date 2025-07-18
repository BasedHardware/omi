# OMI Glass Firmware Guide

This document provides comprehensive instructions for building, flashing, and managing the OMI Glass firmware.

## 1. Flashing with UF2 (Easiest Method)

The UF2 (USB Flashing Format) method is the simplest way to flash your ESP32-S3 device by dragging and dropping a file.

### 🚀 Quick Start

#### 1. Build UF2 File
From the `firmware` directory, run the build script:
```bash
# Build optimized release version (recommended)
./scripts/build_uf2.sh -e uf2_release

# Or build standard version
./scripts/build_uf2.sh
```

#### 2. Flash to Device
1. **Enter Bootloader Mode:**
   - Hold down the **BOOT** button on your ESP32-S3.
   - While holding BOOT, press and release the **RESET** button.
   - Release the **BOOT** button.
   - Your device should appear as a USB drive named **"ESP32S3"**.

2. **Flash the Firmware:**
   - Copy the generated `omi_glass_firmware.uf2` file to the "ESP32S3" drive.
   - The device will automatically flash and reboot.

3. **Monitor (Optional):**
   ```bash
   pio device monitor --baud 115200
   ```

### 🏗️ Build Environments

| Environment | Description | Use Case |
|---|---|---|
| `seeed_xiao_esp32s3` | Standard build | Development |
| `seeed_xiao_esp32s3_slow` | Slower upload | For connection issues |
| `uf2_release` | Optimized release | Production/Best battery |

### 📁 Generated Files

After building, you'll get:
- `omi_glass_firmware.uf2` - Main firmware file (ready to flash).
- `.pio/build/*/firmware.bin` - Original binary (for advanced use).

### 🛠️ Troubleshooting UF2

- **Device Not Appearing as USB Drive**: Ensure you are correctly entering bootloader mode. Try a different USB cable or port.
- **Build Fails**: Make sure PlatformIO is installed (`pip install platformio`). Try cleaning the build first (`pio run --target clean`).
- **Upload Issues**: Use the slower environment (`./scripts/build_uf2.sh -e seeed_xiao_esp32s3_slow`).

---

## 2. Flashing with PlatformIO

PlatformIO provides more control over the build and upload process.

### Prerequisites

- [PlatformIO](https://platformio.org/install) installed.
- ESP32 S3 XIAO board connected via USB.

### Flashing Instructions

1. **Connect** your ESP32 S3 XIAO board.
2. **Enter Bootloader Mode** (see UF2 section for instructions).
3. **Run the upload command** from the `firmware` directory:
   ```bash
   # Try standard environment first
   platformio run -e seeed_xiao_esp32s3 --target upload
   
   # If the above fails, try the slower environment
   platformio run -e seeed_xiao_esp32s3_slow --target upload
   ```
4. **Monitor the serial output**:
   ```bash
   platformio device monitor --baud 115200
   ```

### 🛠️ Troubleshooting PlatformIO

- **"No serial data received" Error**: Ensure the board is in bootloader mode. Try the `seeed_xiao_esp32s3_slow` environment.
- **Cannot Find Device**: Check USB connection and drivers. On macOS, ensure you allow the device in System Settings.
- **Upload Fails**: Try holding the BOOT button during the entire upload process.

---

## 3. Flashing with Arduino-CLI

This method is for users who prefer using `arduino-cli`.

### Install the board

```bash
arduino-cli config add board_manager.additional_urls https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
arduino-cli core install esp32:esp32@2.0.17
```

### Get board details

On Windows 11 board should be showing as ```esp32:esp32:XIAO_ESP32S3```
but instead might show as ```esp32:esp32:nora_w10```, ```esp32:esp32:wifiduino32c3```, or something else.

```bash
arduino-cli board list
arduino-cli board details -b esp32:esp32:XIAO_ESP32S3
```

### Compile and upload

Change `COM5` to the port name from the board list output.

```bash
arduino-cli compile --build-path build --output-dir dist -e -u -p COM5 -b esp32:esp32:XIAO_ESP32S3:PSRAM=opi
```

### Opus support

Go to your Arduino libraries folder. You can find the location with `arduino-cli config get directories.user` (add `/libraries` to the path).

Then clone the two libraries needed for Opus support:

```bash
git clone https://github.com/pschatzmann/arduino-libopus.git
git clone https://github.com/pschatzmann/arduino-audio-tools.git
```

---

## 4. Hardware, Battery & Charging Guide

This section covers battery setup, charging, and monitoring.

### Battery Indicator Setup

The firmware includes a battery service that reports the battery level to the companion app.

#### Hardware Requirements

- **ADC Pin**: `A0`
- **Voltage Divider**: A voltage divider is required to safely measure the 4.2V battery voltage with the 3.3V ADC.

#### Hardware Configuration (Seeed XIAO ESP32S3 Sense)

- **ADC Pin**: `A0`
- **Battery**: 3.7V LiPo (3.7V - 4.2V range)
- **Voltage divider**: R1=169kΩ, R2=110kΩ (2.536:1 ratio)
- **ADC Reference**: 3.3V

Your current setup:
```
Battery + ----[R1: 169kΩ]----+----[R2: 110kΩ]---- Battery -
                             |
                           ADC Pin A0
```

The firmware is configured for these values. If you use different resistors, you must update the voltage multiplier in the code.

### How to Charge Your OMI Glass

#### **Hardware Setup**
- **Batteries**: Dual 250mAh Li-ion batteries (500mAh total, 3.7V-4.3V range)
- **Charging Method**: Connect USB-C cable to ESP32-S3 board
- **Charging LED**: On-board LED indicates charging status

#### **Charging Process**
1. **Connect USB-C cable** to the ESP32-S3 board (or Mac/PC)
2. **Red LED** = Charging in progress
3. **Green LED** = Fully charged
4. **Charging time**: ~1-1.5 hours for full charge (from Mac USB)

#### **Mac USB Charging Rates**
- **USB 2.0 port**: ~500mA (1-1.5 hours full charge)
- **USB 3.0 port**: ~900mA (45-60 minutes full charge)
- **USB-C port**: ~1.5A (30-45 minutes full charge)
- **Actual rate**: Limited by ESP32 charging circuit (~500mA typical)

---

### Monitoring Battery Status

#### **Real-time Monitoring via Serial**

Connect to the device via serial monitor (115200 baud) and use these commands:

##### **Quick Status Check**
```
status
```
Shows current battery level, connection status, and device state.

##### **Charging Status Monitor**
```
charging
```
Takes 10 readings over 20 seconds and shows charging status:
- 🔋 **CHARGING** (>4.1V) - Actively charging
- ⚡ **CHARGED** (3.9-4.1V) - Good charge level
- 🔴 **LOW** (3.7-3.9V) - Needs charging
- ❌ **CRITICAL** (<3.7V) - Check connections

##### **Battery Runtime Calculator**
```
runtime
```
Shows how long your glasses will last with current charge level for different usage scenarios.

##### **Charging Time Calculator**
```
chargetime
```
Calculates estimated time to reach 80%, 90%, and 100% charge based on current level.

##### **Continuous Monitor**
```
monitor
```
Continuous 5-second interval monitoring. Type any command to stop.

#### **OMI App Battery Display**
The OMI app automatically shows battery percentage when connected to the glasses.

---

### Expected Voltage Levels & Charging Times

| **Voltage Range** | **Battery %** | **Status** | **Time to Full (Mac USB)** |
|-------------------|---------------|------------|----------------------------|
| **4.2V - 4.3V** | 100% | Fully charged | 0 minutes |
| **4.0V - 4.2V** | 80-100% | Good charge | 15-20 minutes |
| **3.8V - 4.0V** | 20-80% | Moderate | 30-60 minutes |
| **3.7V - 3.8V** | 0-20% | Low battery | 60-90 minutes |
| **3.5V - 3.7V** | Critical | Very low | 90+ minutes |
| **<3.5V** | Critical | Unsafe | Check hardware |

**Note**: Times are for 500mAh total capacity (2 x 250mAh) at typical Mac USB rates.

---

### Battery Life Estimates (500mAh Total)

#### **Expected Runtime on Full Charge**

| **Usage Pattern** | **Runtime** | **Description** |
|-------------------|-------------|-----------------|
| **🔥 Heavy Use** | **6-7 hours** | Continuous photo capture, always active |
| **⚡ Normal Use** | **8-10 hours** | Mixed usage: 60% active, 30% standby, 10% sleep |
| **💤 Light Use** | **12-15 hours** | Mostly connected but idle, occasional photos |

#### **Current Consumption Breakdown**
- **Active Mode**: ~80mA (Camera + BLE + processing)
- **Standby Mode**: ~40mA (BLE connected, camera off)
- **Sleep Mode**: ~2mA (Deep sleep, button wake-up)

#### **Real-World Usage Examples**

##### **All-Day Meeting Recording** (8 hours)
- 30-second photo intervals
- Continuous BLE connection
- **Expected result**: 8-10 hours runtime ✅

##### **Occasional Use** (throughout day)
- Photos every few minutes
- Connected but mostly idle
- **Expected result**: 12-15 hours runtime ✅

##### **Intensive Documentation** (non-stop)
- Continuous photo capture
- High processing load
- **Expected result**: 6-7 hours runtime ⚠️

---

### Charging Verification Steps

#### **Step 1: Connect & Check Initial Reading**
```
status
```
Note the starting voltage (should be <4.1V if not charged).

#### **Step 2: Connect Charger**
1. Plug in USB-C charger
2. Check for charging LED (red light)
3. Wait 5 minutes for voltage to stabilize

#### **Step 3: Monitor Charging Progress**
```
charging
```
You should see:
- **Voltage increasing** over time
- **Status showing "CHARGING"** when >4.1V
- **Steady upward trend** in readings

#### **Step 4: Verify Full Charge**
After 2-3 hours:
```
status
```
Should show:
- **Voltage: 4.2V-4.3V**
- **Battery: 100%**
- **Green charging LED**

---

### Hardware Verification & Troubleshooting

#### **Problem**: Always shows 0% or 100%
**Solution**: Check voltage divider connections.
```
status
```
Look for unrealistic voltages (<2V or >5V).

#### **Problem**: Voltage doesn't change during charging
**Solution**: 
1. Verify charger is connected.
2. Check charging LED on ESP32-S3.
3. Try different USB cable/charger.
4. Check battery connections.

#### **Problem**: Shows "CRITICAL" with charger connected
**Solution**:
1. Check voltage divider wiring.
2. Ensure `A0` is connected correctly.
3. Verify resistor values (169kΩ and 110kΩ).

---

### Charging Best Practices

#### **Optimal Charging**
- **Charge when battery drops below 20%** (3.8V)
- **Don't let battery go below 3.5V** (damages Li-ion cells)
- **Charge in moderate temperatures** (10°C-40°C)
- **Use quality USB-C charger** (5V, 1A minimum)

#### **Battery Life Optimization**
- **Avoid complete discharge** (stop using at 3.7V)
- **Charge regularly** (don't leave dead for days)
- **Store at 50% charge** if not using for weeks
- **Optimize usage patterns** for longer runtime:
  - Use light sleep mode when possible
  - Reduce photo frequency for all-day use
  - Disconnect when not needed to save power

#### **Status Monitoring Schedule**
- **Before use**: Quick `status` check
- **During long sessions**: Periodic `status` checks
- **While charging**: Use `charging` command to verify progress
- **For troubleshooting**: Use `monitor` for continuous tracking

---

### Troubleshooting Quick Reference

| **Issue** | **Command** | **Expected Result** | **Fix** |
|-----------|-------------|-------------------|---------|
| Won't charge | `charging` | Voltage increases | Check charger/cable |
| Shows 0% always | `status` | Voltage <2V | Check hardware connections |
| Won't turn on | `monitor` | No response | Charge for 30+ minutes |
| Inconsistent readings | `charging` | Fluctuating values | Check loose connections |
| App shows wrong % | `status` | Compare readings | Reconnect BLE |

**For hardware issues**: Check the voltage divider circuit and ensure the ADC pin `A0` is properly connected to the battery voltage divider midpoint.
