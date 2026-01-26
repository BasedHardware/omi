# OMI EVT test commands

This document describes the commands that can be used to test the OMI EVT board.

## Initialization

This project uses [Zephyr](https://docs.zephyrproject.org/latest/getting_started/index.html) as the OS and [nRF Connect SDK](https://docs.nordicsemi.com/bundle/ncs-latest/page/zephyr/develop/toolchains/zephyr_sdk.html) for BLE support.Before using the commands below, make sure you have vscode and nRF Connect SDK installed. You can follow the [nRF Connect SDK Getting Started](https://docs.nordicsemi.com/bundle/ncs-latest/page/nrf/installation/install_ncs.html) guide to install it.

## Build Instructions

### Using VS Code

1. Open nRF Connect Extension inside VS Code.
2. Click "Open an existing application" and navigate to the `firmware/test` folder.
3. In the application panel, click the **Add Build Configuration** icon. Choose a CMake Preset that matches your hardware.
4. Click "Build Configuration" to start the build process. A VS Code notification will show build progress.

---

## Shell Commands Reference

All commands are executed via the Zephyr shell interface (UART or BLE NUS).

### BLE Commands

Control Bluetooth Low Energy functionality.

| Command | Description | Example |
| --- | --- | --- |
| `ble on` | Enable BLE and start advertising as `Omi EVT` | `ble on` |
| `ble off` | Disable BLE and stop advertising | `ble off` |

**Notes:**
- BLE uses Nordic UART Service (NUS) for shell transport over BLE
- Default device name: `Omi EVT`

---

### WiFi Commands

Control WiFi functionality (nRF70 series).

| Command | Description | Example |
| --- | --- | --- |
| `wifi scan` | Scan for available WiFi networks | `wifi scan` |
| `wifi connect -s <ssid>` | Connect to a WiFi access point | `wifi connect -s MyNetwork` |
| `wifi disconnect` | Disconnect from current WiFi AP | `wifi disconnect` |
| `wifi status` | Get current WiFi connection status | `wifi status` |
| `wifi ap` | Access Point mode commands | `wifi ap` |

More commands can be found in the [Nordic Wi-Fi shell](https://docs.nordicsemi.com/bundle/ncs-latest/page/nrf/samples/wifi/shell/README.html#supported_cli_commands) documentation.

---

### Battery/Charger Commands

Monitor battery voltage and charging status.

| Command | Description | Example Output |
| --- | --- | --- |
| `bat get` | Read battery ADC value and charging status | `Raw: 2048, Voltage: 4.2V, Charging: Yes` |

**Notes:**
- Voltage is calculated from ADC raw value
- Charging status indicates if device is connected to charger

---

### SPI Flash Commands

Read/write/erase external SPI flash memory.

| Command | Description | Example |
| --- | --- | --- |
| `flash id` | Read flash chip JEDEC ID | `flash id` |
| `flash erase <addr>` | Erase flash page at address | `flash erase 0x1000` |
| `flash read <addr> <len>` | Read bytes from flash address | `flash read 0x0 32` |
| `flash write <addr> <data>` | Write hex data to flash address | `flash write 0x0 aabbccdd` |

**Notes:**
- Address values are in hexadecimal (prefix with `0x`)
- Write data is hex-encoded (e.g., `aabbccdd` = 4 bytes: 0xAA, 0xBB, 0xCC, 0xDD)
- Erase before write (flash bits can only be cleared by erase)

---

### IMU/Sensor Commands

Read accelerometer and gyroscope data from LSM6DS3TR-C IMU.

| Command | Description | Example Output |
| --- | --- | --- |
| `imu get` | Read accelerometer and gyroscope XYZ values | `Accel: X=0.02 Y=-0.01 Z=9.81 m/s², Gyro: X=0.1 Y=-0.2 Z=0.0 rad/s` |

**Notes:**
- Accelerometer values in m/s²
- Gyroscope values in rad/s

---

### Microphone Commands

Capture audio samples from PDM microphone.

| Command | Description | Example |
| --- | --- | --- |
| `mic capture [seconds]` | Capture audio for specified duration (default: 1s) | `mic capture 3` |

**Notes:**
- Default capture duration is 1 second
- Outputs raw PCM samples to console
- Sample rate: 16000 Hz

---

### LED Commands

Control RGB LEDs via PWM.

| Command | Description | Example |
| --- | --- | --- |
| `led on <num>` | Turn ON LED by index | `led on 0` |
| `led off <num>` | Turn OFF LED by index | `led off 0` |

**LED Index Mapping:**

| Index | Color |
| --- | --- |
| 0 | Red |
| 1 | Green |
| 2 | Blue |

---

### Button Commands

Check button state and events.

| Command | Description | Example Output |
| --- | --- | --- |
| `button check` | Enter button monitoring mode (5s timeout) | `usr button pressed` / `usr button released` |

**Notes:**
- Command waits for button events for up to 5 seconds
- Reports press and release events
- Press Ctrl+C to exit monitoring mode

---

### Motor/Haptic Commands

Control vibration motor.

| Command | Description | Example |
| --- | --- | --- |
| `motor on` | Turn ON motor (auto-off after 100ms) | `motor on` |
| `motor off` | Turn OFF motor immediately | `motor off` |

**Notes:**
- Motor automatically turns off after 100ms for safety
- Used for haptic feedback testing

---

### SD Card Commands

Manage SD card filesystem (ext2).

| Command | Description | Example |
| --- | --- | --- |
| `sd mount` | Mount SD card filesystem | `sd mount` |
| `sd unmount` | Unmount SD card filesystem | `sd unmount` |
| `sd ls <path>` | List files in directory | `sd ls /ext` |
| `sd read <file>` | Read entire file content | `sd read test.txt` |
| `sd write <file> <data>` | Append data to file (creates if not exist) | `sd write log.txt "Hello World"` |
| `sd rm <file>` | Delete a file | `sd rm old.txt` |
| `sd readline <file> <line>` | Read specific line number from file | `sd readline log.txt 5` |

**Notes:**
- Filesystem: ext2
- Mount point: `/ext`
- For `ls` command: use **absolute path** (e.g., `sd ls /ext`, `sd ls /ext/mydir`)
- For `read/write/rm`: paths are **relative to mount point** (e.g., `sd read test.txt` = `/ext/test.txt`)
- `write` appends data with newline
- `sd ls /` shows system root (only shows `ext` folder = mount point)

---

### System Commands

System power management.

| Command | Description | Example |
| --- | --- | --- |
| `sys off` | Enter System OFF (deep sleep) mode | `sys off` |

**Notes:**
- Device enters lowest power state
- Press user button to wake up and restart
- WiFi RPU is disabled before entering System OFF

---

## Quick Test Sequence

Here's a recommended sequence to test all peripherals:

```shell
# 1. Test LEDs
led on 0
led off 0
led on 1
led off 1
led on 2
led off 2

# 2. Test Motor
motor on
motor off

# 3. Test Battery
bat get

# 4. Test IMU
imu get

# 5. Test Button
button check
# (press button within 5 seconds)

# 6. Test Flash
flash id
flash erase 0x0
flash write 0x0 deadbeef
flash read 0x0 4

# 7. Test SD Card
sd mount
sd ls /ext
sd write test.txt "Hello Omi"
sd read test.txt
sd unmount

# 8. Test Microphone
mic capture 1

# 9. Test BLE
ble on
# (connect with nRF Connect app)
ble off

# 10. Test WiFi
wifi scan

# 11. System Off Test
sys off
# (press button to wake)
```

---

## BLE Throughput Test

This test allows you to measure the BLE throughput performance of your device. For detailed instructions, see [BLE_THROUGHPUT_TEST.md](./BLE_THROUGHPUT_TEST.md).
