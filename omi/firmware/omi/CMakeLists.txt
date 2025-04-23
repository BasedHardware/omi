cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
enable_language(C ASM) # OPUS

project(omi)

file(GLOB app_sources src/main.c src/mic.c src/battery.c src/led.c)
file(GLOB dk2_sources src/lib/dk2/codec.c src/lib/dk2/config.h src/lib/dk2/transport.c)
target_sources(app PRIVATE ${dk2_sources} ${app_sources})

if(CONFIG_OMI_CODEC_OPUS)
    add_subdirectory(src/lib/dk2/lib/opus-1.2.1/)
    target_link_libraries(app PRIVATE opus_codec)
endif()
