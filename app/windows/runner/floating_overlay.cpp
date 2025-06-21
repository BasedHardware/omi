#include "floating_overlay.h"
#include <dwmapi.h>
#include <windowsx.h>
#include <iostream>

#pragma comment(lib, "dwmapi.lib")

const wchar_t* OVERLAY_CLASS_NAME = L"OmiFloatingOverlay";

FloatingOverlay::FloatingOverlay() 
    : hwnd_(nullptr)
    , hinstance_(GetModuleHandle(nullptr))
    , original_proc_(nullptr)
    , is_visible_(false)
    , is_dragging_(false)
    , play_pause_button_(nullptr)
    , stop_button_(nullptr)
    , expand_button_(nullptr)
    , is_recording_(false)
    , is_paused_(false)
    , segment_count_(0)
    , background_brush_(nullptr)
    , text_font_(nullptr)
    , border_pen_(nullptr) {
}

FloatingOverlay::~FloatingOverlay() {
    OnDestroy();
}

bool FloatingOverlay::Create() {
    std::cout << "FloatingOverlay::Create() - Creating modern pill-shaped overlay..." << std::endl;
    
    // Register custom window class for modern overlay
    WNDCLASSEXW wc = {};
    wc.cbSize = sizeof(WNDCLASSEX);
    wc.style = CS_HREDRAW | CS_VREDRAW;
    wc.lpfnWndProc = WindowProc;
    wc.hInstance = hinstance_;
    wc.hCursor = LoadCursor(nullptr, IDC_ARROW);
    wc.hbrBackground = (HBRUSH)(COLOR_WINDOW + 1); // Use a standard background
    wc.lpszClassName = OVERLAY_CLASS_NAME;

    if (!RegisterClassExW(&wc)) {
        DWORD error = GetLastError();
        if (error != ERROR_CLASS_ALREADY_EXISTS) {
            std::cerr << "Failed to register overlay window class. Error: " << error << std::endl;
            return false;
        }
    }

    // Calculate position (top-right corner, matching macOS design)
    int screenWidth = GetSystemMetrics(SM_CXSCREEN);
    int x = screenWidth - OVERLAY_WIDTH - 50;
    int y = 50;
    
    // Create a standard popup window. We will shape it later.
    hwnd_ = CreateWindowExW(
        WS_EX_TOPMOST | WS_EX_TOOLWINDOW,
        OVERLAY_CLASS_NAME,
        L"Omi Recording Overlay",
        WS_POPUP,
        x, y, OVERLAY_WIDTH, OVERLAY_HEIGHT,
        nullptr, nullptr, hinstance_, this
    );

    if (!hwnd_) {
        DWORD error = GetLastError();
        std::cerr << "FloatingOverlay::Create() - Modern window creation failed. Error: " << error << std::endl;
        return false;
    }
    
    // Create the pill shape by setting a window region
    HRGN region = CreateRoundRectRgn(0, 0, OVERLAY_WIDTH, OVERLAY_HEIGHT, 26, 26);
    SetWindowRgn(hwnd_, region, TRUE);

    // Create modern controls matching macOS design
    CreateModernControls();
    
    // Initialize drawing resources
    background_brush_ = CreateSolidBrush(RGB(28, 28, 30)); 
    text_font_ = CreateFontW(
        -12, 0, 0, 0, FW_NORMAL, FALSE, FALSE, FALSE,
        DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS,
        CLEARTYPE_QUALITY, DEFAULT_PITCH | FF_DONTCARE, L"Segoe UI"
    );
    border_pen_ = CreatePen(PS_SOLID, 1, RGB(60, 60, 67));

    return true;
}

void FloatingOverlay::SetupWindowStyle() {
    // This function is now empty but kept for potential future use.
}

void FloatingOverlay::CreateControls() {
    std::cout << "FloatingOverlay::CreateControls()" << std::endl;

    // Create a "Pause" button.
    // Legacy method - use modern controls
    CreateModernControls();
}

