import Foundation

/// Centralized configuration for event-driven data refresh.
/// All periodic polling timers have been removed — data refreshes on
/// app activation (didBecomeActiveNotification) and manual Cmd+R.
enum PollingConfig {
    /// Minimum time between app-activation conversation refreshes (seconds).
    /// Prevents cmd-tab spam from flooding the API.
    static let activationCooldown: TimeInterval = 60.0
}
