cd ./build/build_xiao_ble_sense_devkitv2-adafruit
set -e
west build
cp ./zephyr/zephyr.uf2 /Volumes/XIAO-SENSE/