import XCTest

@testable import Omi_Computer

final class DesktopDiagnosticsManagerTests: XCTestCase {
  override func setUp() {
    super.setUp()
    DesktopDiagnosticsManager.shared.resetForTests()
  }

  override func tearDown() {
    DesktopDiagnosticsManager.shared.resetForTests()
    super.tearDown()
  }

  func testDiagnosticsAttachmentUsesSafeOperationalFields() throws {
    DesktopDiagnosticsManager.shared.recordPTTSilentTurn(
      source: "hub",
      mode: "hold",
      audioSeconds: 2.14,
      voicedSeconds: nil,
      peak: 0,
      rms: 0,
      deviceDescription: "built-in id=123 Alice private microphone",
      micPermissionGranted: true,
      hubActive: true)

    let url = try XCTUnwrap(DesktopDiagnosticsManager.shared.writeDiagnosticsAttachment())
    defer { try? FileManager.default.removeItem(at: url) }

    let data = try Data(contentsOf: url)
    let root = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    let snapshots = try XCTUnwrap(root["snapshots"] as? [[String: Any]])
    let snapshot = try XCTUnwrap(snapshots.last)

    XCTAssertEqual(snapshot["event"] as? String, "ptt_audio_capture_silent_turn")
    XCTAssertEqual(snapshot["input_device_class"] as? String, "built_in_mic")
    XCTAssertEqual(snapshot["peak"] as? Int, 0)
    XCTAssertEqual(snapshot["rms"] as? Int, 0)

    let json = String(data: data, encoding: .utf8) ?? ""
    XCTAssertFalse(json.contains("Alice"))
    XCTAssertFalse(json.contains("private microphone"))
    XCTAssertFalse(json.contains("id=123"))
  }

  func testSilentTurnRecordsRecoveryActionAndResult() throws {
    DesktopDiagnosticsManager.shared.recordPTTSilentTurn(
      source: "omni_stt",
      mode: "hold",
      audioSeconds: 1.2,
      voicedSeconds: 0,
      peak: 0,
      rms: 0,
      deviceDescription: "built-in microphone",
      micPermissionGranted: true,
      hubActive: false,
      recoveryAction: "capture_rebuild",
      recoveryResult: "attempted")

    let url = try XCTUnwrap(DesktopDiagnosticsManager.shared.writeDiagnosticsAttachment())
    defer { try? FileManager.default.removeItem(at: url) }

    let data = try Data(contentsOf: url)
    let root = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    let snapshots = try XCTUnwrap(root["snapshots"] as? [[String: Any]])
    let snapshot = try XCTUnwrap(snapshots.last)

    XCTAssertEqual(snapshot["recovery_action"] as? String, "capture_rebuild")
    XCTAssertEqual(snapshot["recovery_result"] as? String, "attempted")
  }

  func testSilentTurnRecoveryFieldsDefaultToNone() throws {
    DesktopDiagnosticsManager.shared.recordPTTSilentTurn(
      source: "hub",
      mode: "hold",
      audioSeconds: 1.2,
      voicedSeconds: nil,
      peak: 0,
      rms: 0,
      deviceDescription: "built-in microphone",
      micPermissionGranted: true,
      hubActive: true)

    let url = try XCTUnwrap(DesktopDiagnosticsManager.shared.writeDiagnosticsAttachment())
    defer { try? FileManager.default.removeItem(at: url) }

    let data = try Data(contentsOf: url)
    let root = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    let snapshots = try XCTUnwrap(root["snapshots"] as? [[String: Any]])
    let snapshot = try XCTUnwrap(snapshots.last)

    XCTAssertEqual(snapshot["recovery_action"] as? String, "none")
    XCTAssertEqual(snapshot["recovery_result"] as? String, "not_attempted")
  }

  func testShortSilentTurnsDoNotAdvanceWatchdogCounter() throws {
    for _ in 0..<3 {
      DesktopDiagnosticsManager.shared.recordPTTSilentTurn(
        source: "hub",
        mode: "hold",
        audioSeconds: 0,
        voicedSeconds: nil,
        peak: 0,
        rms: 0,
        deviceDescription: "built-in microphone",
        micPermissionGranted: true,
        hubActive: true)
    }

    let url = try XCTUnwrap(DesktopDiagnosticsManager.shared.writeDiagnosticsAttachment())
    defer { try? FileManager.default.removeItem(at: url) }

    let data = try Data(contentsOf: url)
    let root = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    let snapshots = try XCTUnwrap(root["snapshots"] as? [[String: Any]])

    XCTAssertEqual(snapshots.count, 3)
    XCTAssertTrue(snapshots.allSatisfy { $0["event"] as? String == "ptt_audio_capture_silent_turn" })
    XCTAssertTrue(snapshots.allSatisfy { $0["watchdog_eligible"] as? Bool == false })
    XCTAssertTrue(snapshots.allSatisfy { $0["consecutive_silent_turns"] as? Int == 0 })
  }

