import XCTest

@testable import Omi_Computer

#if DEBUG
  // omi-release-compile: this suite drives DEBUG-only test seams; the release-mode
  // notification regression step must compile the bundle without them.

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
      let snapshot = try XCTUnwrap(
        snapshots.first(where: { $0["event"] as? String == "user_visible_issue" }))

      XCTAssertEqual(snapshot["event"] as? String, "user_visible_issue")
      XCTAssertEqual(snapshot["area"] as? String, "ptt")
      XCTAssertEqual(snapshot["input_device_class"] as? String, "built_in_mic")
      XCTAssertEqual(snapshot["peak"] as? Int, 0)
      XCTAssertEqual(snapshot["rms"] as? Int, 0)

      let json = String(data: data, encoding: .utf8) ?? ""
      XCTAssertFalse(json.contains("Alice"))
      XCTAssertFalse(json.contains("private microphone"))
      XCTAssertFalse(json.contains("id=123"))
    }

    func testIncidentAttachmentUsesRedactedBoundedLocalLogContext() throws {
      let logURL = FileManager.default.temporaryDirectory
        .appendingPathComponent("omi-incident-log-\(UUID().uuidString).txt")
      try """
      [12:00:00] [app] PTT capture started
      [12:00:01] [app] PTT device=[David's AirPods]
      Authorization: Bearer very-sensitive-token-value
      user@example.com opened /Users/example/Documents/private.txt
      Conversation title: confidential meeting notes
      Arbitrary component message: this must not reach cloud
      [12:00:02] [error] silent capture detected
      """.write(to: logURL, atomically: true, encoding: .utf8)
      defer { try? FileManager.default.removeItem(at: logURL) }
      DesktopDiagnosticsManager.shared.recordWalUploadFailed(
        walId: "private-wal-id",
        reason: "backend returned customer-specific private detail")

      let url = try XCTUnwrap(
        DesktopDiagnosticsManager.shared.writeIncidentDiagnosticsAttachment(
          area: "ptt",
          failureClass: "silent_capture",
          phase: "audio_capture",
          logPath: logURL.path,
          maxLogLines: 20))
      defer { try? FileManager.default.removeItem(at: url) }

      let data = try Data(contentsOf: url)
      let json = String(data: data, encoding: .utf8) ?? ""
      let root = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
      let incident = try XCTUnwrap(root["incident"] as? [String: String])
      let tail = try XCTUnwrap(root["redacted_log_tail"] as? String)

      XCTAssertEqual(incident["area"], "ptt")
      XCTAssertEqual(incident["failure_class"], "silent_capture")
      XCTAssertEqual(incident["phase"], "audio_capture")
      XCTAssertFalse(tail.contains("very-sensitive-token-value"))
      XCTAssertFalse(tail.contains("user@example.com"))
      XCTAssertFalse(tail.contains("/Users/example/Documents/private.txt"))
      XCTAssertFalse(tail.contains("confidential meeting notes"))
      XCTAssertFalse(tail.contains("this must not reach cloud"))
      XCTAssertFalse(tail.contains("David's AirPods"))
      XCTAssertFalse(json.contains("private-wal-id"))
      XCTAssertFalse(json.contains("customer-specific private detail"))
      XCTAssertTrue(tail.contains("PTT capture started"))
      XCTAssertTrue(tail.contains("silent capture detected"))
    }

    func testBetaTrailIncludesTypedErrorContextWithoutRawMessage() throws {
      DesktopDiagnosticsManager.shared.recordBetaLogError(
        message: "Chat bridge returned Alice's private conversation title",
        error: NSError(domain: NSURLErrorDomain, code: NSURLErrorTimedOut),
        enabled: true)

      let url = try XCTUnwrap(
        DesktopDiagnosticsManager.shared.writeIncidentDiagnosticsAttachment(
          area: "chat",
          failureClass: "timeout",
          phase: "query",
          includeBetaDiagnostics: true))
      defer { try? FileManager.default.removeItem(at: url) }

      let data = try Data(contentsOf: url)
      let json = String(data: data, encoding: .utf8) ?? ""
      let root = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
      let snapshots = try XCTUnwrap(root["snapshots"] as? [[String: Any]])
      let trail = try XCTUnwrap(
        snapshots.first(where: { $0["event"] as? String == "beta_diagnostic_trail" }))

      XCTAssertNil(root["redacted_log_tail"])
      XCTAssertEqual(trail["component"] as? String, "chat")
      XCTAssertEqual(trail["failure_class"] as? String, "timeout")
      XCTAssertEqual(trail["error_domain"] as? String, "url")
      XCTAssertEqual(trail["error_code"] as? Int, NSURLErrorTimedOut)
      XCTAssertFalse(json.contains("Alice"))
      XCTAssertFalse(json.contains("private conversation title"))
    }

    func testBetaTrailIsExcludedWhenEnhancedDiagnosticsIsDisabled() throws {
      DesktopDiagnosticsManager.shared.recordBetaLogError(
        message: "Chat bridge timed out",
        error: NSError(domain: NSURLErrorDomain, code: NSURLErrorTimedOut),
        enabled: true)

      let url = try XCTUnwrap(
        DesktopDiagnosticsManager.shared.writeIncidentDiagnosticsAttachment(
          area: "chat",
          failureClass: "timeout",
          phase: "query",
          includeBetaDiagnostics: false))
      defer { try? FileManager.default.removeItem(at: url) }

      let data = try Data(contentsOf: url)
      let root = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
      let snapshots = try XCTUnwrap(root["snapshots"] as? [[String: Any]])
      XCTAssertFalse(snapshots.contains { $0["event"] as? String == "beta_diagnostic_trail" })
    }

    func testBetaTrailIsBoundedIndependentlyFromIncidentSnapshots() throws {
      for _ in 0..<55 {
        DesktopDiagnosticsManager.shared.recordBetaLogError(
          message: "Chat bridge timed out",
          error: NSError(domain: NSURLErrorDomain, code: NSURLErrorTimedOut),
          enabled: true)
      }

      let url = try XCTUnwrap(
        DesktopDiagnosticsManager.shared.writeIncidentDiagnosticsAttachment(
          area: "chat",
          failureClass: "timeout",
          phase: "query",
          includeBetaDiagnostics: true))
      defer { try? FileManager.default.removeItem(at: url) }

      let data = try Data(contentsOf: url)
      let root = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
      let snapshots = try XCTUnwrap(root["snapshots"] as? [[String: Any]])
      let betaTrail = snapshots.filter { $0["event"] as? String == "beta_diagnostic_trail" }
      XCTAssertEqual(betaTrail.count, 50)
    }
    func testPTTSilentTurnCreatesUserVisibleIssueSnapshot() throws {
      DesktopDiagnosticsManager.shared.recordPTTSilentTurn(
        source: "hub",
        mode: "hold",
        audioSeconds: 1.2,
        voicedSeconds: 0,
        peak: 0,
        rms: 0,
        deviceDescription: "built-in microphone",
        micPermissionGranted: true,
        hubActive: true)

      let snapshot = try latestSnapshot()
      XCTAssertEqual(snapshot["event"] as? String, "user_visible_issue")
      XCTAssertEqual(snapshot["area"] as? String, "ptt")
      XCTAssertEqual(snapshot["failure_class"] as? String, "silent_capture")
      XCTAssertEqual(snapshot["phase"] as? String, "audio_capture")
    }

    func testChatFailureCreatesUserVisibleIssueSnapshot() throws {
      DesktopDiagnosticsManager.shared.recordChatFailure(errorClass: "tool_stall")

      let snapshot = try latestSnapshot()
      XCTAssertEqual(snapshot["event"] as? String, "user_visible_issue")
      XCTAssertEqual(snapshot["area"] as? String, "chat")
      XCTAssertEqual(snapshot["failure_class"] as? String, "tool_stall")
      XCTAssertEqual(snapshot["phase"] as? String, "query")
      XCTAssertNil(snapshot["incident_id"])
      XCTAssertNil(snapshot["attempt_id"])
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

    func testVoiceTurnTerminalRecordsReliabilityAndFullAnswerDuration() throws {
      DesktopDiagnosticsManager.shared.recordVoiceTurnTerminal(
        turnID: "turn-123",
        reason: "provider_no_response",
        route: "hub",
        intent: "hold",
        durationMs: 4_250,
        answerDelivered: false,
        staleEventCount: 1,
        invalidTransitionCount: 0)

      let snapshot = try latestSnapshot()

      XCTAssertEqual(snapshot["event"] as? String, "voice_turn_terminal")
      XCTAssertEqual(snapshot["attempt_id"] as? String, "turn-123")
      XCTAssertEqual(snapshot["terminal_reason"] as? String, "provider_no_response")
      XCTAssertEqual(snapshot["outcome"] as? String, "failure")
      XCTAssertEqual(snapshot["response_outcome"] as? String, "failure")
      XCTAssertEqual(snapshot["route"] as? String, "hub")
      XCTAssertEqual(snapshot["intent"] as? String, "hold")
      XCTAssertEqual(snapshot["duration_ms"] as? Int, 4_250)
      XCTAssertEqual(snapshot["telemetry_schema_version"] as? Int, 1)
    }

    func testVoiceToolLatencyRecordsBoundedPerToolDuration() throws {
      DesktopDiagnosticsManager.shared.recordVoiceToolLatency(
        toolName: "search_conversations",
        provider: "gemini",
        durationMs: 4_213.6,
        resultBytes: 1_842)

      let snapshot = try latestSnapshot()
      XCTAssertEqual(snapshot["event"] as? String, "voice_tool_latency")
      XCTAssertEqual(snapshot["tool_name"] as? String, "search_conversations")
      XCTAssertEqual(snapshot["provider"] as? String, "gemini")
      XCTAssertEqual(snapshot["result_bytes"] as? Int, 1_842)
      XCTAssertEqual((snapshot["duration_ms"] as? Double) ?? -1, 4_213.6, accuracy: 0.01)
    }

    func testVoiceToolLatencyTimerEmitsOnlyForAMatchedStart() throws {
      // Finish without a start is a no-op (stale/dropped result).
      DesktopDiagnosticsManager.shared.finishVoiceToolLatency(
        key: "no-start", toolName: "get_tasks", provider: "openai", resultBytes: 10)
      // Matched start → finish emits exactly one voice_tool_latency event.
      DesktopDiagnosticsManager.shared.markVoiceToolStart(key: "call-1")
      DesktopDiagnosticsManager.shared.finishVoiceToolLatency(
        key: "call-1", toolName: "get_tasks", provider: "openai", resultBytes: 42)

      let url = try XCTUnwrap(DesktopDiagnosticsManager.shared.writeDiagnosticsAttachment())
      defer { try? FileManager.default.removeItem(at: url) }
      let root = try XCTUnwrap(
        JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any])
      let snapshots = try XCTUnwrap(root["snapshots"] as? [[String: Any]])
      let latencyEvents = snapshots.filter { $0["event"] as? String == "voice_tool_latency" }

      XCTAssertEqual(latencyEvents.count, 1)
      let snapshot = try XCTUnwrap(latencyEvents.last)
      XCTAssertEqual(snapshot["tool_name"] as? String, "get_tasks")
      XCTAssertEqual(snapshot["provider"] as? String, "openai")
      XCTAssertEqual(snapshot["result_bytes"] as? Int, 42)
      XCTAssertGreaterThanOrEqual((snapshot["duration_ms"] as? Double) ?? -1, 0)
    }

    func testVoiceTurnOutcomeExcludesUserControlledEnds() {
      XCTAssertEqual(DesktopDiagnosticsManager.voiceTurnOutcome(for: "success"), "success")
      XCTAssertEqual(DesktopDiagnosticsManager.voiceTurnOutcome(for: "cancelled"), "excluded")
      XCTAssertEqual(DesktopDiagnosticsManager.voiceTurnOutcome(for: "too_short"), "excluded")
      XCTAssertEqual(DesktopDiagnosticsManager.voiceTurnOutcome(for: "playback_failed"), "failure")
      XCTAssertEqual(
        DesktopDiagnosticsManager.voiceResponseOutcome(for: "journal_failed", answerDelivered: true),
        "success")
    }

    @MainActor
    func testPTTAttemptLifecycleSnapshotIsBoundedInDiagnosticsAttachment() throws {
      // End-to-end: the recorder's default emit routes through the diagnostics
      // manager, so the lifecycle event must land in the Sentry attachment with
      // its bounded causal keys and no raw device identity.
      let recorder = PTTAttemptLifecycleRecorder()
      recorder.beginAttempt(mode: "hold", hubActive: true, micPermissionGranted: true)
      recorder.captureStartRequested()
      recorder.captureStartResolved(outcome: .failed, statusClass: .engineStartFailed)
      recorder.noteInputRoute(class: .bluetooth, source: .override)
      recorder.terminate(
        disposition: .silentRejected,
        source: "hub",
        peak: 0,
        rms: 0,
        turnAudioSeconds: 1.2,
        voicedAudioSeconds: nil,
        isNearZero: true,
        judgeable: true)

      let url = try XCTUnwrap(DesktopDiagnosticsManager.shared.writeDiagnosticsAttachment())
      defer { try? FileManager.default.removeItem(at: url) }

      let data = try Data(contentsOf: url)
      let json = String(data: data, encoding: .utf8) ?? ""
      let root = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
      let snapshots = try XCTUnwrap(root["snapshots"] as? [[String: Any]])
      let snapshot = try XCTUnwrap(
        snapshots.first(where: { $0["event"] as? String == "ptt_audio_capture_lifecycle" }))

      XCTAssertEqual(snapshot["failure_class"] as? String, "capture_never_operational")
      XCTAssertEqual(snapshot["capture_start_outcome"] as? String, "failed")
      XCTAssertEqual(snapshot["capture_start_status_class"] as? String, "engine_start_failed")
      XCTAssertEqual(snapshot["input_route_class"] as? String, "bluetooth")
      XCTAssertEqual(snapshot["input_route_source"] as? String, "override")
      XCTAssertEqual(snapshot["turn_disposition"] as? String, "silent_rejected")
      XCTAssertNotNil(snapshot["attempt_id"])
      // Privacy: no raw device identity, hardware id, or error string leaks.
      XCTAssertFalse(json.contains("engineStartFailed") || json.contains("OSStatus"))
      XCTAssertNil(snapshot["device_description"])
    }

    // MARK: - Release-health telemetry contract (#10425)

    @MainActor
    func testPTTCommittedLifecycleRecordsSuccessDenominator() throws {
      // Success (`failure_class = committed`) is part of the remote funnel so a
      // release-health query has a success denominator, not only classified failures.
      let snapshot = PTTAttemptLifecycleRecorder.Snapshot(
        attemptId: "1", failureClass: .committed, captureStartOutcome: .accepted,
        captureStartStatusClass: .ok, msToFirstAudioBucket: .lt100,
        msToFirstUsableFrameBucket: .lt200, firstChunksEnergyBucket: .audible,
        turnDisposition: .committed, inputRouteClass: .builtIn, inputRouteSource: .default,
        routeChangedDuringAttempt: false, recoveryTriggered: false, recoveryAction: .none,
        recoveryAttemptId: nil, recoveryOutcomeOfNextTurn: .none, mode: "hold", source: "hub",
        hubActive: true, micPermissionGranted: true, turnAudioSeconds: 2.0,
        voicedAudioSeconds: 1.5, peak: 1200, rms: 300, isNearZero: false, judgeable: true,
        telemetrySchemaVersion: 2)
      DesktopDiagnosticsManager.shared.recordPTTAttemptLifecycle(snapshot)
      try assertLatestHealthSnapshot(
        event: .pttAudioCaptureLifecycle,
        contains: ["failure_class": "committed", "turn_disposition": "committed", "telemetry_schema_version": 2])
    }

    func testRealtimeMintPhaseBucketedAndCarriesOutcomeAndMintAttemptId() throws {
      DesktopDiagnosticsManager.shared.recordRealtimeTokenMintFailed(
        provider: "openai", reason: "backend_transient", phase: "warm",
        outcome: .degraded, mintAttemptId: "42")
      try assertLatestHealthSnapshot(
        event: .realtimeTokenMintFailed,
        contains: ["provider": "openai", "phase": "warm", "outcome": "degraded", "mint_attempt_id": "42"])

      // An unknown phase collapses to the closed set's `other` (warm-vs-active is bounded).
      DesktopDiagnosticsManager.shared.recordRealtimeTokenMintFailed(
        provider: "gemini", reason: "provider_5xx", phase: "totally-new-thing")
      try assertLatestHealthSnapshot(event: .realtimeTokenMintFailed, contains: ["phase": "other"])
    }

    func testRealtimeProviderCloseMarksExpectedLifecycle() throws {
      DesktopDiagnosticsManager.shared.recordRealtimeProviderClose(
        provider: "gemini",
        category: RealtimeHubCloseCategory.expectedIdleTeardown.rawValue,
        aliveFor: 180, activeTurn: false, authMode: .managed, failureClass: nil)
      try assertLatestHealthSnapshot(
        event: .realtimeProviderExpectedIdleTeardown,
        contains: ["expected": true, "lifecycle_class": "expected"])

      DesktopDiagnosticsManager.shared.recordRealtimeProviderClose(
        provider: "openai", category: nil, aliveFor: 7, activeTurn: true,
        authMode: .managed, failureClass: nil)
      try assertLatestHealthSnapshot(
        event: .realtimeProviderSessionError,
        contains: ["expected": false, "lifecycle_class": "error"])
    }

    func testFallbackNamedAreasAreNotCollapsedToOther() throws {
      for area in ["screen_capture", "memory_scope", "desktop_update", "tts_fallback", "task_workflow", "auth_storage"] {
        DesktopDiagnosticsManager.shared.resetForTests()
        DesktopDiagnosticsManager.shared.recordFallback(
          area: area, from: "a", to: "b", reason: "capability_mismatch", outcome: .degraded)
        try assertLatestHealthSnapshot(
          event: .fallbackTriggered, contains: ["area": area, "outcome": "degraded"])
      }
    }

    func testHealthEventsStripContentBearingKeysButKeepBoundedCousins() throws {
      DesktopDiagnosticsManager.shared.recordFallback(
        area: "realtime_hub", from: "openai", to: "gemini", reason: "other", outcome: .recovered,
        extra: [
          "transcript": "the user said a secret",
          "prompt": "secret prompt",
          "audio": "base64-audio",
          "response": "secret response",
          "message": "free-form local error detail",
          "transcript_length": 42,
        ])
      let snapshot = try latestSnapshot()
      XCTAssertEqual(snapshot["event"] as? String, "fallback_triggered")
      // Content-bearing keys are stripped at the single emit chokepoint (#10425 privacy).
      XCTAssertNil(snapshot["transcript"])
      XCTAssertNil(snapshot["prompt"])
      XCTAssertNil(snapshot["audio"])
      XCTAssertNil(snapshot["response"])
      XCTAssertNil(snapshot["message"])
      // The bounded cousin (a length, not content) survives.
      XCTAssertEqual(snapshot["transcript_length"] as? Int, 42)
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
      let url = try XCTUnwrap(DesktopDiagnosticsManager.shared.writeDiagnosticsAttachment())
      defer { try? FileManager.default.removeItem(at: url) }

      let data = try Data(contentsOf: url)
      let root = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
      let snapshots = try XCTUnwrap(root["snapshots"] as? [[String: Any]])
      return try XCTUnwrap(snapshots.last, file: file, line: line)
    }
  }
#endif
