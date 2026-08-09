cmake_minimum_required(VERSION 3.22.1)
project(omi_lynx_native)

get_filename_component(OMI_CPP_DIR "${CMAKE_CURRENT_LIST_DIR}/../../../../../../../../../cpp" ABSOLUTE)

add_library(omi_lynx_native SHARED omi_lynx_jni.cpp ${OMI_CPP_DIR}/src/omi_native_boundary.cpp)
target_include_directories(omi_lynx_native PRIVATE ${OMI_CPP_DIR}/include)
target_compile_features(omi_lynx_native PRIVATE cxx_std_17)
