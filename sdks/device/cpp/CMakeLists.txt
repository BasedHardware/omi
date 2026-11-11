cmake_minimum_required(VERSION 3.16)
project(omi_device VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

option(OMI_DEVICE_BUILD_TESTS "Build omi_device tests" OFF)

# The SimpleBLE-backed BLE client was removed (BUSL-1.1). A consumer that still
# passes the retired flags must fail here, not silently configure and then throw
# BleDisabled at runtime on the first Scan/Listen.
foreach(_omi_retired_ble_var OMI_DEVICE_BLE OMI_DEVICE_SIMPLEBLE_SOURCE_DIR)
  if(DEFINED ${_omi_retired_ble_var})
    message(FATAL_ERROR
      "${_omi_retired_ble_var} was removed along with the SimpleBLE dependency.\n"
      "omi_device now takes the BLE stack from the application: implement "
      "omi::device::BleBackend against CoreBluetooth, Windows.Devices.Bluetooth, "
      "or BlueZ and install it with omi::device::SetBleBackend(). Scan/Listen/"
      "ListenPayload are otherwise unchanged.\n"
      "Migration guide: sdks/device/cpp/README.md")
  endif()
endforeach()

# This package has no third-party dependencies. The BLE surface in
# include/omi/device/ble.hpp is an interface the embedding application binds to
# its own platform stack (CoreBluetooth, WinRT, BlueZ) via SetBleBackend().
add_library(omi_device
  src/protocol.cpp
  src/ble.cpp
)

target_include_directories(omi_device PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)

if(OMI_DEVICE_BUILD_TESTS)
  enable_testing()
  add_executable(omi_device_tests tests/ble_test.cpp)
  target_link_libraries(omi_device_tests PRIVATE omi_device)
  add_test(NAME omi_device_tests COMMAND omi_device_tests)
endif()

install(TARGETS omi_device)
install(DIRECTORY include/ DESTINATION include)
