# Optional isolated research app inclusion only. No production CMake references it.
option(CV1_RESEARCH_COMPILE_STORAGE_ADAPTER "Compile nondeployable, disabled adapter" OFF)
if(CV1_RESEARCH_COMPILE_STORAGE_ADAPTER)
  if(NOT CONFIG_TRUSTED_EXECUTION_SECURE OR CONFIG_BOOTLOADER_MCUBOOT OR CONFIG_SIGN_IMAGES)
    message(FATAL_ERROR "Only key-free Secure research configuration is allowed")
  endif()
  target_sources(app PRIVATE storage_adapter.c source_binding.c zephyr_storage.c)
  target_include_directories(app PRIVATE . ../shared)
endif()

# Both research switches remain OFF unless explicitly selected.
add_subdirectory(bus_epoch)
