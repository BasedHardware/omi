import XCTest

@testable import Omi_Computer

/// BL-022 / S-14b: the privileged shell-out runner must report launch failures
/// and non-zero exits as structured outcomes (never silently swallow them like
/// the previous `try? process.run()`), and must bound + sanitize captured stderr.
/// Exercised hermetically via `/bin/sh` and a nonexistent path — no privileged
/// tools, no side effects.
final class SystemCommandTests: XCTestCase {
  func testSucceededOnZeroExit() {
    let outcome = SystemCommand.run(executable: "/bin/sh", arguments: ["-c", "exit 0"])
    XCTAssertEqual(outcome, .succeeded)
    XCTAssertTrue(outcome.isSuccess)
    XCTAssertEqual(outcome.summary, "ok")
  }

  func testExitedNonZeroCapturesCodeAndStderr() {
    let outcome = SystemCommand.run(
      executable: "/bin/sh", arguments: ["-c", "echo boom 1>&2; exit 3"])
    guard case let .exitedNonZero(code, stderr) = outcome else {
      return XCTFail("expected exitedNonZero, got \(outcome)")
    }
    XCTAssertEqual(code, 3)
    XCTAssertTrue(stderr.contains("boom"), "stderr snippet should carry the tool's message")
    XCTAssertFalse(outcome.isSuccess)
    XCTAssertTrue(outcome.summary.contains("exit 3"))
  }

  func testFailedToLaunchOnMissingExecutable() {
    let outcome = SystemCommand.run(
      executable: "/no/such/binary-\(UUID().uuidString)", arguments: [])
    guard case .failedToLaunch = outcome else {
      return XCTFail("expected failedToLaunch, got \(outcome)")
    }
    XCTAssertFalse(outcome.isSuccess)
    XCTAssertTrue(outcome.summary.hasPrefix("failed to launch"))
  }

  func testRunLoggingReturnsSuccessOnlyForZeroExit() {
    XCTAssertTrue(
      SystemCommand.runLogging("test ok", executable: "/bin/sh", arguments: ["-c", "exit 0"]))
    XCTAssertFalse(
      SystemCommand.runLogging("test fail", executable: "/bin/sh", arguments: ["-c", "exit 1"]))
  }

  func testSanitizerCollapsesWhitespaceAndTrims() {
    XCTAssertEqual(sanitizedCommandOutput("  hello\nworld\t!  "), "hello world !")
  }

  func testSanitizerBoundsLength() {
    let long = String(repeating: "x", count: 500)
    let bounded = sanitizedCommandOutput(long, maxLength: 200)
    XCTAssertEqual(bounded.count, 201)  // 200 chars + the single ellipsis
    XCTAssertTrue(bounded.hasSuffix("…"))
  }
}
