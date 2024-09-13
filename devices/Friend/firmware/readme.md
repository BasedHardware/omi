### Install adafruit-nrfutil

```
pip3 install --user adafruit-nrfutil
```

### Create firmware OTA .zip using adafruit-nrfutil

```bash
adafruit-nrfutil dfu genpkg --dev-type 0x0052 --dev-revision 0xCE68 --application zephyr.hex zephyr.zip
```

### Upgrade firmware using UF2 file

Download the latest version of the firmware ```xiao_nrf52840_ble_sense-XXXX.uf2```
from [Friend firmware releases](https://github.com/BasedHardware/Omi/releases)

Put the board in bootloader mode by double pressing the reset button. The board should appear as a USB drive.

Copy the new firmware file in the root directory of the board. The board will automatically update the firmware and reset back to application mode.
You can check the firmware version from the Friend companion app.

### Upgrade bootloader using UF2 file

Download a compatible version of the ```update-xiao_nrf52840_ble_sense_bootloader-XXX.uf2``` bootloader
from [Adafurit bootloader releases](https://github.com/adafruit/Adafruit_nRF52_Bootloader/releases)
The latest tested version is 0.9.0. Newer versions should work as well.

Put the board in bootloader mode by double pressing the reset button. The board should appear as a USB drive.

Copy the bootloader update file in the root directory of the board. The board will automatically update the bootloader and reset back to application mode.
To check the bootloader was updated, put the board in bootloader mode again and check the INFO_UF2.TXT file for the new bootloader version.
