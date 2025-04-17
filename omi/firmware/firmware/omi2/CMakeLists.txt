cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})

project(omi2)

file(GLOB app_sources src/*.c)
file(GLOB evt_sources src/lib/evt/*.c) # todo: remove evt_sources
list(FILTER evt_sources EXCLUDE REGEX ".*main\\.c$")
target_sources(app PRIVATE ${evt_sources} ${app_sources})
