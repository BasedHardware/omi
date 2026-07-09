import XCTest

@testable import Omi_Computer

/// CHAT-02: a stalled agent must surface "Response took too long" within the 180s
/// send watchdog, not vanish silently.
///
/// The bug: the watchdog's own `interrupt()` resumes the in-flight request with
/// `BridgeError.stopped`, which the send-loop catch treated as a *user stop*
/// (silent) — releasing `isSending` before the watchdog could set its error. The
/// fix marks the watchdog-fired generation so the catch surfaces the timeout for
/// it while a genuine user Stop stays silent.
///
/// The full 180s race is a runtime path (Codex owns that proof). These lock in the
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

  // MARK: - Source-invariant: the marker is set before interrupt() and consumed by the catch

  func testWatchdogMarksGenerationBeforeInterrupting() throws {
    let source = try chatProviderSource()
    guard let watchdog = slice(
      source, from: "send watchdog fired at 180s", to: "// Fallback for the")
    else {
      throw XCTSkip("send watchdog block not found")
    }
    guard let markIdx = watchdog.range(of: "self.sendWatchdogFiredGeneration = sendGen"),
      let interruptIdx = watchdog.range(of: ".interrupt()")
    else {
      return XCTFail("watchdog must mark sendWatchdogFiredGeneration and call interrupt()")
    }
    XCTAssertTrue(
      markIdx.lowerBound < interruptIdx.lowerBound,
      "the watchdog must mark the generation BEFORE interrupt() resumes the request with .stopped")
  }

  func testStoppedCatchConsultsTheWatchdogMarker() throws {
    let source = try chatProviderSource()
    // The `.stopped` catch must gate on the marker and route through the shared
    // helper — so a future refactor can't silently re-treat a timeout as a user stop.
    XCTAssertTrue(
      source.contains("let watchdogFired = (sendWatchdogFiredGeneration == sendGen)"),
      "the .stopped catch must check the watchdog marker")
    XCTAssertTrue(
      source.contains("ChatProvider.stoppedTurnErrorMessage(watchdogFired: watchdogFired)"),
      "the .stopped catch must derive its message from the shared helper")
  }

  // MARK: - Helpers

  private func chatProviderSource() throws -> String {
    let url = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Providers/ChatProvider.swift")
    return try String(contentsOf: url, encoding: .utf8)
  }

  private func slice(_ source: String, from: String, to: String) -> String? {
    guard let start = source.range(of: from),
      let end = source[start.upperBound...].range(of: to)
    else { return nil }
    return String(source[start.lowerBound..<end.lowerBound])
  }
}
