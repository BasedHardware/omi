# omi_native_core_jni — binds the repo's native-core C++ middleware into the
# Android host through JNI. Nothing here re-implements policy: every entry
# point is a thin marshalling shim onto the shared C ABI.
#
# Path note: this CMakeLists.txt lives at
#   <repo>/app/Platforms/android/app/src/main/cpp/
# so the repo root (and native-core/) is six directories up.
cmake_minimum_required(VERSION 3.22.1)
project(omi_native_core_jni LANGUAGES C CXX)

set(OMI_NATIVE_CORE_DIR ../../../../../../native-core)

set(OMI_NATIVE_SOURCES
    ${OMI_NATIVE_CORE_DIR}/src/omi_native_boundary.cpp
    ${OMI_NATIVE_CORE_DIR}/src/omi_backend_policy.cpp
    ${OMI_NATIVE_CORE_DIR}/src/omi_backend_http.cpp
    ${OMI_NATIVE_CORE_DIR}/src/omi_backend_recording.cpp
)

add_library(omi_native_core_jni SHARED
    omi_jni.c
    ${OMI_NATIVE_SOURCES}
)

target_include_directories(omi_native_core_jni PRIVATE
    ${OMI_NATIVE_CORE_DIR}/include
)

target_compile_features(omi_native_core_jni PUBLIC cxx_std_20)