  func testExpectedIdleTeardownUsesSeparateHealthEvent() throws {
    DesktopDiagnosticsManager.shared.recordRealtimeProviderClose(
      provider: "gemini",
      category: RealtimeHubCloseCategory.expectedIdleTeardown.rawValue,
      aliveFor: 180,
      activeTurn: false,
      authMode: .managed,
      failureClass: nil)

    let snapshot = try latestSnapshot()

    XCTAssertEqual(snapshot["event"] as? String, "realtime_provider_expected_idle_teardown")
    XCTAssertEqual(snapshot["provider"] as? String, "gemini")
    XCTAssertEqual(snapshot["category"] as? String, "expected_idle_teardown")
    XCTAssertEqual(snapshot["auth_mode"] as? String, "managed")
    XCTAssertEqual(snapshot["active_turn"] as? Bool, false)
  }

  func testExpectedSessionRotationUsesNonErrorHealthEvent() throws {
    DesktopDiagnosticsManager.shared.recordRealtimeProviderClose(
      provider: "openai",
      category: RealtimeHubCloseCategory.expectedSessionRotation.rawValue,
      aliveFor: 3_600,
      activeTurn: true,
      authMode: .managed,
      failureClass: nil)

    let snapshot = try latestSnapshot()

    XCTAssertEqual(snapshot["event"] as? String, "realtime_provider_expected_session_rotation")
    XCTAssertEqual(snapshot["provider"] as? String, "openai")
    XCTAssertEqual(snapshot["category"] as? String, "expected_session_rotation")
    XCTAssertEqual(snapshot["recovery_action"] as? String, "rotate_realtime_session")
    XCTAssertEqual(snapshot["recovery_result"] as? String, "turn_terminated_and_rewarm_started")
  }

  func testRealtimeContextPlanTelemetryContainsOnlyHashedPlanFieldsAndTokenCounts() throws {
    let plan = RealtimeCachePlanTelemetry(
      planID: "sha256:" + String(repeating: "a", count: 64),
      stableCachePrefixFingerprint: "sha256:" + String(repeating: "b", count: 64),
      dynamicContextFingerprint: "sha256:" + String(repeating: "c", count: 64),
      retainedFirstTurnSeq: 2,
      retainedLastTurnSeq: 65,
      omittedTurnCount: 1)

    DesktopDiagnosticsManager.shared.recordRealtimeContextPlan(
      provider: "openai",
      model: "gpt-realtime-2",
      plan: plan,
      replacementReason: "voice_context_changed")
    DesktopDiagnosticsManager.shared.recordRealtimeContextPlanUsage(
      provider: "openai",
      model: "gpt-realtime-2",
      plan: plan,
      cacheReadTokens: 123,
      inputTokens: 345)

    let snapshots = try healthSnapshots()
    let start = try XCTUnwrap(snapshots.first)
    let usage = try XCTUnwrap(snapshots.last)
    XCTAssertEqual(start["event"] as? String, "realtime_context_plan")
    XCTAssertEqual(start["phase"] as? String, "session_start")
    XCTAssertEqual(start["retained_first_turn_sequence"] as? Int, 2)
    XCTAssertEqual(start["retained_last_turn_sequence"] as? Int, 65)
    XCTAssertEqual(start["omitted_turn_count"] as? Int, 1)
    XCTAssertEqual(start["session_replacement_reason"] as? String, "voice_context_changed")
    XCTAssertEqual(usage["phase"] as? String, "turn_usage")
    XCTAssertEqual(usage["cache_read_tokens"] as? Int, 123)
    XCTAssertEqual(usage["input_tokens"] as? Int, 345)
    XCTAssertNil(usage["conversation_id"])
    XCTAssertNil(usage["context"])
  }

  func testProviderCloseFallsBackToFailureClassInsteadOfUnclassified() throws {
    DesktopDiagnosticsManager.shared.recordRealtimeProviderClose(
      provider: "openai",
      category: nil,
      aliveFor: 7,
      activeTurn: true,
      authMode: .byok,
      failureClass: .providerTransient(provider: .openai))

    let snapshot = try latestSnapshot()

    XCTAssertEqual(snapshot["event"] as? String, "realtime_provider_session_error")
    XCTAssertEqual(snapshot["category"] as? String, "provider_transient")
    XCTAssertEqual(snapshot["failure_class"] as? String, "provider_transient")
    XCTAssertEqual(snapshot["auth_mode"] as? String, "byok")
  }

