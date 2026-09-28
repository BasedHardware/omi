# omi-v5 Windows host — CMake skeleton
#
# SOURCE-ONLY ON THIS MACHINE: CMake here has never been configured (no
# Windows SDK, no swift-winrt). This file documents the intended build.
#
# Path choice (documented in README.md): the WinUI 3 host shell is
# C++/WinRT (the supported first-class WinUI 3 consumer), and the Swift
# sources build as a static library consumed by that shell. The
# pure-Swift "swift-winui" host pattern is too immature to pin.
cmake_minimum_required(VERSION 3.24)
project(omi-v5-windows LANGUAGES CXX Swift)

find_package(WindowsAppSDK CONFIG REQUIRED)
find_package(cppwinrt CONFIG REQUIRED)   # provides the cppwinrt generator target

# 1. Swift platform sources (transport + credential store) as a static lib.
#    The swift-winrt projections (Generated/ — run generate-projections.ps1
#    first on Windows) compile into the same module.
add_library(OmiWindows STATIC
    Sources/WindowsTransport.swift
    # Generated/*.swift (swift-winrt output, gitignored)
)

# 2. WinUI 3 host shell (C++/WinRT): unpackaged app, single window hosting
#    the Swift-provided content through a C ABI bridge.
add_executable(OmiHost WIN32
    host/App.cpp          # WinUI 3 bootstrap, single-window policy
    host/MainWindow.cpp   # Mica/glass title bar, chrome-row inset handling
)

target_link_libraries(OmiHost PRIVATE
    OmiWindows
    Microsoft::WindowsAppSDK
    WindowsAppSDK::Microsoft.UI.Xaml
)
