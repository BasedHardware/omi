cmake_minimum_required(VERSION 3.22.1)
project(appmodules)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_library(omi_native SHARED
  omi/jni_bridge.cpp
  ../../../../../../native-core/src/omi_native_boundary.cpp
  ../../../../../../native-core/src/omi_backend_policy.cpp
  ../../../../../../native-core/src/omi_backend_http.cpp
  ../../../../../../native-core/src/omi_backend_recording.cpp
)

target_include_directories(omi_native PRIVATE
  ../../../../../../native-core/include
)

find_library(log-lib log)
target_link_libraries(omi_native ${log-lib})

include(${REACT_ANDROID_DIR}/cmake-utils/ReactNative-application.cmake)
