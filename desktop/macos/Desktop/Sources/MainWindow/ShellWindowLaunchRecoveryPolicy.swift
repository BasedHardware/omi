/// Recovery policy for the first shell window on launch.
///
/// SwiftUI may not have mounted the `main` scene by the time the application delegate receives
/// `applicationDidFinishLaunching`.  Keep the recovery finite and deterministic: ask SwiftUI for
/// the scene at the first probe, give it a few probes to mount, and periodically ask again in case
/// the environment action was not registered yet.
enum ShellWindowLaunchRecoveryPolicy {
  enum Decision: Equatable {
    case requestWindow
    case retry
    case stop
  }

  /// Twenty-one probes at the launch retry interval keep the recovery under five seconds while
  /// still covering slow profile restoration and freshly-created dev bundles.
  static let maxAttempt = 20
  private static let requestInterval = 5

  static func decision(for attempt: Int) -> Decision {
    guard attempt >= 0, attempt <= maxAttempt else { return .stop }
    return attempt.isMultiple(of: requestInterval) ? .requestWindow : .retry
  }
}
