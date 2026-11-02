# Opt-in isolated key-free research compilation only; no production references.
option(CV1_RESEARCH_COMPILE_BUS_EPOCH "Compile disabled shared-bus/epoch research" OFF)
if(CV1_RESEARCH_COMPILE_BUS_EPOCH)
  if(NOT CONFIG_TRUSTED_EXECUTION_SECURE OR CONFIG_BOOTLOADER_MCUBOOT OR CONFIG_SIGN_IMAGES)
    message(FATAL_ERROR "Only key-free Secure research is permitted")
  endif()
  target_sources(app PRIVATE secure_bus.c boot_epoch.c zephyr_bus.c)
  target_include_directories(app PRIVATE . .. ../../shared)
endif()
