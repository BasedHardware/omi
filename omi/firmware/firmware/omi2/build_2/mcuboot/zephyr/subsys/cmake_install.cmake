# Install script for directory: /opt/nordic/ncs/v2.9.0/zephyr/subsys

# Set the install prefix
if(NOT DEFINED CMAKE_INSTALL_PREFIX)
  set(CMAKE_INSTALL_PREFIX "/usr/local")
endif()
string(REGEX REPLACE "/$" "" CMAKE_INSTALL_PREFIX "${CMAKE_INSTALL_PREFIX}")

# Set the install configuration name.
if(NOT DEFINED CMAKE_INSTALL_CONFIG_NAME)
  if(BUILD_TYPE)
    string(REGEX REPLACE "^[^A-Za-z0-9_]+" ""
           CMAKE_INSTALL_CONFIG_NAME "${BUILD_TYPE}")
  else()
    set(CMAKE_INSTALL_CONFIG_NAME "MinSizeRel")
  endif()
  message(STATUS "Install configuration: \"${CMAKE_INSTALL_CONFIG_NAME}\"")
endif()

# Set the component getting installed.
if(NOT CMAKE_INSTALL_COMPONENT)
  if(COMPONENT)
    message(STATUS "Install component: \"${COMPONENT}\"")
    set(CMAKE_INSTALL_COMPONENT "${COMPONENT}")
  else()
    set(CMAKE_INSTALL_COMPONENT)
  endif()
endif()

# Is this installation the result of a crosscompile?
if(NOT DEFINED CMAKE_CROSSCOMPILING)
  set(CMAKE_CROSSCOMPILING "TRUE")
endif()

# Set default install directory permissions.
if(NOT DEFINED CMAKE_OBJDUMP)
  set(CMAKE_OBJDUMP "/opt/nordic/ncs/toolchains/f8037e9b83/opt/zephyr-sdk/arm-zephyr-eabi/bin/arm-zephyr-eabi-objdump")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for each subdirectory.
  include("/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_2/mcuboot/zephyr/subsys/canbus/cmake_install.cmake")
  include("/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_2/mcuboot/zephyr/subsys/debug/cmake_install.cmake")
  include("/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_2/mcuboot/zephyr/subsys/fb/cmake_install.cmake")
  include("/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_2/mcuboot/zephyr/subsys/fs/cmake_install.cmake")
  include("/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_2/mcuboot/zephyr/subsys/ipc/cmake_install.cmake")
  include("/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_2/mcuboot/zephyr/subsys/logging/cmake_install.cmake")
  include("/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_2/mcuboot/zephyr/subsys/mem_mgmt/cmake_install.cmake")
  include("/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_2/mcuboot/zephyr/subsys/mgmt/cmake_install.cmake")
  include("/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_2/mcuboot/zephyr/subsys/modbus/cmake_install.cmake")
  include("/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_2/mcuboot/zephyr/subsys/pm/cmake_install.cmake")
  include("/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_2/mcuboot/zephyr/subsys/portability/cmake_install.cmake")
  include("/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_2/mcuboot/zephyr/subsys/random/cmake_install.cmake")
  include("/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_2/mcuboot/zephyr/subsys/rtio/cmake_install.cmake")
  include("/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_2/mcuboot/zephyr/subsys/sd/cmake_install.cmake")
  include("/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_2/mcuboot/zephyr/subsys/stats/cmake_install.cmake")
  include("/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_2/mcuboot/zephyr/subsys/storage/cmake_install.cmake")
  include("/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_2/mcuboot/zephyr/subsys/task_wdt/cmake_install.cmake")
  include("/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_2/mcuboot/zephyr/subsys/testsuite/cmake_install.cmake")
  include("/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_2/mcuboot/zephyr/subsys/tracing/cmake_install.cmake")
  include("/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_2/mcuboot/zephyr/subsys/usb/cmake_install.cmake")

endif()

