import CoreGraphics
import Foundation

enum ScreenContextFailureCode: String, CaseIterable {
  case permissionDenied = "permission_denied"
  case databaseUnavailable = "database_unavailable"
  case screenNowUnavailable = "screen_now_unavailable"
  case screenshotPending = "screenshot_pending"
  case screenshotFileMissing = "screenshot_file_missing"
  case screenshotChunkCorrupted = "screenshot_chunk_corrupted"
  case screenshotSharingDisabled = "screenshot_sharing_disabled"
  case imageUnavailable = "image_unavailable"
  case policyApprovalRequired = "policy_approval_required"
  case captureFailed = "capture_failed"
  case unknown = "unknown"
}

struct ScreenshotUnavailableClassification {
  let code: ScreenContextFailureCode
  let reason: String
  let hint: String
}

enum ScreenContextInterestDetector {
  private static let exactPhrases = [
    "what is on my screen",
    "what's on my screen",
    "whats on my screen",
    "what do you see on my screen",
    "can you see my screen",
    "do you see my screen",
    "look at my screen",
    "look on my screen",
    "see my screen",
    "view my screen",
    "current screen",
    "this screen",
    "my screen",
    "what am i looking at",
    "what i'm looking at",
    "this error",
    "this page",
    "this window",
    "this app",
    "on the left",
    "on the right",
    "at the top",
    "at the bottom",
  ]

  private static let contextualVerbs = [
    "look",
    "see",
    "view",
    "read",
    "inspect",
    "debug",
    "identify",
  ]

  private static let visualReferences = [
    "page",
    "window",
    "error",
    "dialog",
    "button",
    "option",
    "screen",
  ]

  static func isScreenContextRequest(_ text: String) -> Bool {
    let lower = text.lowercased()
      .replacingOccurrences(of: "’", with: "'")
      .trimmingCharacters(in: .whitespacesAndNewlines)
    guard !lower.isEmpty else { return false }
    if exactPhrases.contains(where: { lower.contains($0) }) {
      return true
    }
    let words = lower.split { !$0.isLetter && !$0.isNumber }.map(String.init)
    guard !words.isEmpty else { return false }
    let wordSet = Set(words)
    return contextualVerbs.contains(where: wordSet.contains) && visualReferences.contains(where: wordSet.contains)
  }
}

enum ScreenContextAutoIncludeReason: Equatable {
  case explicitScreenRequest
  case ambientSurfaceContext

  var isExplicitScreenRequest: Bool {
    self == .explicitScreenRequest
  }
}

enum ScreenContextAutoIncludePolicy {
  static func reason(
    userText: String,
    systemPromptStyle: ChatSystemPromptStyle,
    turnOwner: ChatTurnOwner
  ) -> ScreenContextAutoIncludeReason? {
    if ScreenContextInterestDetector.isScreenContextRequest(userText) {
      return .explicitScreenRequest
    }

    switch turnOwner {
    case .floatingDefault, .floatingVoice, .taskChat, .agentPill:
      return .ambientSurfaceContext
    case .mainChat:
      return systemPromptStyle == .floating ? .ambientSurfaceContext : nil
    }
  }

  static func shouldInclude(
    userText: String,
    systemPromptStyle: ChatSystemPromptStyle,
    turnOwner: ChatTurnOwner
  ) -> Bool {
    reason(userText: userText, systemPromptStyle: systemPromptStyle, turnOwner: turnOwner) != nil
  }
}

struct ScreenContextTelemetryContext {
  let surface: String
  let surfaceKind: String?
  let externalRefKind: String?
  let externalRefId: String?
  let runId: String?
  let pillId: String?

  static let desktopChat = ScreenContextTelemetryContext(surface: "desktop_chat")

  init(
    surface: String,
    surfaceKind: String? = nil,
    externalRefKind: String? = nil,
    externalRefId: String? = nil,
    runId: String? = nil,
    pillId: String? = nil
  ) {
    self.surface = surface
    self.surfaceKind = surfaceKind
    self.externalRefKind = externalRefKind
    self.externalRefId = externalRefId
    self.runId = runId
    self.pillId = pillId
  }

