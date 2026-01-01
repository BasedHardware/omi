cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
enable_language(C ASM) # OPUS

project(omi)

file(GLOB app_sources
    src/main.c
    src/mic.c
    src/battery.c
    src/led.c
    src/haptic.c
    src/sd_card.c
    src/spi_flash.c
    src/settings.c
    src/feedback.c
    src/wdog_facade.c
)
file(GLOB core_sources
    src/lib/core/config.h
    src/lib/core/codec.c
    src/lib/core/transport.c
    src/lib/core/button.c
    src/lib/core/monitor.c
)

if(CONFIG_OMI_ENABLE_OFFLINE_STORAGE)
    list(APPEND core_sources src/lib/core/storage.c)
endif()

if(CONFIG_OMI_ENABLE_WIFI)
    list(APPEND core_sources src/wifi.c)
endif()

target_sources(app PRIVATE ${core_sources} ${app_sources})
target_include_directories(app PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/src
    ${CMAKE_CURRENT_SOURCE_DIR}/src/lib/core
)

if(CONFIG_OMI_CODEC_OPUS)
    add_subdirectory(src/lib/core/lib/opus-1.2.1/)
    target_link_libraries(app PRIVATE opus_codec)
endif()
