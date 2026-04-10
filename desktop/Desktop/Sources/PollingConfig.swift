import Foundation

/// Centralized polling interval constants for all desktop auto-refresh timers.
/// Changing values here updates every timer that references them.
enum PollingConfig {
    /// Chat message polling interval (seconds). Syncs messages from other platforms.
    static let chatPollInterval: TimeInterval = 120.0

    /// Tasks auto-refresh interval (seconds). Guarded by page visibility.
    static let tasksPollInterval: TimeInterval = 120.0

    /// Memories auto-refresh interval (seconds). Guarded by page visibility.
    static let memoriesPollInterval: TimeInterval = 120.0

    /// Conversations auto-refresh interval (seconds).
    static let conversationsPollInterval: TimeInterval = 120.0

    /// Minimum time between app-activation conversation refreshes (seconds).
    static let activationCooldown: TimeInterval = 60.0
}
