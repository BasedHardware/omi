#pragma once

#include <windows.h>
#include <shellapi.h>
#include <string>
#include <functional>

// System tray manager for Windows notification area
class SystemTrayManager {
public:
    SystemTrayManager();
    ~SystemTrayManager();

    // Tray management
    bool Create(HWND parentHwnd);
    void Destroy();
    bool IsCreated() const { return is_created_; }

    // Update tray status
    void UpdateStatus(const std::string& status, bool isActive = false);
    void UpdateTooltip(const std::string& tooltip);

    // Callbacks for tray interactions
    std::function<void()> onToggleWindow;
    std::function<void()> onQuit;

private:
    // Window procedure for tray messages
    static LRESULT CALLBACK TrayWindowProc(HWND hwnd, UINT uMsg, WPARAM wParam, LPARAM lParam);
    LRESULT HandleTrayMessage(WPARAM wParam, LPARAM lParam);

    // Menu management
    void ShowContextMenu(int x, int y);
    void CreateTrayIcon();
    void UpdateTrayIcon(bool isActive);

    // Tray data
    NOTIFYICONDATAW tray_data_;
    HWND parent_hwnd_;
    HWND tray_hwnd_;
    HINSTANCE hinstance_;
    bool is_created_;
    bool is_active_;
    std::string current_status_;

    // Icons
    HICON default_icon_;
    HICON active_icon_;

    // Menu IDs
    static const int ID_TOGGLE_WINDOW = 2001;
    static const int ID_QUIT = 2002;
    static const int TRAY_ICON_ID = 1;
    
    // Custom message for tray
    static const int WM_TRAY_MESSAGE = WM_USER + 1;
}; 