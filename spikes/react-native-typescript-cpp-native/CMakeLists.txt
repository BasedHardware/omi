cmake_minimum_required(VERSION 3.14)
project(omi_native_boundary CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_library(omi_native_boundary STATIC
    cpp/src/omi_native_boundary.cpp
)

target_include_directories(omi_native_boundary PUBLIC cpp/include)

enable_testing()

add_executable(test_omi_native_boundary cpp/tests/test_omi_native_boundary.cpp)
target_link_libraries(test_omi_native_boundary PRIVATE omi_native_boundary)

add_test(NAME NativeBoundaryHostTest COMMAND test_omi_native_boundary)
