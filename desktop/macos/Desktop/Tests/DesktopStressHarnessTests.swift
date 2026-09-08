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
        "voice_output_overlap",
        "realtime_no_response_timeout",
        "deferred_commit_timeout",
        "barge_in_replacement_timeout",
        "stale_provider_audio_after_interrupt",
      ])
    XCTAssertFalse(DesktopStressTerminalReason.pttVoicedSuccess.isReleaseGateFailure)
    XCTAssertFalse(DesktopStressTerminalReason.pttSilentRejected.isReleaseGateFailure)
    XCTAssertFalse(DesktopStressTerminalReason.chatBridgeSuccess.isReleaseGateFailure)
    XCTAssertFalse(DesktopStressTerminalReason.subagentLaunchSuccess.isReleaseGateFailure)
    XCTAssertFalse(DesktopStressTerminalReason.providerFallback.isReleaseGateFailure)
    XCTAssertTrue(DesktopStressTerminalReason.audioFramesMissing.isReleaseGateFailure)
    XCTAssertTrue(DesktopStressTerminalReason.realtimeTokenMintFailure.isReleaseGateFailure)
    XCTAssertTrue(DesktopStressTerminalReason.responseAlreadyRunning.isReleaseGateFailure)
    XCTAssertTrue(DesktopStressTerminalReason.voiceOutputOverlap.isReleaseGateFailure)
    XCTAssertTrue(DesktopStressTerminalReason.realtimeNoResponseTimeout.isReleaseGateFailure)
    XCTAssertTrue(DesktopStressTerminalReason.deferredCommitTimeout.isReleaseGateFailure)
    XCTAssertTrue(DesktopStressTerminalReason.bargeInReplacementTimeout.isReleaseGateFailure)
    XCTAssertTrue(DesktopStressTerminalReason.staleProviderAudioAfterInterrupt.isReleaseGateFailure)
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

  func testScriptRejectsMalformedFieldTypesWithoutCrashing() throws {
    let malformedScenario = """
      {"run_id":"run-typed","iteration":1,"scenario":["ptt_voiced"],"terminal_reason":"ptt_voiced_success","timestamp":"2026-07-07T12:00:00.000Z"}

      """
    let scenarioResult = try runScript(jsonl: malformedScenario)
    XCTAssertEqual(scenarioResult.exitCode, 2)
    XCTAssertTrue(scenarioResult.stderr.contains("scenario must be a string"), scenarioResult.stderr)

    let boolIteration = """
      {"run_id":"run-typed","iteration":true,"scenario":"ptt_voiced","terminal_reason":"ptt_voiced_success","timestamp":"2026-07-07T12:00:00.000Z","duration_ms":false}

      """
    let iterationResult = try runScript(jsonl: boolIteration)
    XCTAssertEqual(iterationResult.exitCode, 2)
    XCTAssertTrue(iterationResult.stderr.contains("iteration must be a positive integer"), iterationResult.stderr)
  }

  func testScriptRejectsCraftedLoopbackLikeHostnameWithToken() throws {
    let result = try runScript(
      arguments: [
        "--base-url", "https://127.evil.com",
        "--token", "secret",
      ])

    XCTAssertEqual(result.exitCode, 2)
    XCTAssertTrue(result.stderr.contains("must be loopback"), result.stderr)
  }

  func testBridgeTerminalReasonDoesNotTrustExplicitSuccessOnFailure() throws {
    let scriptPath = stressScriptURL().path
    let snippet = """
      import importlib.util
      spec = importlib.util.spec_from_file_location("stress_ptt_chat", \(pythonStringLiteral(scriptPath)))
      module = importlib.util.module_from_spec(spec)
      spec.loader.exec_module(module)
      reason = module.terminal_from_bridge_response("chat_bridge", {"ok": False, "terminal_reason": "chat_bridge_success"})
      assert reason == "bridge_launch_failure", reason
      assert module.is_loopback_url("http://127.0.0.1:47777")
      assert module.is_loopback_url("http://[::1]:47777")
      assert not module.is_loopback_url("https://127.evil.com")
      """

    let result = try runPythonSnippet(snippet)
    XCTAssertEqual(result.exitCode, 0, result.stderr)
  }

  func testBridgeActionDiscoveryTreatsNullResultAsLaunchFailure() throws {
    let scriptPath = stressScriptURL().path
    let snippet = """
      import importlib.util
      spec = importlib.util.spec_from_file_location("stress_ptt_chat", \(pythonStringLiteral(scriptPath)))
      module = importlib.util.module_from_spec(spec)
      spec.loader.exec_module(module)

      def fake_request_json(base_url, token, method, path, body=None):
          if path == "/health":
              return {"ok": True}
          if path == "/actions":
              return {"ok": True, "result": None}
          raise AssertionError(path)

      module.request_json = fake_request_json
      events = module.collect_from_bridge("http://localhost:47777", "secret", ["chat_bridge"], 1)
      assert len(events) == 1, events
      assert events[0]["terminal_reason"] == "bridge_launch_failure", events
      assert "result must be a list" in events[0]["details"]["error"], events
      """

    let result = try runPythonSnippet(snippet)
    XCTAssertEqual(result.exitCode, 0, result.stderr)
  }

  private func runScript(
    jsonl: String,
    extraArguments: [String] = []
  ) throws -> (exitCode: Int32, stdout: String, stderr: String) {
    let tempURL = FileManager.default.temporaryDirectory
      .appendingPathComponent("omi-stress-\(UUID().uuidString).jsonl")
    try jsonl.write(to: tempURL, atomically: true, encoding: .utf8)
    defer { try? FileManager.default.removeItem(at: tempURL) }

    return try runScript(arguments: ["--input-jsonl", tempURL.path] + extraArguments)
  }

  private func runScript(
    arguments: [String]
  ) throws -> (exitCode: Int32, stdout: String, stderr: String) {
    let process = Process()
    process.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
    process.arguments = [stressScriptURL().path] + arguments

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

  private func runPythonSnippet(_ snippet: String) throws -> (exitCode: Int32, stdout: String, stderr: String) {
    let process = Process()
    process.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
    process.arguments = ["-c", snippet]

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

  private func stressScriptURL() -> URL {
    URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("scripts/stress_ptt_chat.py")
  }

  private func pythonStringLiteral(_ value: String) -> String {
    let data = try! JSONSerialization.data(withJSONObject: [value])
    let encoded = String(data: data, encoding: .utf8)!
    return String(encoded.dropFirst().dropLast()).replacingOccurrences(of: "\\/", with: "/")
  }
}
