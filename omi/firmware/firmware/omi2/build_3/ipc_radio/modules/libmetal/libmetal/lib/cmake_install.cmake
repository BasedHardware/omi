# Install script for directory: /opt/nordic/ncs/v2.9.0/modules/hal/libmetal/libmetal/lib

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

if("x${CMAKE_INSTALL_COMPONENT}x" STREQUAL "xUnspecifiedx" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include" TYPE FILE RENAME "metal/alloc.h" FILES "/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_3/ipc_radio/modules/libmetal/libmetal/lib/include/metal/alloc.h")
endif()

if("x${CMAKE_INSTALL_COMPONENT}x" STREQUAL "xUnspecifiedx" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include" TYPE FILE RENAME "metal/assert.h" FILES "/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_3/ipc_radio/modules/libmetal/libmetal/lib/include/metal/assert.h")
endif()

if("x${CMAKE_INSTALL_COMPONENT}x" STREQUAL "xUnspecifiedx" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include" TYPE FILE RENAME "metal/atomic.h" FILES "/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_3/ipc_radio/modules/libmetal/libmetal/lib/include/metal/atomic.h")
endif()

if("x${CMAKE_INSTALL_COMPONENT}x" STREQUAL "xUnspecifiedx" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include" TYPE FILE RENAME "metal/cache.h" FILES "/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_3/ipc_radio/modules/libmetal/libmetal/lib/include/metal/cache.h")
endif()

if("x${CMAKE_INSTALL_COMPONENT}x" STREQUAL "xUnspecifiedx" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include" TYPE FILE RENAME "metal/compiler.h" FILES "/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_3/ipc_radio/modules/libmetal/libmetal/lib/include/metal/compiler.h")
endif()

if("x${CMAKE_INSTALL_COMPONENT}x" STREQUAL "xUnspecifiedx" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include" TYPE FILE RENAME "metal/condition.h" FILES "/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_3/ipc_radio/modules/libmetal/libmetal/lib/include/metal/condition.h")
endif()

if("x${CMAKE_INSTALL_COMPONENT}x" STREQUAL "xUnspecifiedx" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include" TYPE FILE RENAME "metal/config.h" FILES "/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_3/ipc_radio/modules/libmetal/libmetal/lib/include/metal/config.h")
endif()

if("x${CMAKE_INSTALL_COMPONENT}x" STREQUAL "xUnspecifiedx" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include" TYPE FILE RENAME "metal/cpu.h" FILES "/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_3/ipc_radio/modules/libmetal/libmetal/lib/include/metal/cpu.h")
endif()

if("x${CMAKE_INSTALL_COMPONENT}x" STREQUAL "xUnspecifiedx" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include" TYPE FILE RENAME "metal/device.h" FILES "/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_3/ipc_radio/modules/libmetal/libmetal/lib/include/metal/device.h")
endif()

if("x${CMAKE_INSTALL_COMPONENT}x" STREQUAL "xUnspecifiedx" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include" TYPE FILE RENAME "metal/errno.h" FILES "/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_3/ipc_radio/modules/libmetal/libmetal/lib/include/metal/errno.h")
endif()

if("x${CMAKE_INSTALL_COMPONENT}x" STREQUAL "xUnspecifiedx" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include" TYPE FILE RENAME "metal/dma.h" FILES "/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_3/ipc_radio/modules/libmetal/libmetal/lib/include/metal/dma.h")
endif()

if("x${CMAKE_INSTALL_COMPONENT}x" STREQUAL "xUnspecifiedx" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include" TYPE FILE RENAME "metal/io.h" FILES "/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_3/ipc_radio/modules/libmetal/libmetal/lib/include/metal/io.h")
endif()

if("x${CMAKE_INSTALL_COMPONENT}x" STREQUAL "xUnspecifiedx" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include" TYPE FILE RENAME "metal/irq.h" FILES "/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_3/ipc_radio/modules/libmetal/libmetal/lib/include/metal/irq.h")
endif()

if("x${CMAKE_INSTALL_COMPONENT}x" STREQUAL "xUnspecifiedx" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include" TYPE FILE RENAME "metal/irq_controller.h" FILES "/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_3/ipc_radio/modules/libmetal/libmetal/lib/include/metal/irq_controller.h")
endif()

if("x${CMAKE_INSTALL_COMPONENT}x" STREQUAL "xUnspecifiedx" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include" TYPE FILE RENAME "metal/list.h" FILES "/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_3/ipc_radio/modules/libmetal/libmetal/lib/include/metal/list.h")
endif()

if("x${CMAKE_INSTALL_COMPONENT}x" STREQUAL "xUnspecifiedx" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include" TYPE FILE RENAME "metal/log.h" FILES "/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_3/ipc_radio/modules/libmetal/libmetal/lib/include/metal/log.h")
endif()

if("x${CMAKE_INSTALL_COMPONENT}x" STREQUAL "xUnspecifiedx" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include" TYPE FILE RENAME "metal/mutex.h" FILES "/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_3/ipc_radio/modules/libmetal/libmetal/lib/include/metal/mutex.h")
endif()

if("x${CMAKE_INSTALL_COMPONENT}x" STREQUAL "xUnspecifiedx" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include" TYPE FILE RENAME "metal/shmem.h" FILES "/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_3/ipc_radio/modules/libmetal/libmetal/lib/include/metal/shmem.h")
endif()

if("x${CMAKE_INSTALL_COMPONENT}x" STREQUAL "xUnspecifiedx" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include" TYPE FILE RENAME "metal/sleep.h" FILES "/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_3/ipc_radio/modules/libmetal/libmetal/lib/include/metal/sleep.h")
endif()

if("x${CMAKE_INSTALL_COMPONENT}x" STREQUAL "xUnspecifiedx" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include" TYPE FILE RENAME "metal/softirq.h" FILES "/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_3/ipc_radio/modules/libmetal/libmetal/lib/include/metal/softirq.h")
endif()

if("x${CMAKE_INSTALL_COMPONENT}x" STREQUAL "xUnspecifiedx" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include" TYPE FILE RENAME "metal/spinlock.h" FILES "/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_3/ipc_radio/modules/libmetal/libmetal/lib/include/metal/spinlock.h")
endif()

if("x${CMAKE_INSTALL_COMPONENT}x" STREQUAL "xUnspecifiedx" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include" TYPE FILE RENAME "metal/sys.h" FILES "/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_3/ipc_radio/modules/libmetal/libmetal/lib/include/metal/sys.h")
endif()

if("x${CMAKE_INSTALL_COMPONENT}x" STREQUAL "xUnspecifiedx" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include" TYPE FILE RENAME "metal/time.h" FILES "/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_3/ipc_radio/modules/libmetal/libmetal/lib/include/metal/time.h")
endif()

if("x${CMAKE_INSTALL_COMPONENT}x" STREQUAL "xUnspecifiedx" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include" TYPE FILE RENAME "metal/utilities.h" FILES "/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_3/ipc_radio/modules/libmetal/libmetal/lib/include/metal/utilities.h")
endif()

if("x${CMAKE_INSTALL_COMPONENT}x" STREQUAL "xUnspecifiedx" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include" TYPE FILE RENAME "metal/version.h" FILES "/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_3/ipc_radio/modules/libmetal/libmetal/lib/include/metal/version.h")
endif()

if("x${CMAKE_INSTALL_COMPONENT}x" STREQUAL "xUnspecifiedx" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include" TYPE FILE RENAME "metal/compiler/armcc/errno.h" FILES "/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_3/ipc_radio/modules/libmetal/libmetal/lib/include/metal/compiler/armcc/errno.h")
endif()

if("x${CMAKE_INSTALL_COMPONENT}x" STREQUAL "xUnspecifiedx" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include" TYPE FILE RENAME "metal/compiler/gcc/atomic.h" FILES "/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_3/ipc_radio/modules/libmetal/libmetal/lib/include/metal/compiler/gcc/atomic.h")
endif()

if("x${CMAKE_INSTALL_COMPONENT}x" STREQUAL "xUnspecifiedx" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include" TYPE FILE RENAME "metal/compiler/gcc/compiler.h" FILES "/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_3/ipc_radio/modules/libmetal/libmetal/lib/include/metal/compiler/gcc/compiler.h")
endif()

if("x${CMAKE_INSTALL_COMPONENT}x" STREQUAL "xUnspecifiedx" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include" TYPE FILE RENAME "metal/compiler/iar/compiler.h" FILES "/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_3/ipc_radio/modules/libmetal/libmetal/lib/include/metal/compiler/iar/compiler.h")
endif()

if("x${CMAKE_INSTALL_COMPONENT}x" STREQUAL "xUnspecifiedx" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include" TYPE FILE RENAME "metal/compiler/iar/errno.h" FILES "/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_3/ipc_radio/modules/libmetal/libmetal/lib/include/metal/compiler/iar/errno.h")
endif()

if("x${CMAKE_INSTALL_COMPONENT}x" STREQUAL "xUnspecifiedx" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include" TYPE FILE RENAME "metal/processor/generic/cpu.h" FILES "/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_3/ipc_radio/modules/libmetal/libmetal/lib/include/metal/processor/generic/cpu.h")
endif()

if("x${CMAKE_INSTALL_COMPONENT}x" STREQUAL "xUnspecifiedx" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include" TYPE FILE RENAME "metal/processor/generic/atomic.h" FILES "/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_3/ipc_radio/modules/libmetal/libmetal/lib/include/metal/processor/generic/atomic.h")
endif()

if("x${CMAKE_INSTALL_COMPONENT}x" STREQUAL "xUnspecifiedx" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include" TYPE FILE RENAME "metal/system/zephyr/alloc.h" FILES "/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_3/ipc_radio/modules/libmetal/libmetal/lib/include/metal/system/zephyr/alloc.h")
endif()

if("x${CMAKE_INSTALL_COMPONENT}x" STREQUAL "xUnspecifiedx" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include" TYPE FILE RENAME "metal/system/zephyr/assert.h" FILES "/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_3/ipc_radio/modules/libmetal/libmetal/lib/include/metal/system/zephyr/assert.h")
endif()

if("x${CMAKE_INSTALL_COMPONENT}x" STREQUAL "xUnspecifiedx" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include" TYPE FILE RENAME "metal/system/zephyr/cache.h" FILES "/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_3/ipc_radio/modules/libmetal/libmetal/lib/include/metal/system/zephyr/cache.h")
endif()

if("x${CMAKE_INSTALL_COMPONENT}x" STREQUAL "xUnspecifiedx" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include" TYPE FILE RENAME "metal/system/zephyr/condition.h" FILES "/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_3/ipc_radio/modules/libmetal/libmetal/lib/include/metal/system/zephyr/condition.h")
endif()

if("x${CMAKE_INSTALL_COMPONENT}x" STREQUAL "xUnspecifiedx" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include" TYPE FILE RENAME "metal/system/zephyr/io.h" FILES "/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_3/ipc_radio/modules/libmetal/libmetal/lib/include/metal/system/zephyr/io.h")
endif()

if("x${CMAKE_INSTALL_COMPONENT}x" STREQUAL "xUnspecifiedx" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include" TYPE FILE RENAME "metal/system/zephyr/irq.h" FILES "/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_3/ipc_radio/modules/libmetal/libmetal/lib/include/metal/system/zephyr/irq.h")
endif()

if("x${CMAKE_INSTALL_COMPONENT}x" STREQUAL "xUnspecifiedx" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include" TYPE FILE RENAME "metal/system/zephyr/log.h" FILES "/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_3/ipc_radio/modules/libmetal/libmetal/lib/include/metal/system/zephyr/log.h")
endif()

if("x${CMAKE_INSTALL_COMPONENT}x" STREQUAL "xUnspecifiedx" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include" TYPE FILE RENAME "metal/system/zephyr/mutex.h" FILES "/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_3/ipc_radio/modules/libmetal/libmetal/lib/include/metal/system/zephyr/mutex.h")
endif()

if("x${CMAKE_INSTALL_COMPONENT}x" STREQUAL "xUnspecifiedx" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include" TYPE FILE RENAME "metal/system/zephyr/sleep.h" FILES "/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_3/ipc_radio/modules/libmetal/libmetal/lib/include/metal/system/zephyr/sleep.h")
endif()

if("x${CMAKE_INSTALL_COMPONENT}x" STREQUAL "xUnspecifiedx" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include" TYPE FILE RENAME "metal/system/zephyr/sys.h" FILES "/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_3/ipc_radio/modules/libmetal/libmetal/lib/include/metal/system/zephyr/sys.h")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for each subdirectory.
  include("/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_3/ipc_radio/modules/libmetal/libmetal/lib/compiler/cmake_install.cmake")
  include("/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_3/ipc_radio/modules/libmetal/libmetal/lib/processor/cmake_install.cmake")
  include("/Users/nik/projects/omi/omi/firmware/firmware/omi2/build_3/ipc_radio/modules/libmetal/libmetal/lib/system/cmake_install.cmake")

endif()

