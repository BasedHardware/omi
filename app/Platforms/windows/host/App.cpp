// WinUI 3 host skeleton (C++/WinRT). SOURCE-ONLY: never compiled; written
// against Windows App SDK 1.5 conventions. The host is bootstrap only —
// product UI is served by OmiUI (via the Swift bridge once projected).
#include "pch.h"
#include "App.h"
#include "MainWindow.h"

using namespace winrt;
using namespace Microsoft::UI::Xaml;

int __stdcall wWinMain(HINSTANCE, HINSTANCE, PWSTR, int) {
    init_apartment(winrt::apartment_type::single_threaded);

    // Single-window policy: exactly one MainWindow for the process, mirroring
    // the macOS WindowGroup.
    auto window = make<MainWindow>();
    window.Activate();

    Window::Current().Content(window);
    Run();
    return 0;
}
