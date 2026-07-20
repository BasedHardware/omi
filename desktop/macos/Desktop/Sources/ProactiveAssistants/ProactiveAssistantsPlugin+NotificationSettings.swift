import Foundation
import UserNotifications

extension ProactiveAssistantsPlugin {
  /// Registers the system callback outside MainActor, then hands only its
  /// authorization status to a MainActor handler. `query` is injected so the
  /// off-main callback contract is exercised without a system permission prompt.
  nonisolated static func queryStartupNotificationSettings(
    query: @escaping @Sendable (@escaping @Sendable (UNAuthorizationStatus) -> Void) -> Void,
    handler: @escaping @MainActor @Sendable (UNAuthorizationStatus) -> Void,
    dispatchToMain: @escaping @Sendable (@escaping @MainActor @Sendable () -> Void) -> Void =
      dispatchNotificationCallbackToMain
  ) {
    query { authorizationStatus in
      dispatchToMain {
        handler(authorizationStatus)
      }
    }
  }

  /// UserNotifications invokes its callback on a private XPC queue. Dispatching
  /// explicitly to the main queue avoids inheriting that queue's executor into a
  /// Swift task before the MainActor handler runs.
  nonisolated private static func dispatchNotificationCallbackToMain(
    _ work: @escaping @MainActor @Sendable () -> Void
  ) {
    DispatchQueue.main.async {
      MainActor.assumeIsolated {
        work()
      }
    }
  }
}
