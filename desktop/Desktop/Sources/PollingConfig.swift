import Foundation

/// Centralized configuration for event-driven data refresh.
/// All periodic polling timers have been removed — data refreshes on
/// app activation (didBecomeActiveNotification) and manual Cmd+R.
enum PollingConfig {
    /// Minimum time between app-activation conversation refreshes (seconds).
    /// Prevents cmd-tab spam from flooding the API.
    static let activationCooldown: TimeInterval = 60.0

    /// Returns `true` when enough time has passed since `lastRefresh` to allow
    /// another activation-triggered refresh. Used by DesktopHomeView to throttle
    /// didBecomeActiveNotification bursts. Shared between production and tests
    /// so a regression (e.g. `>=` → `>`) is caught by the unit tests.
    static func shouldAllowActivationRefresh(now: Date = Date(), lastRefresh: Date) -> Bool {
        now.timeIntervalSince(lastRefresh) >= activationCooldown
    }
}
