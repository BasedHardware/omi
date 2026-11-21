import OmiService
import UIKit

/// The app's half of `TransferLease`: the two calls iOS actually answers.
///
/// When the app leaves the foreground, iOS suspends it after a few seconds of grace; asking for a
/// background task buys a few more minutes, which is what a long read or upload needs to finish
/// rather than be cut. iOS decides how much time that is and can take it back early, so its expiry
/// handler is handed straight on to the lease.
extension TransferLease {
    /// The lease the running app uses for its transfers.
    static func app(name: String, log: DebugLog? = nil) -> TransferLease {
        let held = HeldBackgroundTask()
        return TransferLease(
            begin: { expiration in
                let identifier = UIApplication.shared.beginBackgroundTask(withName: name) {
                    // iOS is about to suspend the app: the time is gone, and the grant with it.
                    expiration()
                    held.end()
                }
                guard identifier != .invalid else { return false }
                held.begin(identifier)
                return true
            },
            end: { held.end() },
            log: log
        )
    }
}

/// The identifier of the grant in flight. iOS hands one out per `beginBackgroundTask` and that
/// identifier is the only handle for giving the time back, so both closures of the lease share it.
@MainActor
private final class HeldBackgroundTask {
    private var identifier: UIBackgroundTaskIdentifier = .invalid

    func begin(_ identifier: UIBackgroundTaskIdentifier) {
        self.identifier = identifier
    }

    /// Gives the grant back. Safe from both sides: whoever gets there first clears the identifier,
    /// so the second call is a no-op rather than an `endBackgroundTask` on a stale one.
    func end() {
        guard identifier != .invalid else { return }
        let ending = identifier
        identifier = .invalid
        UIApplication.shared.endBackgroundTask(ending)
    }
}
