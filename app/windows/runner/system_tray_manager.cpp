#include "system_tray_manager.h"
#include <iostream>

const wchar_t* TRAY_CLASS_NAME = L"OmiTrayWindowClass";

SystemTrayManager::SystemTrayManager() 
    : parent_hwnd_(nullptr)
    , tray_hwnd_(nullptr)
    , hinstance_(GetModuleHandle(nullptr))
    , is_created_(false)
    , is_active_(false)
    , default_icon_(nullptr)
    , active_icon_(nullptr) {
    ZeroMemory(&tray_data_, sizeof(tray_data_));
}

SystemTrayManager::~SystemTrayManager() {
    Destroy();
}

bool SystemTrayManager::Create(HWND parentHwnd) {
    parent_hwnd_ = parentHwnd;

    // Register window class for tray messages
    WNDCLASSEXW wc = {};
    wc.cbSize = sizeof(WNDCLASSEX);
    wc.lpfnWndProc = TrayWindowProc;
    wc.hInstance = hinstance_;
    wc.lpszClassName = TRAY_CLASS_NAME;

    if (!RegisterClassExW(&wc)) {
        DWORD error = GetLastError();
        if (error != ERROR_CLASS_ALREADY_EXISTS) {
            std::cerr << "Failed to register tray window class. Error: " << error << std::endl;
            return false;
        }
    }

    // Create invisible window for tray messages
    tray_hwnd_ = CreateWindowExW(
        0, TRAY_CLASS_NAME, L"OmiTrayWindow", 0,
        0, 0, 0, 0, HWND_MESSAGE, nullptr, hinstance_, this
    );

    if (!tray_hwnd_) {
        std::cerr << "Failed to create tray window. Error: " << GetLastError() << std::endl;
        return false;
    }

    // Load icons (try to load from resources, fall back to default)
    default_icon_ = LoadIconW(hinstance_, MAKEINTRESOURCEW(101));
    if (!default_icon_) {
        default_icon_ = LoadIconW(nullptr, IDI_APPLICATION);
    }
    
    active_icon_ = LoadIconW(hinstance_, MAKEINTRESOURCEW(102));
    if (!active_icon_) {
        active_icon_ = default_icon_;
    }

    CreateTrayIcon();
    is_created_ = true;
    return true;
}

void SystemTrayManager::CreateTrayIcon() {
    tray_data_.cbSize = sizeof(NOTIFYICONDATAW);
    tray_data_.hWnd = tray_hwnd_;
    tray_data_.uID = TRAY_ICON_ID;
    tray_data_.uFlags = NIF_ICON | NIF_MESSAGE | NIF_TIP;
    tray_data_.uCallbackMessage = WM_TRAY_MESSAGE;
    tray_data_.hIcon = default_icon_;
    wcscpy_s(tray_data_.szTip, L"Omi - Always On AI");

    Shell_NotifyIconW(NIM_ADD, &tray_data_);
}

void SystemTrayManager::Destroy() {
    if (is_created_) {
        Shell_NotifyIconW(NIM_DELETE, &tray_data_);
        is_created_ = false;
    }

    if (tray_hwnd_) {
        DestroyWindow(tray_hwnd_);
        tray_hwnd_ = nullptr;
    }

    // Don't destroy icons if they're system icons
    if (default_icon_ && default_icon_ != LoadIconW(nullptr, IDI_APPLICATION)) {
        DestroyIcon(default_icon_);
    }
    if (active_icon_ && active_icon_ != default_icon_) {
        DestroyIcon(active_icon_);
    }
    
    default_icon_ = nullptr;
    active_icon_ = nullptr;
}

void SystemTrayManager::UpdateStatus(const std::string& status, bool isActive) {
    current_status_ = status;
    is_active_ = isActive;
    
    if (is_created_) {
        UpdateTrayIcon(isActive);
        
        // Update tooltip with status
        std::string tooltip = "Omi - " + status;
        UpdateTooltip(tooltip);
    }
}

void SystemTrayManager::UpdateTooltip(const std::string& tooltip) {
    if (!is_created_) return;

    // Convert to wide string
    int wideLen = MultiByteToWideChar(CP_UTF8, 0, tooltip.c_str(), -1, nullptr, 0);
    if (wideLen > 0 && wideLen <= 128) {  // NIF_TIP limit
        std::wstring wideTooltip(wideLen, 0);
        MultiByteToWideChar(CP_UTF8, 0, tooltip.c_str(), -1, &wideTooltip[0], wideLen);
        
        wcscpy_s(tray_data_.szTip, wideTooltip.c_str());
        Shell_NotifyIconW(NIM_MODIFY, &tray_data_);
    }
}

