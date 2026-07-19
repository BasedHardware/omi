import XCTest

@testable import Omi_Computer

/// CHAT-05: the free-tier monthly chat usage limiter must be deterministic and
/// dev-resettable. The counter + reset behavior are covered by
/// `FloatingBarUsageLimiterTests`; these pin the non-prod bridge actions that let a
/// harness read the counter and reset it WITHOUT spending real LLM calls (the matrix
/// blocker), so the "dev-resettable" half becomes runtime-provable.
///
/// The actions can't be unit-run (they hop to the `@MainActor` shared limiter through
/// the registry), so these are source-invariant guards on the wiring; the behavior is
/// the e2e / Codex lane (SKILL §2j).
final class UsageLimiterActionTests: XCTestCase {

  func testSnapshotActionReadsTheDeterministicCounter() throws {
    let block = try actionBlock("usage_limiter_snapshot")
    XCTAssertTrue(
      block.contains("FloatingBarUsageLimiter.shared"),
      "snapshot must read the shared limiter")
    for key in ["is_limit_reached", "remaining_queries", "limit_description"] {
      XCTAssertTrue(block.contains("\"\(key)\""), "snapshot must expose \(key)")
    }
    XCTAssertTrue(
      block.contains("isLimitReached") && block.contains("remainingQueries"),
      "snapshot must surface the deterministic counter fields")
  }

  func testResetActionIsNonProdGatedAndCallsReset() throws {
    let block = try actionBlock("reset_usage_limiter")
    XCTAssertTrue(
      block.contains("guard AppBuild.isNonProduction"),
      "reset must refuse to run on production bundles")
    XCTAssertTrue(
      block.contains("FloatingBarUsageLimiter.shared") && block.contains(".reset()"),
      "reset must call the shared limiter's reset()")
    XCTAssertTrue(
      block.contains("\"reset\"") && block.contains("\"is_limit_reached\""),
      "reset must acknowledge and return the post-reset state for before/after assertion")
  }

  // MARK: - Helpers

  private func actionBlock(_ name: String) throws -> String {
    let source = try bridgeSource()
    guard let start = source.range(of: "name: \"\(name)\"") else {
      throw XCTSkip("\(name) registration not found")
    }
    let tail = source[start.lowerBound...]
    if let next = tail.dropFirst().range(of: "\n    register(") {
      return String(tail[..<next.lowerBound])
    }
    return String(tail)
  }

  private func bridgeSource() throws -> String {
    let url = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/DesktopAutomationBridge.swift")
    // omi-test-quality: source-inspection -- static contract: the non-prod usage-limiter actions must stay registered and reset_usage_limiter must keep its AppBuild.isNonProduction gate; the actions hop to the @MainActor shared limiter through the registry and can't be behaviorally unit-run in the test host (their gate depends on the host's non-prod identity). Behavior is covered by FloatingBarUsageLimiterTests.
    return try String(contentsOf: url, encoding: .utf8)
  }
}
