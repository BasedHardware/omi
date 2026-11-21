# Only the MCUboot image may replace main. Never affect the pendant application.
if(NOT APPLICATION_SOURCE_DIR STREQUAL "${ZEPHYR_MCUBOOT_MODULE_DIR}/boot/zephyr")
  message(FATAL_ERROR "CV1 MCUboot overlay loaded outside the MCUboot image")
endif()
include(${CMAKE_CURRENT_LIST_DIR}/../mcuboot-main.cmake)
