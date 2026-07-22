cmake_minimum_required(VERSION 3.16)
project(omi_device VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

option(OMI_DEVICE_BLE "Build optional SimpleBLE client (scan/listen)" OFF)
set(OMI_DEVICE_SIMPLEBLE_SOURCE_DIR "" CACHE PATH
  "Path to a vendored SimpleBLE source tree (overrides the pinned FetchContent download)")

set(OMI_DEVICE_SOURCES src/protocol.cpp)

if(OMI_DEVICE_BLE)
  set(OMI_DEVICE_BLE_LINKED OFF)

  find_package(simpleble CONFIG QUIET)
  if(simpleble_FOUND)
    set(OMI_DEVICE_BLE_LINKED ON)
    message(STATUS "OMI_DEVICE_BLE: using installed simpleble")
  else()
    # Explicit vendored or pinned FetchContent path for SimpleBLE.
    if(OMI_DEVICE_SIMPLEBLE_SOURCE_DIR)
      set(_omi_simpleble_src "${OMI_DEVICE_SIMPLEBLE_SOURCE_DIR}")
      message(STATUS "OMI_DEVICE_BLE: using vendored SimpleBLE at ${_omi_simpleble_src}")
    else()
      include(FetchContent)
      FetchContent_Declare(
        simpleble
        GIT_REPOSITORY https://github.com/simpleble/simpleble.git
        GIT_TAG        v0.10.3
        GIT_SHALLOW    TRUE
        GIT_PROGRESS   TRUE
      )
      FetchContent_MakeAvailable(simpleble)
      set(_omi_simpleble_src "${simpleble_SOURCE_DIR}")
      message(STATUS "OMI_DEVICE_BLE: using fetched SimpleBLE v0.10.3 from ${_omi_simpleble_src}")
    endif()

    set(_omi_simpleble_cmake "${_omi_simpleble_src}/simpleble/CMakeLists.txt")
    if(NOT EXISTS "${_omi_simpleble_cmake}")
      message(FATAL_ERROR
        "OMI_DEVICE_BLE=ON but SimpleBLE was not found.\n"
        "Install simpleble (find_package simpleble), set "
        "-DOMI_DEVICE_SIMPLEBLE_SOURCE_DIR=<path>, or ensure network access for the "
        "pinned FetchContent download from https://github.com/simpleble/simpleble.git (v0.10.3).")
    endif()

    set(SIMPLEBLE_INSTALL OFF CACHE BOOL "" FORCE)
    add_subdirectory("${_omi_simpleble_src}/simpleble" "${CMAKE_BINARY_DIR}/_deps/simpleble-build")
    set(OMI_DEVICE_BLE_LINKED ON)
  endif()

  if(OMI_DEVICE_BLE_LINKED)
    list(APPEND OMI_DEVICE_SOURCES src/ble.cpp)
  endif()
endif()

add_library(omi_device ${OMI_DEVICE_SOURCES})
target_include_directories(omi_device PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)

if(OMI_DEVICE_BLE AND OMI_DEVICE_BLE_LINKED)
  target_link_libraries(omi_device PUBLIC simpleble::simpleble)
  target_compile_definitions(omi_device PUBLIC OMI_DEVICE_BLE=1)
endif()

install(TARGETS omi_device)
install(DIRECTORY include/ DESTINATION include)
