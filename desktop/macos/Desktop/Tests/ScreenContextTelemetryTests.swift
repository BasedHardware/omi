import XCTest

@testable import Omi_Computer

final class ScreenContextTelemetryTests: XCTestCase {
  func testScreenshotSharingPreconditionHasBoundedPhysicalFailure() {
    let metrics = ScreenContextChatCycleMetrics()
    metrics.recordToolRequested("capture_screen")
    metrics.recordToolResult(
      name: "capture_screen",
      output:
        #"EXECUTION_PRECONDITION_FAILED: {"code":"execution_precondition_failed","ok":false,"reason":"screenshot_sharing_disabled","tool":"capture_screen"}"#
    )

    let snapshot = metrics.snapshot()
    XCTAssertTrue(snapshot.screenToolRequested)
    XCTAssertFalse(snapshot.screenToolSucceeded)
    XCTAssertFalse(snapshot.screenToolApprovalRequired)
    XCTAssertEqual(snapshot.screenToolFailureCodes, ["screenshot_sharing_disabled"])
  }

  func testPolicyDeniedScreenshotResultMarksApprovalRequired() {
    let metrics = ScreenContextChatCycleMetrics()
    metrics.recordToolRequested("capture_screen")
    metrics.recordToolResult(
      name: "capture_screen",
      output:
        #"POLICY_DENIED: {"capability":"desktop.context.screenshot_image","code":"approval_required","ok":false,"tool":"capture_screen"}"#
    )

    let snapshot = metrics.snapshot()
    XCTAssertTrue(snapshot.screenToolRequested)
    XCTAssertFalse(snapshot.screenToolSucceeded)
    XCTAssertTrue(snapshot.screenToolApprovalRequired)
    XCTAssertEqual(snapshot.screenToolFailureCodes, ["policy_approval_required"])
  }

  func testPermissionRequiredScreenshotResultMarksPermissionDenied() {
    let metrics = ScreenContextChatCycleMetrics()
    metrics.recordToolRequested("capture_screen")
    metrics.recordToolResult(
      name: "capture_screen",
      output:
        #"PERMISSION_REQUIRED: {"code":"permission_required","next_tool":"request_permission","ok":false,"permission":"screen_recording","tool":"capture_screen"}"#
    )

    let snapshot = metrics.snapshot()
    XCTAssertTrue(snapshot.screenToolRequested)
    XCTAssertFalse(snapshot.screenToolSucceeded)
    XCTAssertFalse(snapshot.screenToolApprovalRequired)
    XCTAssertEqual(snapshot.screenToolFailureCodes, ["permission_denied"])
  }

  func testWorkContextResultMarksUsableScreenContext() {
    let metrics = ScreenContextChatCycleMetrics()
    metrics.recordToolResult(
      name: "get_work_context",
      output:
        #"{"ok":true,"name":"get_work_context","screen_now":{"available":true,"image_bytes":1200,"ocr_preview":"redacted"},"timeline":[{"frames":1}]}"#
    )

    let snapshot = metrics.snapshot()
    XCTAssertTrue(snapshot.screenToolRequested)
    XCTAssertTrue(snapshot.screenToolSucceeded)
    XCTAssertFalse(snapshot.screenToolApprovalRequired)
    XCTAssertEqual(snapshot.screenToolFailureCodes, [])
  }

  func testWorkContextUnavailableKeepsFailureCode() {
    let metrics = ScreenContextChatCycleMetrics()
    metrics.recordToolResult(
      name: "get_work_context",
      output:
        #"{"ok":true,"name":"get_work_context","failure_code":"screenshot_pending","screen_now":{"available":false,"failure_code":"screenshot_pending"},"timeline":[]}"#
    )

    let snapshot = metrics.snapshot()
    XCTAssertTrue(snapshot.screenToolRequested)
    XCTAssertFalse(snapshot.screenToolSucceeded)
    XCTAssertEqual(snapshot.screenToolFailureCodes, ["screenshot_pending"])
  }