  static func from(
    surfaceRef: AgentSurfaceReference?,
    fallbackSurface: String = "desktop_chat",
    runId: String? = nil
  ) -> ScreenContextTelemetryContext {
    guard let surfaceRef else {
      return ScreenContextTelemetryContext(surface: fallbackSurface, runId: runId)
    }
    let surface = surfaceRef.surfaceKind.isEmpty ? fallbackSurface : surfaceRef.surfaceKind
    let pillId = surfaceRef.externalRefKind == "pill" ? surfaceRef.externalRefId : nil
    let resolvedRunId = runId ?? (surfaceRef.externalRefKind == "run" ? surfaceRef.externalRefId : nil)
    return ScreenContextTelemetryContext(
      surface: surface,
      surfaceKind: surfaceRef.surfaceKind,
      externalRefKind: surfaceRef.externalRefKind,
      externalRefId: surfaceRef.externalRefId,
      runId: resolvedRunId,
      pillId: pillId
    )
  }
}

enum ScreenContextToolTelemetry {
  private static let screenContextTools: Set<String> = [
    "get_work_context",
    "capture_screen",
    "get_screenshot",
    "search_screen_history",
    "semantic_search",
  ]

  static func isScreenContextTool(_ toolName: String) -> Bool {
    screenContextTools.contains(toolName)
  }

  static func imageBytesBucket(_ byteCount: Int?) -> String? {
    guard let byteCount else { return nil }
    if byteCount <= 0 { return "0" }
    if byteCount <= 50 * 1024 { return "1-50kb" }
    if byteCount <= 250 * 1024 { return "50-250kb" }
    return "250kb+"
  }

  static func trackToolResult(
    toolName: String,
    context: ScreenContextTelemetryContext = .desktopChat,
    ok: Bool,
    failureCode: ScreenContextFailureCode? = nil,
    screenNowAvailable: Bool? = nil,
    timelineCount: Int? = nil,
    latestCaptureAgeSeconds: Int? = nil,
    hasOCRPreview: Bool? = nil,
    imageBytes: Int? = nil,
    permissionTCCGranted: Bool? = nil,
    sckAvailable: Bool? = nil
  ) {
    Task { @MainActor in
      AnalyticsManager.shared.screenContextToolResult(
        toolName: toolName,
        context: context,
        ok: ok,
        failureCode: failureCode?.rawValue,
        screenNowAvailable: screenNowAvailable,
        timelineCount: timelineCount,
        latestCaptureAgeSeconds: latestCaptureAgeSeconds,
        hasOCRPreview: hasOCRPreview,
        imageBytesBucket: imageBytesBucket(imageBytes),
        permissionTCCGranted: permissionTCCGranted,
        sckAvailable: sckAvailable
      )
    }
  }

  static func trackInvariant(
    _ name: String,
    context: ScreenContextTelemetryContext = .desktopChat,
    toolName: String? = nil,
    properties: [String: Any] = [:]
  ) {
    Task { @MainActor in
      AnalyticsManager.shared.screenContextInvariant(
        name: name,
        context: context,
        toolName: toolName,
        properties: properties
      )
    }
  }

  static func classifyScreenshotUnavailable(
    screenshot: Screenshot,
    activeChunk: String?,
    error: Error
  ) -> ScreenshotUnavailableClassification? {
    if let rewindError = error as? RewindError, case .corruptedVideoChunk = rewindError {
      return ScreenshotUnavailableClassification(
        code: .screenshotChunkCorrupted,
        reason: "The video chunk backing this screenshot is corrupted and cannot be decoded.",
        hint: "Pick a different screenshot_id; this frame's pixels are unrecoverable."
      )
    }
    if screenshot.usesVideoStorage, let chunk = screenshot.videoChunkPath, chunk == activeChunk {
      return ScreenshotUnavailableClassification(
        code: .screenshotPending,
        reason: "The frame is in the active recording segment that has not been flushed to disk yet.",
        hint: "Retry in ~60s, or choose an older screenshot_id whose video chunk is already finalized."
      )
    }
    if !screenshot.usesVideoStorage, (screenshot.imagePath ?? "").isEmpty {
      return ScreenshotUnavailableClassification(
        code: .imageUnavailable,
        reason: "This screenshot row has no stored image.",
        hint: "Pick a different screenshot_id from a recent search_screen_history result."
      )
    }
    if error as? RewindError != nil {
      return ScreenshotUnavailableClassification(
        code: .screenshotFileMissing,
        reason: "The image data for this screenshot is no longer on disk.",
        hint: "Pick a more recent screenshot_id whose pixels are still retained."
      )
    }
    return nil
  }

