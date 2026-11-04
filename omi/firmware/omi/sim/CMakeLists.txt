cmake_minimum_required(VERSION 3.20.0)
list(APPEND DTS_ROOT ${CMAKE_CURRENT_SOURCE_DIR}/..)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(omi_startup_sim)
include(../cmake/safe-mode-build.cmake)

if(NOT CONFIG_OMI_NATIVE_SIM)
  message(FATAL_ERROR "This target is only for native_sim")
endif()

# Keep production CMake/config untouched. Compile the actual entrypoint and
# portable settings/time/feedback code; replace device boundaries at link time.
target_sources(app PRIVATE
  ../src/main.c
  ../src/safe_mode.c
  ../src/safe_mode_devices.c
  ../src/settings.c
  ../src/rtc.c
  ../src/feedback.c
  stubs.c
)
# Do not add src/lib/core: its features.h would shadow glibc's <features.h>.
target_include_directories(app PRIVATE ../src .)
