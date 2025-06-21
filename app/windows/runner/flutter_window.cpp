#include "flutter_window.h"
#include "windows_audio_capture.h"
#include "floating_overlay.h"
#include "system_tray_manager.h"

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
  
  // Create and register screen capture method channel
  screen_capture_channel_ = std::make_shared<flutter::MethodChannel<flutter::EncodableValue>>(
      flutter_controller_->engine()->messenger(), "screenCapturePlatform",
      &flutter::StandardMethodCodec::GetInstance());

  audio_capture_->SetMethodChannel(screen_capture_channel_);

  screen_capture_channel_->SetMethodCallHandler(
      [this](const flutter::MethodCall<flutter::EncodableValue>& call,
             std::unique_ptr<flutter::MethodResult<flutter::EncodableValue>> result) {
        HandleMethodCall(call, std::move(result));
      });

  // Create and register overlay method channel
  overlay_channel_ = std::make_shared<flutter::MethodChannel<flutter::EncodableValue>>(
      flutter_controller_->engine()->messenger(), "overlayPlatform",
      &flutter::StandardMethodCodec::GetInstance());

  overlay_channel_->SetMethodCallHandler(
      [this](const flutter::MethodCall<flutter::EncodableValue>& call,
             std::unique_ptr<flutter::MethodResult<flutter::EncodableValue>> result) {
        HandleOverlayMethodCall(call, std::move(result));
      });

  // Don't create overlay immediately - create it when needed
  std::cout << "FlutterWindow: Overlay will be created on demand" << std::endl;

  // Initialize system tray
  system_tray_ = std::make_unique<SystemTrayManager>();
  if (!system_tray_->Create(GetHandle())) {
    std::cerr << "Warning: Failed to create system tray" << std::endl;
  }

  // Set up system tray callbacks
  system_tray_->onToggleWindow = [this]() {
    if (IsWindowVisible(GetHandle())) {
      ShowWindow(GetHandle(), SW_HIDE);
    } else {
      BringAppToFront();
    }
  };

  system_tray_->onQuit = [this]() {
    PostQuitMessage(0);
  };

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

  if (floating_overlay_) {
    floating_overlay_->Destroy();
    floating_overlay_.reset();
  }

  if (system_tray_) {
    system_tray_->Destroy();
    system_tray_.reset();
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
  else if (method == "bringAppToFront") {
    BringAppToFront();
    result->Success();
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

void FlutterWindow::HandleOverlayMethodCall(
    const flutter::MethodCall<flutter::EncodableValue>& call,
    std::unique_ptr<flutter::MethodResult<flutter::EncodableValue>> result) {
  
  const std::string& method = call.method_name();
  
  if (method == "showOverlay") {
    std::cout << "FlutterWindow: Received showOverlay method call" << std::endl;
    ShowOverlay();
    std::cout << "FlutterWindow: ShowOverlay() completed" << std::endl;
    result->Success();
  }
  else if (method == "hideOverlay") {
    HideOverlay();
    result->Success();
  }
  else if (method == "updateOverlayState") {
    const auto* arguments = std::get_if<flutter::EncodableMap>(call.arguments());
    if (arguments) {
      auto isRecording_it = arguments->find(flutter::EncodableValue("isRecording"));
      auto isPaused_it = arguments->find(flutter::EncodableValue("isPaused"));
      
      if (isRecording_it != arguments->end() && isPaused_it != arguments->end()) {
        bool isRecording = std::get<bool>(isRecording_it->second);
        bool isPaused = std::get<bool>(isPaused_it->second);
        UpdateOverlayState(isRecording, isPaused);
        result->Success();
      } else {
        result->Error("INVALID_ARGUMENTS", "Missing required parameters");
      }
    } else {
      result->Error("INVALID_ARGUMENTS", "Arguments must be a map");
    }
  }
  else if (method == "updateOverlayTranscript") {
    const auto* arguments = std::get_if<flutter::EncodableMap>(call.arguments());
    if (arguments) {
      auto transcript_it = arguments->find(flutter::EncodableValue("transcript"));
      auto segmentCount_it = arguments->find(flutter::EncodableValue("segmentCount"));
      
      if (transcript_it != arguments->end() && segmentCount_it != arguments->end()) {
        std::string transcript = std::get<std::string>(transcript_it->second);
        int segmentCount = std::get<int>(segmentCount_it->second);
        UpdateOverlayTranscript(transcript, segmentCount);
        result->Success();
      } else {
        result->Error("INVALID_ARGUMENTS", "Missing required parameters");
      }
    } else {
      result->Error("INVALID_ARGUMENTS", "Arguments must be a map");
    }
  }
  else if (method == "updateOverlayStatus") {
    const auto* arguments = std::get_if<flutter::EncodableMap>(call.arguments());
    if (arguments) {
      auto status_it = arguments->find(flutter::EncodableValue("status"));
      
      if (status_it != arguments->end()) {
        std::string status = std::get<std::string>(status_it->second);
        UpdateOverlayStatus(status);
        result->Success();
      } else {
        result->Error("INVALID_ARGUMENTS", "Missing status parameter");
      }
    } else {
      result->Error("INVALID_ARGUMENTS", "Arguments must be a map");
    }
  }
  else if (method == "moveOverlay") {
    const auto* arguments = std::get_if<flutter::EncodableMap>(call.arguments());
    if (arguments) {
      auto x_it = arguments->find(flutter::EncodableValue("x"));
      auto y_it = arguments->find(flutter::EncodableValue("y"));
      
      if (x_it != arguments->end() && y_it != arguments->end()) {
        double x = std::get<double>(x_it->second);
        double y = std::get<double>(y_it->second);
        MoveOverlay(x, y);
        result->Success();
      } else {
        result->Error("INVALID_ARGUMENTS", "Missing position parameters");
      }
    } else {
      result->Error("INVALID_ARGUMENTS", "Arguments must be a map");
    }
  }
  else {
    result->NotImplemented();
  }
}

void FlutterWindow::ShowOverlay() {
  std::cout << "FlutterWindow::ShowOverlay() called" << std::endl;
  
  // Debug main window state
  HWND mainHwnd = GetHandle();
  BOOL isVisible = IsWindowVisible(mainHwnd);
  BOOL isIconic = IsIconic(mainHwnd);
  std::cout << "FlutterWindow::ShowOverlay() - Main window state: visible=" << isVisible 
            << ", minimized=" << isIconic << std::endl;
  
  // TEMPORARILY REMOVE THE MINIMIZED CHECK FOR TESTING
  // if (IsWindowVisible(GetHandle()) && !IsIconic(GetHandle())) {
  //   std::cout << "FlutterWindow::ShowOverlay() - Main window is visible, not showing overlay" << std::endl;
  //   return;
  // }
  
  // Always try to create overlay fresh when needed
  std::cout << "FlutterWindow::ShowOverlay() - Creating fresh overlay..." << std::endl;
  floating_overlay_ = std::make_unique<FloatingOverlay>();
  
  if (floating_overlay_->Create()) {
    std::cout << "FlutterWindow::ShowOverlay() - Overlay created successfully, setting up callbacks..." << std::endl;
    
    // Set up callbacks
    floating_overlay_->onPlayPause = [this]() {
      std::cout << "FlutterWindow: onPlayPause callback triggered" << std::endl;
      if (overlay_channel_) overlay_channel_->InvokeMethod("onPlayPause", nullptr);
    };
    floating_overlay_->onStop = [this]() {
      std::cout << "FlutterWindow: onStop callback triggered" << std::endl;
      if (overlay_channel_) overlay_channel_->InvokeMethod("onStop", nullptr);
    };
    floating_overlay_->onExpand = [this]() {
      std::cout << "FlutterWindow: onExpand callback triggered" << std::endl;
      BringAppToFront();
      if (overlay_channel_) overlay_channel_->InvokeMethod("onExpand", nullptr);
    };
    
    std::cout << "FlutterWindow::ShowOverlay() - Callbacks set, showing overlay..." << std::endl;
    floating_overlay_->Show();
  } else {
    std::cerr << "FlutterWindow::ShowOverlay() - Failed to create overlay" << std::endl;
  }
}

void FlutterWindow::HideOverlay() {
  if (floating_overlay_) {
    floating_overlay_->Hide();
  }
}

void FlutterWindow::UpdateOverlayState(bool isRecording, bool isPaused) {
  if (floating_overlay_) {
    floating_overlay_->UpdateRecordingState(isRecording, isPaused);
  }
  
  // Update system tray status
  if (system_tray_) {
    if (isRecording) {
      system_tray_->UpdateStatus("Recording", true);
    } else if (isPaused) {
      system_tray_->UpdateStatus("Paused", false);
    } else {
      system_tray_->UpdateStatus("Ready", false);
    }
  }
}

void FlutterWindow::UpdateOverlayTranscript(const std::string& transcript, int segmentCount) {
  if (floating_overlay_) {
    floating_overlay_->UpdateTranscript(transcript, segmentCount);
  }
  
  // Update system tray with segment count if recording
  if (system_tray_ && segmentCount > 0) {
    std::string status = "Recording (" + std::to_string(segmentCount) + " segments)";
    system_tray_->UpdateStatus(status, true);
  }
}

void FlutterWindow::UpdateOverlayStatus(const std::string& status) {
  if (floating_overlay_) {
    floating_overlay_->UpdateStatus(status);
  }
}

void FlutterWindow::MoveOverlay(double x, double y) {
  if (floating_overlay_) {
    floating_overlay_->Move(x, y);
  }
}

void FlutterWindow::BringAppToFront() {
  HWND hwnd = GetHandle();
  
  // Show the window if it's hidden
  if (!IsWindowVisible(hwnd)) {
    ShowWindow(hwnd, SW_SHOW);
  }
  
  // Restore the window if it's minimized
  if (IsIconic(hwnd)) {
    ShowWindow(hwnd, SW_RESTORE);
  }
  
  // Bring window to front
  SetForegroundWindow(hwnd);
  SetActiveWindow(hwnd);
  BringWindowToTop(hwnd);
  
  // Hide overlay when main window is brought to front
  HideOverlay();
}
