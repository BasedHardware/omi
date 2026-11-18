import XCTest

@testable import Omi_Computer

/// CHAT-02: a silent bridge with no active tool must surface "Response took too
/// long" after the 60s generic watchdog, not vanish silently.
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
      "A tool stopped reporting progress. Try again.")
  }

  func testGenericWatchdogDefersToAnActiveTool() throws {
    let source = try chatProviderSource()
    XCTAssertTrue(source.contains("genericWatchdogInactivityMs = 60_000"))
    XCTAssertTrue(
      source.contains("stallDetector.isSilentWithoutActiveTools"),
      "An active tool owns its no-progress timeout before the generic bridge watchdog can fire")
  }

  func testTurnActivityRefreshesTheSilentBridgeClock() throws {
    let source = try chatProviderSource()
    XCTAssertNotNil(
      source.range(
        of:
          #"let\s+turnActivityHandler[\s\S]*?stallDetector\.step\([\s\S]*?kind:\s*\.other[\s\S]*?onTurnActivity:\s*turnActivityHandler"#,
        options: .regularExpression
      ),
      "content-free runtime activity must refresh the detector and reach the active query"
    )
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

  /// A device tool approval card waiting on the person must never count as a
  /// stalled tool: the tick loop tells the detector about the wait before it
  /// asks which tools are overdue, so the 90 s abort cannot fire under a card.
  func testToolStallGuardPausesWhileAnApprovalCardIsPending() throws {
    let source = try chatProviderSource()
    guard
      let wait = source.range(
        of: #"stallDetector\.setWaitingOnUser\(waitingOnUser,\s*atMs:\s*nowMs\)"#, options: .regularExpression)
    else {
      return XCTFail("the stall tick loop must tell the detector when a card is waiting on the person")
    }
    XCTAssertNotNil(
      source[wait.upperBound...].range(
        of: #"stallDetector\.toolIdsWithoutProgress\("#, options: .regularExpression),
      "the overdue-tool check must run after the detector knows about the wait")
    XCTAssertNotNil(
      source[..<wait.lowerBound].range(of: "ChatProvider.hasPendingToolApproval(sessionId: turnSessionId)"),
      "the wait must come from the approval store, keyed by the turn's own session, not a timer")
    XCTAssertNotNil(
      source.range(of: "let turnSessionId = pinnedSession.sessionId"),
      "the session is the one the turn resolved for its surface, so a pill or workstream turn sees its own card")
  }

  /// A card raised on the agent pill's session pauses that turn's guard; the
  /// main chat's session, with no card, does not. The check is keyed by the
  /// session the turn resolved, never by the main chat surface.
  @MainActor
  func testAPendingCardOnThePillSessionPausesThatTurnAndNotTheMainChat() throws {
    let store = DesktopToolApprovalStore.shared
    store.reset()
    defer { store.reset() }
    let frame = try XCTUnwrap(
      AgentRuntimeProcess.RuntimeMessage.parse(
        #"{"type":"approval_requested","protocolVersion":2,"approvalId":"disp_pill","ownerId":"o","sessionId":"ses_pill","runId":"run_pill","attemptId":"a","invocationId":"i","adapterId":"pi-mono","surfaceKind":"floating_pill","toolName":"send_message","capability":"desktop.messaging.send","operation":"send_message","resourceRef":"+1","title":"Send a message","decisionPrompt":"Send?","preview":{"to":"+1","text":"hi"},"options":[{"id":"allow_once","effect":"allow","scope":"once"},{"id":"deny","effect":"deny","scope":"once"}],"defaultOptionId":"deny","requestedAtMs":1,"expiresAtMs":9999999999999}"#
      ))
    store.ingest(message: frame)

    XCTAssertTrue(ChatProvider.hasPendingToolApproval(sessionId: "ses_pill"))
    XCTAssertFalse(ChatProvider.hasPendingToolApproval(sessionId: "ses_main"))
    XCTAssertFalse(ChatProvider.hasPendingToolApproval(sessionId: nil))

    let resolved = try XCTUnwrap(
      AgentRuntimeProcess.RuntimeMessage.parse(
        #"{"type":"approval_resolved","protocolVersion":2,"approvalId":"disp_pill","ownerId":"o","sessionId":"ses_pill","runId":"run_pill","attemptId":"a","invocationId":"i","toolName":"send_message","decision":"deny","selectedOptionId":"deny","grantId":null,"resolvedBy":"user","resolvedAtMs":2,"automatic":false}"#
      ))
    store.ingest(message: resolved)
    XCTAssertFalse(
      ChatProvider.hasPendingToolApproval(sessionId: "ses_pill"), "a closed card no longer pauses the guard")
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
