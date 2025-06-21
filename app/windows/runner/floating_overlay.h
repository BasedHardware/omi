#pragma once

#include <windows.h>
#include <string>
#include <functional>
#include <memory>

// Floating overlay window for recording status and controls
class FloatingOverlay {
public:
    FloatingOverlay();
    ~FloatingOverlay();

    // Overlay management
    bool Create();
    void Show();
    void Hide();
    void Destroy();
    bool IsVisible() const { return is_visible_; }

    // Update overlay state
    void UpdateRecordingState(bool isRecording, bool isPaused);
    void UpdateTranscript(const std::string& transcript, int segmentCount);
    void UpdateStatus(const std::string& status);
    void Move(double x, double y);

    // Callbacks for user interactions
    std::function<void()> onPlayPause;
    std::function<void()> onStop; 
    std::function<void()> onExpand;

private:
    // Window procedure
    static LRESULT CALLBACK WindowProc(HWND hwnd, UINT uMsg, WPARAM wParam, LPARAM lParam);
    static LRESULT CALLBACK StaticWindowProc(HWND hwnd, UINT uMsg, WPARAM wParam, LPARAM lParam);
    LRESULT HandleMessage(UINT uMsg, WPARAM wParam, LPARAM lParam);

    // UI creation and updates
    void CreateControls();
    void CreateModernControls();
    void UpdateUI();
    void SetupWindowStyle();

    // Event handlers
    void OnPaint(HDC hdc);
    void OnCommand(WPARAM wParam);
    void OnDrawItem(WPARAM wParam, LPARAM lParam);
    void OnMouseMove(WPARAM wParam, LPARAM lParam);
    void OnMouseDown(WPARAM wParam, LPARAM lParam);
    void OnMouseUp(WPARAM wParam, LPARAM lParam);
    void OnDestroy();

    // Drawing helpers
    void DrawBackground(HDC hdc, RECT& rect);
    void DrawModernBackground(HDC hdc, RECT& rect);
    void DrawTextString(HDC hdc, const std::string& text, RECT& rect, COLORREF color);
    void DrawButton(HDC hdc, RECT& rect, const std::string& text, bool isPressed);
    void DrawModernButton(HDC hdc, RECT& rect, const std::wstring& text, bool isPressed, bool isPrimary);

    // Window handle and properties
    HWND hwnd_;
    HINSTANCE hinstance_;
    WNDPROC original_proc_;
    bool is_visible_;
    bool is_dragging_;
    POINT drag_offset_;

    // Control handles
    HWND play_pause_button_;
    HWND stop_button_;
    HWND expand_button_;

    // State
    bool is_recording_;
    bool is_paused_;
    std::string current_transcript_;
    std::string current_status_;
    int segment_count_;

    // Window dimensions (matching macOS design)
    static const int OVERLAY_WIDTH = 220;
    static const int OVERLAY_HEIGHT = 52;
    
    // Control IDs
    static const int ID_PLAY_PAUSE = 1001;
    static const int ID_STOP = 1002;
    static const int ID_EXPAND = 1003;

    // Drawing resources
    HBRUSH background_brush_;
    HBRUSH button_brush_;
    HPEN border_pen_;
    HFONT text_font_;

    // Callbacks
    std::function<void()> on_expand_;
    std::function<void()> on_play_pause_;
}; 