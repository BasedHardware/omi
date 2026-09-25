import XCTest

@testable import Omi_Computer

final class AsyncFirstResolvedTests: XCTestCase {
  /// Regression: the dwell capture race must return when the fallback branch
  /// resolves even if the primary branch NEVER completes — `withTaskGroup`
  /// failed this (leaving the group awaits the stalled child).
  func testResolvesWhenOneBranchNeverCompletes() async {
    let result = await AsyncFirstResolved.run(
      { () async -> Int? in
        await withCheckedContinuation { (_: CheckedContinuation<Void, Never>) in
          // Never resumed: a stalled, cancellation-insensitive call.
        }
        return 1
      },
      { () async -> Int? in nil }
    )
    XCTAssertNil(result, "the fallback branch must win against a hung primary")
  }

  func testFastPrimaryWins() async {
    let result = await AsyncFirstResolved.run(
      { () async -> Int? in 42 },
      { () async -> Int? in
        await withCheckedContinuation { (_: CheckedContinuation<Void, Never>) in }
        return nil
      }
    )
    XCTAssertEqual(result, 42)
  }
}
