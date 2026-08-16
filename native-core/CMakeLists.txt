cmake_minimum_required(VERSION 3.20)
project(omi_native_core LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_library(omi_native_boundary STATIC src/omi_native_boundary.cpp)
target_include_directories(omi_native_boundary PUBLIC include)

enable_testing()
add_executable(test_omi_native_boundary tests/test_omi_native_boundary.cpp)
target_link_libraries(test_omi_native_boundary PRIVATE omi_native_boundary)
add_test(NAME NativeBoundaryHostTest COMMAND test_omi_native_boundary)
