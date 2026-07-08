import XCTest

@testable import Omi_Computer

final class ScreenContextTelemetryTests: XCTestCase {
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

    let facts = ScreenContextToolTelemetry.toolResultFacts(toolName: "get_work_context", output: output)
    XCTAssertEqual(facts?.failureCode, .permissionDenied)
    XCTAssertEqual(facts?.succeeded, false)
  }

  func testAmbientPayloadMinimizesScreenContext() throws {
    let payload: [String: Any] = [
      "ok": true,
      "screen_now": [
        "available": true,
        "app_name": "Safari",
        "window_title": "Docs",
        "ocr_preview": "Sensitive visible text",
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
    XCTAssertFalse(output.contains("Sensitive visible text"))
    XCTAssertFalse(output.contains("image_bytes"))
    XCTAssertTrue(output.contains(#""timeline_count":1"#))
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
    XCTAssertTrue(prompt.contains("request_permission"))
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
