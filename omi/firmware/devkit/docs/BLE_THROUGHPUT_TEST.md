# BLE Throughput Test

This document describes how to setup and run the BLE throughput test for Omi hardware.

## How to Run

### 1. Configuration Setup

Create a `prj.conf` file with the following content:

```
# BLE
#
CONFIG_BT=y
CONFIG_BT_PERIPHERAL=y
CONFIG_BT_DEVICE_NAME="Omi BLE Thoughput Test"
CONFIG_BT_MAX_CONN=1
CONFIG_BT_MAX_PAIRED=1
CONFIG_BT_DEVICE_APPEARANCE=22
CONFIG_BT_GATT_DYNAMIC_DB=y

#
# Large BLE packets / BLE Buffers
#
CONFIG_BT_L2CAP_TX_MTU=498
CONFIG_BT_CTLR_DATA_LENGTH_MAX=251
CONFIG_BT_CTLR_PHY_2M=y
CONFIG_BT_CTLR_PHY_CODED=y
CONFIG_BT_CTLR_SDC_MAX_CONN_EVENT_LEN_DEFAULT=400000
CONFIG_BT_CONN_TX_MAX=20
CONFIG_BT_BUF_ACL_RX_SIZE=1024
CONFIG_BT_L2CAP_TX_BUF_COUNT=10
CONFIG_BT_BUF_ACL_TX_SIZE=2048


#
CONFIG_RING_BUFFER=y

#
# Logs
CONFIG_LOG=y
CONFIG_UART_CONSOLE=y
CONFIG_CONSOLE=y
CONFIG_PRINTK=y
CONFIG_LOG_PRINTK=y
```

### 2. Create `src/main.c`

Create a main.c file with the following content:

```c
#include <zephyr/kernel.h>
#include <zephyr/shell/shell.h>
#include <zephyr/pm/device_runtime.h>

// Declare the external test function
extern int transport_ble_test(void);

int main(void)
{
	// Call the BLE throughput test function
	transport_ble_test();

    while (1) {
		k_msleep(1000); // Sleep for a second
    }
	return 0;
}
```

### 3. Setup `CMakeLists.txt`

Ensure your CMakeLists.txt includes the following:

```
cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})

project(omi_test)

file(GLOB app_sources src/main.c src/ble_throughput_test.c)
target_sources(app PRIVATE ${app_sources})
```

### 4. Add `src/ble_throughput_test.c`

Either copy the existing `ble_throughput_test.c` file from the Omi repository or get it from the [GitHub PR](https://github.com/BasedHardware/omi/pull/2264/files#diff-19b3ae0b9e98b1746d191b6ce5d369ced34f591a127402bffdf3e3ff1e28d6bd).

### 5. Build & Flash

Build the firmware using your normal Zephyr build process:

```
west build -p auto -b <your_board>
west flash
```

### 6. Monitoring Logs

Check available USB devices and connect to the serial console:

```
$ ls -l /dev/*.usb*
crw-rw-rw-  1 root  wheel  0x9000003 Apr 26 16:36 /dev/cu.usbmodem0000697303521
crw-rw-rw-  1 root  wheel  0x9000005 Apr 26 16:36 /dev/cu.usbmodem108NTMX2S5392
crw-rw-rw-  1 root  wheel  0x9000023 Apr 26 16:56 /dev/cu.usbmodem1101
crw-rw-rw-  1 root  wheel  0x9000002 Apr 26 16:36 /dev/tty.usbmodem0000697303521
crw-rw-rw-  1 root  wheel  0x9000004 Apr 26 16:36 /dev/tty.usbmodem108NTMX2S5392
crw-rw-rw-  1 root  wheel  0x9000022 Apr 26 16:59 /dev/tty.usbmodem1101

$ screen /dev/tty.usbmodem1101 115200
```

### 7. Test with Omi AI App

1. Download the Omi AI app on your smartphone
2. Connect to the BLE device named "Omi BLE Thoughput Test"
3. Monitor the logs on your serial console to see throughput metrics