void FloatingOverlay::CreateModernControls() {
    // Create modern circular buttons matching macOS design
    // Play/Pause button (primary action) at position matching macOS layout
    play_pause_button_ = CreateWindowW(
        L"BUTTON", L"▶",
        WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON | BS_FLAT | BS_OWNERDRAW,
        76, 12, 28, 28,
        hwnd_, reinterpret_cast<HMENU>(static_cast<uintptr_t>(ID_PLAY_PAUSE)), hinstance_, nullptr
    );

    // Stop button (initially hidden, appears when recording)
    stop_button_ = CreateWindowW(
        L"BUTTON", L"⏹",
        WS_CHILD | BS_PUSHBUTTON | BS_FLAT | BS_OWNERDRAW,
        108, 12, 28, 28,
        hwnd_, reinterpret_cast<HMENU>(static_cast<uintptr_t>(ID_STOP)), hinstance_, nullptr
    );

    // Expand button (always visible)
    expand_button_ = CreateWindowW(
        L"BUTTON", L"⤢",
        WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON | BS_FLAT | BS_OWNERDRAW,
        140, 12, 28, 28,
        hwnd_, reinterpret_cast<HMENU>(static_cast<uintptr_t>(ID_EXPAND)), hinstance_, nullptr
    );
}

void FloatingOverlay::Show() {
    if (hwnd_) {
        std::cout << "FloatingOverlay::Show() - Showing modern overlay window, HWND: " << hwnd_ << std::endl;
        
        // Check if window is valid before showing
        if (!IsWindow(hwnd_)) {
            std::cerr << "FloatingOverlay::Show() - ERROR: HWND is not a valid window!" << std::endl;
            return;
        }
        
        // Get current window state
        BOOL wasVisible = IsWindowVisible(hwnd_);
        std::cout << "FloatingOverlay::Show() - Window was visible before show: " << (wasVisible ? "YES" : "NO") << std::endl;
        
        // Show with modern entrance animation
        std::cout << "FloatingOverlay::Show() - Calling ShowWindow(SW_SHOWNOACTIVATE)..." << std::endl;
        BOOL showResult = ShowWindow(hwnd_, SW_SHOWNOACTIVATE);
        std::cout << "FloatingOverlay::Show() - ShowWindow result: " << showResult << std::endl;
        
        // Try different show methods if first one fails
        if (!IsWindowVisible(hwnd_)) {
            std::cout << "FloatingOverlay::Show() - Window still not visible, trying SW_SHOW..." << std::endl;
            ShowWindow(hwnd_, SW_SHOW);
        }
        
        // Ensure it stays on top (like macOS floating level)
        std::cout << "FloatingOverlay::Show() - Setting window to topmost..." << std::endl;
        BOOL posResult = SetWindowPos(hwnd_, HWND_TOPMOST, 0, 0, 0, 0, 
                    SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE);
        std::cout << "FloatingOverlay::Show() - SetWindowPos result: " << posResult << std::endl;
        
        is_visible_ = true;
        
        // Update UI to reflect current state
        std::cout << "FloatingOverlay::Show() - Updating UI..." << std::endl;
        UpdateUI();
        
        // Force a redraw
        std::cout << "FloatingOverlay::Show() - Forcing redraw..." << std::endl;
        InvalidateRect(hwnd_, nullptr, TRUE);
        UpdateWindow(hwnd_);
        
        // Verify visibility after all operations
        BOOL isVisible = IsWindowVisible(hwnd_);
        std::cout << "FloatingOverlay::Show() - Final window visible: " << (isVisible ? "YES" : "NO") << std::endl;
        
        if (isVisible) {
            RECT rect;
            GetWindowRect(hwnd_, &rect);
            std::cout << "FloatingOverlay::Show() - Position: (" << rect.left << ", " << rect.top 
                      << ") Size: " << (rect.right - rect.left) << "x" << (rect.bottom - rect.top) << std::endl;
            
            // Check if window is actually on screen
            int screenWidth = GetSystemMetrics(SM_CXSCREEN);
            int screenHeight = GetSystemMetrics(SM_CYSCREEN);
            std::cout << "FloatingOverlay::Show() - Screen size: " << screenWidth << "x" << screenHeight << std::endl;
            
            if (rect.left >= screenWidth || rect.top >= screenHeight || rect.right <= 0 || rect.bottom <= 0) {
                std::cout << "FloatingOverlay::Show() - WARNING: Window is positioned off-screen!" << std::endl;
            }
        } else {
            DWORD error = GetLastError();
            std::cout << "FloatingOverlay::Show() - Window not visible, last error: " << error << std::endl;
        }
    } else {
        std::cout << "FloatingOverlay::Show() - ERROR: hwnd_ is null!" << std::endl;
    }
}

