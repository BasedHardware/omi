import XCTest

@testable import Omi_Computer

final class ChatQuotaBannerTests: XCTestCase {

  private func quota(
    plan: String = "Operator",
    unit: String = "questions",
    used: Double,
    limit: Double? = 500,
    allowed: Bool = true,
    resetAt: Int? = 1_760_000_000,
    isOveragePlan: Bool? = true
  ) throws -> APIClient.ChatUsageQuota {
    var json: [String: Any] = [
      "plan": plan,
      "plan_type": "operator",
      "unit": unit,
      "used": used,
      "percent": 0,
      "allowed": allowed,
    ]
    if let limit { json["limit"] = limit }
    if let resetAt { json["reset_at"] = resetAt }
    if let isOveragePlan { json["is_overage_plan"] = isOveragePlan }
    let data = try JSONSerialization.data(withJSONObject: json)
    return try JSONDecoder().decode(APIClient.ChatUsageQuota.self, from: data)
  }

  private func banner(
    used: Double,
    limit: Double? = 500,
    plan: String = "Operator",
    unit: String = "questions",
    isOveragePlan: Bool? = true,
    optimisticDelta: Int = 0,
    dismissed: Set<String> = []
  ) throws -> ChatQuotaBanner? {
    ChatQuotaBanner.current(
      quota: try quota(
        plan: plan, unit: unit, used: used, limit: limit, isOveragePlan: isOveragePlan),
      optimisticDelta: optimisticDelta,
      dismissed: dismissed,
      now: Date(timeIntervalSince1970: 1_759_000_000))
  }

  // MARK: - Which threshold is showing

  func testBelowFirstThresholdShowsNothing() throws {
    XCTAssertNil(try banner(used: 449))
  }

  func testThresholdsAppearAsUsageClimbs() throws {
    XCTAssertEqual(try banner(used: 450)?.threshold, 90)
    XCTAssertEqual(try banner(used: 499)?.threshold, 90)
    XCTAssertEqual(try banner(used: 500)?.threshold, 100)
    XCTAssertEqual(try banner(used: 900)?.threshold, 100)
  }

  func testLocalSendsMoveTheBannerWithoutAServerSync() throws {
    XCTAssertNil(try banner(used: 445))
    XCTAssertEqual(try banner(used: 445, optimisticDelta: 5)?.threshold, 90)
  }

  func testCostQuotaIgnoresLocalSendCount() throws {
    // Architect meters dollars; a send carries no local cost estimate.
    let shown = try banner(
      used: 100, limit: 400, plan: "Architect", unit: "cost_usd", optimisticDelta: 300)
    XCTAssertNil(shown, "a dollar quota must not be advanced by counting sends")
  }

  func testCostQuotaWarnsWithDollarCopyAtAThreshold() throws {
    // The only surface that states dollars rather than questions, and the
    // branch the nil-below-threshold case above can never reach.
    let shown = try XCTUnwrap(
      try banner(used: 370, limit: 400, plan: "Architect", unit: "cost_usd"))
    XCTAssertEqual(shown.threshold, 90)
    XCTAssertEqual(
      shown.message, "$370.00 of your $400 Architect monthly spend used. Resets in 11 days.")
  }

  func testCostQuotaAtItsLimitStillBillsOverage() throws {
    let shown = try XCTUnwrap(
      try banner(used: 400, limit: 400, plan: "Architect", unit: "cost_usd"))
    XCTAssertEqual(shown.title, "Now billing overage")
    XCTAssertEqual(
      shown.message,
      "$400.00 of your $400 Architect monthly spend used. Extra usage is billed at the end of "
        + "your cycle. Resets in 11 days.")
  }

  func testUnlimitedQuotaNeverWarns() throws {
    XCTAssertNil(try banner(used: 9_000, limit: nil, plan: "Free (BYOK)"))
  }

  // MARK: - Copy

  func testOveragePlanAtLimitSaysItKeepsWorking() throws {
    let shown = try XCTUnwrap(try banner(used: 500))
    XCTAssertEqual(shown.title, "Now billing overage")
    XCTAssertTrue(shown.isBillingOverage)
    XCTAssertEqual(
      shown.message,
      "500 of 500 Operator questions used. Extra usage is billed at the end of your cycle. "
        + "Resets in 11 days.")
  }

  func testHardCappedPlanAtLimitSaysUpgrade() throws {
    let shown = try XCTUnwrap(
      try banner(used: 30, limit: 30, plan: "Free", isOveragePlan: false))
    XCTAssertEqual(shown.title, "Monthly limit reached")
    XCTAssertFalse(shown.isBillingOverage)
    XCTAssertEqual(
      shown.message, "30 of 30 Free questions used. Upgrade to keep chatting. Resets in 11 days.")
  }

  func testWarningThresholdNamesTheApproachAndStatesTheCountAndReset() throws {
    let shown = try XCTUnwrap(try banner(used: 475))
    XCTAssertEqual(shown.title, "Almost at your monthly limit")
    XCTAssertEqual(shown.message, "475 of 500 Operator questions used. Resets in 11 days.")
  }

