cmake_minimum_required(VERSION 3.22.1)

project(local_yoloe)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(ncnn_DIR ${CMAKE_CURRENT_SOURCE_DIR}/third_party/ncnn-android/${ANDROID_ABI}/lib/cmake/ncnn)
find_package(ncnn REQUIRED)

add_library(local_yoloe SHARED local_yoloe_jni.cpp)

target_link_libraries(local_yoloe ncnn log)