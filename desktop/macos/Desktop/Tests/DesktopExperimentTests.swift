import XCTest

@testable import Omi_Computer

/// EXP-002 — desktop identity experiment (`control` vs `memory_v1`).
///
/// Pins the arm contract: which channels may enroll, how the local dogfood
/// override resolves, that failures never apply a treatment arm, and how the
/// arm binds Interject and the director through their existing gates.
final class DesktopExperimentTests: XCTestCase {
  // MARK: - Enrollment policy

  func testOnlyTheBetaProductionBundleRequestsEnrollment() {
    XCTAssertTrue(
      DesktopExperiment.shouldRequestEnrollment(isNonProduction: false, isBetaProductionBundle: true))
    // Stable stays control in v1.
    XCTAssertFalse(
      DesktopExperiment.shouldRequestEnrollment(isNonProduction: false, isBetaProductionBundle: false))
    // Named/dev bundles dogfood through the local override instead.
    XCTAssertFalse(
      DesktopExperiment.shouldRequestEnrollment(isNonProduction: true, isBetaProductionBundle: false))
  }

  func testForcedVariantAcceptsOnlyKnownArms() {
    XCTAssertEqual(
      DesktopExperiment.forcedVariant(environment: ["OMI_FORCE_EXPERIMENT_VARIANT": "memory_v1"]),
      "memory_v1")
    XCTAssertEqual(
      DesktopExperiment.forcedVariant(environment: ["OMI_FORCE_EXPERIMENT_VARIANT": "control"]),
      "control")
    XCTAssertEqual(
      DesktopExperiment.forcedVariant(environment: ["OMI_FORCE_EXPERIMENT_VARIANT": "  memory_v1  "]),
      "memory_v1")
    // A typo cannot invent an arm.
    XCTAssertNil(DesktopExperiment.forcedVariant(environment: ["OMI_FORCE_EXPERIMENT_VARIANT": "mem_v1"]))
    XCTAssertNil(DesktopExperiment.forcedVariant(environment: ["OMI_FORCE_EXPERIMENT_VARIANT": ""]))
    XCTAssertNil(DesktopExperiment.forcedVariant(environment: [:]))
  }

  // MARK: - Coordinator fail-closed

  @MainActor
  func testEnrollmentRefusalResolvesControlChromeWithoutAssignment() async {
    let coordinator = DesktopExperimentCoordinator()
    await coordinator.resolveForCurrentOwner()
    // This process is not a beta production bundle, so the channel gate
    // refuses before any network work: resolved, control chrome, no arm.
    XCTAssertEqual(coordinator.phase, .resolved)
    XCTAssertNil(coordinator.assignment)
    XCTAssertFalse(coordinator.isMemoryV1)
  }

  @MainActor
  func testEnvironmentOverrideAppliesTheArmLocally() {
    let coordinator = DesktopExperimentCoordinator()
    let environment = ["OMI_FORCE_EXPERIMENT_VARIANT": "memory_v1"]
    let variant = DesktopExperiment.forcedVariant(environment: environment)
    XCTAssertEqual(variant, "memory_v1")
    // The forced path resolves synchronously and never enrolls.
    coordinator.applyForTests(
      DesktopExperimentAssignment(variant: variant ?? "", source: .forcedLocal))
    XCTAssertTrue(coordinator.isMemoryV1)
    XCTAssertEqual(coordinator.phase, .resolved)
  }

  @MainActor
  func testOwnerChangeClearsTheArmSoItCannotLeakAcrossAccounts() {
    let coordinator = DesktopExperimentCoordinator()
    coordinator.applyForTests(DesktopExperimentAssignment(variant: "memory_v1", source: .enrolled))
    XCTAssertTrue(coordinator.isMemoryV1)
    coordinator.ownerDidChange()
    XCTAssertEqual(coordinator.phase, .pending)
    XCTAssertNil(coordinator.assignment)
    XCTAssertFalse(coordinator.isMemoryV1)
  }

  @MainActor
  func testInterjectIsOnOnlyForMemoryV1AmongArmedUsers() {
    let decision: (String?, Bool, Bool) -> Bool = {
      InterjectFeature.isEnabled(
        experimentVariant: $0, killSwitchEnabled: $1, unenrolledDecision: $2)
    }
    // memory_v1 turns it on; armed control turns it off.
    XCTAssertTrue(decision("memory_v1", false, false))
    XCTAssertFalse(decision("control", false, true))
    // The fleet kill switch disarms every arm.
    XCTAssertFalse(decision("memory_v1", true, true))
    // Un-armed users keep the existing dogfood decision untouched.
    XCTAssertTrue(decision(nil, false, true))
    XCTAssertFalse(decision(nil, false, false))
  }

  @MainActor
  func testPostcardLandingConsumesEachSummaryExactlyOnce() async throws {
    let defaults = try XCTUnwrap(
      UserDefaults(suiteName: "desktop-experiment-tests-\(UUID().uuidString)"))
    let box = SummaryBox()
    let store = HomeDailySummaryStore(
      ownerFence: { { true } },
      fetch: { _ in box.records },
      now: Date.init)
    let coordinator = ChatDailySummaryCoordinator(
      store: store,
      defaults: defaults,
      ownerID: { "owner-1" },
      cardSink: { _, _, _ in }
    )
    // No summary: never lands.
    XCTAssertFalse(coordinator.consumeUnseenSummaryForPostcardLanding())

    box.records = [
      DailySummaryRecord(id: "summary-1", date: "2026-09-02", headline: "h", overview: "o")
    ]
    await coordinator.refreshIfNeeded()
    XCTAssertEqual(store.latest?.id, "summary-1")

    // First consume lands, second does not — at most once per summary.
    XCTAssertTrue(coordinator.consumeUnseenSummaryForPostcardLanding())
    XCTAssertFalse(coordinator.consumeUnseenSummaryForPostcardLanding())

    // A new summary lands again.
    box.records = [
      DailySummaryRecord(id: "summary-2", date: "2026-09-03", headline: "h", overview: "o")
    ]
    await coordinator.refresh()
    XCTAssertEqual(store.latest?.id, "summary-2")
    XCTAssertTrue(coordinator.consumeUnseenSummaryForPostcardLanding())

    // The landing writes its own latch, not the notch-announcement latch:
    // neither consumes the other.
    let landedKey = ScopedDefaultsKey.dailySummaryPostcardLandedID(ownerID: "owner-1")
    XCTAssertEqual(defaults.string(forKey: landedKey), "summary-2")
  }
}

private final class SummaryBox: @unchecked Sendable {
  nonisolated(unsafe) var records: [DailySummaryRecord] = []
}
