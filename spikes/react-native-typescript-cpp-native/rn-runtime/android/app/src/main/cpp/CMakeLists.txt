cmake_minimum_required(VERSION 3.22.1)
project(omi_native)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_library(omi_native SHARED
  jni_bridge.cpp
  ../../../../../../cpp/src/omi_native_boundary.cpp
)

target_include_directories(omi_native PRIVATE
  ../../../../../../cpp/include
)

find_library(log-lib log)
target_link_libraries(omi_native ${log-lib})
