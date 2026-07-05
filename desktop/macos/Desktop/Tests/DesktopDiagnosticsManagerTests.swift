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
      retryable: true)

    let snapshot = try latestSnapshot()

    XCTAssertEqual(snapshot["event"] as? String, "realtime_token_mint_failed")
    XCTAssertEqual(snapshot["provider"] as? String, "gemini")
    XCTAssertEqual(snapshot["reason"] as? String, "backend_transient")
    XCTAssertEqual(snapshot["phase"] as? String, "warm")
    XCTAssertEqual(snapshot["http_status_code"] as? Int, 503)
    XCTAssertEqual(snapshot["backend_route"] as? String, "/v2/realtime/session")
    XCTAssertEqual(snapshot["upstream_status_code"] as? Int, 503)
    XCTAssertEqual(snapshot["retryable"] as? Bool, true)
  }

  private func latestSnapshot() throws -> [String: Any] {
    let url = try XCTUnwrap(DesktopDiagnosticsManager.shared.writeDiagnosticsAttachment())
    defer { try? FileManager.default.removeItem(at: url) }

    let data = try Data(contentsOf: url)
    let root = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    let snapshots = try XCTUnwrap(root["snapshots"] as? [[String: Any]])
    return try XCTUnwrap(snapshots.last)
  }
}