  func testWorkContextPermissionDeniedPayloadIsTypedForModels() throws {
    let payload = ScreenContextWorkContextBuilder.permissionDeniedPayload(windowMinutes: 10)
    let data = try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
    let output = String(data: data, encoding: .utf8)!

    XCTAssertTrue(output.contains(#""failure_code":"permission_denied""#))
    XCTAssertTrue(output.contains(#""screen_recording":"not_granted""#))
    XCTAssertTrue(output.contains(#""next_tool":"request_permission""#))
    XCTAssertTrue(output.contains(#""type":"screen_recording""#))
    XCTAssertEqual(payload["failure_code"] as? String, "permission_denied")
    XCTAssertEqual(payload["next_tool"] as? String, "request_permission")
    XCTAssertEqual((payload["next_tool_arguments"] as? [String: Any])?["type"] as? String, "screen_recording")

    let facts = ScreenContextToolTelemetry.toolResultFacts(toolName: "get_work_context", output: output)
    XCTAssertEqual(facts?.failureCode, .permissionDenied)
    XCTAssertEqual(facts?.succeeded, false)
  }

  func testTelemetryContextDerivesSurfaceRunAndPillIdentifiers() {
    let pillId = UUID()
    let pillContext = ScreenContextTelemetryContext.from(surfaceRef: .floatingPill(pillId: pillId))
    XCTAssertEqual(pillContext.surface, "floating_bar")
    XCTAssertEqual(pillContext.surfaceKind, "floating_bar")
    XCTAssertEqual(pillContext.externalRefKind, "pill")
    XCTAssertEqual(pillContext.externalRefId, pillId.uuidString)
    XCTAssertEqual(pillContext.pillId, pillId.uuidString)
    XCTAssertNil(pillContext.runId)

    let runContext = ScreenContextTelemetryContext.from(surfaceRef: .floatingBarRun(runId: "run-123"))
    XCTAssertEqual(runContext.surface, "floating_bar")
    XCTAssertEqual(runContext.externalRefKind, "run")
    XCTAssertEqual(runContext.runId, "run-123")
    XCTAssertNil(runContext.pillId)
  }

  func testAmbientPayloadMinimizesScreenContext() throws {
    let payload: [String: Any] = [
      "ok": true,
      "screen_now": [
        "available": true,
        "source": "live_capture_stale_rewind",
        "latest_capture_age_seconds": 0,
        "app_name": "Safari",
        "window_title": "Docs",
        "ocr_preview": "Sensitive visible text",
        "image_base64": "abc123",
        "image_bytes": 12345,
      ],
      "timeline": [
        ["app_name": "Safari"]
      ],
    ]

    let ambient = ScreenContextWorkContextBuilder.ambientPayload(from: payload)
    let data = try JSONSerialization.data(withJSONObject: ambient, options: [.sortedKeys])
    let output = String(data: data, encoding: .utf8)!

    XCTAssertTrue(output.contains(#""ambient":true"#))
    XCTAssertTrue(output.contains(#""app_name":"Safari""#))
    XCTAssertTrue(output.contains(#""source":"live_capture_stale_rewind""#))
    XCTAssertFalse(output.contains("Sensitive visible text"))
    XCTAssertFalse(output.contains("abc123"))
    XCTAssertFalse(output.contains("image_bytes"))
    XCTAssertTrue(output.contains(#""timeline_count":1"#))
  }

  func testWorkContextUsesFreshCaptureWhenFinalizedFrameIsStale() {
    XCTAssertFalse(
      ScreenContextWorkContextBuilder.shouldUseFreshCapture(
        screenNow: ["available": true],
        latestCaptureAgeSeconds: 60
      )
    )
    XCTAssertTrue(
      ScreenContextWorkContextBuilder.shouldUseFreshCapture(
        screenNow: ["available": true],
        latestCaptureAgeSeconds: 61
      )
    )
    XCTAssertTrue(
      ScreenContextWorkContextBuilder.shouldUseFreshCapture(
        screenNow: ["available": false],
        latestCaptureAgeSeconds: 0
      )
    )
    XCTAssertTrue(
      ScreenContextWorkContextBuilder.shouldUseFreshCapture(
        screenNow: ["available": true],
        latestCaptureAgeSeconds: nil
      )
    )
  }

  func testVoiceWorkContextUsesShorterFreshnessBudget() {
    XCTAssertFalse(
      ScreenContextWorkContextBuilder.shouldUseFreshCapture(
        screenNow: ["available": true],
        latestCaptureAgeSeconds: ScreenContextWorkContextBuilder.voiceTurnStaleCaptureThresholdSeconds,
        staleThresholdSeconds: ScreenContextWorkContextBuilder.voiceTurnStaleCaptureThresholdSeconds
      )
    )
    XCTAssertTrue(
      ScreenContextWorkContextBuilder.shouldUseFreshCapture(
        screenNow: ["available": true],
        latestCaptureAgeSeconds: ScreenContextWorkContextBuilder.voiceTurnStaleCaptureThresholdSeconds + 1,
        staleThresholdSeconds: ScreenContextWorkContextBuilder.voiceTurnStaleCaptureThresholdSeconds
      )
    )
  }

  func testPTTTranscriptVocabularyDoesNotFallbackToStaleScreenshots() throws {
    let source = try String(
      contentsOf: URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent()
        .deletingLastPathComponent()
        .appendingPathComponent("Sources/FloatingControlBar/PTTContextVocabularyProvider.swift"),
      encoding: .utf8
    )

    XCTAssertTrue(source.contains("transcription keyword"))
    XCTAssertTrue(source.contains("loadRecentActivityScreenshots"))
    XCTAssertTrue(source.contains("getScreenshots(\n        from: startDate"))
    XCTAssertFalse(source.contains("getRecentScreenshots(limit: 8)"))
    XCTAssertFalse(source.contains("return try await RewindDatabase.shared.getRecentScreenshots"))
  }

  func testPTTDoesNotCreateAnAmbientScreenContextSideChannel() throws {
    let hubSource = try RealtimeHubControllerSourceTestSupport.moduleSource(testFilePath: #filePath)
    let pttSource = try String(
      contentsOf: URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent()
        .deletingLastPathComponent()
        .appendingPathComponent("Sources/FloatingControlBar/PushToTalkManager.swift"),
      encoding: .utf8
    )

    XCTAssertFalse(hubSource.contains("prefetchVoiceTurnScreenContextIfNeeded"))
    XCTAssertFalse(hubSource.contains("voiceTurnScreenContextEnvelopeJSON"))
    XCTAssertFalse(hubSource.contains("ScreenContextWorkContextBuilder.payload"))
    XCTAssertFalse(hubSource.contains("speculativeScreenshot"))
    XCTAssertFalse(pttSource.contains("prefetchVoiceTurnScreenContextIfNeeded"))
    XCTAssertTrue(hubSource.contains("FloatingControlBarManager.shared.kernelVoiceContextSnapshot()"))
  }

  func testStaleWorkContextDropsScreenNowWhenFreshCaptureFails() throws {
    let source = try String(
      contentsOf: URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent()
        .deletingLastPathComponent()
        .appendingPathComponent("Sources/Chat/ScreenContextTelemetry.swift"),
      encoding: .utf8
    )

    XCTAssertTrue(source.contains("failureCode = .imageUnavailable"))
    XCTAssertTrue(source.contains(#""available": false"#))
    XCTAssertTrue(source.contains("Latest finalized work-context frame was older than \\(staleThresholdSeconds) seconds"))
    XCTAssertTrue(source.contains(#""stale_inspection_ignored""#))
    XCTAssertFalse(source.contains(#""image_base64": data.base64EncodedString()"#))
    XCTAssertTrue(source.contains(#""raw_image_tool": "capture_screen""#))
  }

  func testChatMessageSentPropertyNamesDoNotUseAmbiguousHasContext() throws {
    let sourcesDir = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources")

    let postHog = try String(
      contentsOf: sourcesDir.appendingPathComponent("PostHogManager.swift"),
      encoding: .utf8
    )
    XCTAssertFalse(postHog.contains(#""has_context""#))
    XCTAssertTrue(postHog.contains(#""has_selected_app_context""#))
  }

  func testDesktopPromptSendsCurrentScreenQuestionsToWorkContextFirst() {
    let prompt = DesktopCapabilityRegistry.desktopToolPrompt
    XCTAssertTrue(prompt.contains("Current screen/current work questions"))
    XCTAssertTrue(prompt.contains("get_work_context first"))
    XCTAssertTrue(prompt.contains("Raw screenshot pixels"))
    XCTAssertTrue(prompt.contains("only after explicit current-turn consent"))
    XCTAssertTrue(prompt.contains("request_permission"))
  }

  func testScopedDesktopPromptDoesNotMentionExcludedScreenTools() {
    let prompt = DesktopCapabilityRegistry.scopedDesktopToolPrompt(
      excluding: ["get_work_context", "capture_screen", "get_screenshot", "request_permission", "check_permission_status"]
    )
    XCTAssertFalse(prompt.contains("get_work_context"))
    XCTAssertFalse(prompt.contains("capture_screen"))
    XCTAssertFalse(prompt.contains("get_screenshot"))
    XCTAssertFalse(prompt.contains("request_permission"))
    XCTAssertFalse(prompt.contains("check_permission_status"))
    XCTAssertFalse(prompt.contains("Current screen/current work questions"))
    XCTAssertFalse(prompt.contains("Raw screenshot pixels"))
  }

  func testScopedDesktopPromptDoesNotMentionPartiallyExcludedAlternatives() {
    let prompt = DesktopCapabilityRegistry.scopedDesktopToolPrompt(
      excluding: [
        "request_permission", "get_screenshot", "search_memories", "create_action_item", "delete_task",
        "update_agent_artifact_lifecycle",
      ]
    )
    XCTAssertFalse(prompt.contains("request_permission"))
    XCTAssertFalse(prompt.contains("get_screenshot"))
    XCTAssertFalse(prompt.contains("search_memories"))
    XCTAssertFalse(prompt.contains("create_action_item"))
    XCTAssertFalse(prompt.contains("delete_task"))
    XCTAssertFalse(prompt.contains("update_agent_artifact_lifecycle"))
    XCTAssertTrue(prompt.contains("check_permission_status"))
    XCTAssertTrue(prompt.contains("capture_screen"))
    XCTAssertTrue(prompt.contains("get_memories"))
    XCTAssertTrue(prompt.contains("update_action_item"))
    XCTAssertTrue(prompt.contains("complete_task"))
    XCTAssertTrue(prompt.contains("set_desktop_attention_override"))
  }

  func testScreenInterestDetectorCatchesExplicitAndDeicticRequests() {
    XCTAssertTrue(ScreenContextInterestDetector.isScreenContextRequest("Can you see my screen?"))
    XCTAssertTrue(ScreenContextInterestDetector.isScreenContextRequest("Debug this error"))
    XCTAssertFalse(ScreenContextInterestDetector.isScreenContextRequest("What did I do yesterday?"))
  }

  func testScreenContextAutoIncludePolicyCoversFloatingAndAgentTurns() {
    XCTAssertEqual(
      ScreenContextAutoIncludePolicy.reason(
        userText: "can you see my screen?",
        systemPromptStyle: .main,
        turnOwner: .mainChat
      ),
      .explicitScreenRequest
    )
    XCTAssertEqual(
      ScreenContextAutoIncludePolicy.reason(
        userText: "which one",
        systemPromptStyle: .floating,
        turnOwner: .floatingDefault
      ),
      .ambientSurfaceContext
    )
    XCTAssertTrue(
      ScreenContextAutoIncludePolicy.shouldInclude(
        userText: "which one",
        systemPromptStyle: .floating,
        turnOwner: .floatingDefault
      ))
    XCTAssertTrue(
      ScreenContextAutoIncludePolicy.shouldInclude(
        userText: "take a look",
        systemPromptStyle: .main,
        turnOwner: .agentPill(UUID())
      ))
    XCTAssertTrue(
      ScreenContextAutoIncludePolicy.shouldInclude(
        userText: "debug this error",
        systemPromptStyle: .main,
        turnOwner: .mainChat
      ))
    XCTAssertFalse(
      ScreenContextAutoIncludePolicy.shouldInclude(
        userText: "what did I do yesterday?",
        systemPromptStyle: .main,
        turnOwner: .mainChat
      ))
  }
}
