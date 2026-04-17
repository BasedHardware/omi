import XCTest

@testable import Omi_Computer

@MainActor
final class FloatingBarUsageLimiterTests: XCTestCase {

  private func makeQuota(
    plan: String = "Free",
    unit: String = "questions",
    used: Double = 0,
    limit: Double? = 30,
    percent: Double = 0,
    allowed: Bool = true,
    resetAt: Int? = nil
  ) throws -> APIClient.ChatUsageQuota {
    var json: [String: Any] = [
      "plan": plan,
      "plan_type": "basic",
      "unit": unit,
      "used": used,
      "percent": percent,
      "allowed": allowed,
    ]
    if let limit { json["limit"] = limit }
    if let resetAt { json["reset_at"] = resetAt }
    let data = try JSONSerialization.data(withJSONObject: json)
    return try JSONDecoder().decode(APIClient.ChatUsageQuota.self, from: data)
  }

  // MARK: - No quota snapshot

  func testNoQuotaAllowsQuery() {
    let limiter = FloatingBarUsageLimiter()
    XCTAssertFalse(limiter.isLimitReached)
    XCTAssertEqual(limiter.remainingQueries, .max)
    XCTAssertEqual(limiter.limitDescription, "your monthly free message limit")
  }

  // MARK: - Question-based quota (Free / Operator / Unlimited)

  func testBelowLimitAllowsQuery() throws {
    let limiter = FloatingBarUsageLimiter()
    let quota = try makeQuota(plan: "Free", used: 10, limit: 30, percent: 33, allowed: true)
    limiter.applyQuota(quota)
    XCTAssertFalse(limiter.isLimitReached)
    XCTAssertEqual(limiter.remainingQueries, 20)
  }

  func testExactlyAtLimitBlocks() throws {
    let limiter = FloatingBarUsageLimiter()
    let quota = try makeQuota(plan: "Free", used: 30, limit: 30, percent: 100, allowed: true)
    limiter.applyQuota(quota)
    XCTAssertTrue(limiter.isLimitReached)
    XCTAssertEqual(limiter.remainingQueries, 0)
  }

  func testRecordQueryPushesToLimit() throws {
    let limiter = FloatingBarUsageLimiter()
    let quota = try makeQuota(plan: "Free", used: 29, limit: 30, percent: 96, allowed: true)
    limiter.applyQuota(quota)
    XCTAssertFalse(limiter.isLimitReached)
    XCTAssertEqual(limiter.remainingQueries, 1)

    limiter.recordQuery()
    XCTAssertTrue(limiter.isLimitReached)
    XCTAssertEqual(limiter.remainingQueries, 0)
  }

  func testServerDeniedBlocks() throws {
    let limiter = FloatingBarUsageLimiter()
    let quota = try makeQuota(plan: "Free", used: 30, limit: 30, percent: 100, allowed: false)
    limiter.applyQuota(quota)
    XCTAssertTrue(limiter.isLimitReached)
  }

  // MARK: - Cost-based quota (Architect / Pro)

  func testCostUsdDoesNotApplyOptimisticDelta() throws {
    let limiter = FloatingBarUsageLimiter()
    let quota = try makeQuota(
      plan: "Architect", unit: "cost_usd", used: 399, limit: 400, percent: 99, allowed: true)
    limiter.applyQuota(quota)
    XCTAssertFalse(limiter.isLimitReached)
    // recordQuery should NOT push to limit for cost_usd
    limiter.recordQuery()
    limiter.recordQuery()
    XCTAssertFalse(limiter.isLimitReached)
    XCTAssertEqual(limiter.remainingQueries, .max)
  }

  func testCostUsdServerDeniedBlocks() throws {
    let limiter = FloatingBarUsageLimiter()
    let quota = try makeQuota(
      plan: "Architect", unit: "cost_usd", used: 420, limit: 400, percent: 105, allowed: false)
    limiter.applyQuota(quota)
    XCTAssertTrue(limiter.isLimitReached)
  }

  // MARK: - limitDescription

  func testLimitDescriptionQuestions() throws {
    let limiter = FloatingBarUsageLimiter()
    let quota = try makeQuota(plan: "Free", used: 10, limit: 30, percent: 33, allowed: true)
    limiter.applyQuota(quota)
    XCTAssertEqual(limiter.limitDescription, "30 Free messages this month")
  }

  func testLimitDescriptionCostUsd() throws {
    let limiter = FloatingBarUsageLimiter()
    let quota = try makeQuota(
      plan: "Architect", unit: "cost_usd", used: 50, limit: 400, percent: 12, allowed: true)
    limiter.applyQuota(quota)
    XCTAssertEqual(limiter.limitDescription, "your $400 Architect monthly spend limit")
  }

  // MARK: - applyQuota resets optimistic delta

  func testApplyQuotaResetsOptimisticDelta() throws {
    let limiter = FloatingBarUsageLimiter()
    let quota = try makeQuota(plan: "Free", used: 10, limit: 30, percent: 33, allowed: true)
    limiter.applyQuota(quota)
    limiter.recordQuery()
    limiter.recordQuery()
    XCTAssertEqual(limiter.optimisticDelta, 2)

    let freshQuota = try makeQuota(plan: "Free", used: 12, limit: 30, percent: 40, allowed: true)
    limiter.applyQuota(freshQuota)
    XCTAssertEqual(limiter.optimisticDelta, 0)
    XCTAssertEqual(limiter.remainingQueries, 18)
  }

  // MARK: - reset() clears all state

  func testResetClearsAll() throws {
    let limiter = FloatingBarUsageLimiter()
    let quota = try makeQuota(plan: "Plus", used: 500, limit: 500, percent: 100, allowed: false)
    limiter.applyQuota(quota)
    limiter.applyPlan(plan: .unlimited, status: .active)
    limiter.recordQuery()
    XCTAssertTrue(limiter.hasPaidPlan)

    limiter.reset()
    XCTAssertNil(limiter.serverQuota)
    XCTAssertEqual(limiter.optimisticDelta, 0)
    XCTAssertFalse(limiter.hasPaidPlan)
    XCTAssertFalse(limiter.isLimitReached)
    XCTAssertEqual(limiter.remainingQueries, .max)
  }

  // MARK: - applyPlan

  func testApplyPlanBasicIsNotPaid() {
    let limiter = FloatingBarUsageLimiter()
    limiter.applyPlan(plan: .basic, status: .active)
    XCTAssertFalse(limiter.hasPaidPlan)
  }

  func testApplyPlanOperatorActiveIsPaid() {
    let limiter = FloatingBarUsageLimiter()
    limiter.applyPlan(plan: .operator, status: .active)
    XCTAssertTrue(limiter.hasPaidPlan)
  }

  func testApplyPlanInactiveIsNotPaid() {
    let limiter = FloatingBarUsageLimiter()
    limiter.applyPlan(plan: .operator, status: .inactive)
    XCTAssertFalse(limiter.hasPaidPlan)
  }
}