  static func toolResultFacts(toolName: String, output: String) -> ScreenContextToolFacts? {
    if output.hasPrefix("EXECUTION_PRECONDITION_FAILED:"),
      output.contains("\"code\":\"execution_precondition_failed\""),
      output.contains("\"reason\":\"screenshot_sharing_disabled\"")
    {
      return ScreenContextToolFacts(
        requested: true,
        succeeded: false,
        approvalRequired: false,
        failureCode: .screenshotSharingDisabled
      )
    }
    if output.hasPrefix("POLICY_DENIED:"), output.contains("\"code\":\"approval_required\"") {
      return ScreenContextToolFacts(
        requested: true,
        succeeded: false,
        approvalRequired: true,
        failureCode: .policyApprovalRequired
      )
    }
    if output.hasPrefix("PERMISSION_REQUIRED:"), output.contains("\"code\":\"permission_required\"") {
      if !permissionErrorHasNextTool(output) {
        trackInvariant("screen_tool_permission_error_missing_next_tool", toolName: toolName)
      }
      return ScreenContextToolFacts(
        requested: true,
        succeeded: false,
        approvalRequired: false,
        failureCode: .permissionDenied
      )
    }

    let normalizedOutput = output
      .replacingOccurrences(of: "EXECUTION_PRECONDITION_FAILED: ", with: "")
      .replacingOccurrences(of: "POLICY_DENIED: ", with: "")
      .replacingOccurrences(of: "PERMISSION_REQUIRED: ", with: "")
    guard
      let data = normalizedOutput.data(using: .utf8),
      let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    else {
      return nil
    }

    let ok = (json["ok"] as? Bool) == true
    if toolName == "get_work_context" {
      let screenNow = json["screen_now"] as? [String: Any]
      let screenAvailable = (screenNow?["available"] as? Bool) == true
      let failureRaw = (json["failure_code"] as? String) ?? (screenNow?["failure_code"] as? String)
      if failureRaw == ScreenContextFailureCode.permissionDenied.rawValue, !jsonPermissionErrorHasNextTool(json) {
        trackInvariant("screen_tool_permission_error_missing_next_tool", toolName: toolName)
      }
      return ScreenContextToolFacts(
        requested: true,
        succeeded: ok && screenAvailable,
        approvalRequired: false,
        failureCode: failureRaw.flatMap(ScreenContextFailureCode.init(rawValue:))
      )
    }

    if toolName == "get_screenshot" || toolName == "capture_screen" {
      let failureRaw = (json["error"] as? String) ?? (json["code"] as? String)
      return ScreenContextToolFacts(
        requested: true,
        succeeded: ok,
        approvalRequired: failureRaw == "approval_required",
        failureCode: failureRaw.flatMap(ScreenContextFailureCode.init(rawValue:))
      )
    }

    return nil
  }

  private static func permissionErrorHasNextTool(_ output: String) -> Bool {
    let normalizedOutput = output
      .replacingOccurrences(of: "PERMISSION_REQUIRED: ", with: "")
    guard
      let data = normalizedOutput.data(using: .utf8),
      let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    else {
      return false
    }
    return jsonPermissionErrorHasNextTool(json)
  }

  private static func jsonPermissionErrorHasNextTool(_ json: [String: Any]) -> Bool {
    guard json["next_tool"] as? String == "request_permission",
      let args = json["next_tool_arguments"] as? [String: Any]
    else {
      return false
    }
    return args["type"] as? String == "screen_recording"
  }
}

struct ScreenContextToolFacts {
  let requested: Bool
  let succeeded: Bool
  let approvalRequired: Bool
  let failureCode: ScreenContextFailureCode?
}

struct ScreenContextChatCycleSnapshot {
  let screenToolRequested: Bool
  let screenToolSucceeded: Bool
  let screenToolApprovalRequired: Bool
  let screenToolFailureCodes: [String]
}

final class ScreenContextChatCycleMetrics: @unchecked Sendable {
  private let lock = NSLock()
  private var screenToolRequested = false
  private var screenToolSucceeded = false
  private var screenToolApprovalRequired = false
  private var failureCodes: Set<String> = []

  func recordToolRequested(_ toolName: String) {
    guard ScreenContextToolTelemetry.isScreenContextTool(toolName) else { return }
    lock.lock()
    screenToolRequested = true
    lock.unlock()
  }

