import Foundation

/// Response contract for `POST /v1/desktop/experiments/enroll`
/// (`backend/routers/desktop_experiments.py`). `variant` is the persisted arm
/// name; `chromeEnabled` false paints control regardless of any assignment
/// (kill switch, gate refusal, or persist failure).
struct DesktopExperimentEnrollmentResponse: Decodable, Equatable {
  let variant: String?
  let enrolled: Bool
  let newlyEnrolled: Bool
  let chromeEnabled: Bool
  let reason: String

  enum CodingKeys: String, CodingKey {
    case variant, enrolled, reason
    case newlyEnrolled = "newly_enrolled"
    case chromeEnabled = "chrome_enabled"
  }
}

private struct DesktopExperimentEnrollBody: Encodable {
  let experimentId: String
  let channel: String
  let bundleId: String
  let appVersion: String
  let appBuild: String?
  let platform: String = "macos"

  enum CodingKeys: String, CodingKey {
    case channel, platform
    case experimentId = "experiment_id"
    case bundleId = "bundle_id"
    case appVersion = "app_version"
    case appBuild = "app_build"
  }
}

extension APIClient {
  /// Requests EXP-002 enrollment for the signed-in owner. Both arms resolve
  /// through this one call; the server emits `Experiment Enrolled` before the
  /// response, so enrollment lands before any treatment UI. The request
  /// timeout bounds launch blocking — a slow network resolves control
  /// (fail closed) rather than holding the splash.
  func enrollDesktopExperiment(
    experimentId: String,
    expectedOwnerId: String,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?
  ) async throws -> DesktopExperimentEnrollmentResponse {
    try await post(
      "v1/desktop/experiments/enroll",
      body: DesktopExperimentEnrollBody(
        experimentId: experimentId,
        channel: AppBuild.isBetaProductionBundle ? "beta" : "stable",
        bundleId: AppBuild.bundleIdentifier,
        appVersion: Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "",
        appBuild: Bundle.main.infoDictionary?["CFBundleVersion"] as? String),
      expectedOwnerId: expectedOwnerId,
      authorizationSnapshot: authorizationSnapshot,
      requestTimeout: DesktopExperimentCoordinator.enrollmentTimeout)
  }
}
