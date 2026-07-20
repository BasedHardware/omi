import XCTest

@testable import Omi_Computer

/// CHAT-02: a stalled agent must surface "Response took too long" within the 60s
/// send watchdog, not vanish silently.
///
/// The bug: the watchdog's own `interrupt()` resumes the in-flight request with
/// `BridgeError.stopped`, which the send-loop catch treated as a *user stop*
/// (silent) — releasing `isSending` before the watchdog could set its error. The
/// fix marks the watchdog-fired generation so the catch surfaces the timeout for
/// it while a genuine user Stop stays silent.
///
/// The full 60s race is a runtime path (Codex owns that proof). These lock in the
/// load-bearing decision and its wiring hermetically.
final class ChatStallWatchdogTests: XCTestCase {

  // MARK: - Behavioral: the watchdog-vs-user-stop decision

  func testWatchdogStoppedSurfacesTimeoutMessage() {
    XCTAssertEqual(
      ChatProvider.stoppedTurnErrorMessage(watchdogFired: true),
      "Response took too long. Try again.")
  }

  func testUserStopStaysSilent() {
    XCTAssertNil(ChatProvider.stoppedTurnErrorMessage(watchdogFired: false))
  }

  func testToolStallStopSurfacesToolTimeoutMessage() {
    XCTAssertEqual(
      ChatProvider.stoppedTurnErrorMessage(watchdogFired: false, toolStallAbortFired: true),
      "A tool took too long. Try again.")
  }

  // MARK: - Source-invariant: the marker is set before interrupt() and consumed by the catch

  func testWatchdogMarksGenerationBeforeInterrupting() throws {
    // Anchored on the fix's own code tokens (not comment prose) and fails loudly
    // (never skips) if they drift. Whitespace-tolerant regex so auto-format churn
    // can't break the invariant.
    let source = try chatProviderSource()
    guard
      let mark = source.range(
        of: #"sendWatchdogFiredGeneration\s*=\s*sendGen"#, options: .regularExpression)
    else {
      return XCTFail("watchdog must mark the generation (sendWatchdogFiredGeneration = sendGen)")
    }
    // The interrupt that must come AFTER the mark is the watchdog's own call.
    // Searching from just past the mark proves the mark precedes it.
    guard
      source[mark.upperBound...].range(
        of: #"resolvedAgentClient\(\)\s*\.\s*interrupt\(\)"#, options: .regularExpression) != nil
    else {
      return XCTFail("watchdog must call interrupt() AFTER marking the generation")
    }
  }

  func testStoppedCatchConsultsTheWatchdogMarker() throws {
    let source = try chatProviderSource()
    // The `.stopped` catch must gate on the marker and route through the shared
    // helper — so a future refactor can't silently re-treat a timeout as a user
    // stop. Whitespace-tolerant regex so formatting changes don't false-fail.
    XCTAssertNotNil(
      source.range(
        of: #"watchdogFired\s*=\s*\(\s*sendWatchdogFiredGeneration\s*==\s*sendGen\s*\)"#,
        options: .regularExpression),
      "the .stopped catch must check the watchdog marker")
    XCTAssertNotNil(
      source.range(
        of:
          #"stoppedTurnErrorMessage\(\s*watchdogFired:\s*watchdogFired[\s\S]*?toolStallAbortFired:\s*toolStallAbortFired\s*\)"#,
        options: .regularExpression),
      "the .stopped catch must derive its message from the shared helper")
  }

  func testToolStallGuardMarksGenerationBeforeInterrupting() throws {
    let source = try chatProviderSource()
    guard
      let mark = source.range(
        of: #"sendToolStallAbortGeneration\s*=\s*sendGen"#, options: .regularExpression)
    else {
      return XCTFail("tool stall guard must mark the active generation")
    }
    XCTAssertNotNil(
      source[mark.upperBound...].range(
        of: #"resolvedAgentClient\(\)\s*\.\s*interrupt\(\)"#, options: .regularExpression),
      "tool stall guard must interrupt after marking its generation")
  }

  // MARK: - Helpers

  private func chatProviderSource() throws -> String {
    let url = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Providers/ChatProvider.swift")
    return try String(contentsOf: url, encoding: .utf8)
  }
}