  func recordToolResult(name: String, output: String) {
    guard ScreenContextToolTelemetry.isScreenContextTool(name) else { return }
    guard let facts = ScreenContextToolTelemetry.toolResultFacts(toolName: name, output: output) else {
      lock.lock()
      screenToolRequested = true
      lock.unlock()
      return
    }
    lock.lock()
    screenToolRequested = screenToolRequested || facts.requested
    screenToolSucceeded = screenToolSucceeded || facts.succeeded
    screenToolApprovalRequired = screenToolApprovalRequired || facts.approvalRequired
    if let failureCode = facts.failureCode {
      failureCodes.insert(failureCode.rawValue)
    }
    lock.unlock()
  }

  func snapshot() -> ScreenContextChatCycleSnapshot {
    lock.lock()
    defer { lock.unlock() }
    return ScreenContextChatCycleSnapshot(
      screenToolRequested: screenToolRequested,
      screenToolSucceeded: screenToolSucceeded,
      screenToolApprovalRequired: screenToolApprovalRequired,
      screenToolFailureCodes: failureCodes.sorted()
    )
  }
}

enum ScreenContextWorkContextBuilder {
  static let staleCaptureThresholdSeconds = 60
  static let voiceTurnStaleCaptureThresholdSeconds = 15

  static func payload(arguments: [String: Any]) async -> [String: Any] {
    let minutes = max(1, min(120, Int(parseInt64(arguments["minutes"]) ?? 10)))
    let staleThresholdSeconds = max(
      1,
      min(300, Int(parseInt64(arguments["max_age_seconds"]) ?? Int64(staleCaptureThresholdSeconds)))
    )
    let now = Date()
    let start = now.addingTimeInterval(-Double(minutes) * 60)
    let formatter = ISO8601DateFormatter()

    guard CGPreflightScreenCaptureAccess() else {
      return permissionDeniedPayload(windowMinutes: minutes)
    }

	    guard await RewindDatabase.shared.getDatabaseQueue() != nil else {
	      if let fresh = freshScreenCapturePayload(now: now, formatter: formatter) {
	        return [
	          "ok": true,
	          "name": "get_work_context",
	          "window_minutes": minutes,
	          "screen_now": fresh,
	          "timeline": [],
	          "latest_capture_age_seconds": 0,
	          "memories_hint": "For the user's operating principles/preferences, also call search_memories (omi-memory).",
	          "guidance":
	            "The local Rewind timeline database is unavailable, but a fresh live screen capture succeeded. Use capture_screen if raw pixels are necessary.",
	        ]
	      }
      return [
        "ok": false,
        "name": "get_work_context",
        "window_minutes": minutes,
        "failure_code": ScreenContextFailureCode.databaseUnavailable.rawValue,
        "screen_now": ["available": false, "failure_code": ScreenContextFailureCode.databaseUnavailable.rawValue],
        "timeline": [],
        "guidance": "Omi Desktop local screen history is not available yet.",
      ]
    }

    var screenNow: [String: Any] = ["available": false]
    var failureCode: ScreenContextFailureCode?
    var latestCaptureAgeSeconds: Int?
    let activeChunk = await VideoChunkEncoder.shared.currentChunkPath

    if let recent = try? await RewindDatabase.shared.getRecentScreenshots(limit: 25) {
      latestCaptureAgeSeconds = recent.first.map { max(0, Int(now.timeIntervalSince($0.timestamp))) }
      var firstUnavailable: ScreenContextFailureCode?
      for shot in recent {
        guard let sid = shot.id else { continue }
        if shot.usesVideoStorage, let chunk = shot.videoChunkPath, chunk == activeChunk {
          firstUnavailable = firstUnavailable ?? .screenshotPending
          continue
        }
        do {
          let data = try await loadScreenshotDataEnsuringStorage(for: shot)
          screenNow = [
            "available": true,
            "screenshot_id": sid,
            "timestamp": formatter.string(from: shot.timestamp),
            "app_name": shot.appName,
            "window_title": shot.windowTitle ?? NSNull(),
            "ocr_preview": String((shot.ocrText ?? "").prefix(800)),
            "image_bytes": data.count,
            "latest_capture_age_seconds": max(0, Int(now.timeIntervalSince(shot.timestamp))),
            "note":
              "Latest available finalized frame (may be up to ~1 min old, and can predate window_minutes). Call get_screenshot with this screenshot_id only when you need raw pixels.",
          ]
          failureCode = nil
          break
        } catch {
          let classified = ScreenContextToolTelemetry.classifyScreenshotUnavailable(
            screenshot: shot,
            activeChunk: activeChunk,
            error: error
          )
          firstUnavailable = firstUnavailable ?? classified?.code ?? .imageUnavailable
        }
      }
      if (screenNow["available"] as? Bool) != true {
        failureCode = firstUnavailable ?? .screenNowUnavailable
        screenNow["failure_code"] = failureCode?.rawValue
      }
    } else {
      failureCode = .screenNowUnavailable
      screenNow["failure_code"] = failureCode?.rawValue
    }

    if shouldUseFreshCapture(
      screenNow: screenNow,
      latestCaptureAgeSeconds: latestCaptureAgeSeconds,
      staleThresholdSeconds: staleThresholdSeconds
    ) {
      if let fresh = freshScreenCapturePayload(now: now, formatter: formatter) {
        screenNow = fresh
        failureCode = nil
        latestCaptureAgeSeconds = 0
      } else if let latestCaptureAgeSeconds, latestCaptureAgeSeconds > staleThresholdSeconds {
        failureCode = .imageUnavailable
        screenNow = [
          "available": false,
          "failure_code": failureCode?.rawValue ?? ScreenContextFailureCode.imageUnavailable.rawValue,
          "latest_capture_age_seconds": latestCaptureAgeSeconds,
          "note":
            "Latest finalized work-context frame was older than \(staleThresholdSeconds) seconds and live capture was unavailable.",
        ]
        ScreenContextToolTelemetry.trackInvariant(
          "stale_inspection_ignored",
          toolName: "get_work_context",
          properties: ["latest_capture_age_seconds": latestCaptureAgeSeconds]
        )
      }
    }

    var timeline: [[String: Any]] = []
    let calendar = Calendar.current
    func clock(_ date: Date) -> String {
      let c = calendar.dateComponents([.hour, .minute], from: date)
      return String(format: "%02d:%02d", c.hour ?? 0, c.minute ?? 0)
    }
    if let shots = try? await RewindDatabase.shared.getScreenshotsSampled(from: start, to: now, targetCount: 80) {
      var runs: [(app: String, window: String, start: String, end: String, frames: Int)] = []
      for shot in shots {
        let window = normalizeWindow(shot.windowTitle ?? "")
        let cl = clock(shot.timestamp)
        if var last = runs.last, last.app == shot.appName, last.window == window {
          last.end = cl
          last.frames += 1
          runs[runs.count - 1] = last
        } else {
          runs.append((shot.appName, window, cl, cl, 1))
        }
      }
      for run in runs.reversed().prefix(20) {
        timeline.append([
          "start": run.start,
          "end": run.end,
          "app": run.app,
          "window": run.window,
          "frames": run.frames,
        ])
      }
    }

    var payload: [String: Any] = [
      "ok": true,
      "name": "get_work_context",
      "window_minutes": minutes,
      "screen_now": screenNow,
      "timeline": timeline,
      "memories_hint": "For the user's operating principles/preferences, also call search_memories (omi-memory).",
      "guidance":
        "This is the user's recent on-screen activity. Act on it directly instead of asking them to screenshot or re-explain what they were doing.",
    ]
    if let failureCode {
      payload["failure_code"] = failureCode.rawValue
    }
    if let latestCaptureAgeSeconds {
      payload["latest_capture_age_seconds"] = latestCaptureAgeSeconds
    }
    payload["freshness_threshold_seconds"] = staleThresholdSeconds
    return payload
  }

