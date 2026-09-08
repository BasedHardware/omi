import Foundation

/// Feature gate for the persistent window-capture stream (`WindowCaptureStreamEngine`).
///
/// Why this exists: every one-shot `SCScreenshotManager.captureImage` with an app-built
/// `SCContentFilter(desktopIndependentWindow:)` opens a fresh capture session, and macOS
/// runs a full TCC authorization (with a `SecStaticCodeCheckValidity` pass) per session —
/// measured at 267 `kTCCServiceScreenCapture` requests in 180 s on a live machine. macOS
/// ties its periodic re-confirmation of app-built filters to session creation, so that
/// sampling rate makes the "Omi would like to record this computer's screen and audio"
/// dialog fire the moment it comes due, repeatedly. One long-lived `SCStream` collapses
/// that to one authorization per stream start. See
/// `docs/screencapture-consent-reprompt.md`.
///
/// Rollout shape (mirrors `ContextBucketsFeature`): non-production bundles default ON so
/// the dogfood channel exercises the stream engine, with an inverted env override
/// (`OMI_PERSISTENT_CAPTURE_STREAM=0` turns it off). Production reads the PostHog flag
/// fail-closed — a brand-new capture engine must not reach users before it has survived
/// dogfood — and because `PostHogManager` is MainActor-bound while the capture path is
/// not, the production value is resolved at monitoring start and cached behind a lock.
enum ScreenCaptureStreamFeature {
  static let flagName = "desktop_persistent_capture_stream"
  private static let localOverrideName = "OMI_PERSISTENT_CAPTURE_STREAM"

  private static let cacheLock = NSLock()
  /// Must be accessed only while holding cacheLock.
  nonisolated(unsafe) private static var cachedProductionEnabled: Bool?

  /// Resolve the production rollout flag where PostHog is reachable (MainActor) and
  /// cache it for the capture path. Called from `startMonitoring`; until the first
  /// resolution, production behaves as flag-off (fail closed).
  @MainActor static func resolveAndCache() {
    guard !AppBuild.isNonProduction else { return }
    let enabled = PostHogManager.shared.isFeatureEnabled(flagName)
    cacheLock.withLock { cachedProductionEnabled = enabled }
  }

  nonisolated static var isEnabled: Bool {
    if AppBuild.isNonProduction {
      return ProcessInfo.processInfo.environment[localOverrideName] != "0"
    }
    return cacheLock.withLock { cachedProductionEnabled } ?? false
  }

  // MARK: - Test seams

  nonisolated static func _setProductionCacheForTests(_ value: Bool?) {
    cacheLock.withLock { cachedProductionEnabled = value }
  }

  nonisolated static func _peekProductionCacheForTests() -> Bool? {
    cacheLock.withLock { cachedProductionEnabled }
  }
}
