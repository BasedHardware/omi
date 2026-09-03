cmake_minimum_required(VERSION 3.16)
project(omi_device VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

option(OMI_DEVICE_BUILD_TESTS "Build omi_device tests" OFF)

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