void FloatingOverlay::Hide() {
    if (hwnd_ && is_visible_) {
        ShowWindow(hwnd_, SW_HIDE);
        is_visible_ = false;
    }
}

void FloatingOverlay::Destroy() {
    if (hwnd_) {
        DestroyWindow(hwnd_);
        hwnd_ = nullptr;
    }

    // Cleanup drawing resources
    if (background_brush_) {
        DeleteObject(background_brush_);
        background_brush_ = nullptr;
    }
    if (text_font_) {
        DeleteObject(text_font_);
        text_font_ = nullptr;
    }
    if (border_pen_) {
        DeleteObject(border_pen_);
        border_pen_ = nullptr;
    }

    is_visible_ = false;
}

void FloatingOverlay::UpdateRecordingState(bool isRecording, bool isPaused) {
    is_recording_ = isRecording;
    is_paused_ = isPaused;
    UpdateUI();
}

void FloatingOverlay::UpdateTranscript(const std::string& transcript, int segmentCount) {
    current_transcript_ = transcript;
    segment_count_ = segmentCount;
    UpdateUI();
}

void FloatingOverlay::UpdateStatus(const std::string& status) {
    current_status_ = status;
    UpdateUI();
}

void FloatingOverlay::Move(double x, double y) {
    if (hwnd_) {
        SetWindowPos(hwnd_, HWND_TOPMOST, 
                    static_cast<int>(x), static_cast<int>(y), 
                    0, 0, SWP_NOSIZE | SWP_NOACTIVATE);
    }
}

void FloatingOverlay::UpdateUI() {
    if (hwnd_ && is_visible_) {
        // Update button text based on state
        if (play_pause_button_) {
            SetWindowTextW(play_pause_button_, is_paused_ ? L"▶️" : L"⏸️");
        }
        
        // Force redraw
        InvalidateRect(hwnd_, nullptr, TRUE);
    }
}

LRESULT CALLBACK FloatingOverlay::WindowProc(HWND hwnd, UINT uMsg, WPARAM wParam, LPARAM lParam) {
    FloatingOverlay* overlay = nullptr;

    if (uMsg == WM_NCCREATE) {
        CREATESTRUCT* create_struct = reinterpret_cast<CREATESTRUCT*>(lParam);
        overlay = reinterpret_cast<FloatingOverlay*>(create_struct->lpCreateParams);
        SetWindowLongPtr(hwnd, GWLP_USERDATA, reinterpret_cast<LONG_PTR>(overlay));
    } else {
        overlay = reinterpret_cast<FloatingOverlay*>(GetWindowLongPtr(hwnd, GWLP_USERDATA));
    }

    if (overlay) {
        return overlay->HandleMessage(uMsg, wParam, lParam);
    }
    
    return DefWindowProc(hwnd, uMsg, wParam, lParam);
}

