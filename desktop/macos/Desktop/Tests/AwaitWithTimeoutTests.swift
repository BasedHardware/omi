import XCTest

@testable import Omi_Computer

/// Ratchet for the automation-bridge `/state` hang fix: `awaitWithTimeout` must
/// bound the live MainActor refresh so a wedged main thread (e.g. a blocking
/// Keychain read during sign-in) can't hang the bridge. The load-bearing property
/// is that it returns at the timeout WITHOUT waiting for a non-cancellable, still-
/// running operation — a `withTaskGroup` implementation would deadlock here
/// because it awaits all child tasks at scope exit.
final class AwaitWithTimeoutTests: XCTestCase {
  func testReturnsOperationValueWhenItFinishesFirst() async {
    let result = await awaitWithTimeout(.seconds(5)) { "live" }
    XCTAssertEqual(result, "live")
  }

  func testReturnsNilWhenOperationExceedsTimeout() async {
    let start = Date()
    let result = await awaitWithTimeout(.milliseconds(50)) { () -> String in
      try? await Task.sleep(for: .seconds(10))
      return "late"
    }
    let elapsed = Date().timeIntervalSince(start)
    XCTAssertNil(result)
    XCTAssertLessThan(elapsed, 5.0, "must not wait out the full operation")
  }

  /// The regression guard. The operation blocks a background thread on a semaphore
  /// the test releases only AFTER asserting — so the operation is genuinely still
  /// running and non-cancellable when the timeout fires. `awaitWithTimeout` must
  /// still return promptly; a task-group version would hang until `gate.signal()`.
  func testReturnsAtTimeoutEvenWhenOperationIsBlockedAndNonCancellable() async {
    let gate = DispatchSemaphore(value: 0)
    let start = Date()
    let result = await awaitWithTimeout(.milliseconds(100)) { () -> String in
      await withCheckedContinuation { (continuation: CheckedContinuation<String, Never>) in
        DispatchQueue.global().async {
          gate.wait()  // stays blocked until the test releases it below
          continuation.resume(returning: "late")
        }
      }
    }
    let elapsed = Date().timeIntervalSince(start)
    XCTAssertNil(result, "must return nil at the timeout, not the blocked operation's value")
    XCTAssertLessThan(elapsed, 5.0, "must not wait for the blocked operation to finish")
    gate.signal()  // release the background thread so nothing leaks
  }

  // MARK: - Source-invariant wiring guard

  func testStateSnapshotUsesTheTimeoutFallback() throws {
    let source = try bridgeSource()
    guard let range = source.range(of: "private func liveAutomationSnapshot()") else {
      throw XCTSkip("liveAutomationSnapshot not found")
    }
    let body = String(source[range.lowerBound...].prefix(900))
    XCTAssertTrue(
      body.contains("awaitWithTimeout(liveSnapshotMainActorTimeout"),
      "/state must bound the MainActor hop with awaitWithTimeout")
    XCTAssertTrue(
      body.contains("cachedAutomationSnapshot()") && body.contains("snapshotStale = true"),
      "/state must fall back to the cached snapshot (marked stale) on timeout")
  }

  private func bridgeSource() throws -> String {
    let url = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/DesktopAutomationBridge.swift")
    return try String(contentsOf: url, encoding: .utf8)
  }
}