  static func shouldUseFreshCapture(
    screenNow: [String: Any],
    latestCaptureAgeSeconds: Int?,
    staleThresholdSeconds: Int = staleCaptureThresholdSeconds
  ) -> Bool {
    guard (screenNow["available"] as? Bool) == true else { return true }
    guard let latestCaptureAgeSeconds else { return true }
    return latestCaptureAgeSeconds > staleThresholdSeconds
  }

  static func freshScreenCapturePayload(now: Date = Date(), formatter: ISO8601DateFormatter = ISO8601DateFormatter())
    -> [String: Any]?
  {
    guard ScreenCaptureManager.captureScreenData() != nil else { return nil }
    return [
      "available": true,
      "source": "live_capture_stale_rewind",
      "timestamp": formatter.string(from: now),
      "latest_capture_age_seconds": 0,
      "fresh_capture_available": true,
      "raw_image_tool": "capture_screen",
      "note":
        "Fresh live screenshot capture succeeded because the latest finalized work-context frame was missing or stale. Raw pixels are not included here; call capture_screen if the current screen contents matter.",
    ]
  }

  static func permissionDeniedPayload(windowMinutes minutes: Int) -> [String: Any] {
    [
      "ok": false,
      "name": "get_work_context",
      "window_minutes": max(1, min(120, minutes)),
      "failure_code": ScreenContextFailureCode.permissionDenied.rawValue,
      "permission": [
        "screen_recording": "not_granted"
      ],
      "screen_now": [
        "available": false,
        "failure_code": ScreenContextFailureCode.permissionDenied.rawValue,
      ],
      "timeline": [],
      "guidance":
        "Omi does not have Screen Recording permission for current screen access. Tell the user plainly, then call request_permission with type=screen_recording if current screen access is needed.",
      "next_tool": "request_permission",
      "next_tool_arguments": [
        "type": "screen_recording"
      ],
    ]
  }

