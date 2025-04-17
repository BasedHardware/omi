cmake_minimum_required(VERSION 3.20.0)

# Set Kconfig configuration file
set(KCONFIG_ROOT ${CMAKE_CURRENT_SOURCE_DIR}/Kconfig)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})

project(omi2)

file(GLOB app_sources src/*.c)
file(GLOB evt_sources src/lib/evt/*.c) # todo: remove evt_sources
file(GLOB dk2_sources src/lib/dk2/mic.c src/lib/dk2/codec.c src/lib/dk2/utils.h)
list(FILTER evt_sources EXCLUDE REGEX ".*main\\.c$")
target_sources(app PRIVATE ${evt_sources} ${dk2_sources} ${app_sources})

# Conditionally include Opus codec if enabled
if(CONFIG_OMI2_CODEC_OPUS)
  target_include_directories(app PRIVATE src/lib/opus-1.2.1)
  file(GLOB opus_sources src/lib/opus-1.2.1/*.c)
  target_sources(app PRIVATE ${opus_sources})
endif()

# Conditionally include accelerometer support if enabled
if(CONFIG_OMI2_ENABLE_ACCELEROMETER)
  target_compile_definitions(app PRIVATE -DCONFIG_OMI2_ENABLE_ACCELEROMETER)
endif()

# Conditionally include button support if enabled
if(CONFIG_OMI2_ENABLE_BUTTON)
  target_compile_definitions(app PRIVATE -DCONFIG_OMI2_ENABLE_BUTTON)
endif()

# Conditionally include speaker support if enabled
if(CONFIG_OMI2_ENABLE_SPEAKER)
  target_compile_definitions(app PRIVATE -DCONFIG_OMI2_ENABLE_SPEAKER)
endif()

# Conditionally include battery support if enabled
if(CONFIG_OMI2_ENABLE_BATTERY)
  target_compile_definitions(app PRIVATE -DCONFIG_OMI2_ENABLE_BATTERY)
endif()

# Conditionally include USB support if enabled
if(CONFIG_OMI2_ENABLE_USB)
  target_compile_definitions(app PRIVATE -DCONFIG_OMI2_ENABLE_USB)
endif()

# Conditionally include haptic support if enabled
if(CONFIG_OMI2_ENABLE_HAPTIC)
  target_compile_definitions(app PRIVATE -DCONFIG_OMI2_ENABLE_HAPTIC)
endif()
