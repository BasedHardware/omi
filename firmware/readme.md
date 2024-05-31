### Install adafruit-nrfutil

```
pip3 install --user adafruit-nrfutil
```

### Upgrade bootloader

Download the a compatible version of the ```xiao_nrf52840_ble_sense_bootloader-``` bootloader
from [Adafurit bootloader releases](https://github.com/adafruit/Adafruit_nRF52_Bootloader/releases)
The minimum version required is 0.8.0.

Put the board in bootloader mode by double pressing the reset button.
Check the serial port for the board and modify the command below accordingly.

```
adafruit-nrfutil dfu serial -p COM8 -pkg xiao_nrf52840_ble_sense_bootloader-0.8.0_s140_7.3.0.zip
```

### Upgrade firmware

Put the board in bootloader mode by double pressing the reset button.
Check the serial port for the board and modify the command below accordingly.

```
adafruit-nrfutil dfu genpkg --dev-type 0x0052 --dev-revision 0xCE68 --application zephyr.hex zephyr.zip
adafruit-nrfutil dfu serial -p COM8 -pkg zephyr.zip
```

You can also use the Nordic nRF Connect app to upgrade the bootloader and firmware. Make sure
to change the PRN option from the default of 12 to 8.