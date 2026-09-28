// MainWindow declaration skeleton (SOURCE-ONLY, never compiled).
#pragma once
#include "pch.h"
#include "MainWindow.g.h" // C++/WinRT XAML codegen (XAML compiler output)

namespace winrt::OmiHost::implementation {
struct MainWindow : MainWindowT<MainWindow> {
    MainWindow();

    static winrt::hstring const kClassName;
    static double const kWindowInset;      // mirrors OmiWindowInset = 12.0
    static double const kChromeRowHeight;  // mirrors OmiChromeRowHeight = 44.0
};
}

namespace winrt::OmiHost::factory_implementation {
struct MainWindow : MainWindowT<MainWindow, implementation::MainWindow> {};
}
