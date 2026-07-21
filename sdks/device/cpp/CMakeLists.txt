cmake_minimum_required(VERSION 3.16)
project(omi_device VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

option(OMI_DEVICE_BLE "Build optional SimpleBLE client (scan/listen)" OFF)

set(OMI_DEVICE_SOURCES src/protocol.cpp)

if(OMI_DEVICE_BLE)
  set(OMI_DEVICE_BLE_LINKED OFF)

  find_package(simpleble CONFIG QUIET)
  if(simpleble_FOUND)
    set(OMI_DEVICE_BLE_LINKED ON)
    message(STATUS "OMI_DEVICE_BLE: using installed simpleble")
  else()
    set(_omi_simpleble_src "${CMAKE_BINARY_DIR}/_deps/simpleble-src")
    set(_omi_simpleble_cmake "${_omi_simpleble_src}/simpleble/CMakeLists.txt")
    if(NOT EXISTS "${_omi_simpleble_cmake}")
      find_package(Git QUIET)
      if(NOT Git_FOUND)
        message(WARNING
          "OMI_DEVICE_BLE=ON but simpleble not found and Git is missing.\n"
          "Install SimpleBLE (find_package simpleble) or install Git to FetchContent.\n"
          "Shipping sources at src/ble.cpp; building without BLE client.")
      else()
        message(STATUS "OMI_DEVICE_BLE: fetching SimpleBLE (v0.10.3)...")
        execute_process(
          COMMAND "${GIT_EXECUTABLE}" clone --depth 1 --branch v0.10.3
                  https://github.com/simpleble/simpleble.git "${_omi_simpleble_src}"
          RESULT_VARIABLE _omi_sb_rc
          ERROR_VARIABLE _omi_sb_err
          OUTPUT_VARIABLE _omi_sb_out
        )
        if(NOT _omi_sb_rc EQUAL 0)
          message(WARNING
            "OMI_DEVICE_BLE=ON but failed to fetch SimpleBLE:\n${_omi_sb_err}${_omi_sb_out}\n"
            "Install SimpleBLE system-wide or re-run with network access.\n"
            "Shipping sources at src/ble.cpp; building without BLE client.")
        endif()
      endif()
    endif()

    if(EXISTS "${_omi_simpleble_cmake}")
      set(SIMPLEBLE_INSTALL OFF CACHE BOOL "" FORCE)
      add_subdirectory("${_omi_simpleble_src}/simpleble" "${CMAKE_BINARY_DIR}/_deps/simpleble-build")
      set(OMI_DEVICE_BLE_LINKED ON)
      message(STATUS "OMI_DEVICE_BLE: using fetched SimpleBLE from ${_omi_simpleble_src}")
    endif()
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
