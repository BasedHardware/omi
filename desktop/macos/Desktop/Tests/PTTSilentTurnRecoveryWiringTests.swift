import XCTest

@testable import Omi_Computer

/// Regression for issue #9081: PTT hold turns on a dead mic reported
/// `recovery_action=none / recovery_result=not_attempted` for hundreds of users.
///
/// Root cause: the two buffered silent-turn exits — `commitBufferedRealtimeHubTurn`
/// (`source: "buffered_hub"`) and `transcribeBufferedWarmWaitAudio`
/// (`source: "warm_wait_fallback"`) — discarded near-silent turns without ever
/// feeding `silentMicRecoveryPolicy.recordDiscardedTurn` or requesting a CoreAudio
/// capture rebuild, unlike the primary hub/omni/batch gates. A user whose turns
/// landed on the warm-wait path could never accumulate toward recovery.
///
/// `PushToTalkManager` is a `@MainActor` singleton not constructible in a unit test,
/// so this is a source-scrape guard (same pattern as `PTTAudioCaptureRaceTests`).
/// The invariant: every `recordPTTSilentTurn` discard site reports a recovery
/// decision and every discard is counted by the recovery policy.
final class PTTSilentTurnRecoveryWiringTests: XCTestCase {
  func testEverySilentTurnSiteWiresRecovery() throws {
    let source = try managerSource()

    // Every silent-turn record must carry an explicit recovery decision — no site
    // may fall back to the `recoveryAction: "none"` default silently.
    let silentTurnCalls = source.components(separatedBy: "recordPTTSilentTurn(").count - 1
    let recoveryDecisions = source.components(separatedBy: "recoveryResult: recoveryDecision.shouldRebuildCapture").count - 1
    XCTAssertEqual(
      silentTurnCalls, recoveryDecisions,
      "Every recordPTTSilentTurn site must pass the production recovery decision")

    // Every discard must be counted toward the dead-mic threshold so recovery can
    // eventually trip, and each site attempts a capture rebuild once tripped.
    XCTAssertEqual(
      source.components(separatedBy: "silentMicRecoveryPolicy.recordDiscardedTurn").count - 1,
      silentTurnCalls,
      "Every silent-turn discard must call recordDiscardedTurn")
    XCTAssertEqual(
      source.components(separatedBy: "requestCoreAudioCaptureRecovery(reason: \"repeated dead-mic PTT turns\"").count - 1,
      silentTurnCalls,
      "Every silent-turn discard must guard a capture rebuild")

    // A rebuild is not proven by being invoked: each silent discard and each
    // accepted audible turn must resolve the pending recovery through the shared
    // diagnostics surface on its next judgeable result.
    let recoveryOutcomeRecords = source.components(
      separatedBy: "recordSilentMicRecoveryOutcome(").count - 2
    let successfulTurns = source.components(
      separatedBy: "silentMicRecoveryPolicy.recordSuccessfulTurn()").count - 1
    XCTAssertEqual(
      recoveryOutcomeRecords,
      silentTurnCalls + successfulTurns,
      "Every judgeable PTT turn must record a pending capture-rebuild outcome")
    XCTAssertTrue(source.contains("recoveryAction: \"capture_rebuild\""))
    XCTAssertTrue(source.contains("DesktopDiagnosticsManager.shared.recordPTTDeviceRouteChanged"))
    // CoreAudio rebuild owns outcome arming; Bluetooth keeps recordCaptureRebuild unarmed.
    XCTAssertTrue(source.contains("silentMicRecoveryPolicy.armCaptureRebuildOutcome()"))
    let recoveryHelper = source.components(separatedBy: "private func requestCoreAudioCaptureRecovery").last ?? ""
    let recoveryBody = recoveryHelper.components(separatedBy: "private func recordSilentMicRecoveryOutcome").first ?? ""
    XCTAssertTrue(
      recoveryBody.contains("armCaptureRebuildOutcome()"),
      "requestCoreAudioCaptureRecovery must arm capture_rebuild outcomes")
    XCTAssertFalse(
      recoveryBody.contains("recordCaptureRebuild()"),
      "requestCoreAudioCaptureRecovery must not call Bluetooth-only recordCaptureRebuild")

    // The two previously-unwired buffered paths must now participate.
    XCTAssertTrue(source.contains("source: \"buffered_hub\""))
    XCTAssertTrue(source.contains("source: \"warm_wait_fallback\""))
  }

  private func managerSource() throws -> String {
    let url = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/FloatingControlBar/PushToTalkManager.swift")
    // omi-test-quality: source-inspection -- static contract: every recordPTTSilentTurn discard site must wire recovery and settle its outcome; PushToTalkManager is a @MainActor singleton with no behavioral seam
    return try String(contentsOf: url, encoding: .utf8)
  }
}
