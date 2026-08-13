import XCTest

@testable import Omi_Computer

final class ContextProactivityEngineTests: XCTestCase {
  func testDwellAdmissionTracksVisitsInsteadOfSuppressingARevisitToTheSameBucket() {
    var admission = ContextVisitDwellAdmission()

    XCTAssertTrue(admission.begin(visitID: 41))
    XCTAssertTrue(admission.begin(visitID: 42), "a new visit needs its own dwell timer")
    XCTAssertFalse(admission.begin(visitID: 42), "the same visit must not be scheduled twice")

    admission.finish(visitID: 41)
    admission.finish(visitID: 42)
    XCTAssertTrue(admission.begin(visitID: 42))
  }

  func testDirectorDecisionClampsUntrustedOutputBeforeDatabaseQueriesAndPresentation() {
    let decision = ContextDirectorDecision(
      decision: "suggest",
      title: String(repeating: "t", count: 500),
      message: String(repeating: "m", count: 1_000),
      reasoning: String(repeating: "r", count: 2_000),
      bucketEntryRefs: (0..<50).map { "entry:\($0)" },
      factIDs: (0..<50).map { "fact:\($0)" })

    let clamped = decision.clamped()

    XCTAssertEqual(clamped.title.count, 120)
    XCTAssertEqual(clamped.message.count, 600)
    XCTAssertEqual(clamped.reasoning.count, 1_200)
    XCTAssertEqual(clamped.bucketEntryRefs.count, 20)
    XCTAssertEqual(clamped.factIDs.count, 20)
  }

  @MainActor
  func testPresentationFreeGateRebuildSuppressesMasterAndQuietChanges() throws {
    let suiteName = "ContextProactivityEngineTests.\(UUID().uuidString)"
    guard let defaults = UserDefaults(suiteName: suiteName) else {
      XCTFail("failed to create isolated defaults suite")
      return
    }
    defer { defaults.removePersistentDomain(forName: suiteName) }

    defaults.set(true, forKey: NotificationService.masterEnabledDefaultsKey)
    defaults.set(3, forKey: NotificationService.frequencyDefaultsKey)
    defaults.set(8 * 60, forKey: NotificationService.activePeriodStartDefaultsKey)
    defaults.set(22 * 60, forKey: NotificationService.activePeriodEndDefaultsKey)

    let noonComponents = DateComponents(calendar: .current, year: 2026, month: 8, day: 12, hour: 12)
    let noon = noonComponents.date ?? Date()
    let lateComponents = DateComponents(calendar: .current, year: 2026, month: 8, day: 12, hour: 23)
    let late = lateComponents.date ?? Date()

    // Mirror the production rebuild path: capture gate inputs, then re-evaluate
    // after master/quiet flips before presentation.
    let allowed = ContextDeliveryGateInput(
      masterEnabled: defaults.bool(forKey: NotificationService.masterEnabledDefaultsKey),
      frequencyLevel: defaults.integer(forKey: NotificationService.frequencyDefaultsKey),
      snoozed: false,
      paywalled: false,
      minuteOfDay: 12 * 60,
      activePeriod: NotificationService.currentActivePeriod(defaults: defaults),
      cooldownSeconds: ContextDeliveryBudget.cooldownSeconds(frequencyLevel: 3))
    XCTAssertEqual(ContextDeliveryBudget.freeGate(input: allowed), .allowed)

    defaults.set(false, forKey: NotificationService.masterEnabledDefaultsKey)
    let noonMinute =
      try XCTUnwrap(Calendar.current.dateComponents([.hour, .minute], from: noon).hour) * 60
      + (try XCTUnwrap(Calendar.current.dateComponents([.hour, .minute], from: noon).minute))
    let masterOff = ContextDeliveryGateInput(
      masterEnabled: defaults.bool(forKey: NotificationService.masterEnabledDefaultsKey),
      frequencyLevel: defaults.integer(forKey: NotificationService.frequencyDefaultsKey),
      snoozed: false,
      paywalled: false,
      minuteOfDay: noonMinute,
      activePeriod: NotificationService.currentActivePeriod(defaults: defaults),
      cooldownSeconds: 0)
    XCTAssertEqual(ContextDeliveryBudget.freeGate(input: masterOff), .masterDisabled)

    defaults.set(true, forKey: NotificationService.masterEnabledDefaultsKey)
    let lateMinute =
      try XCTUnwrap(Calendar.current.dateComponents([.hour, .minute], from: late).hour) * 60
      + (try XCTUnwrap(Calendar.current.dateComponents([.hour, .minute], from: late).minute))
    let quiet = ContextDeliveryGateInput(
      masterEnabled: true,
      frequencyLevel: 3,
      snoozed: false,
      paywalled: false,
      minuteOfDay: lateMinute,
      activePeriod: NotificationService.currentActivePeriod(defaults: defaults),
      cooldownSeconds: 0)
    XCTAssertEqual(ContextDeliveryBudget.freeGate(input: quiet), .quietHours)
  }

  func testAttemptGateRebuildSuppressesBeforeBudgetReservation() {
    let allowed = ContextDeliveryGateInput(
      masterEnabled: true,
      frequencyLevel: 3,
      snoozed: false,
      paywalled: false,
      minuteOfDay: 12 * 60,
      cooldownSeconds: 0)
    XCTAssertEqual(ContextDeliveryBudget.freeGate(input: allowed), .allowed)

    let snoozed = ContextDeliveryGateInput(
      masterEnabled: true,
      frequencyLevel: 3,
      snoozed: true,
      paywalled: false,
      minuteOfDay: 12 * 60,
      cooldownSeconds: 0)
    XCTAssertEqual(ContextDeliveryBudget.freeGate(input: snoozed), .snoozed)

    let paywalled = ContextDeliveryGateInput(
      masterEnabled: true,
      frequencyLevel: 3,
      snoozed: false,
      paywalled: true,
      minuteOfDay: 12 * 60,
      cooldownSeconds: 0)
    XCTAssertEqual(ContextDeliveryBudget.freeGate(input: paywalled), .paywalled)
  }

  func testPresentationPreflightMustBeQueuedBeforeAnAttemptCanBegin() {
    XCTAssertTrue(ContextProactivityEngine.presentationSurfaceAvailable(.queued))
    XCTAssertFalse(ContextProactivityEngine.presentationSurfaceAvailable(.suppressed))
    XCTAssertFalse(ContextProactivityEngine.presentationSurfaceAvailable(.windowUnavailable))
    XCTAssertFalse(ContextProactivityEngine.presentationSurfaceAvailable(.rejectedOwnerChange))
    XCTAssertFalse(ContextProactivityEngine.presentationSurfaceAvailable(.presented))
  }
}
