cmake_minimum_required(VERSION 3.24)

if(NOT WIN32)
    message(FATAL_ERROR
        "Context for Claude's Windows host can only be configured on Windows. "
        "Build the portable core on this host instead: cmake -S ../core -B <build-dir>")
endif()

project(context_for_claude_windows LANGUAGES CXX)

if(NOT MSVC)
    message(FATAL_ERROR
        "Context for Claude's Windows host requires MSVC. Open a Visual Studio Developer PowerShell "
        "with the Desktop development with C++ workload installed, then rerun CMake.")
endif()

find_program(CONTEXT_FOR_CLAUDE_SWIFTC_EXECUTABLE NAMES swiftc)
if(NOT CONTEXT_FOR_CLAUDE_SWIFTC_EXECUTABLE)
    message(FATAL_ERROR
        "Context for Claude's Windows host requires a Swift toolchain with swiftc on PATH. "
        "Install the Windows toolchain recommended by swift-winrt, then rerun CMake.")
endif()

execute_process(
    COMMAND "${CONTEXT_FOR_CLAUDE_SWIFTC_EXECUTABLE}" --version
    RESULT_VARIABLE CONTEXT_FOR_CLAUDE_SWIFTC_RESULT
)
if(NOT CONTEXT_FOR_CLAUDE_SWIFTC_RESULT EQUAL 0)
    message(FATAL_ERROR
        "swiftc was found but could not run. Repair the Windows Swift toolchain, then rerun CMake.")
endif()

include(CheckIncludeFileCXX)
check_include_file_cxx(windows.h CONTEXT_FOR_CLAUDE_HAS_WINDOWS_SDK)
if(NOT CONTEXT_FOR_CLAUDE_HAS_WINDOWS_SDK)
    message(FATAL_ERROR
        "The Windows SDK headers are unavailable. Install a Windows SDK, including its C++ headers, "
        "through the Visual Studio Installer, then rerun CMake from a Developer PowerShell.")
endif()

include(CTest)

add_subdirectory("${CMAKE_CURRENT_LIST_DIR}/../core" "${CMAKE_CURRENT_BINARY_DIR}/core")

include(FetchContent)
FetchContent_Declare(
    swift_winrt
    GIT_REPOSITORY https://github.com/thebrowsercompany/swift-winrt.git
    GIT_TAG 79ffa65c
    GIT_SUBMODULES_RECURSE TRUE
    SOURCE_SUBDIR swiftwinrt
)
FetchContent_MakeAvailable(swift_winrt)

add_executable(context_for_claude_windows_core_smoke src/core_smoke.cpp)
target_link_libraries(context_for_claude_windows_core_smoke PRIVATE ContextForClaude::core)
target_compile_features(context_for_claude_windows_core_smoke PRIVATE cxx_std_17)
target_compile_options(context_for_claude_windows_core_smoke PRIVATE /W4 /WX /permissive-)
add_dependencies(context_for_claude_windows_core_smoke swiftwinrt)

add_test(NAME context_for_claude_windows_core_smoke COMMAND context_for_claude_windows_core_smoke)
