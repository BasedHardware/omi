import XCTest

@testable import Omi_Computer

/// CHAT-02 recovery: after a watchdog-fired stall, `resume_agent_stream` must
/// return promptly and a follow-up ask must complete.
///
/// The bug: `AgentRuntimeProcess` is an actor and `sendJson()` does a blocking
/// stdin write; when the agent is frozen (SIGSTOP) and a query fills the pipe, the
/// actor blocks on that write — and the resume/auto-resume SIGCONT, being
/// actor-isolated, could never run, deadlocking the agent permanently. The fix
/// routes the SIGCONT through an off-actor `DebugSuspendControl` and makes
/// `debugResumeStream` `nonisolated`.
///
/// These tests pin the control's generation/disarm logic hermetically (injected
/// signal, no real `kill`) and pin the off-actor wiring via source invariants. The
/// full stall→resume→recover runtime path is the e2e / Codex lane (SKILL §2e).
final class ChatStallRecoveryTests: XCTestCase {

  // MARK: - DebugSuspendControl behavior (hermetic; signal injected)

  private func makeControl() -> (DebugSuspendControl, () -> [pid_t]) {
    let box = SignalBox()
    let control = DebugSuspendControl(sendContinue: { box.record($0) })
    return (control, { box.signalled })
  }

  func testResumeSignalsArmedPidThenClears() {
    let (control, signalled) = makeControl()
    _ = control.arm(pid: 42)
    XCTAssertEqual(control.resume(), 42)
    XCTAssertEqual(signalled(), [42], "resume must SIGCONT the armed pid")
    XCTAssertNil(control.resume(), "a second resume with nothing armed returns nil")
  }

  func testAutoResumeRespectsGeneration() {
    let (control, signalled) = makeControl()
    let gen = control.arm(pid: 7)
    XCTAssertEqual(control.autoResume(generation: gen), 7)
    XCTAssertEqual(signalled(), [7])
  }

  func testStaleAutoResumeDoesNotSignal() {
    let (control, signalled) = makeControl()
    let old = control.arm(pid: 7)
    _ = control.arm(pid: 8)  // newer suspend advances the generation
    XCTAssertNil(control.autoResume(generation: old), "a stale auto-resume must no-op")
    XCTAssertEqual(signalled(), [], "no SIGCONT for a superseded generation")
  }

  func testExplicitResumeCancelsPendingAutoResume() {
    let (control, signalled) = makeControl()
    let gen = control.arm(pid: 5)
    XCTAssertEqual(control.resume(), 5)          // advances generation
    XCTAssertNil(control.autoResume(generation: gen), "auto-resume after explicit resume must no-op")
    XCTAssertEqual(signalled(), [5], "only the explicit resume signals")
  }

  func testDisarmPreventsResumeSignalingAReusedPid() {
    let (control, signalled) = makeControl()
    _ = control.arm(pid: 9)
    control.disarm()  // process torn down
    XCTAssertNil(control.resume())
    XCTAssertEqual(signalled(), [], "a disarmed control must not SIGCONT a (possibly reused) pid")
  }

  // MARK: - Source-invariant: the SIGCONT resume path is off the actor

  func testResumeIsNonisolatedAndRoutedThroughTheControl() throws {
    let source = try agentRuntimeSource()
    XCTAssertTrue(
      source.contains("nonisolated func debugResumeStream"),
      "debugResumeStream must be nonisolated so it isn't starved by a blocked actor")
    XCTAssertTrue(
      source.contains("debugSuspend.resume()"),
      "debugResumeStream must resume via the off-actor control")
  }

  func testAutoResumeRunsOffActorAndTeardownDisarms() throws {
    let source = try agentRuntimeSource()
    XCTAssertTrue(
      source.contains("debugSuspend.autoResume(generation:"),
      "the safety auto-resume must go through the off-actor control, not an actor-isolated method")
    // No actor-isolated autoResumeStream should remain to be starved.
    XCTAssertFalse(
      source.contains("func autoResumeStream"),
      "the actor-isolated autoResumeStream must be gone")
    XCTAssertTrue(
      source.contains("debugSuspend.disarm()"),
      "process teardown (closePipes) must disarm the control so resume can't hit a reused pid")
  }

  // MARK: - Helpers

  private func agentRuntimeSource() throws -> String {
    let url = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Chat/AgentRuntimeProcess.swift")
    return try String(contentsOf: url, encoding: .utf8)
  }
}

private final class SignalBox: @unchecked Sendable {
  private let lock = NSLock()
  private var pids: [pid_t] = []
  func record(_ pid: pid_t) {
    lock.lock(); defer { lock.unlock() }
    pids.append(pid)
  }
  var signalled: [pid_t] {
    lock.lock(); defer { lock.unlock() }
    return pids
  }
}
