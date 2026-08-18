# The portable half of the Context for Claude data plane.
#
# Configures and builds identically on macOS and Windows, with no dependency to resolve — see
# README.md for why the seam is where it is. On macOS the same sources are additionally compiled by
# SwiftPM as the `ContextCoreCxx` target, so this file is the Windows build and the second opinion
# rather than the only build.

cmake_minimum_required(VERSION 3.20)

project(context_core LANGUAGES CXX VERSION 1.0.0)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_library(context_core STATIC
    src/audio_policy.cpp
    src/moment_grouping.cpp
    src/recall_ranking.cpp
    src/session_policy.cpp
)

target_include_directories(context_core PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
)

# Position-independent so a host that wants the rules inside a shared library or a Swift module can
# link this one without rebuilding it differently.
set_target_properties(context_core PROPERTIES POSITION_INDEPENDENT_CODE ON)

if(MSVC)
    target_compile_options(context_core PRIVATE /W4 /WX /permissive-)
    # The ABI is C, and MSVC otherwise warns about the C++ standard library being used behind it.
    target_compile_definitions(context_core PRIVATE _CRT_SECURE_NO_WARNINGS)
else()
    target_compile_options(context_core PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()

add_library(ContextForClaude::core ALIAS context_core)

# Tests are opt-out rather than top-level-only: the Windows project pulls this directory in as a
# subdirectory and must still be able to run them, because it is the build where a regression would
# otherwise go unnoticed.
option(CONTEXT_CORE_BUILD_TESTS "Build the context_core unit tests" ON)

if(CONTEXT_CORE_BUILD_TESTS)
    include(CTest)
    enable_testing()

    add_executable(context_core_tests tests/context_core_tests.cpp)
    target_link_libraries(context_core_tests PRIVATE context_core)

    if(MSVC)
        target_compile_options(context_core_tests PRIVATE /W4 /WX /permissive-)
    else()
        target_compile_options(context_core_tests PRIVATE -Wall -Wextra -Wpedantic -Werror)
    endif()

    add_test(NAME context_core_tests COMMAND context_core_tests)
endif()
