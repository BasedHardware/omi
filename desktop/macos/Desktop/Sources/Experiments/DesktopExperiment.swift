import Foundation
import Sentry

/// EXP-002 — desktop identity experiment (`control` vs `memory_v1`).
///
/// One shell; the arm is a parameter pack. `control` is byte-identical to the
/// un-enrolled experience. `memory_v1` changes only wiring and defaults:
/// postcard-first landing, Interject on, director starved, generic web Q&A
/// starved in the agent prompt. See `backend/docs/experiments/EXP-002-desktop-identity-memory-v1.md`.
///
/// The experiment id is the assignment salt server-side: **never rename it**.
enum DesktopExperiment {
  static let experimentId = "EXP-002-desktop-identity-memory-v1"
  static let controlVariant = "control"
  static let memoryV1Variant = "memory_v1"

  /// Which launch paths may call the enrollment endpoint at all. v1 exposes
  /// the Beta bundle only; stable stays control until explicitly widened, and
  /// named/dev bundles exercise arms through the local environment override
  /// instead (they never enroll and never write assignments).
  static func shouldRequestEnrollment(isNonProduction: Bool, isBetaProductionBundle: Bool) -> Bool {
    isBetaProductionBundle && !isNonProduction
  }

  /// The local dogfood override for non-production bundles:
  /// `OMI_FORCE_EXPERIMENT_VARIANT=memory_v1` (or `control`). Returns nil for
  /// unknown values so a typo cannot invent an arm.
  static func forcedVariant(environment env: [String: String]) -> String? {
    guard let raw = env["OMI_FORCE_EXPERIMENT_VARIANT"]?.trimmingCharacters(in: .whitespaces),
      !raw.isEmpty
    else { return nil }
    return raw == memoryV1Variant || raw == controlVariant ? raw : nil
  }
}

/// The arm this launch renders, and where it came from. `enrolled` came from
/// the server-side assignment (persisted, both arms through one code path);
/// `forcedLocal` is a non-production dogfood override that never touched the
/// roster.
struct DesktopExperimentAssignment: Equatable {
  enum Source: String, Equatable {
    case enrolled
    case forcedLocal
  }

  let variant: String
  let source: Source

  var isMemoryV1: Bool { variant == DesktopExperiment.memoryV1Variant }
}

/// Resolves the arm once per owner, **before the main shell paints**, and
/// publishes it for every consumer (landing, Interject, director, chat
/// prompt, telemetry, Sentry, logs).
///
/// Fail-closed: any error, timeout, gate refusal, or kill switch resolves to
/// no assignment — the app then paints control chrome. A treatment arm that
/// cannot be confirmed is never applied.
@MainActor
final class DesktopExperimentCoordinator: ObservableObject {
  static let shared = DesktopExperimentCoordinator()

  enum Phase: Equatable {
    case pending
    case resolved
  }

  @Published private(set) var phase: Phase = .pending
  @Published private(set) var assignment: DesktopExperimentAssignment?

  /// Bounded so a slow network cannot hold the launch splash indefinitely;
  /// the request timeout resolves control (fail closed) and the next launch
  /// retries. Public for `APIClient+Experiments` to reuse.
  static let enrollmentTimeout: TimeInterval = 4.0

  private var inFlightOwnerID: String?

  var isMemoryV1: Bool { assignment?.isMemoryV1 == true }

  /// Non-production bundles resolve the arm from the launch environment.
  /// Never enrolled, never persisted — purely local chrome for dogfooding.
  func resolveFromLaunchEnvironment() {
    guard phase == .pending else { return }
    guard AppBuild.isNonProduction else { return }
    if let variant = DesktopExperiment.forcedVariant(environment: ProcessInfo.processInfo.environment) {
      apply(DesktopExperimentAssignment(variant: variant, source: .forcedLocal))
      log("DesktopExperiment: forced local arm \(variant) (OMI_FORCE_EXPERIMENT_VARIANT)")
    } else {
      resolveWithoutAssignment(reason: "non-production bundle without override")
    }
  }

  /// Requests server-side enrollment for the current owner. Idempotent: the
  /// backend returns the persisted assignment for an already-enrolled owner.
  func resolveForCurrentOwner() async {
    guard phase == .pending else { return }
    guard
      DesktopExperiment.shouldRequestEnrollment(
        isNonProduction: AppBuild.isNonProduction,
        isBetaProductionBundle: AppBuild.isBetaProductionBundle)
    else {
      resolveWithoutAssignment(reason: "channel does not enroll in v1")
      return
    }
    guard let ownerID = RuntimeOwnerIdentity.currentOwnerId() else {
      // No stable uid: unit-of-assignment is the Firebase uid, so there is
      // nothing to enroll. Control chrome, no retry this launch.
      resolveWithoutAssignment(reason: "no owner")
      return
    }
    guard
      let authorization = RuntimeOwnerIdentity.captureAuthorizationSnapshot(expectedOwnerID: ownerID)
    else {
      resolveWithoutAssignment(reason: "stale owner")
      return
    }
    inFlightOwnerID = ownerID

    do {
      let response = try await APIClient.shared.enrollDesktopExperiment(
        experimentId: DesktopExperiment.experimentId,
        expectedOwnerId: ownerID,
        authorizationSnapshot: authorization
      )
      guard inFlightOwnerID == ownerID else { return }
      if let variant = response.variant, response.chromeEnabled {
        apply(DesktopExperimentAssignment(variant: variant, source: .enrolled))
        log(
          "DesktopExperiment: enrolled variant=\(variant) newly=\(response.newlyEnrolled) reason=\(response.reason)"
        )
      } else {
        resolveWithoutAssignment(reason: response.reason)
      }
    } catch {
      guard inFlightOwnerID == ownerID else { return }
      // Fail closed to control chrome; the next launch retries.
      resolveWithoutAssignment(reason: "enrollment unavailable")
      log("DesktopExperiment: enrollment failed (\(type(of: error))) — painting control")
    }
  }

  /// Owner switch (account change): the previous owner's arm must not leak
  /// into the next owner's chrome. Resets to pending so the shell gate
  /// re-resolves.
  func ownerDidChange() {
    inFlightOwnerID = nil
    assignment = nil
    phase = .pending
  }

  // MARK: - Resolution

  private func apply(_ assignment: DesktopExperimentAssignment) {
    self.assignment = assignment
    phase = .resolved
    attachTelemetryContext(assignment)
  }

  /// Test seam for pinning an assignment without a bundle, backend, or
  /// PostHog. Deliberately skips telemetry attachment: tests assert
  /// coordinator state, not the telemetry context.
  func applyForTests(_ assignment: DesktopExperimentAssignment) {
    self.assignment = assignment
    phase = .resolved
  }

  private func resolveWithoutAssignment(reason: String) {
    assignment = nil
    phase = .resolved
    log("DesktopExperiment: control chrome (reason=\(reason))")
  }

  /// `experiment_id` + `variant` on every PostHog event (super-properties),
  /// every Sentry crash (scope tags), and every desktop log line.
  private func attachTelemetryContext(_ assignment: DesktopExperimentAssignment) {
    PostHogManager.shared.setExperimentContext(
      experimentId: DesktopExperiment.experimentId,
      variant: assignment.variant,
      forced: assignment.source == .forcedLocal)
    SentrySDK.configureScope { scope in
      scope.setTag(value: DesktopExperiment.experimentId, key: "experiment_id")
      scope.setTag(value: assignment.variant, key: "experiment_variant")
    }
    setLogExperimentContext(
      experimentId: DesktopExperiment.experimentId,
      variant: assignment.variant)
  }
}
