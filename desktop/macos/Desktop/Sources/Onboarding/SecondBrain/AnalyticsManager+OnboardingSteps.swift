import Foundation

/// One event per live Second Brain onboarding step. Bounded dimensions only: the
/// step's enum name, its index, dwell time, whether it was skipped, how it was
/// exited, and — for the seven permission steps — which permission and whether
/// it was granted. Never names, roles, page copy, or other free text.
enum OnboardingStepTelemetry {
  static let eventName = "Onboarding Step Completed"

  /// How the step was left. Closed set: a skip-rate on `skipped` cannot tell a
  /// user "Skip for now" from a permission page the user never saw.
  enum ExitReason: String, Equatable, CaseIterable {
    /// The user completed the step (answered, granted, continued).
    case answered
    /// The user declined the step, or used skip-the-rest.
    case skipped
    /// `firstUnaskedStep` jumped this permission because it was already granted.
    case autoGranted = "auto_granted"
  }

  /// The allow-list this event may never grow past without a deliberate review.
  /// Asserted by the boundary test so a future emitter cannot attach a name,
  /// a role, or a page title.
  static let allowedKeys: Set<String> = [
    "step", "index", "elapsed_ms", "skipped", "exit_reason", "permission", "granted",
  ]

  static func payload(
    step: String,
    index: Int,
    elapsedMs: Int,
    skipped: Bool,
    exitReason: ExitReason,
    permission: String?,
    granted: Bool?
  ) -> [String: Any] {
    var properties: [String: Any] = [
      "step": step,
      "index": index,
      "elapsed_ms": max(0, elapsedMs),
      "skipped": skipped,
      "exit_reason": exitReason.rawValue,
    ]
    if let permission { properties["permission"] = permission }
    if let granted { properties["granted"] = granted }
    return properties
  }

  /// Test seam: nil in production. Scoped by the test that installs it.
  @MainActor static var captureForTests: ((String, [String: Any]) -> Void)?
  /// Injected clock so dwell-time tests do not wait on the wall clock.
  @MainActor static var now: () -> Date = Date.init
}

extension SBOnboardingModel.Step {
  /// PostHog `step` property. The enum case name is the contract with the admin
  /// funnel; renaming a case must break `SBOnboardingStepTelemetryTests`.
  var analyticsName: String { String(describing: self) }
}

extension AnalyticsManager {
  /// One event per step exit, including skips. See `OnboardingStepTelemetry`.
  func onboardingStepExited(
    step: String,
    index: Int,
    elapsedMs: Int,
    skipped: Bool,
    exitReason: OnboardingStepTelemetry.ExitReason,
    permission: String?,
    granted: Bool?
  ) {
    let properties = OnboardingStepTelemetry.payload(
      step: step,
      index: index,
      elapsedMs: elapsedMs,
      skipped: skipped,
      exitReason: exitReason,
      permission: permission,
      granted: granted)
    OnboardingStepTelemetry.captureForTests?(OnboardingStepTelemetry.eventName, properties)
    PostHogManager.shared.track(OnboardingStepTelemetry.eventName, properties: properties)
  }
}

extension SBOnboardingModel {
  /// Fire the current step's event. `skipped` is inferred from the permission
  /// outcome when this is a permission step; pass an override for the rest-of-
  /// onboarding escape hatch, which exits a non-permission step as a skip.
  func recordStepExit(skipped skippedOverride: Bool? = nil) {
    guard !stepExitRecorded else { return }
    stepExitRecorded = true
    let permission = permissionKey(for: step)
    let granted = permission.map { permState($0) == .on }
    let skipped = skippedOverride ?? (granted.map { !$0 } ?? false)
    AnalyticsManager.shared.onboardingStepExited(
      step: step.analyticsName,
      index: step.rawValue,
      elapsedMs: Int(OnboardingStepTelemetry.now().timeIntervalSince(stepStartedAt) * 1_000),
      skipped: skipped,
      exitReason: skipped ? .skipped : .answered,
      permission: permission,
      granted: granted)
  }

  /// Permission steps `firstUnaskedStep` jumps because they are already granted
  /// still have to appear in the sequential funnel, or a pre-granted mic looks
  /// like a drop-off. Elapsed time is zero: the user never saw the page.
  /// `skipped` stays true so existing funnel math still counts the step as
  /// reached; `exit_reason` is `auto_granted` so a skip-rate does not.
  func recordJumpedPermissionSteps(from intended: Step, to landed: Step) {
    guard intended.rawValue < landed.rawValue else { return }
    for raw in intended.rawValue..<landed.rawValue {
      guard let jumped = Step(rawValue: raw), let permission = permissionKey(for: jumped) else {
        continue
      }
      AnalyticsManager.shared.onboardingStepExited(
        step: jumped.analyticsName,
        index: jumped.rawValue,
        elapsedMs: 0,
        skipped: true,
        exitReason: .autoGranted,
        permission: permission,
        granted: true)
    }
  }
}