void SystemTrayManager::UpdateTrayIcon(bool isActive) {
    if (!is_created_) return;

    tray_data_.hIcon = isActive ? active_icon_ : default_icon_;
    Shell_NotifyIconW(NIM_MODIFY, &tray_data_);
}

LRESULT CALLBACK SystemTrayManager::TrayWindowProc(HWND hwnd, UINT uMsg, WPARAM wParam, LPARAM lParam) {
    SystemTrayManager* trayManager = nullptr;

    if (uMsg == WM_NCCREATE) {
        CREATESTRUCT* createStruct = reinterpret_cast<CREATESTRUCT*>(lParam);
        trayManager = reinterpret_cast<SystemTrayManager*>(createStruct->lpCreateParams);
        SetWindowLongPtr(hwnd, GWLP_USERDATA, reinterpret_cast<LONG_PTR>(trayManager));
    } else {
        trayManager = reinterpret_cast<SystemTrayManager*>(GetWindowLongPtr(hwnd, GWLP_USERDATA));
    }

    if (trayManager && uMsg == WM_TRAY_MESSAGE) {
        return trayManager->HandleTrayMessage(wParam, lParam);
    }

    return DefWindowProc(hwnd, uMsg, wParam, lParam);
}

LRESULT SystemTrayManager::HandleTrayMessage(WPARAM wParam, LPARAM lParam) {
    if (wParam != TRAY_ICON_ID) return 0;

    switch (lParam) {
        case WM_RBUTTONUP: {
            // Show context menu
            POINT cursorPos;
            GetCursorPos(&cursorPos);
            ShowContextMenu(cursorPos.x, cursorPos.y);
            break;
        }
        
        case WM_LBUTTONDBLCLK: {
            // Double-click to toggle window
            if (onToggleWindow) {
                onToggleWindow();
            }
            break;
        }
    }

    return 0;
}

void SystemTrayManager::ShowContextMenu(int x, int y) {
    HMENU hMenu = CreatePopupMenu();
    
    if (!hMenu) return;

    // Add menu items
    std::string toggleText = "Show Window";  // Default text, should be updated based on window state
    
    int wideLen = MultiByteToWideChar(CP_UTF8, 0, toggleText.c_str(), -1, nullptr, 0);
    std::wstring wideToggleText(wideLen, 0);
    MultiByteToWideChar(CP_UTF8, 0, toggleText.c_str(), -1, &wideToggleText[0], wideLen);
    
    AppendMenuW(hMenu, MF_STRING, ID_TOGGLE_WINDOW, wideToggleText.c_str());
    
    if (!current_status_.empty()) {
        std::string statusText = "Status: " + current_status_;
        int statusWideLen = MultiByteToWideChar(CP_UTF8, 0, statusText.c_str(), -1, nullptr, 0);
        std::wstring wideStatusText(statusWideLen, 0);
        MultiByteToWideChar(CP_UTF8, 0, statusText.c_str(), -1, &wideStatusText[0], statusWideLen);
        
        AppendMenuW(hMenu, MF_STRING | MF_GRAYED, 0, wideStatusText.c_str());
        AppendMenuW(hMenu, MF_SEPARATOR, 0, nullptr);
    }
    
    AppendMenuW(hMenu, MF_SEPARATOR, 0, nullptr);
    AppendMenuW(hMenu, MF_STRING, ID_QUIT, L"Quit Omi");

    // Set foreground window to ensure menu displays properly
    SetForegroundWindow(tray_hwnd_);

    // Show menu
    int command = TrackPopupMenu(
        hMenu,
        TPM_RETURNCMD | TPM_NONOTIFY,
        x, y, 0, tray_hwnd_, nullptr
    );

    // Handle menu selection
    switch (command) {
        case ID_TOGGLE_WINDOW:
            if (onToggleWindow) {
                onToggleWindow();
            }
            break;
            
        case ID_QUIT:
            if (onQuit) {
                onQuit();
            }
            break;
    }

    DestroyMenu(hMenu);
} 