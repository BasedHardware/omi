import Flutter

final class CaptureFlutterViewController: FlutterViewController {
  override var prefersHomeIndicatorAutoHidden: Bool {
    ProcessInfo.processInfo.arguments.contains(where: {
      $0.hasPrefix("--omi-capture-query=")
    })
  }
}
