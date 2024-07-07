### Install adafruit-nrfutil

```
pip3 install --user adafruit-nrfutil
```

### Upgrade bootloader using adafruit-nrfutil

Download a compatible version of the ```xiao_nrf52840_ble_sense_bootloader-``` bootloader
from [Adafurit bootloader releases](https://github.com/adafruit/Adafruit_nRF52_Bootloader/releases)
The minimum version required is 0.8.0.

Put the board in bootloader mode by double pressing the reset button.
Check the serial port for the board and modify the command below accordingly.

```
adafruit-nrfutil dfu serial -p COM8 -pkg xiao_nrf52840_ble_sense_bootloader-0.8.0_s140_7.3.0.zip
```

### Upgrade firmware using adafruit-nrfutil

Put the board in bootloader mode by double pressing the reset button.
Check the serial port for the board and modify the command below accordingly.

```
adafruit-nrfutil dfu genpkg --dev-type 0x0052 --dev-revision 0xCE68 --application zephyr.hex zephyr.zip
adafruit-nrfutil dfu serial -p COM8 -pkg zephyr.zip
```

You can also use the Nordic nRF Connect app to upgrade the bootloader and firmware. Make sure
to change the PRN option from the default of 12 to 8.

### Create firmware UF2 file

You need the uf2conv.py script to convert the hex file to a uf2 file. You can find the script in the Adafruit
bootloader repository. The script is located in the ```lib/uf2/utils``` directory.
Alternatively, you can get the script from the Microsoft UF2 repository.

```bash
git clone https://github.com/adafruit/Adafruit_nRF52_Bootloader
cd Adafruit_nRF52_Bootloader
git submodule update --init
cd lib\uf2\utils
```

To create UF2 file with the application hex file, run the following command:

```bash
python c:\src\Adafruit_nRF52_Bootloader\lib\uf2\utils\uf2conv.py --convert --family 0xADA52840 --output friend-1.0.2.uf2 firmware_v1.0\build\zephyr\zephyr.hex
```

### Upgrade bootloader using UF2 file

Download a compatible version of the ```update-xiao_nrf52840_ble_sense_bootloader-``` bootloader
from [Adafurit bootloader releases](https://github.com/adafruit/Adafruit_nRF52_Bootloader/releases)
The latest tested version is 0.9.0. Newer versions should work as well.

Put the board in bootloader mode by double pressing the reset button. The board should appear as a USB drive.

Copy the bootloader update file in the root directory of the board. The board will automatically update the bootloader and reset back to application mode.
To check the bootloader was updated, put the board in bootloader mode again and check the INFO_UF2.TXT file for the new bootloader version.
