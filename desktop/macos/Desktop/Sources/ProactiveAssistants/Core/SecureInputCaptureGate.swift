import Foundation

/// Decides, once per capture tick, whether Omi must skip screen capture because macOS
/// reports **secure keyboard entry** active — the process-wide flag an app raises while a
/// password field holds focus (browser logins, `sudo`, the login window, 2FA prompts).
///
/// `RewindSettings.defaultExcludedApps` can only name password managers someone thought to
/// list; secure input is raised by every app that handles a credential correctly, including
/// a web form inside a browser that is otherwise captured normally. Both feed the same
/// privacy gate established by #7098 — an excluded frame reaches no consumer.
///
/// A short backoff after the flag clears covers the frames where the credential is still
/// on screen (reveal-password toggles, a filled field) before the app redraws.
///
/// An app can fail to clear the flag on exit, which would pause capture indefinitely.
/// `stuckThreshold` does not change the decision — privacy still wins — but it reports once
/// per continuous run so the pause is visible instead of silent.
struct SecureInputCaptureGate {
  enum Decision: Equatable {
    case capture
    /// `reportStuck` is true exactly once per continuous active run that outlives
    /// `stuckThreshold`, so a stuck flag costs one telemetry event rather than one per tick.
    case skip(reportStuck: Bool)
  }

  private var gate = ProactiveScreenshotCaptureGate()
  private var activeSince: Date?
  private var didReportStuck = false

  mutating func nextDecision(
    isSecureInputActive: Bool,
    now: Date,
    backoffDuration: TimeInterval,
    stuckThreshold: TimeInterval
  ) -> Decision {
    var reportStuck = false
    if isSecureInputActive {
      let since = activeSince ?? now
      activeSince = since
      if !didReportStuck, now.timeIntervalSince(since) >= stuckThreshold {
        didReportStuck = true
        reportStuck = true
      }
    } else {
      activeSince = nil
      didReportStuck = false
    }

    switch gate.nextDecision(
      isScreenshotAppFrontmost: isSecureInputActive,
      now: now,
      backoffDuration: backoffDuration
    ) {
    case .pause, .resumeIntoBackoff, .continueBackoff:
      return .skip(reportStuck: reportStuck)
    case .resumeAndCapture, .capture:
      return .capture
    }
  }

  mutating func reset() {
    gate.reset()
    activeSince = nil
    didReportStuck = false
  }

  /// Records the one-shot report for a flag an app never cleared. Kept beside the gate so the
  /// capture loop keeps a single call site.
  static func reportStuckFlag(threshold: TimeInterval) {
    DesktopDiagnosticsManager.shared.recordFallback(
      area: "screen_capture",
      from: "capture",
      to: "paused",
      reason: "policy",
      outcome: .degraded,
      extra: ["signal": "secure_input_stuck"]
    )
    log(
      "SecureInputGate: secure keyboard entry still active after \(Int(threshold))s — capture stays paused"
    )
  }
}
