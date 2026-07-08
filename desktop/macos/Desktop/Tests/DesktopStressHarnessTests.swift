import XCTest

@testable import Omi_Computer

final class DesktopStressHarnessTests: XCTestCase {
  func testTerminalTaxonomyNamesCurrentPTTRealtimeAndBridgeFailures() {
    let rawReasons = Set(DesktopStressTerminalReason.allCases.map(\.rawValue))

    XCTAssertEqual(
      rawReasons,
      [
        "ptt_voiced_success",
        "ptt_silent_rejected",
        "chat_bridge_success",
        "subagent_launch_success",
        "too_short_tap",
        "audio_frames_missing",
        "silent_audio",
        "realtime_token_mint_failure",
        "provider_fallback",
        "bridge_launch_failure",
        "response_already_running",
      ])
    XCTAssertFalse(DesktopStressTerminalReason.pttVoicedSuccess.isReleaseGateFailure)
    XCTAssertFalse(DesktopStressTerminalReason.pttSilentRejected.isReleaseGateFailure)
    XCTAssertFalse(DesktopStressTerminalReason.chatBridgeSuccess.isReleaseGateFailure)
    XCTAssertFalse(DesktopStressTerminalReason.subagentLaunchSuccess.isReleaseGateFailure)
    XCTAssertFalse(DesktopStressTerminalReason.providerFallback.isReleaseGateFailure)
    XCTAssertTrue(DesktopStressTerminalReason.audioFramesMissing.isReleaseGateFailure)
    XCTAssertTrue(DesktopStressTerminalReason.realtimeTokenMintFailure.isReleaseGateFailure)
    XCTAssertTrue(DesktopStressTerminalReason.responseAlreadyRunning.isReleaseGateFailure)
  }

  func testStressEventJSONRoundTripsWithStableSnakeCaseKeys() throws {
    let event = DesktopStressDiagnosticEvent(
      runID: "run-1",
      iteration: 2,
      scenario: .chatBridge,
      terminalReason: .responseAlreadyRunning,
      timestamp: "2026-07-07T12:00:00.000Z",
      durationMs: 123,
      details: ["phase": "send"])

    let data = try JSONEncoder().encode(event)
    let object = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])

    XCTAssertEqual(object["run_id"] as? String, "run-1")
    XCTAssertEqual(object["terminal_reason"] as? String, "response_already_running")
    XCTAssertEqual(object["duration_ms"] as? Int, 123)

    let decoded = try JSONDecoder().decode(DesktopStressDiagnosticEvent.self, from: data)
    XCTAssertEqual(decoded, event)
  }

  func testRunSummaryFailsReleaseGateOnForbiddenTerminalReasons() {
    let summary = DesktopStressRunSummary(events: [
      DesktopStressDiagnosticEvent(
        runID: "run-1",
        iteration: 1,
        scenario: .pttVoiced,
        terminalReason: .pttVoicedSuccess),
      DesktopStressDiagnosticEvent(
        runID: "run-1",
        iteration: 2,
        scenario: .pttVoiced,
        terminalReason: .silentAudio),
    ])

    XCTAssertFalse(summary.passedReleaseGate)
    XCTAssertEqual(summary.totalEvents, 2)
    XCTAssertEqual(summary.terminalReasonCounts["ptt_voiced_success"], 1)
    XCTAssertEqual(summary.terminalReasonCounts["silent_audio"], 1)
    XCTAssertEqual(summary.forbiddenTerminalReasons, ["silent_audio"])
  }

  func testScriptOfflineValidationPassesForAllowedReasons() throws {
    let jsonl = """
      {"run_id":"run-1","iteration":1,"scenario":"ptt_voiced","terminal_reason":"ptt_voiced_success","timestamp":"2026-07-07T12:00:00.000Z"}
      {"run_id":"run-1","iteration":2,"scenario":"chat_bridge","terminal_reason":"provider_fallback","timestamp":"2026-07-07T12:00:01.000Z","duration_ms":44,"details":{"provider":"openai"}}

      """
    let result = try runScript(jsonl: jsonl)

    XCTAssertEqual(result.exitCode, 0, result.stderr)
    XCTAssertTrue(result.stdout.contains("\"passed_release_gate\": true"))
    XCTAssertTrue(result.stdout.contains("\"provider_fallback\": 1"))
  }

  func testScriptOfflineValidationFailsWhenRequiredScenarioIsMissing() throws {
    let jsonl = """
      {"run_id":"run-coverage","iteration":1,"scenario":"ptt_voiced","terminal_reason":"ptt_voiced_success","timestamp":"2026-07-07T12:00:00.000Z"}

      """
    let result = try runScript(jsonl: jsonl, extraArguments: ["--require-scenario", "chat_bridge"])

    XCTAssertEqual(result.exitCode, 2)
    XCTAssertTrue(result.stdout.contains("\"missing_required_scenarios\""))
    XCTAssertTrue(result.stdout.contains("\"chat_bridge\""))
  }

  func testScriptOfflineValidationFailsOnForbiddenReason() throws {
    let jsonl = """
      {"run_id":"run-2","iteration":1,"scenario":"subagent_launch","terminal_reason":"bridge_launch_failure","timestamp":"2026-07-07T12:00:00.000Z","details":{"error":"spawn failed"}}

      """
    let result = try runScript(jsonl: jsonl)

    XCTAssertEqual(result.exitCode, 2)
    XCTAssertTrue(result.stdout.contains("\"passed_release_gate\": false"))
    XCTAssertTrue(result.stdout.contains("\"bridge_launch_failure\""))
  }

  func testScriptRejectsRemoteAutomationTokenByDefault() throws {
    let desktopDir = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .deletingLastPathComponent()
    let scriptURL = desktopDir.appendingPathComponent("scripts/stress_ptt_chat.py")

    let process = Process()
    process.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
    process.arguments = [scriptURL.path, "--base-url", "https://example.com", "--token", "secret"]

    let stdout = Pipe()
    let stderr = Pipe()
    process.standardOutput = stdout
    process.standardError = stderr

    try process.run()
    process.waitUntilExit()

    let stderrText = String(data: stderr.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
    XCTAssertEqual(process.terminationStatus, 2)
    XCTAssertTrue(stderrText.contains("must be loopback"), stderrText)
  }

  private func runScript(
    jsonl: String,
    extraArguments: [String] = []
  ) throws -> (exitCode: Int32, stdout: String, stderr: String) {
    let tempURL = FileManager.default.temporaryDirectory
      .appendingPathComponent("omi-stress-\(UUID().uuidString).jsonl")
    try jsonl.write(to: tempURL, atomically: true, encoding: .utf8)
    defer { try? FileManager.default.removeItem(at: tempURL) }

    let scriptURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("scripts/stress_ptt_chat.py")

    let process = Process()
    process.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
    process.arguments = [scriptURL.path, "--input-jsonl", tempURL.path] + extraArguments

    let stdout = Pipe()
    let stderr = Pipe()
    process.standardOutput = stdout
    process.standardError = stderr

    try process.run()
    process.waitUntilExit()

    let stdoutText = String(data: stdout.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
    let stderrText = String(data: stderr.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
    return (process.terminationStatus, stdoutText, stderrText)
  }
}
