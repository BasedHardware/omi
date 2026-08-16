import XCTest

@testable import Omi_Computer

/// PERM-06: the `quit_and_reopen` bridge action must trigger the real
/// permission-flow "Quit & Reopen" restart (`AppState.restartApp()`) so a harness
/// can prove the same bundle relaunches with the session intact — NOT the
/// onboarding-mutating `reset_onboarding` path.
///
/// `restartApp()` spawns a relaunch and terminates the process, so it can't be
/// unit-run (it would kill the test host). These source-invariant guards pin the
/// action's registration, the non-prod gate, and that it drives the
/// session-preserving restart with the response-flush delay. The same-bundle /
/// session-intact runtime proof is the e2e / Codex lane (SKILL §2i).
final class QuitAndReopenActionTests: XCTestCase {
  private let actionName = "quit_and_reopen"

  func testActionIsRegisteredAndNonProdGated() throws {
    let source = try bridgeSource()
    XCTAssertTrue(
      source.contains("name: \"\(actionName)\""),
      "quit_and_reopen must be registered under its stable name")
    let block = try actionBlock()
    XCTAssertTrue(
      block.contains("guard AppBuild.isNonProduction"),
      "quit_and_reopen must refuse to run on production bundles")
  }

  func testTriggersTheSessionPreservingRestartNotOnboardingReset() throws {
    let block = try actionBlock()
    // The real permission-flow Quit & Reopen path is AppState.restartApp() — it
    // relaunches the same bundle without touching auth/onboarding.
    XCTAssertTrue(
      block.contains("appState.restartApp()"),
      "quit_and_reopen must drive AppState.restartApp() (the session-preserving restart)")
    // Must NOT use the onboarding-mutating restart, which is a different criterion.
    XCTAssertFalse(
      block.contains("resetOnboardingAndRestart"),
      "quit_and_reopen must not mutate onboarding state")
  }

  func testDelaysRestartSoTheResponseFlushesFirst() throws {
    let block = try actionBlock()
    // restartApp() terminates the process; schedule it after a delay so the HTTP
    // response is sent before the app dies — otherwise the caller sees a dropped
    // connection instead of the restart acknowledgement.
    guard let scheduleIdx = block.range(of: "asyncAfter"),
      let restartIdx = block.range(of: "appState.restartApp()")
    else {
      return XCTFail("quit_and_reopen must schedule restartApp() via asyncAfter")
    }
    XCTAssertTrue(
      scheduleIdx.lowerBound < restartIdx.lowerBound,
      "restartApp() must be scheduled (asyncAfter) rather than called inline")
    XCTAssertTrue(
      block.contains("\"restarting\": \"true\"") && block.contains("\"bundle_id\""),
      "quit_and_reopen must acknowledge the restart with the bundle id for before/after assertions")
  }

  // MARK: - Helpers

  private func actionBlock() throws -> String {
    let source = try bridgeSource()
    guard let start = source.range(of: "name: \"\(actionName)\"") else {
      throw XCTSkip("\(actionName) registration not found")
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
    return try String(contentsOf: url, encoding: .utf8)
  }
}
