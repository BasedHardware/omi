#include "flutter_window.h"
#include "windows_audio_capture.h"

#include <optional>

#include "flutter/generated_plugin_registrant.h"

FlutterWindow::FlutterWindow(const flutter::DartProject& project)
    : project_(project) {}

FlutterWindow::~FlutterWindow() {}

bool FlutterWindow::OnCreate() {
  if (!Win32Window::OnCreate()) {
    return false;
  }

  RECT frame = GetClientArea();

  // The size here must match the window dimensions to avoid unnecessary surface
  // creation / destruction in the startup path.
  flutter_controller_ = std::make_unique<flutter::FlutterViewController>(
      frame.right - frame.left, frame.bottom - frame.top, project_);
  // Ensure that basic setup of the controller was successful.
  if (!flutter_controller_->engine() || !flutter_controller_->view()) {
    return false;
  }
  RegisterPlugins(flutter_controller_->engine());

  // Initialize Windows Audio Capture
  audio_capture_ = std::make_unique<WindowsAudioCapture>();
  
  // Create and register method channel
  auto channel = std::make_shared<flutter::MethodChannel<flutter::EncodableValue>>(
      flutter_controller_->engine()->messenger(), "screenCapturePlatform",
      &flutter::StandardMethodCodec::GetInstance());

  audio_capture_->SetMethodChannel(channel);

  channel->SetMethodCallHandler(
      [this](const flutter::MethodCall<flutter::EncodableValue>& call,
             std::unique_ptr<flutter::MethodResult<flutter::EncodableValue>> result) {
        HandleMethodCall(call, std::move(result));
      });

  SetChildContent(flutter_controller_->view()->GetNativeWindow());

  flutter_controller_->engine()->SetNextFrameCallback([&]() {
    this->Show();
  });

  // Flutter can complete the first frame before the "show window" callback is
  // registered. The following call ensures a frame is pending to ensure the
  // window is shown. It is a no-op if the first frame hasn't completed yet.
  flutter_controller_->ForceRedraw();

  return true;
}

void FlutterWindow::OnDestroy() {
  if (audio_capture_) {
    audio_capture_->Cleanup();
    audio_capture_.reset();
  }

  if (flutter_controller_) {
    flutter_controller_ = nullptr;
  }

  Win32Window::OnDestroy();
}

void FlutterWindow::HandleMethodCall(
    const flutter::MethodCall<flutter::EncodableValue>& call,
    std::unique_ptr<flutter::MethodResult<flutter::EncodableValue>> result) {
  
  const std::string& method = call.method_name();

  if (method == "checkMicrophonePermission") {
    std::string status = audio_capture_->CheckMicrophonePermission();
    result->Success(flutter::EncodableValue(status));
  }
  else if (method == "requestMicrophonePermission") {
    bool granted = audio_capture_->RequestMicrophonePermission();
    result->Success(flutter::EncodableValue(granted));
  }
  else if (method == "checkScreenCapturePermission") {
    std::string status = audio_capture_->CheckScreenCapturePermission();
    result->Success(flutter::EncodableValue(status));
  }
  else if (method == "requestScreenCapturePermission") {
    bool granted = audio_capture_->RequestScreenCapturePermission();
    result->Success(flutter::EncodableValue(granted));
  }
  else if (method == "checkBluetoothPermission") {
    std::string status = audio_capture_->CheckBluetoothPermission();
    result->Success(flutter::EncodableValue(status));
  }
  else if (method == "requestBluetoothPermission") {
    bool granted = audio_capture_->RequestBluetoothPermission();
    result->Success(flutter::EncodableValue(granted));
  }
  else if (method == "checkLocationPermission") {
    std::string status = audio_capture_->CheckLocationPermission();
    result->Success(flutter::EncodableValue(status));
  }
  else if (method == "requestLocationPermission") {
    bool granted = audio_capture_->RequestLocationPermission();
    result->Success(flutter::EncodableValue(granted));
  }
  else if (method == "checkNotificationPermission") {
    std::string status = audio_capture_->CheckNotificationPermission();
    result->Success(flutter::EncodableValue(status));
  }
  else if (method == "requestNotificationPermission") {
    bool granted = audio_capture_->RequestNotificationPermission();
    result->Success(flutter::EncodableValue(granted));
  }
  else if (method == "start") {
    if (!audio_capture_->Initialize()) {
      result->Error("INIT_ERROR", "Failed to initialize audio capture system");
      return;
    }
    
    if (audio_capture_->StartCapture()) {
      result->Success();
    } else {
      result->Error("START_ERROR", "Failed to start audio capture");
    }
  }
  else if (method == "stop") {
    if (audio_capture_->StopCapture()) {
      result->Success();
    } else {
      result->Error("STOP_ERROR", "Failed to stop audio capture");
    }
  }
  else {
    result->NotImplemented();
  }
}

LRESULT
FlutterWindow::MessageHandler(HWND hwnd, UINT const message,
                              WPARAM const wparam,
                              LPARAM const lparam) noexcept {
  // Give Flutter, including plugins, an opportunity to handle window messages.
  if (flutter_controller_) {
    std::optional<LRESULT> result =
        flutter_controller_->HandleTopLevelWindowProc(hwnd, message, wparam,
                                                      lparam);
    if (result) {
      return *result;
    }
  }

  switch (message) {
    case WM_FONTCHANGE:
      flutter_controller_->engine()->ReloadSystemFonts();
      break;
  }

  return Win32Window::MessageHandler(hwnd, message, wparam, lparam);
}
