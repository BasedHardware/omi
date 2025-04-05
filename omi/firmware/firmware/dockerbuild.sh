#!/bin/bash

set -e

docker run --rm \
    -v .:/workdir \
    ghcr.io/zephyrproject-rtos/zephyr-build:v0.26-branch \
    bash -c " \
        if [ ! -d .west ]; then \
            west init; \
            west update; \
        fi && \
        west build \
            --build-dir ./build/docker \
            . \
            --pristine \
            --board xiao_ble/nrf52840/sense \
            -- \
            -DNCS_TOOLCHAIN_VERSION=NONE \
            -DDTC_OVERLAY_FILE=./overlay/xiao_ble_sense_devkitv2-adafruit.overlay \
            -DCMAKE_EXPORT_COMPILE_COMMANDS=YES \
            -DCMAKE_BUILD_TYPE=Debug \
            -DCONF_FILE=./prj_xiao_ble_sense_devkitv2-adafruit.conf
    "

cp build/docker/zephyr/zephyr.uf2 build/firmware.uf2

echo -e "\033[32mBuild complete: build/firmware.uf2\033[0m"