LRESULT CALLBACK FloatingOverlay::StaticWindowProc(HWND hwnd, UINT uMsg, WPARAM wParam, LPARAM lParam) {
    FloatingOverlay* overlay = reinterpret_cast<FloatingOverlay*>(GetWindowLongPtr(hwnd, GWLP_USERDATA));
    
    if (overlay) {
        // Handle clicks on the static control
        if (uMsg == WM_LBUTTONUP) {
            std::cout << "FloatingOverlay: Static window clicked!" << std::endl;
            if (overlay->onExpand) {
                std::cout << "FloatingOverlay: Calling onExpand callback" << std::endl;
                overlay->onExpand();
            }
            return 0;
        }
        
        // Handle right-click for potential context menu
        if (uMsg == WM_RBUTTONUP) {
            std::cout << "FloatingOverlay: Right-click detected" << std::endl;
            // Could show context menu here in the future
            return 0;
        }
    }
    
    // Call original window procedure for STATIC control
    if (overlay && overlay->original_proc_) {
        return CallWindowProc(overlay->original_proc_, hwnd, uMsg, wParam, lParam);
    }
    
    return DefWindowProc(hwnd, uMsg, wParam, lParam);
}

LRESULT FloatingOverlay::HandleMessage(UINT uMsg, WPARAM wParam, LPARAM lParam) {
    switch (uMsg) {
        case WM_PAINT: {
            PAINTSTRUCT ps;
            HDC hdc = BeginPaint(hwnd_, &ps);
            OnPaint(hdc);
            EndPaint(hwnd_, &ps);
            return 0;
        }

        case WM_COMMAND:
            OnCommand(wParam);
            return 0;
            
        case WM_DRAWITEM:
            OnDrawItem(wParam, lParam);
            return TRUE;

        case WM_LBUTTONDOWN:
            OnMouseDown(wParam, lParam);
            return 0;

        case WM_LBUTTONUP:
            OnMouseUp(wParam, lParam);
            return 0;

        case WM_MOUSEMOVE:
            OnMouseMove(wParam, lParam);
            return 0;

        case WM_DESTROY:
            is_visible_ = false;
            return 0;

        default:
            return DefWindowProc(hwnd_, uMsg, wParam, lParam);
    }
}

void FloatingOverlay::OnPaint(HDC hdc) {
    RECT clientRect;
    GetClientRect(hwnd_, &clientRect);

    // Draw modern background
    DrawModernBackground(hdc, clientRect);

    // Draw app logo/icon area (left side of pill)
    RECT logoRect = {16, 14, 44, 42};
    HBRUSH logoBrush = CreateSolidBrush(RGB(88, 86, 214)); // Purple accent
    HBRUSH oldBrush = (HBRUSH)SelectObject(hdc, logoBrush);
    Ellipse(hdc, logoRect.left, logoRect.top, logoRect.right, logoRect.bottom);
    SelectObject(hdc, oldBrush);
    DeleteObject(logoBrush);
    
    // Draw microphone icon in logo area
    SetTextColor(hdc, RGB(255, 255, 255));
    SetBkMode(hdc, TRANSPARENT);
    RECT micRect = {20, 18, 40, 38};
    DrawTextW(hdc, L"🎙", -1, &micRect, DT_CENTER | DT_VCENTER | DT_SINGLELINE);
}

void FloatingOverlay::DrawBackground(HDC hdc, RECT& rect) {
    // Legacy method - use modern background
    DrawModernBackground(hdc, rect);
}

