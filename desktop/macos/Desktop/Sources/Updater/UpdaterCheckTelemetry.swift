import Foundation

/// The source of an individual Sparkle update check.
///
/// Sparkle does not include the source of a check in its delegate callbacks. The
/// view model records this before invoking Sparkle, while the delegate falls
/// back to `automatic` for checks started by Sparkle's own scheduler.
enum UpdateCheckTrigger: String, Equatable, Sendable {
  case automatic
  case manual
}

enum UpdateCheckResult: String, Equatable, Sendable {
  case noUpdate = "no_update"
  case updateAvailable = "update_available"
  /// An automatic housekeeping check observed that the Mac was offline. This
  /// is expected environmental unavailability, not an updater defect.
  case networkUnavailable = "network_unavailable"
  /// Sparkle admitted a later check without closing the prior callback chain.
  case callbackMissing = "callback_missing"
  case failed
}

/// Identity and bounded release metadata for one Sparkle update-check attempt.
struct UpdateCheckAttempt: Equatable, Sendable {
  let id: String
  let trigger: UpdateCheckTrigger
  let startedAt: Date
  let sourceAppVersion: String
  let sourceAppBuild: String
  let updateChannel: String

  var analyticsProperties: [String: Any] {
    [
      "attempt_id": id,
      "trigger": trigger.rawValue,
      "started_at": ISO8601DateFormatter().string(from: startedAt),
      "source_app_version": sourceAppVersion,
      "source_app_build": sourceAppBuild,
      "update_channel": updateChannel,
    ]
  }

  init(
    id: String,
    trigger: UpdateCheckTrigger,
    startedAt: Date,
    context: UpdateAnalyticsContext
  ) {
    self.id = id
    self.trigger = trigger
    self.startedAt = startedAt
    sourceAppVersion = context.sourceAppVersion
    sourceAppBuild = context.sourceAppBuild
    updateChannel = ["stable", "beta"].contains(context.updateChannel) ? context.updateChannel : "other"
  }
}

struct UpdateCheckTerminal: Equatable, Sendable {
  let attempt: UpdateCheckAttempt
  let result: UpdateCheckResult
  let durationSeconds: TimeInterval
  let diagnostics: UpdateFailureDiagnostics?

  var analyticsProperties: [String: Any] {
    var properties = attempt.analyticsProperties
    properties["result"] = result.rawValue
    properties["duration_seconds"] = durationSeconds
    if let diagnostics {
      // The authoritative terminal metric accepts only bounded diagnostics.
      // Keep the legacy event's human-readable message out of this payload.
      properties["update_failure_reason"] = diagnostics.reason.rawValue
      properties["update_failure_code"] = diagnostics.code
      properties["launch_location_bucket"] = diagnostics.launchLocationBucket
      if let nsurlErrorCode = diagnostics.nsurlErrorCode {
        properties["nsurl_error_code"] = nsurlErrorCode
      }
    }
    return properties
  }
}

/// Serializes Sparkle callbacks into one terminal outcome per check attempt.
///
/// Sparkle can deliver a duplicate `didAbortWithError` after a no-update callback.
/// Starts are registered only from Sparkle's admitted `mayPerform` boundary, where
/// its driver is serialized. Atomically consuming the identity therefore rejects
/// duplicate terminals without confusing a merely requested check for a real one.
final class UpdateCheckAttemptTracker: @unchecked Sendable {
  private let lock = NSLock()
  private let now: () -> Date
  private let makeID: () -> String
  private var active: UpdateCheckAttempt?
  /// Retain the most recent real terminal so Sparkle's duplicate callbacks
  /// can be classified from the original attempt rather than from a nil
  /// consume result.
  private var lastTerminal: UpdateCheckTerminal?

  init(
    now: @escaping () -> Date = Date.init,
    makeID: @escaping () -> String = { UUID().uuidString }
  ) {
    self.now = now
    self.makeID = makeID
  }

  /// Begins an actual Sparkle-admitted check. An active identity here means the
  /// prior driver lost its terminal callback, so close it explicitly before replacement.
  func begin(
    trigger: UpdateCheckTrigger,
    context: UpdateAnalyticsContext
  ) -> (attempt: UpdateCheckAttempt, abandoned: UpdateCheckTerminal?) {
    lock.lock()
    defer { lock.unlock() }

    let abandoned = active.map {
      UpdateCheckTerminal(
        attempt: $0,
        result: .callbackMissing,
        durationSeconds: max(0, now().timeIntervalSince($0.startedAt)),
        diagnostics: nil
      )
    }

    let attempt = UpdateCheckAttempt(
      id: makeID(),
      trigger: trigger,
      startedAt: now(),
      context: context
    )
    active = attempt
    return (attempt, abandoned)
  }

  /// Completes and consumes the active attempt. A second callback returns nil,
  /// making the exactly-one-terminal-outcome contract explicit.
  func finish(
    result: UpdateCheckResult,
    diagnostics: UpdateFailureDiagnostics? = nil
  ) -> UpdateCheckTerminal? {
    lock.lock()
    defer { lock.unlock() }

    guard let attempt = active else { return nil }
    active = nil
    let duration = max(0, now().timeIntervalSince(attempt.startedAt))
    let terminal = UpdateCheckTerminal(
      attempt: attempt,
      result: result,
      durationSeconds: duration,
      diagnostics: diagnostics
    )
    lastTerminal = terminal
    return terminal
  }

  /// Finish a failed Sparkle callback while separating expected automatic
  /// offline checks from genuine updater failures. Manual checks remain failed
  /// so the user still receives actionable feedback.
  func finishFailure(diagnostics: UpdateFailureDiagnostics) -> UpdateCheckTerminal? {
    lock.lock()
    defer { lock.unlock() }

    guard let attempt = active else { return nil }
    active = nil
    let result: UpdateCheckResult =
      attempt.trigger == .automatic && diagnostics.nsurlErrorCode == NSURLErrorNotConnectedToInternet
      ? .networkUnavailable : .failed
    let terminal = UpdateCheckTerminal(
      attempt: attempt,
      result: result,
      durationSeconds: max(0, now().timeIntervalSince(attempt.startedAt)),
      diagnostics: diagnostics
    )
    lastTerminal = terminal
    return terminal
  }

  /// Sparkle may deliver a duplicate abort after the first failure callback
  /// consumed the active attempt. Preserve the original trigger classification
  /// so an automatic offline check cannot be replayed as a user-visible error.
  func lastCompletedWasExpectedAutomaticOffline(for diagnostics: UpdateFailureDiagnostics) -> Bool {
    lock.lock()
    defer { lock.unlock() }

    guard let terminal = lastTerminal,
      terminal.result == .networkUnavailable,
      terminal.attempt.trigger == .automatic,
      diagnostics.nsurlErrorCode == NSURLErrorNotConnectedToInternet
    else { return false }
    return terminal.diagnostics?.nsurlErrorCode == diagnostics.nsurlErrorCode
  }

}

/// Emits updater lifecycle events without modifying the shared analytics
/// managers. Keeping this adapter updater-specific lets the terminal event carry
/// an attempt identity while `Update Check Failed` remains backward compatible.
enum UpdaterCheckTelemetry {
  static func recordStarted(_ attempt: UpdateCheckAttempt) {
    Task { @MainActor in
      PostHogManager.shared.track("Update Check Started", properties: attempt.analyticsProperties)
    }
  }

  static func recordCompleted(_ terminal: UpdateCheckTerminal) {
    Task { @MainActor in
      PostHogManager.shared.track("Update Check Completed", properties: terminal.analyticsProperties)
    }
  }
}
