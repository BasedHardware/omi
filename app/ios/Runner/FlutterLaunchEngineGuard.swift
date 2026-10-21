import Foundation

/// Decides whether `AppDelegate` may register Flutter plugins at launch and
/// what to show when it cannot.
///
/// A debug build launched without Flutter tooling attached (a Home Screen tap,
/// or an iOS background relaunch for BLE/VoIP after `flutter run` has gone)
/// cannot start a JIT Dart VM on a physical device. `FlutterEngine` init then
/// returns nil, the storyboard `FlutterViewController` has no engine, every
/// registrar the app delegate vends is nil, and the first Swift plugin
/// dereferences it (SIGSEGV in `SwiftAwesomeNotificationsPlugin.register`).
/// Skipping registration and explaining the situation turns that crash into an
/// actionable screen. Foundation-only so `ios/test` can compile it standalone.
enum FlutterLaunchEngineGuard {
    /// True only when a Flutter root view controller exists and owns an engine.
    static func canRegisterPlugins(hasFlutterRootViewController: Bool, hasEngine: Bool) -> Bool {
        hasFlutterRootViewController && hasEngine
    }

    /// Developer-facing text for the replacement root view controller.
    static func unavailableNotice(debugBuild: Bool, bundleDisplayName: String) -> String {
        if debugBuild {
            return """
            \(bundleDisplayName) is a debug build, and iOS only lets Flutter tooling start a debug Dart VM on a device.

            Launch it again with flutter run, or install a build that opens on its own (from app/):
            OMI_MOBILE_BUILD_MODE=profile bash setup.sh ios
            """
        }
        return "\(bundleDisplayName) could not start its Flutter engine. Reinstall the app."
    }
}
