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

  func testExplicitCurrentScreenPayloadOnlyAcceptsTurnScopedAttachedImage() throws {
    let formatter = ISO8601DateFormatter()
    let capturedAt = Date(timeIntervalSince1970: 1_000)
    let delivered = ScreenContextWorkContextBuilder.explicitCurrentScreenPayload(
      screenRecordingGranted: true,
      imageAttached: true,
      capturedAt: capturedAt,
      formatter: formatter
    )
    let unavailable = ScreenContextWorkContextBuilder.explicitCurrentScreenPayload(
      screenRecordingGranted: true,
      imageAttached: false,
      capturedAt: capturedAt,
      formatter: formatter
    )
    let deliveredJSON =
      try String(
        data: JSONSerialization.data(withJSONObject: delivered, options: [.sortedKeys]),
        encoding: .utf8
      ) ?? ""

    XCTAssertTrue(deliveredJSON.contains(#""source":"turn_scoped_live_capture""#))
    XCTAssertEqual(
      ((delivered["screen_now"] as? [String: Any])?["image_delivered_to_model"] as? NSNumber)?.boolValue,
      true
    )
    XCTAssertFalse(deliveredJSON.contains("Rewind"))
    XCTAssertEqual((unavailable["screen_now"] as? [String: Any])?["available"] as? Bool, false)
    XCTAssertEqual(unavailable["failure_code"] as? String, "image_unavailable")
  }

  func testPTTTranscriptVocabularyUsesOnlyTurnScopedOCRAndExplicitVocabulary() {
    let snapshot = PTTContextVocabularyProvider.snapshot(
      capturedAt: Date(timeIntervalSince1970: 1_000),
      settingsVocabulary: ["Omi"],
      immediateOCRText: "Codex is open on the current screen")

    XCTAssertEqual(snapshot.sourceCount, 1)
    XCTAssertTrue(snapshot.keywords.contains("Omi"))
    XCTAssertTrue(snapshot.keywords.contains("Codex"))
    XCTAssertFalse(snapshot.keywords.contains("Cursor"))
    // The think_deeper fallback reads the same frame's text; an empty OCR result stays nil.
    XCTAssertEqual(snapshot.visibleText, "Codex is open on the current screen")
    XCTAssertNil(
      PTTContextVocabularyProvider.snapshot(
        capturedAt: Date(), settingsVocabulary: [], immediateOCRText: ""
      ).visibleText)
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
    XCTAssertTrue(
      source.contains("Latest finalized work-context frame was older than \\(staleThresholdSeconds) seconds"))
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

  func testDesktopPromptSeparatesCurrentScreenCaptureFromHistoricalWorkContext() {
    let prompt = DesktopCapabilityRegistry.desktopToolPrompt
    XCTAssertTrue(prompt.contains("Direct current-screen questions"))
    XCTAssertTrue(prompt.contains("get_work_context only for recent historical activity"))
    XCTAssertTrue(prompt.contains("never proves the screen is current"))
    XCTAssertTrue(prompt.contains("capture_screen"))
    XCTAssertTrue(prompt.contains("only after explicit current-turn consent"))
    XCTAssertTrue(prompt.contains("request_permission"))
    XCTAssertTrue(prompt.contains("get_work_context before semantic_search or execute_sql"))
    XCTAssertTrue(prompt.contains("It does not own recent-work retrieval"))
    XCTAssertTrue(prompt.contains("never select raw screenshots.ocrText"))
  }

  func testDesktopChatSQLExamplesDoNotRouteRecentWorkToScreenshots() {
    let prompt = ChatPrompts.desktopChat
    XCTAssertTrue(prompt.contains("use get_work_context for \"what was I doing\""))
    XCTAssertTrue(prompt.contains("recent-work retrieval belongs to get_work_context"))
    XCTAssertFalse(prompt.contains("run ALL 3 for \"what did I do\" questions"))
    XCTAssertFalse(prompt.contains("SELECT s.* FROM screenshots"))
  }

  func testScopedDesktopPromptDoesNotMentionExcludedScreenTools() {
    let prompt = DesktopCapabilityRegistry.scopedDesktopToolPrompt(
      excluding: [
        "get_work_context", "capture_screen", "get_screenshot", "request_permission", "check_permission_status",
      ]
    )
    XCTAssertFalse(prompt.contains("get_work_context"))
    XCTAssertFalse(prompt.contains("capture_screen"))
    XCTAssertFalse(prompt.contains("get_screenshot"))
    XCTAssertFalse(prompt.contains("request_permission"))
    XCTAssertFalse(prompt.contains("check_permission_status"))
    XCTAssertFalse(prompt.contains("Direct current-screen questions"))
    XCTAssertFalse(prompt.contains("Recent work/activity history"))
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

  /// A message with an attachment is about the attachment. "Look at this page" beside a PDF used
  /// to trip the deictic detector and capture the desktop, and a floating turn added an ambient
  /// desktop snapshot regardless — so the model described a blank screen instead of the file.
  func testAttachmentsAreTheSubjectUnlessTheScreenIsNamed() {
    // Deictic cues point at the file, not the desktop.
    XCTAssertNil(
      ScreenContextAutoIncludePolicy.reason(
        userText: "look at this page",
        systemPromptStyle: .main,
        turnOwner: .mainChat,
        hasAttachments: true
      ))
    XCTAssertNil(
      ScreenContextAutoIncludePolicy.reason(
        userText: "look",
        systemPromptStyle: .floating,
        turnOwner: .floatingDefault,
        hasAttachments: true
      ),
      "an attachment on a floating turn replaces the ambient desktop snapshot, it does not sit beside it")
    XCTAssertFalse(
      ScreenContextAutoIncludePolicy.shouldInclude(
        userText: "what do you think of this?",
        systemPromptStyle: .main,
        turnOwner: .agentPill(UUID()),
        hasAttachments: true
      ))
    // Naming the screen is still an explicit ask, attachment or not.
    XCTAssertEqual(
      ScreenContextAutoIncludePolicy.reason(
        userText: "compare this file with what is on my screen",
        systemPromptStyle: .main,
        turnOwner: .mainChat,
        hasAttachments: true
      ),
      .explicitScreenRequest
    )
    // The attachment rule is inert without an attachment.
    XCTAssertEqual(
      ScreenContextAutoIncludePolicy.reason(
        userText: "look at this page",
        systemPromptStyle: .main,
        turnOwner: .mainChat,
        hasAttachments: false
      ),
      .explicitScreenRequest
    )
  }

  func testOnboardingFloatingTurnsAreExplicitScreenRequests() {
    // The demo's suggested query has no screen-cue words; during onboarding a
    // floating turn must still attempt a real capture so failures surface.
    XCTAssertEqual(
      ScreenContextAutoIncludePolicy.reason(
        userText: "Which computer should I buy?",
        systemPromptStyle: .floating,
        turnOwner: .floatingDefault,
        onboardingActive: true
      ),
      .explicitScreenRequest
    )
    XCTAssertEqual(
      ScreenContextAutoIncludePolicy.reason(
        userText: "Which computer should I buy?",
        systemPromptStyle: .floating,
        turnOwner: .floatingDefault,
        onboardingActive: false
      ),
      .ambientSurfaceContext
    )
    // Onboarding must not change non-floating owners.
    XCTAssertNil(
      ScreenContextAutoIncludePolicy.reason(
        userText: "hello",
        systemPromptStyle: .main,
        turnOwner: .mainChat,
        onboardingActive: true
      ))
  }

  func testCaptureFailureGuidanceTellsUserToRelaunch() {
    let payload = ScreenContextWorkContextBuilder.explicitCurrentScreenPayload(
      screenRecordingGranted: true,
      imageAttached: false
    )
    let guidance = payload["guidance"] as? String ?? ""
    XCTAssertTrue(guidance.contains("quit and reopen Omi"))
  }

  func testAmbientPermissionUnavailablePayloadIsConditionalOnScreenDependence() {
    let payload = ScreenContextWorkContextBuilder.ambientPermissionUnavailablePayload()
    let guidance = payload["guidance"] as? String ?? ""
    XCTAssertTrue(guidance.contains("enable Screen Recording"))
    XCTAssertTrue(guidance.contains("ONLY if"))
    let permission = payload["permission"] as? [String: String]
    XCTAssertEqual(permission?["screen_recording"], "not_granted")
  }

  // MARK: - Main-chat explicit evidence (the Omi-frontmost fallback)

  /// Fake store: one ChatGPT row plus, optionally, an excluded one. No GRDB.
  @MainActor private func fallbackLoader(
    appName: String = "ChatGPT",
    ageSeconds: TimeInterval = 30,
    excludedAppName: String? = "1Password",
    frameData: Data? = Data([0xFF, 0xD8, 0xFF]),
    failLoad: Bool = false
  ) -> RewindFrameLoader {
    let rows: [Screenshot?] = [
      excludedAppName.map {
        Screenshot(
          id: 1, timestamp: Date().addingTimeInterval(-5), appName: $0)
      },
      Screenshot(
        id: 2, timestamp: Date().addingTimeInterval(-ageSeconds), appName: appName),
    ]
    let excluded: Set<String> = excludedAppName.map { [$0] } ?? []
    return RewindFrameLoader(
      environment: .init(
        recentScreenshots: { _ in rows.compactMap { $0 } },
        activeChunkPath: { nil },
        loadData: { _ in
          if failLoad { throw RewindError.screenshotNotFound }
          return frameData ?? Data()
        },
        excludedApps: { excluded }
      ))
  }

  /// Lock-protected flag for @Sendable capture closures under test: a plain
  /// captured `var` cannot cross into a `@Sendable` closure.
  private final class CaptureFlag: @unchecked Sendable {
    private let lock = NSLock()
    private var value = false
    var isSet: Bool { lock.withLock { value } }
    func set() { lock.withLock { value = true } }
  }

  @MainActor
  func testMainChatExplicitRequestAnswersFromLastExternalFrameNotLiveCapture() async {
    let frameData = Data([0xFF, 0xD8, 0xFF, 0xE0])
    let capturedLive = CaptureFlag()
    let evidence = await ScreenContextWorkContextBuilder.explicitScreenEvidence(
      turnOwner: .mainChat,
      now: Date(),
      frontmostBundleIdentifier: "com.omi.computer-macos",
      omiBundleIdentifier: "com.omi.computer-macos",
      loader: fallbackLoader(frameData: frameData),
      isScreenRecordingGranted: { true },
      captureNow: {
        capturedLive.set()
        return nil
      }
    )

    // The pixels the model receives are the frame's, and no live capture was
    // taken — the self-portrait never ships alongside the fallback.
    XCTAssertEqual(evidence.imageData, frameData)
    XCTAssertFalse(capturedLive.isSet)
    let screenNow = evidence.payload["screen_now"] as? [String: Any]
    XCTAssertEqual(screenNow?["source"] as? String, "last_external_frame")
    XCTAssertEqual(screenNow?["app_name"] as? String, "ChatGPT")
    XCTAssertEqual((screenNow?["image_delivered_to_model"] as? NSNumber)?.boolValue, true)
    XCTAssertEqual((screenNow?["omi_frontmost_at_send"] as? NSNumber)?.boolValue, true)
    let guidance = evidence.payload["guidance"] as? String ?? ""
    XCTAssertTrue(guidance.contains("ChatGPT"))
    XCTAssertTrue(guidance.contains("Do not describe Omi"))
  }

  @MainActor
  func testMainChatExplicitRequestWithoutFramesFailsHonestNeverSelfPortrait() async {
    // An empty store (fresh install, capture off): no frame, so the honest
    // failure payload answers and no capture of Omi's own window is taken.
    let emptyLoader = RewindFrameLoader(
      environment: .init(
        recentScreenshots: { _ in [] },
        activeChunkPath: { nil },
        loadData: { _ in throw RewindError.screenshotNotFound },
        excludedApps: { [] }
      ))
    let capturedLive = CaptureFlag()
    let evidence = await ScreenContextWorkContextBuilder.explicitScreenEvidence(
      turnOwner: .mainChat,
      now: Date(),
      frontmostBundleIdentifier: "com.omi.computer-macos",
      omiBundleIdentifier: "com.omi.computer-macos",
      loader: emptyLoader,
      isScreenRecordingGranted: { true },
      captureNow: {
        capturedLive.set()
        return nil
      }
    )

    XCTAssertNil(evidence.imageData)
    XCTAssertFalse(capturedLive.isSet)
    XCTAssertEqual(evidence.payload["failure_code"] as? String, "omi_frontmost_no_frame")
    let screenNow = evidence.payload["screen_now"] as? [String: Any]
    XCTAssertEqual((screenNow?["available"] as? NSNumber)?.boolValue, false)
    let guidance = evidence.payload["guidance"] as? String ?? ""
    XCTAssertTrue(guidance.contains("switch to the app"))
  }

  @MainActor
  func testMainChatExplicitRequestWithUnreadableFrameFailsHonest() async {
    let evidence = await ScreenContextWorkContextBuilder.explicitScreenEvidence(
      turnOwner: .mainChat,
      now: Date(),
      frontmostBundleIdentifier: "com.omi.computer-macos",
      omiBundleIdentifier: "com.omi.computer-macos",
      loader: fallbackLoader(failLoad: true),
      isScreenRecordingGranted: { true },
      captureNow: {
        XCTFail("no live capture may be taken for a main-chat explicit ask")
        return nil
      }
    )

    XCTAssertEqual(evidence.imageData, nil)
    XCTAssertEqual(evidence.payload["failure_code"] as? String, "omi_frontmost_no_frame")
    let screenNow = evidence.payload["screen_now"] as? [String: Any]
    XCTAssertEqual(screenNow?["last_external_app_name"] as? String, "ChatGPT")
  }

  @MainActor
  func testNonMainChatExplicitRequestStillCapturesLive() async {
    let liveJPEG = Data([0xFF, 0xD8, 0xFF, 0xDB])
    let evidence = await ScreenContextWorkContextBuilder.explicitScreenEvidence(
      turnOwner: .floatingVoice,
      now: Date(),
      frontmostBundleIdentifier: "com.openai.chat",
      omiBundleIdentifier: "com.omi.computer-macos",
      loader: fallbackLoader(
        appName: "ChatGPT",
        frameData: Data(),
        failLoad: false
      ),
      isScreenRecordingGranted: { true },
      captureNow: { liveJPEG }
    )
    // The store is never consulted for a non-main-chat ask — the voice path
    // interjects while the user is inside the other app — so the pixels are
    // the live capture's, not the frame's.
    XCTAssertEqual(evidence.imageData, liveJPEG)
    let screenNow = evidence.payload["screen_now"] as? [String: Any]
    XCTAssertEqual(screenNow?["source"] as? String, "turn_scoped_live_capture")
    XCTAssertEqual((screenNow?["omi_frontmost_at_send"] as? NSNumber)?.boolValue, false)
  }

  @MainActor
  func testExplicitRequestWithoutPermissionAnswersPermissionPayloadOnEveryOwner() async {
    for owner in [ChatTurnOwner.mainChat, .floatingVoice] {
      let evidence = await ScreenContextWorkContextBuilder.explicitScreenEvidence(
        turnOwner: owner,
        now: Date(),
        frontmostBundleIdentifier: "com.omi.computer-macos",
        omiBundleIdentifier: "com.omi.computer-macos",
        loader: fallbackLoader(),
        isScreenRecordingGranted: { false },
        captureNow: {
          XCTFail("no capture without the permission")
          return nil
        }
      )
      XCTAssertEqual(
        evidence.payload["failure_code"] as? String, "permission_denied", "\(owner)")
      XCTAssertNil(evidence.imageData)
    }
  }

  func testLastExternalFramePayloadIsSelfContained() throws {
    let payload = ScreenContextWorkContextBuilder.explicitLastExternalFramePayload(
      appName: "ChatGPT",
      windowTitle: "  How do I parse JSON?  ",
      frameAgeSeconds: 42,
      capturedAt: Date(timeIntervalSince1970: 1_000)
    )
    let json =
      try String(
        data: JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys]),
        encoding: .utf8
      ) ?? ""
    XCTAssertTrue(json.contains(#""source":"last_external_frame""#))
    XCTAssertTrue(json.contains("How do I parse JSON?"))
    XCTAssertTrue(json.contains("Do not describe Omi"))
    XCTAssertTrue(json.contains("42 seconds"))
  }

  func testSelfFrontmostUnavailablePayloadCarriesStalenessDetail() throws {
    let noFrame = ScreenContextWorkContextBuilder.selfFrontmostUnavailablePayload(
      reason: .noAttachableFrame)
    let stale = ScreenContextWorkContextBuilder.selfFrontmostUnavailablePayload(
      reason: .frameTooStale(ageSeconds: 300),
      lastExternalAppName: "ChatGPT",
      lastExternalFrameAgeSeconds: 300
    )
    XCTAssertEqual(noFrame["failure_code"] as? String, "omi_frontmost_no_frame")
    XCTAssertEqual(stale["failure_code"] as? String, "omi_frontmost_no_frame")
    let staleScreen = stale["screen_now"] as? [String: Any]
    XCTAssertEqual(staleScreen?["last_external_app_name"] as? String, "ChatGPT")
    XCTAssertEqual(staleScreen?["last_external_frame_age_seconds"] as? Int, 300)
    let staleGuidance = stale["guidance"] as? String ?? ""
    XCTAssertTrue(staleGuidance.contains("300 seconds"))
    XCTAssertFalse((noFrame["guidance"] as? String ?? "").contains("seconds old"))
  }
}
