cmake_minimum_required(VERSION 3.20.0)
list(APPEND DTS_ROOT ${CMAKE_CURRENT_SOURCE_DIR}/.. ${CMAKE_CURRENT_SOURCE_DIR})
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(omi_startup_sim)
include(../cmake/safe-mode-build.cmake)

if(NOT CONFIG_OMI_NATIVE_SIM)
  message(FATAL_ERROR "This target is only for native_sim")
endif()

# Keep production CMake/config untouched. Compile the actual entrypoint, the
# safe-mode state machine (including its power-on hold sampling and recovery
# loop), the button FSM and the capture-mute/settings code; replace device
# boundaries at link time (stubs.c) and model power/reset/pins (sim_power.c).
target_sources(app PRIVATE
  ../src/main.c
  ../src/safe_mode.c
  ../src/boot_telemetry.c
  ../src/boot_telemetry_logic.c
  ../src/diagnostics_packet.c
  ../src/safe_mode_devices.c
  ../src/settings.c
  ../src/rtc.c
  ../src/feedback.c
  ../src/lib/core/battery_guard.c
  ../src/lib/core/button.c
  ../src/lib/core/capture_mute.c
  ../src/lib/core/custody.c
  ../src/sd_card.c
  sim_power.c
  sim_sd.c
  stubs.c
)
# The raw ring opens the SD disk by its Kconfig volume name; the sim registers
# "SDMMC" itself (sim_sd.c) instead of enabling the SDMMC disk driver.
set_source_files_properties(../src/sd_card.c PROPERTIES COMPILE_DEFINITIONS "CONFIG_SDMMC_VOLUME_NAME=\"SDMMC\"")
# Do not add src/lib/core: its features.h would shadow glibc's <features.h>.
# Core sources include their siblings with quotes, which needs no -I.
# include/ carries the sim reset-register shim (hal/nrf_reset.h).
target_include_directories(app PRIVATE ../src . include)

# Runner side (host libc): reads boot.cfg / retained.bin in the boot's cwd.
target_sources(native_simulator INTERFACE ${CMAKE_CURRENT_SOURCE_DIR}/host/sim_host.c)

# Settings fault injection without touching production code.
zephyr_ld_options(
  -Wl,--wrap=settings_subsys_init
  -Wl,--wrap=settings_load_subtree
  -Wl,--wrap=settings_save_one
  -Wl,--wrap=sd_write_pause
)
