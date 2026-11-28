import Foundation
import OmiNetwork

public extension FakeAPIClient {
    /// Logged to `settingsLog` as `fcm-token:<token>`.
    func saveNotificationToken(_ token: String, timeZone _: String, deviceIDHash _: String?) async throws {
        if let failure = lock.withLock({ _error }) { throw failure }
        lock.withLock { settingsLog.append("fcm-token:\(token)") }
    }
}