void FloatingOverlay::DrawModernBackground(HDC hdc, RECT& rect) {
    // Create modern pill-shaped background
    HRGN region = CreateRoundRectRgn(0, 0, rect.right, rect.bottom, 26, 26);
    
    // Use solid modern background color (simpler approach to avoid library dependencies)
    HBRUSH modernBrush = CreateSolidBrush(RGB(28, 28, 30)); // Modern dark background
    FillRgn(hdc, region, modernBrush);
    DeleteObject(modernBrush);
    
    // Add subtle highlight at the top for depth
    HBRUSH highlightBrush = CreateSolidBrush(RGB(40, 40, 45));
    HRGN highlightRegion = CreateRoundRectRgn(0, 0, rect.right, rect.bottom / 3, 26, 26);
    FillRgn(hdc, highlightRegion, highlightBrush);
    DeleteObject(highlightBrush);
    DeleteObject(highlightRegion);
    
    // Draw subtle border
    HBRUSH oldBrush = (HBRUSH)SelectObject(hdc, GetStockObject(NULL_BRUSH));
    HPEN oldPen = (HPEN)SelectObject(hdc, border_pen_);
    RoundRect(hdc, 0, 0, rect.right, rect.bottom, 26, 26);
    SelectObject(hdc, oldPen);
    SelectObject(hdc, oldBrush);
    
    DeleteObject(region);
}

void FloatingOverlay::DrawTextString(HDC hdc, const std::string& text, RECT& rect, COLORREF color) {
    HFONT oldFont = (HFONT)SelectObject(hdc, text_font_);
    SetTextColor(hdc, color);
    SetBkMode(hdc, TRANSPARENT);
    
    // Convert to wide string
    int wideLen = MultiByteToWideChar(CP_UTF8, 0, text.c_str(), -1, nullptr, 0);
    std::wstring wideText(wideLen, 0);
    MultiByteToWideChar(CP_UTF8, 0, text.c_str(), -1, &wideText[0], wideLen);
    
    ::DrawTextW(hdc, wideText.c_str(), -1, &rect, DT_LEFT | DT_VCENTER | DT_SINGLELINE);
    SelectObject(hdc, oldFont);
}

void FloatingOverlay::OnCommand(WPARAM wParam) {
    int controlId = LOWORD(wParam);
    int notificationCode = HIWORD(wParam);
    
    // Only handle button clicks (BN_CLICKED)
    if (notificationCode != BN_CLICKED) {
        return;
    }
    
    std::cout << "FloatingOverlay: Button clicked, ID=" << controlId << std::endl;
    
    switch (controlId) {
        case ID_PLAY_PAUSE:
            std::cout << "FloatingOverlay: Play/Pause button clicked" << std::endl;
            if (onPlayPause) {
                std::cout << "FloatingOverlay: Calling onPlayPause callback" << std::endl;
                onPlayPause();
            } else {
                std::cout << "FloatingOverlay: onPlayPause callback is null!" << std::endl;
            }
            break;
            
        case ID_STOP:
            std::cout << "FloatingOverlay: Stop button clicked" << std::endl;
            if (onStop) {
                std::cout << "FloatingOverlay: Calling onStop callback" << std::endl;
                onStop();
            } else {
                std::cout << "FloatingOverlay: onStop callback is null!" << std::endl;
            }
            break;
            
        case ID_EXPAND:
            std::cout << "FloatingOverlay: Expand button clicked" << std::endl;
            if (onExpand) {
                std::cout << "FloatingOverlay: Calling onExpand callback" << std::endl;
                onExpand();
            } else {
                std::cout << "FloatingOverlay: onExpand callback is null!" << std::endl;
            }
            break;
            
        default:
            std::cout << "FloatingOverlay: Unknown button ID=" << controlId << std::endl;
            break;
    }
}

void FloatingOverlay::OnDrawItem(WPARAM wParam, LPARAM lParam) {
    DRAWITEMSTRUCT* dis = (DRAWITEMSTRUCT*)lParam;
    if (!dis) return;
    
    bool isPressed = (dis->itemState & ODS_SELECTED) != 0;
    bool isPrimary = false;
    std::wstring buttonText;
    
    switch (dis->CtlID) {
        case ID_PLAY_PAUSE:
            buttonText = is_paused_ ? L"▶" : L"⏸";
            isPrimary = true;
            break;
        case ID_STOP:
            buttonText = L"⏹";
            break;
        case ID_EXPAND:
            buttonText = L"⤢";
            break;
        default:
            return;
    }
    
    DrawModernButton(dis->hDC, dis->rcItem, buttonText, isPressed, isPrimary);
}

