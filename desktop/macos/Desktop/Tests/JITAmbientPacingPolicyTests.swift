import XCTest

@testable import Omi_Computer

final class JITAmbientPacingPolicyTests: XCTestCase {
  private let now = Date(timeIntervalSince1970: 1_777_248_000)

  private func input(
    used: Int, budget: Int = 8, lastSpentAgo: TimeInterval? = nil, derived: Bool = false
  ) -> JITAmbientPacingInput {
    JITAmbientPacingInput(
      usedToday: used,
      budget: budget,
      lastSpentAt: lastSpentAgo.map { now.addingTimeInterval(-$0) },
      now: now,
      derivedIntentMatched: derived)
  }

  func testBurstAllowanceThenSpacing() {
    XCTAssertEqual(JITAmbientPacingPolicy.decide(input(used: 0)), .spend)
    XCTAssertEqual(JITAmbientPacingPolicy.decide(input(used: 1, lastSpentAgo: 5)), .spend)
    // The measured failure: the third triage seconds after the second.
    XCTAssertEqual(
      JITAmbientPacingPolicy.decide(input(used: 2, lastSpentAgo: 30)),
      .deferred(reason: "ambient_paced"))
    XCTAssertEqual(
      JITAmbientPacingPolicy.decide(input(used: 2, lastSpentAgo: JITAmbientPacingPolicy.spacing(budget: 8))),
      .spend)
  }

  func testSpacingIsTheActiveDayDividedByTheBudget() {
    XCTAssertEqual(JITAmbientPacingPolicy.spacing(budget: 8), 2 * 60 * 60)
    XCTAssertEqual(JITAmbientPacingPolicy.spacing(budget: 0), JITAmbientPacingPolicy.activeDaySeconds)
  }

  func testReserveKeepsTheTailOfTheBudgetForStandingIntent() {
    let atReserve = input(used: 6, lastSpentAgo: 10 * 60 * 60)
    XCTAssertEqual(
      JITAmbientPacingPolicy.decide(atReserve), .deferred(reason: "ambient_reserved_for_intent"))
    XCTAssertEqual(
      JITAmbientPacingPolicy.decide(input(used: 6, lastSpentAgo: 10 * 60 * 60, derived: true)), .spend)
  }

  func testDerivedIntentBypassesSpacingNeverTheCap() {
    XCTAssertEqual(JITAmbientPacingPolicy.decide(input(used: 3, lastSpentAgo: 5, derived: true)), .spend)
    XCTAssertEqual(JITAmbientPacingPolicy.decide(input(used: 8, lastSpentAgo: 5, derived: true)), .exhausted)
    XCTAssertEqual(JITAmbientPacingPolicy.decide(input(used: 8)), .exhausted)
    XCTAssertEqual(JITAmbientPacingPolicy.decide(input(used: 0, budget: 0, derived: true)), .exhausted)
  }

  func testUnknownLastSpendNeverBlocksAfterTheBurst() {
    XCTAssertEqual(JITAmbientPacingPolicy.decide(input(used: 3, lastSpentAgo: nil)), .spend)
  }
}
