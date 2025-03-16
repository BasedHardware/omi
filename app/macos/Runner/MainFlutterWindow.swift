import AVFoundation
import Cocoa
import FlutterMacOS

class MainFlutterWindow: NSWindow {
  override func awakeFromNib() {
    let flutterViewController = FlutterViewController()
    let windowFrame = self.frame
    self.contentViewController = flutterViewController
    self.setFrame(windowFrame, display: true)

    let permissionChannel = FlutterMethodChannel(
      name: "com.omi.friend/permissions",
      binaryMessenger: flutterViewController.engine.binaryMessenger)

    permissionChannel.setMethodCallHandler { (call, result) in
      switch call.method {
      case "microphone":
        Task {
          let access = await AVCaptureDevice.requestAccess(for: .audio)
          result(access)  // ✅ Return result inside the async task
        }
      case "configure":
        Task {
          let session = await AVCaptureDevice.beginConfiguration();
        }
      default:
        result(FlutterMethodNotImplemented)
      }
    }

    RegisterGeneratedPlugins(registry: flutterViewController)

    super.awakeFromNib()
  }
}