  func testTokenMintFailureIncludesHttpStatusWhenKnown() throws {
    DesktopDiagnosticsManager.shared.recordRealtimeTokenMintFailed(
      provider: "gemini",
      reason: "backend_transient",
      phase: "warm",
      httpStatusCode: 503,
      backendRoute: "/v2/realtime/session",
      upstreamStatusCode: 503,
      providerCode: "UNAVAILABLE",
      retryable: true)

    let snapshot = try latestSnapshot()

    XCTAssertEqual(snapshot["event"] as? String, "realtime_token_mint_failed")
    XCTAssertEqual(snapshot["provider"] as? String, "gemini")
    XCTAssertEqual(snapshot["reason"] as? String, "backend_transient")
    XCTAssertEqual(snapshot["phase"] as? String, "warm")
    XCTAssertEqual(snapshot["http_status_code"] as? Int, 503)
    XCTAssertEqual(snapshot["backend_route"] as? String, "/v2/realtime/session")
    XCTAssertEqual(snapshot["upstream_status_code"] as? Int, 503)
    XCTAssertEqual(snapshot["provider_code"] as? String, "UNAVAILABLE")
    XCTAssertEqual(snapshot["retryable"] as? Bool, true)
  }

  func testRecordFallbackUsesSharedContractFields() throws {
    DesktopDiagnosticsManager.shared.recordFallback(
      area: "realtime_hub",
      from: "openai",
      to: "gemini",
      reason: "auth",
      outcome: .recovered,
      extra: ["user_visible": false])

    let snapshot = try latestSnapshot()
    XCTAssertEqual(snapshot["event"] as? String, "fallback_triggered")
    XCTAssertEqual(snapshot["area"] as? String, "realtime_hub")
    XCTAssertEqual(snapshot["from"] as? String, "openai")
    XCTAssertEqual(snapshot["to"] as? String, "gemini")
    XCTAssertEqual(snapshot["reason"] as? String, "auth")
    XCTAssertEqual(snapshot["outcome"] as? String, "recovered")
    XCTAssertEqual(snapshot["user_visible"] as? Bool, false)
  }

  func testRecordFallbackBucketsUnknownAreaAndReason() throws {
    DesktopDiagnosticsManager.shared.recordFallback(
      area: "brand_new_area",
      from: "Cloud Tasks!",
      to: "",
      reason: "totally_novel_failure",
      outcome: .degraded)

    let snapshot = try latestSnapshot()
    XCTAssertEqual(snapshot["event"] as? String, "fallback_triggered")
    XCTAssertEqual(snapshot["area"] as? String, "other")
    XCTAssertEqual(snapshot["from"] as? String, "cloud_tasks_")
    XCTAssertEqual(snapshot["to"] as? String, "none")
    XCTAssertEqual(snapshot["reason"] as? String, "other")
    XCTAssertEqual(snapshot["outcome"] as? String, "degraded")
  }

  func testAuthTokenStorageFallbackRecordsHealthSnapshot() throws {
    DesktopDiagnosticsManager.shared.recordAuthTokenStorageFallback(
      reason: "keychain_write_failed",
      updateChannel: "beta")

    try assertLatestHealthSnapshot(
      event: .authTokenStorageFallback,
      contains: [
        "storage": "user_defaults",
        "reason": "keychain_write_failed",
        "update_channel": "beta",
      ])
  }

  private func assertLatestHealthSnapshot(
    event: DesktopHealthEventName,
    contains expected: [String: Any] = [:],
    file: StaticString = #filePath,
    line: UInt = #line
  ) throws {
    let snapshot = try latestSnapshot(file: file, line: line)
    XCTAssertEqual(snapshot["event"] as? String, event.rawValue, file: file, line: line)
    for (key, value) in expected {
      switch value {
      case let string as String:
        XCTAssertEqual(snapshot[key] as? String, string, "key: \(key)", file: file, line: line)
      case let int as Int:
        XCTAssertEqual(snapshot[key] as? Int, int, "key: \(key)", file: file, line: line)
      case let bool as Bool:
        XCTAssertEqual(snapshot[key] as? Bool, bool, "key: \(key)", file: file, line: line)
      default:
        XCTFail("Unsupported expected value type for key \(key)", file: file, line: line)
      }
    }
  }

  private func latestSnapshot(
    file: StaticString = #filePath,
    line: UInt = #line
  ) throws -> [String: Any] {
    try XCTUnwrap(healthSnapshots().last, file: file, line: line)
  }

  private func healthSnapshots() throws -> [[String: Any]] {
    let url = try XCTUnwrap(DesktopDiagnosticsManager.shared.writeDiagnosticsAttachment())
    defer { try? FileManager.default.removeItem(at: url) }

    let data = try Data(contentsOf: url)
    let root = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    return try XCTUnwrap(root["snapshots"] as? [[String: Any]])
  }
}