  func testMeterPercentFloorsAndClampsToTheAllowance() throws {
    XCTAssertEqual(try banner(used: 475)?.percent, 95)
    // 499/500 must not render a full meter before the cap is actually reached.
    XCTAssertEqual(try banner(used: 499)?.percent, 99)
    XCTAssertEqual(try banner(used: 500)?.percent, 100)
    // Past the allowance the meter stays full rather than overshooting.
    XCTAssertEqual(try banner(used: 900)?.percent, 100)
  }

  func testSummaryIsTheCompactCountForTheSingleLineBanner() throws {
    XCTAssertEqual(try banner(used: 475)?.summary, "475 of 500 used")
    // Dollar plans meter the same line in the unit the plan bills in.
    let cost = try banner(used: 370, limit: 400, plan: "Architect", unit: "cost_usd")
    XCTAssertEqual(try XCTUnwrap(cost).summary, "$370 of $400 used")
  }

  func testMissingOverageFieldReadsAsHardCap() throws {
    // A server predating `is_overage_plan` must not promise overage billing.
    let shown = try XCTUnwrap(try banner(used: 500, isOveragePlan: nil))
    XCTAssertEqual(shown.title, "Monthly limit reached")
  }

  // MARK: - Dismissal

  func testDismissingOneThresholdHidesOnlyThatThreshold() throws {
    let atNinety = try XCTUnwrap(try banner(used: 460))
    let key = ChatQuotaBanner.dismissalKey(
      threshold: atNinety.threshold, cycleID: atNinety.cycleID)

    XCTAssertNil(try banner(used: 460, dismissed: [key]), "the dismissed threshold stays hidden")
    XCTAssertEqual(
      try banner(used: 500, dismissed: [key])?.threshold, 100,
      "crossing the next threshold speaks again")
  }

  func testDismissalExpiresWithTheBillingCycle() throws {
    let key = ChatQuotaBanner.dismissalKey(
      threshold: 90, cycleID: ChatQuotaBanner.cycleID(for: try quota(used: 475)))
    let nextCycle = ChatQuotaBanner.current(
      quota: try quota(used: 475, resetAt: 1_762_678_400),
      optimisticDelta: 0,
      dismissed: [key],
      now: Date(timeIntervalSince1970: 1_759_000_000))
    XCTAssertEqual(nextCycle?.threshold, 90, "a new cycle is not covered by last cycle's dismissal")
  }

  func testUpgradeUndoesADismissalTakenAgainstTheOldAllowance() throws {
    let key = ChatQuotaBanner.dismissalKey(
      threshold: 90, cycleID: ChatQuotaBanner.cycleID(for: try quota(used: 460)))
    XCTAssertNil(try banner(used: 460, dismissed: [key]))
    XCTAssertEqual(
      try banner(used: 900, limit: 1000, dismissed: [key])?.threshold, 90,
      "a bigger allowance is a different banner, not the dismissed one")
  }

  // MARK: - Reset copy

  func testResetTextCountsWholeDays() {
    let now = Date(timeIntervalSince1970: 1_760_000_000)
    XCTAssertEqual(ChatQuotaBanner.resetText(1_760_000_000, now: now), "Resets today")
    XCTAssertEqual(ChatQuotaBanner.resetText(1_760_090_000, now: now), "Resets tomorrow")
    XCTAssertEqual(ChatQuotaBanner.resetText(1_760_950_000, now: now), "Resets in 10 days")
    XCTAssertEqual(ChatQuotaBanner.resetText(nil, now: now), "Resets next month")
  }

  // MARK: - Dismissal store

  @MainActor
  func testStoreDropsDismissalsFromAnEarlierCycle() throws {
    // Only the current cycle can still be consulted, so the persisted set must
    // not accumulate an entry per threshold per month for the life of the user.
    let defaults = try XCTUnwrap(UserDefaults(suiteName: "chat-quota-store-\(UUID().uuidString)"))
    let store = ChatQuotaBannerDismissals(defaults: defaults)

    store.dismiss(threshold: 90, cycleID: "1000-500")
    store.dismiss(threshold: 100, cycleID: "1000-500")
    XCTAssertEqual(store.dismissed, ["90@1000-500", "100@1000-500"])

    store.dismiss(threshold: 90, cycleID: "2000-500")
    XCTAssertEqual(store.dismissed, ["90@2000-500"], "last cycle's dismissals are dropped")
  }

  @MainActor
  func testStorePersistsAcrossRelaunch() throws {
    let suite = "chat-quota-store-\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
    ChatQuotaBannerDismissals(defaults: defaults)
      .dismiss(threshold: 90, cycleID: "1000-500")

    let reloaded = ChatQuotaBannerDismissals(defaults: defaults)
    XCTAssertEqual(reloaded.dismissed, ["90@1000-500"], "a dismissal survives a relaunch")
  }
}