  static func ambientPayload(from payload: [String: Any]) -> [String: Any] {
    var minimized: [String: Any] = [
      "ok": payload["ok"] as? Bool ?? false,
      "name": "get_work_context",
      "ambient": true,
    ]
    if let failureCode = payload["failure_code"] as? String {
      minimized["failure_code"] = failureCode
    }
    if let screenNow = payload["screen_now"] as? [String: Any] {
      var compactScreen: [String: Any] = [:]
      for key in ["available", "app_name", "window_title", "captured_at", "age_seconds", "latest_capture_age_seconds", "source"] {
        if let value = screenNow[key] {
          compactScreen[key] = value
        }
      }
      minimized["screen_now"] = compactScreen
    }
    if let timeline = payload["timeline"] as? [[String: Any]] {
      minimized["timeline_count"] = timeline.count
    }
    return minimized
  }

  static func telemetryValues(from payload: [String: Any]) -> (
    ok: Bool, failureCode: ScreenContextFailureCode?, screenNowAvailable: Bool?, timelineCount: Int?,
    latestCaptureAgeSeconds: Int?, hasOCRPreview: Bool?, imageBytes: Int?
  ) {
    let screenNow = payload["screen_now"] as? [String: Any]
    let screenNowAvailable = screenNow?["available"] as? Bool
    let failureRaw = (payload["failure_code"] as? String) ?? (screenNow?["failure_code"] as? String)
    let timelineCount = (payload["timeline"] as? [[String: Any]])?.count
    let latestAge = (screenNow?["latest_capture_age_seconds"] as? Int) ?? (payload["latest_capture_age_seconds"] as? Int)
    let ocr = screenNow?["ocr_preview"] as? String
    return (
      ok: (payload["ok"] as? Bool) == true,
      failureCode: failureRaw.flatMap(ScreenContextFailureCode.init(rawValue:)),
      screenNowAvailable: screenNowAvailable,
      timelineCount: timelineCount,
      latestCaptureAgeSeconds: latestAge,
      hasOCRPreview: ocr.map { !$0.isEmpty },
      imageBytes: screenNow?["image_bytes"] as? Int
    )
  }

  private static func loadScreenshotDataEnsuringStorage(for screenshot: Screenshot) async throws -> Data {
    do {
      return try await RewindStorage.shared.loadScreenshotData(for: screenshot)
    } catch {
      try await RewindStorage.shared.initialize()
      return try await RewindStorage.shared.loadScreenshotData(for: screenshot)
    }
  }

  private static func parseInt64(_ value: Any?) -> Int64? {
    if let value = value as? Int64 { return value }
    if let value = value as? Int { return Int64(value) }
    if let value = value as? Double { return Int64(value) }
    if let value = value as? String { return Int64(value.trimmingCharacters(in: .whitespacesAndNewlines)) }
    return nil
  }

  private static func normalizeWindow(_ raw: String) -> String {
    var window = String(
      raw.unicodeScalars.filter { scalar in
        let category = scalar.properties.generalCategory
        return category != .format && category != .control
      })
    if let range = window.range(of: #"\s*\(\d{2,}\)\s*$"#, options: .regularExpression) {
      window.removeSubrange(range)
    }
    if let range = window.range(of: #"^\(\d+\)\s*"#, options: .regularExpression) {
      window.removeSubrange(range)
    }
    return window.trimmingCharacters(in: .whitespacesAndNewlines)
  }
}
