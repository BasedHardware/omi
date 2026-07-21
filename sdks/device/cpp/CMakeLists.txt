cmake_minimum_required(VERSION 3.16)
project(omi_device VERSION 0.1.0 LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
add_library(omi_device src/protocol.cpp)
target_include_directories(omi_device PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)
install(TARGETS omi_device)
install(DIRECTORY include/ DESTINATION include)
