# SPDX-License-Identifier: Apache-2.0
set(BOARD seeed_xiao_nrf52840_sense)
cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(nrf52840_nordic)
enable_language(C ASM)

target_sources(app PRIVATE
    src/main.c
    src/transport.c
    src/mic.c
    src/led.c
    src/codec.c
    src/lib/battery/battery.c
    src/button.c
    src/speaker.c
    src/sdcard.c
    src/storage.c
    src/usb.c
	# src/nfc.c future release
)

if(CONFIG_OMI_CODEC_OPUS)
    add_subdirectory(src/lib/opus-1.2.1/)
    target_link_libraries(app PRIVATE opus_codec)
endif()
