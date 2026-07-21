cmake_minimum_required(VERSION 3.16)
project(omi_integration VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(CURL REQUIRED)

add_library(omi_integration
  src/client.cpp
)
target_include_directories(omi_integration
  PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
)
target_link_libraries(omi_integration PUBLIC CURL::libcurl)

install(TARGETS omi_integration)
install(DIRECTORY include/ DESTINATION include)
