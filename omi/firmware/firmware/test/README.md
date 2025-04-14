# OMI EVT test commands

This document describes the commands that can be used to test the OMI EVT board.

## Initialization

This project uses [Zephyr](https://docs.zephyrproject.org/latest/getting_started/index.html) as the OS and [nRF Connect SDK](https://docs.nordicsemi.com/bundle/ncs-latest/page/zephyr/develop/toolchains/zephyr_sdk.html) for BLE support.Before using the commands below, make sure you have vscode and nRF Connect SDK installed. You can follow the [nRF Connect SDK Getting Started](https://docs.nordicsemi.com/bundle/ncs-latest/page/nrf/installation/install_ncs.html) guide to install it.

### Build

To build the firmware, you can use VS Code.

#### Using VSCode:
1.Open nRF Connect Extension inside VS Code.

2.Click “Open an existing application” and navigate to the firmware/firmware/test folder in the root of this repository.

3.In the application panel of the extension, click the Add Build Configuration icon. Choose a CMake Preset that matches your hardware.

4.Scroll to the bottom and click “Build Configuration.” This will start the nRFConnect SDK building your firmware file. A VSCode notification popup will notify you of the progress of your build.

## 
## Commands

### BLE

| Command | Description |
| --- | --- |
| `ble on` | Turn ON BLE and advertising as `OMI shell` |
| `ble off` | Turn OFF BLE |

### Wifi

| Command | Description |
| --- | --- |
| `wifi ap` | Access Point mode commands. |
| `wifi scan` | Scan for available wifi networks |
| `wifi connect -s $ssid` | Connect to a Wi-Fi AP |
| `wifi disconnect` | Disconnect from the current Wi-Fi AP |
| `wifi status` | Get Wi-Fi connection status |
more commands can be found in the [Nordic Wi-Fi shell](https://docs.nordicsemi.com/bundle/ncs-latest/page/nrf/samples/wifi/shell/README.html#supported_cli_commands) documentation.


### Charger

| Command | Description |
| --- | --- |
| `charger get` | Get battery voltage |

### Flash

| Command | Description |
| --- | --- |
| `flash id` | Read flash chip JEDEC ID |
| `flash erase $ADDR` | Erase flash page for the given `$ADDR` |
| `flash read $ADDR $N` | Read `$N` bytes from address `$ADDR` |
| `flash write $ADDR $VAL` | Write `$VAL` (hex encoded, e.g. `aabbccdd`) to `$ADDR` |

### Sensors

| Command | Description |
| --- | --- |
| `imu get` | Obtain IMU readings (acc/gyro) |

### Microphone

| Command | Description |
| --- | --- |
| `mic capture [sec]` | Capture microphone data for the given number of seconds (default: 1) |


### LED

| Command | Description |
| --- | --- |
| `led on $num` | Turn ON LED (0-3) |
| `led off $num` | Turn OFF LED (0-3) |

### Button

| Command | Description |
| --- | --- |
| `button check` | Check button state |

### Motor

| Command | Description |
| --- | --- |
| `motor on` | Turn ON motor |
| `motor off` | Turn OFF motor |

### sdcard

| Command | Description |
| --- | --- |
| `sdcard mount` | Mount SD card filesystem |
| `sdcard unmount` | Unmount SD card filesystem |
| `sdcard ls $path` | List files in `$path` on the SD card |
| `sdcard read $path ` | Read from file at `$path` |
| `sdcard write $path $data` | Write to file at `$path` with data `$data` |

###  System off

| Command | Description |
| --- | --- |
| `System off` | Turn OFF the device |
