cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(omi_bsim)

set(OMI_SOURCE_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../omi/src)

target_sources(app PRIVATE
    src/main.c
    src/stubs.c
    ${OMI_SOURCE_DIR}/settings.c
    ${OMI_SOURCE_DIR}/lib/core/button_service.c
    ${OMI_SOURCE_DIR}/lib/core/transport.c
)

target_include_directories(app PRIVATE
    ${OMI_SOURCE_DIR}
    ${OMI_SOURCE_DIR}/lib/core
)
