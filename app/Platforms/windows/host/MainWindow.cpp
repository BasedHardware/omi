// WinUI 3 main window skeleton (C++/WinRT). SOURCE-ONLY: never compiled.
//
// Window contract notes (ported from docs/desktop-app.md once this builds):
// the macOS glass contract (OmiWindowInset = 12, OmiChromeRowHeight = 44,
// traffic lights centered on the chrome row) is Apple-specific; the Windows
// counterpart is an inset content grid under a themed title bar
// (TitleBar + ExtendsContentIntoTitleBar), with the app icon and a 44 px
// chrome row so the shared chrome layout lands consistently.
#include "pch.h"
#include "MainWindow.h"

using namespace winrt;
using namespace Microsoft::UI::Xaml;

winrt::hstring const MainWindow::kClassName = L"OmiHost.MainWindow";
double const MainWindow::kWindowInset = 12.0;   // mirrors OmiWindowInset
double const MainWindow::kChromeRowHeight = 44.0; // mirrors OmiChromeRowHeight

MainWindow::MainWindow() {
    Title(L"Omi");
    ExtendsContentIntoTitleBar(true);
    // TODO(Windows build): set the AppWindow presenter size to 900x700 to
    // match the macOS default, and host the bridged OmiUI content.
}
