import XCTest

@testable import Omi_Computer

final class ContextDeliveryAuthorityTests: XCTestCase {
  func testFreeGatesAreSingleAuthorityInputs() {
    XCTAssertEqual(
      ContextDeliveryBudget.freeGate(
        input: .init(
          masterEnabled: true, frequencyLevel: 3, snoozed: false, paywalled: false, minuteOfDay: 12 * 60,
          cooldownSeconds: 30 * 60)),
      .allowed)
    XCTAssertEqual(
      ContextDeliveryBudget.freeGate(
        input: .init(
          masterEnabled: true, frequencyLevel: 3, snoozed: false, paywalled: false, minuteOfDay: 23 * 60,
          cooldownSeconds: 30 * 60)),
      .quietHours)
    XCTAssertEqual(ContextDeliveryBudget.dailyLimit(frequencyLevel: 5), 20)
    let now = Date(timeIntervalSince1970: 1_725_000_000)
    XCTAssertTrue(
      ContextDeliveryBudget.isCoolingDown(
        lastDeliveredAt: now.addingTimeInterval(-60), now: now, cooldownSeconds: 30 * 60))
  }
}