void FloatingOverlay::DrawModernButton(HDC hdc, RECT& rect, const std::wstring& text, bool isPressed, bool isPrimary) {
    // Create circular button background
    int radius = 14;
    HRGN buttonRegion = CreateRoundRectRgn(rect.left, rect.top, rect.right, rect.bottom, radius * 2, radius * 2);
    
    // Button background color
    COLORREF bgColor;
    if (isPrimary) {
        bgColor = isPressed ? RGB(70, 68, 180) : RGB(88, 86, 214); // Purple accent
    } else {
        bgColor = isPressed ? RGB(50, 50, 55) : RGB(60, 60, 67); // Subtle gray
    }
    
    HBRUSH buttonBrush = CreateSolidBrush(bgColor);
    FillRgn(hdc, buttonRegion, buttonBrush);
    DeleteObject(buttonBrush);
    
    // Draw button border
    HPEN borderPen = CreatePen(PS_SOLID, 1, RGB(80, 80, 87));
    HPEN oldPen = (HPEN)SelectObject(hdc, borderPen);
    HBRUSH oldBrush = (HBRUSH)SelectObject(hdc, GetStockObject(NULL_BRUSH));
    
    Ellipse(hdc, rect.left, rect.top, rect.right, rect.bottom);
    
    SelectObject(hdc, oldPen);
    SelectObject(hdc, oldBrush);
    DeleteObject(borderPen);
    
    // Draw button text/icon
    SetTextColor(hdc, RGB(255, 255, 255));
    SetBkMode(hdc, TRANSPARENT);
    
    HFONT buttonFont = CreateFontW(-11, 0, 0, 0, FW_NORMAL, FALSE, FALSE, FALSE,
        DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS,
        CLEARTYPE_QUALITY, DEFAULT_PITCH | FF_DONTCARE, L"Segoe UI Symbol");
    HFONT oldFont = (HFONT)SelectObject(hdc, buttonFont);
    
    DrawTextW(hdc, text.c_str(), -1, &rect, DT_CENTER | DT_VCENTER | DT_SINGLELINE);
    
    SelectObject(hdc, oldFont);
    DeleteObject(buttonFont);
    DeleteObject(buttonRegion);
}

void FloatingOverlay::OnMouseDown(WPARAM wParam, LPARAM lParam) {
    if (wParam & MK_LBUTTON) {
        is_dragging_ = true;
        SetCapture(hwnd_);
        
        POINT cursorPos;
        GetCursorPos(&cursorPos);
        
        RECT windowRect;
        GetWindowRect(hwnd_, &windowRect);
        
        drag_offset_.x = cursorPos.x - windowRect.left;
        drag_offset_.y = cursorPos.y - windowRect.top;
    }
}

void FloatingOverlay::OnMouseUp(WPARAM wParam, LPARAM lParam) {
    if (is_dragging_) {
        is_dragging_ = false;
        ReleaseCapture();
    }
}

void FloatingOverlay::OnMouseMove(WPARAM wParam, LPARAM lParam) {
    if (is_dragging_ && (wParam & MK_LBUTTON)) {
        POINT cursorPos;
        GetCursorPos(&cursorPos);
        
        int newX = cursorPos.x - drag_offset_.x;
        int newY = cursorPos.y - drag_offset_.y;
        
        SetWindowPos(hwnd_, HWND_TOPMOST, newX, newY, 0, 0, 
                    SWP_NOSIZE | SWP_NOACTIVATE);
    }
}

void FloatingOverlay::OnDestroy() {
    std::cout << "FloatingOverlay::OnDestroy()" << std::endl;
    if (hwnd_) {
        DestroyWindow(hwnd_);
        hwnd_ = nullptr;
    }
    // Clean up GDI objects
    if (background_brush_) DeleteObject(background_brush_);
    if (text_font_) DeleteObject(text_font_);
    if (border_pen_) DeleteObject(border_pen_);
} 