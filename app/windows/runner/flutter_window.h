#ifndef FLUTTER_WINDOW_H_
#define FLUTTER_WINDOW_H_

#include <flutter/dart_project.h>
#include <flutter/flutter_view_controller.h>
#include <flutter/method_channel.h>
#include <flutter/encodable_value.h>

#include <memory>

#include "win32_window.h"
#include "windows_audio_capture.h"

// Forward declarations
class FloatingOverlay;
class SystemTrayManager;

// A window that does nothing but host a Flutter view.
class FlutterWindow : public Win32Window {
 public:
  // Creates a new FlutterWindow hosting a Flutter view running |project|.
  explicit FlutterWindow(const flutter::DartProject& project);
  virtual ~FlutterWindow();

 protected:
  // Win32Window:
  bool OnCreate() override;
  void OnDestroy() override;
  LRESULT MessageHandler(HWND window, UINT const message, WPARAM const wparam,
                         LPARAM const lparam) noexcept override;

 private:
  // Handle Flutter method calls
  void HandleMethodCall(
      const flutter::MethodCall<flutter::EncodableValue>& call,
      std::unique_ptr<flutter::MethodResult<flutter::EncodableValue>> result);

  // Handle overlay method calls
  void HandleOverlayMethodCall(
      const flutter::MethodCall<flutter::EncodableValue>& call,
      std::unique_ptr<flutter::MethodResult<flutter::EncodableValue>> result);

  // Overlay management methods
  void ShowOverlay();
  void HideOverlay();
  void UpdateOverlayState(bool isRecording, bool isPaused);
  void UpdateOverlayTranscript(const std::string& transcript, int segmentCount);
  void UpdateOverlayStatus(const std::string& status);
  void MoveOverlay(double x, double y);

  // Window management methods
  void BringAppToFront();

  // The project to run.
  flutter::DartProject project_;

  // The Flutter instance hosted by this window.
  std::unique_ptr<flutter::FlutterViewController> flutter_controller_;

  // Audio capture instance
  std::unique_ptr<WindowsAudioCapture> audio_capture_;

  // Overlay instance
  std::unique_ptr<FloatingOverlay> floating_overlay_;

  // System tray manager
  std::unique_ptr<SystemTrayManager> system_tray_;

  // Method channels
  std::shared_ptr<flutter::MethodChannel<flutter::EncodableValue>> screen_capture_channel_;
  std::shared_ptr<flutter::MethodChannel<flutter::EncodableValue>> overlay_channel_;
};

#endif  // FLUTTER_WINDOW_H_
