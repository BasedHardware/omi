@preconcurrency import AVFoundation
import AppKit
import Foundation
@preconcurrency import GRDB
@preconcurrency import UserNotifications

private enum ChatToolOwnerAuthorization {
  @TaskLocal static var snapshot: RuntimeOwnerAuthorizationSnapshot?
}

/// Bridges callback-based macOS permission APIs into structured concurrency.
/// Cancellation wins exactly once and late TCC callbacks are ignored, so an
/// owner transition never waits indefinitely for a user to answer an OS prompt.
private final class CancellablePermissionContinuation<Value: Sendable>: @unchecked Sendable {
  private let lock = NSLock()
  private var continuation: CheckedContinuation<Value?, Never>?
  private var isFinished = false
  private var result: Value?

  func install(_ continuation: CheckedContinuation<Value?, Never>) {
    let completedResult: Value?
    let shouldResume: Bool
    lock.lock()
    if isFinished {
      completedResult = result
      shouldResume = true
    } else {
      self.continuation = continuation
      completedResult = nil
      shouldResume = false
    }
    lock.unlock()
    if shouldResume {
      continuation.resume(returning: completedResult)
    }
  }

  func finish(_ value: Value?) {
    let continuationToResume: CheckedContinuation<Value?, Never>?
    lock.lock()
    guard !isFinished else {
      lock.unlock()
      return
    }
    isFinished = true
    result = value
    continuationToResume = continuation
    continuation = nil
    lock.unlock()
    continuationToResume?.resume(returning: value)
  }
}

/// Executes tool calls from Gemini and returns results
/// Tools: execute_sql (read/write SQL on omi.db), semantic_search (vector similarity)
@MainActor
class ChatToolExecutor {

  nonisolated static var currentOwnerAuthorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? {
    ChatToolOwnerAuthorization.snapshot
  }

  // MARK: - Onboarding State

  /// Set by OnboardingChatView before starting the chat
  static var onboardingAppState: AppState?
  /// Called when AI invokes complete_onboarding
  static var onCompleteOnboarding: (() -> Void)?
  /// Called when AI invokes ask_followup — delivers quick-reply options to the UI
  static var onQuickReplyOptions: ((_ options: [String]) -> Void)?
  /// Called when AI invokes ask_followup — delivers the question text to the UI
  static var onQuickReplyQuestion: ((_ question: String) -> Void)?
  /// Called when AI invokes save_knowledge_graph — notifies the graph view to update
  static var onKnowledgeGraphUpdated: (() -> Void)?
  /// Called when scan_files completes — used to kick off parallel exploration
  static var onScanFilesCompleted: ((_ fileCount: Int) -> Void)?
  /// Called when request_permission returns "pending" — used to trigger the permission help timer
  static var onPermissionPending: ((_ permissionType: String) -> Void)?

  /// Email/calendar insights from background reading (set by OnboardingChatView)
  static var emailInsightsText: String?
  static var calendarInsightsText: String?

  private static var fileScanFileCount = 0

  nonisolated static let onboardingPermissionTypes = [
    "screen_recording",
    "microphone",
    "notifications",
    "accessibility",
    "automation",
    "full_disk_access",
  ]

  nonisolated static var onboardingPermissionTypesDescription: String {
    onboardingPermissionTypes.joined(separator: ", ")
  }

  nonisolated static func onboardingPermissionStatusPayload(
    screenRecording: Bool,
    microphone: Bool,
    notifications: Bool,
    accessibility: Bool,
    automation: Bool,
    fullDiskAccess: Bool
  ) -> [String: String] {
    [
      "screen_recording": screenRecording ? "granted" : "not_granted",
      "microphone": microphone ? "granted" : "not_granted",
      "notifications": notifications ? "granted" : "not_granted",
      "accessibility": accessibility ? "granted" : "not_granted",
      "automation": automation ? "granted" : "not_granted",
      "full_disk_access": fullDiskAccess ? "granted" : "not_granted",
    ]
  }

  struct LocalFileScanOutcome {
    let hasReadableUserFileTarget: Bool
    let didCompleteSuccessfully: Bool
    let indexedFileCount: Int
    /// User-file folders (e.g. "~/Downloads") the scan could not read because
    /// access was denied. System targets like /Applications are excluded.
    let deniedUserFolders: [String]
    /// Agent-facing markdown scan report for the chat surface. UI surfaces
    /// must compose their messages from the structured fields instead.
    let summaryText: String
  }

  /// Execute a tool call and return the result as a string
  static func execute(
    _ toolCall: ToolCall,
    originatingChatMode: ChatMode? = nil,
    originatingClientScope: String? = nil,
    originatingSurfaceRef: AgentSurfaceReference? = nil,
    originatingRunId: String? = nil,
    originatingUserText: String? = nil,
    isOnboardingSurface: Bool = false,
    expectedOwnerID: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil,
    backendAPIClient: APIClient = .shared
  ) async -> String {
    let pinnedOwnerID = expectedOwnerID ?? RuntimeOwnerIdentity.currentOwnerId()
    let allowsSignedOutOnboardingPermission =
      isOnboardingSurface
      && ["request_permission", "check_permission_status"].contains(toolCall.name)
    guard pinnedOwnerID != nil || allowsSignedOutOnboardingPermission else {
      return authorizedOwnerChangedResult()
    }
    let pinnedAuthorization: RuntimeOwnerAuthorizationSnapshot?
    if let pinnedOwnerID {
      guard
        let authorization = authorizationSnapshot
          ?? RuntimeOwnerIdentity.captureAuthorizationSnapshot(expectedOwnerID: pinnedOwnerID),
        authorization.ownerID == pinnedOwnerID,
        RuntimeOwnerIdentity.isAuthorizationCurrent(authorization)
      else {
        return authorizedOwnerChangedResult()
      }
      pinnedAuthorization = authorization
    } else {
      pinnedAuthorization = nil
    }
    guard isExpectedOwnerCurrent(pinnedOwnerID, authorizationSnapshot: pinnedAuthorization) else {
      return authorizedOwnerChangedResult()
    }
    return await ChatToolOwnerAuthorization.$snapshot.withValue(pinnedAuthorization) {
      let result = await executeUnchecked(
        toolCall,
        originatingChatMode: originatingChatMode,
        originatingClientScope: originatingClientScope,
        originatingSurfaceRef: originatingSurfaceRef,
        originatingRunId: originatingRunId,
        isOnboardingSurface: isOnboardingSurface,
        expectedOwnerID: pinnedOwnerID,
        backendAPIClient: backendAPIClient)
      guard isExpectedOwnerCurrent(pinnedOwnerID) else {
        return authorizedOwnerChangedResult()
      }
      return result
    }
  }

  private static func executeUnchecked(
    _ toolCall: ToolCall,
    originatingChatMode: ChatMode?,
    originatingClientScope: String?,
    originatingSurfaceRef: AgentSurfaceReference?,
    originatingRunId: String?,
    isOnboardingSurface: Bool,
    expectedOwnerID: String?,
    backendAPIClient: APIClient
  ) async -> String {
    log("Executing tool: \(toolCall.name) with args: \(toolCall.arguments)")
    let telemetryContext = ScreenContextTelemetryContext.from(
      surfaceRef: originatingSurfaceRef,
      runId: originatingRunId
    )

    if case .failed(let message) = physicalExecutionPrecondition(toolName: toolCall.name) {
      log("Tool \(toolCall.name) failed its physical execution precondition")
      if ScreenContextToolTelemetry.isScreenContextTool(toolCall.name) {
        ScreenContextToolTelemetry.trackToolResult(
          toolName: toolCall.name,
          context: telemetryContext,
          ok: false,
          failureCode: .screenshotSharingDisabled,
          permissionTCCGranted: CGPreflightScreenCaptureAccess()
        )
      }
      return message
    }

    switch GeneratedToolExecutors.chatDispatch(for: toolCall.name) {
    case .executeSql:
      return await executeSQL(toolCall.arguments, expectedOwnerID: expectedOwnerID)

    case .semanticSearch:
      return await executeSemanticSearch(toolCall.arguments, expectedOwnerID: expectedOwnerID)

    case .getDailyRecap:
      return await executeDailyRecap(toolCall.arguments, expectedOwnerID: expectedOwnerID)

    case .searchTasks:
      return await executeSearchTasks(toolCall.arguments, expectedOwnerID: expectedOwnerID)

    case .completeTask:
      return await executeCompleteTask(
        toolCall.arguments,
        expectedOwnerID: expectedOwnerID)

    case "manage_agent_pills":
      return await executeManageAgentPills(toolCall.arguments)

    case "setup_agent_provider":
      return await executeSetupAgentProvider(
        toolCall.arguments,
        originatingChatMode: originatingChatMode,
        originatingClientScope: originatingClientScope
      )

    case "execute_sql":
      return await executeSQL(toolCall.arguments)

    case "semantic_search", "search_screen_history":
      return await executeSemanticSearch(toolCall.arguments)

    case "get_daily_recap":
      return await executeDailyRecap(toolCall.arguments)

    case "search_tasks":
      return await executeSearchTasks(toolCall.arguments)

    case "complete_task":
      return await executeCompleteTask(toolCall.arguments)

    case "delete_task":
      return await executeDeleteTask(toolCall.arguments)

    // Onboarding tools
    case .requestPermission:
      let isOnboardingRequest = isOnboardingSurface
      let permissionAuthorization = currentOwnerAuthorizationSnapshot
      guard
        let result = await performOwnerBoundAsyncPhysicalEffect(
          expectedOwnerID: expectedOwnerID,
          authorizationSnapshot: permissionAuthorization,
          ownerIsCurrent: {
            isPermissionAuthorizationCurrent(
              $0,
              authorizationSnapshot: permissionAuthorization)
          },
          effect: {
            await executeRequestPermission(
              toolCall.arguments,
              expectedOwnerID: expectedOwnerID,
              authorizationSnapshot: permissionAuthorization)
          })
      else { return authorizedOwnerChangedResult() }
      guard
        isPermissionAuthorizationCurrent(
          expectedOwnerID,
          authorizationSnapshot: permissionAuthorization)
      else { return authorizedOwnerChangedResult() }
      let permType = toolCall.arguments["type"] as? String ?? "unknown"
      let granted = permissionToolResultGranted(result)
      if isOnboardingRequest {
        AnalyticsManager.shared.onboardingChatToolUsed(
          tool: "request_permission",
          properties: ["permission": permType, "result": granted ? "granted" : "pending"])
        if !granted {
          let callback = onPermissionPending
          DispatchQueue.main.async {
            publishPermissionPendingIfCurrent(
              permType,
              expectedOwnerID: expectedOwnerID,
              authorizationSnapshot: permissionAuthorization,
              callback: callback)
          }
        }
      }
      return result

    case .checkPermissionStatus:
      let permissionAuthorization = currentOwnerAuthorizationSnapshot
      let result = await executeCheckPermissionStatus(
        toolCall.arguments,
        expectedOwnerID: expectedOwnerID,
        authorizationSnapshot: permissionAuthorization)
      guard
        isPermissionAuthorizationCurrent(
          expectedOwnerID,
          authorizationSnapshot: permissionAuthorization)
      else { return authorizedOwnerChangedResult() }
      AnalyticsManager.shared.onboardingChatToolUsed(tool: "check_permission_status")
      return result

    case .scanFiles:
      AnalyticsManager.shared.onboardingChatToolUsed(tool: "scan_files")
      return await executeScanFiles(toolCall.arguments, expectedOwnerID: expectedOwnerID)

    case .setUserPreferences:
      let result = await executeSetUserPreferences(
        toolCall.arguments,
        expectedOwnerID: expectedOwnerID,
        api: backendAPIClient)
      guard isExpectedOwnerCurrent(expectedOwnerID) else { return authorizedOwnerChangedResult() }
      var props: [String: Any] = [:]
      if let name = toolCall.arguments["name"] as? String {
        props["name_changed"] = true
        props["name"] = name
      }
      if let lang = toolCall.arguments["language"] as? String { props["language"] = lang }
      AnalyticsManager.shared.onboardingChatToolUsed(
        tool: "set_user_preferences", properties: props)
      return result

    case .askFollowup:
      let result = await executeAskFollowup(
        toolCall.arguments,
        expectedOwnerID: expectedOwnerID)
      guard isExpectedOwnerCurrent(expectedOwnerID) else { return authorizedOwnerChangedResult() }
      let question = toolCall.arguments["question"] as? String ?? ""
      let optionCount = (toolCall.arguments["options"] as? [String])?.count ?? 0
      AnalyticsManager.shared.onboardingChatToolUsed(
        tool: "ask_followup",
        properties: ["question_length": question.count, "option_count": optionCount])
      return result

    case .completeOnboarding:
      if !OnboardingChatPersistence.isGoalCompleted {
        return
          "ERROR: Cannot complete onboarding yet. The user has NOT set their monthly goal. You MUST call ask_followup to ask about their top goal this month BEFORE calling complete_onboarding. Call get_email_insights first for context, then ask the goal question."
      }
      let result = await executeCompleteOnboarding(
        toolCall.arguments,
        expectedOwnerID: expectedOwnerID)
      guard isExpectedOwnerCurrent(expectedOwnerID) else { return authorizedOwnerChangedResult() }
      AnalyticsManager.shared.onboardingChatToolUsed(tool: "complete_onboarding")
      return result

    case .saveKnowledgeGraph:
      let result = await executeSaveKnowledgeGraph(
        toolCall.arguments,
        expectedOwnerID: expectedOwnerID)
      guard isExpectedOwnerCurrent(expectedOwnerID) else { return authorizedOwnerChangedResult() }
      let nodeCount = (toolCall.arguments["nodes"] as? [[String: Any]])?.count ?? 0
      let edgeCount = (toolCall.arguments["edges"] as? [[String: Any]])?.count ?? 0
      AnalyticsManager.shared.onboardingChatToolUsed(
        tool: "save_knowledge_graph", properties: ["nodes": nodeCount, "edges": edgeCount])
      return result

    case .getEmailInsights:
      let result = executeGetEmailInsights()
      AnalyticsManager.shared.onboardingChatToolUsed(
        tool: "get_email_insights",
        properties: [
          "has_email": emailInsightsText != nil, "has_calendar": calendarInsightsText != nil,
        ])
      return result

    case .captureScreen:
      return await executeCaptureScreen(
        context: telemetryContext,
        expectedOwnerID: expectedOwnerID)

    case .getWorkContext:
      return await executeGetWorkContext(
        toolCall.arguments,
        context: telemetryContext,
        expectedOwnerID: expectedOwnerID)

    case .fillCloudConnectorForm:
      guard
        let result = await performOwnerBoundAsyncPhysicalEffect(
          expectedOwnerID: expectedOwnerID,
          effect: {
            await CloudConnectorFormAutomation.fill(
              toolCall.arguments,
              expectedOwnerID: expectedOwnerID)
          })
      else { return authorizedOwnerChangedResult() }
      return result

    // Backend RAG/calendar tools — call Python backend /v1/tools/* endpoints
    case .getConversations, .searchConversations, .getMemories, .searchMemories, .getActionItems,
      .createActionItem, .updateActionItem, .createCalendarEvent:
      return await executeBackendTool(
        toolCall,
        expectedOwnerID: expectedOwnerID,
        api: backendAPIClient)

    case .unhandled:
      if toolCall.name == "get_local_status" {
        return await executeLocalStatus(expectedOwnerID: expectedOwnerID)
      }
      if toolCall.name == "get_file_scan_results" || toolCall.name == "start_file_scan" {
        return await executeScanFiles(toolCall.arguments, expectedOwnerID: expectedOwnerID)
      }
      return "Unknown tool: \(toolCall.name)"
    }
  }

  nonisolated static func isExpectedOwnerCurrent(
    _ expectedOwnerID: String?,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) -> Bool {
    if let authorization = authorizationSnapshot ?? ChatToolOwnerAuthorization.snapshot {
      return (expectedOwnerID == nil || authorization.ownerID == expectedOwnerID)
        && RuntimeOwnerIdentity.isAuthorizationCurrent(authorization)
    }
    guard let expectedOwnerID else { return true }
    return AuthorizedToolExecution.isOwnerCurrent(expectedOwnerID)
  }

  /// Permission onboarding is the one authorized signed-out tool path. A nil
  /// owner therefore needs its own fail-closed rule instead of the generic
  /// "no expected owner" behavior: it remains valid only while still signed
  /// out and outside an effective-owner transition.
  nonisolated static func isPermissionAuthorizationCurrent(
    _ expectedOwnerID: String?,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?
  ) -> Bool {
    guard !Task.isCancelled else { return false }
    if let authorizationSnapshot {
      return (expectedOwnerID == nil || authorizationSnapshot.ownerID == expectedOwnerID)
        && RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot)
    }
    if let expectedOwnerID {
      return AuthorizedToolExecution.isOwnerCurrent(expectedOwnerID)
    }
    return !RuntimeOwnerIdentity.effectiveOwnerTransitionInProgress
      && RuntimeOwnerIdentity.currentOwnerId() == nil
  }

  /// Cancellation-aware adapter used by TCC callback APIs. The callback may
  /// still arrive after cancellation, but it can no longer resume or publish
  /// into the revoked owner-bound task.
  nonisolated static func awaitCancellablePermissionRequest<Value: Sendable>(
    _ register: @escaping @Sendable (@escaping @Sendable (Value) -> Void) -> Void
  ) async -> Value? {
    let state = CancellablePermissionContinuation<Value>()
    return await withTaskCancellationHandler {
      await withCheckedContinuation { continuation in
        state.install(continuation)
        guard !Task.isCancelled else {
          state.finish(nil)
          return
        }
        register { value in
          state.finish(value)
        }
      }
    } onCancel: {
      state.finish(nil)
    }
  }

  nonisolated static func authorizedOwnerChangedResult() -> String {
    #"{"ok":false,"error":{"code":"authorized_execution_owner_changed","message":"The signed-in account changed while the authorized tool was executing."}}"#
  }

  @MainActor
  static func performOwnerBoundPhysicalEffect<T: Sendable>(
    expectedOwnerID: String?,
    ownerIsCurrent: (String?) -> Bool = { isExpectedOwnerCurrent($0) },
    effect: () -> T
  ) -> T? {
    guard ownerIsCurrent(expectedOwnerID) else { return nil }
    return effect()
  }

  @MainActor
  static func performOwnerBoundAsyncPhysicalEffect<T: Sendable>(
    expectedOwnerID: String?,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil,
    ownerIsCurrent: ((String?) -> Bool)? = nil,
    prepare: () async -> Void = {},
    effect: () async -> T
  ) async -> T? {
    let validateOwner =
      ownerIsCurrent ?? {
        isExpectedOwnerCurrent($0, authorizationSnapshot: authorizationSnapshot)
      }
    guard validateOwner(expectedOwnerID) else { return nil }
    await prepare()
    guard validateOwner(expectedOwnerID) else { return nil }
    return await effect()
  }

  // MARK: - Physical Execution Preconditions

  nonisolated enum PhysicalExecutionPrecondition: Equatable {
    case satisfied
    case failed(String)
  }

  nonisolated static func physicalExecutionPrecondition(
    toolName: String
  ) -> PhysicalExecutionPrecondition {
    switch toolName {
    case "capture_screen", "get_screenshot":
      if isChatScreenshotSharingEnabled {
        return .satisfied
      }
      return .failed(
        executionPreconditionFailedMessage(
          toolName: toolName,
          reason: "screenshot_sharing_disabled",
          message:
            "Screenshot sharing is turned off. The user can enable \"Screen Sharing in Chat\" in Settings → Floating Bar to let Omi see the screen."
        ))

    default:
      return .satisfied
    }
  }

  /// User-facing grant for `desktop.context.screenshot_image`. Stored in
  /// UserDefaults so the nonisolated policy check can read it synchronously;
  /// absent key means enabled (default on).
  nonisolated static var isChatScreenshotSharingEnabled: Bool {
    UserDefaults.standard.object(forKey: DefaultsKey.chatScreenshotSharingEnabled.rawValue) == nil
      || UserDefaults.standard.bool(forKey: DefaultsKey.chatScreenshotSharingEnabled)
  }

  private nonisolated static func executionPreconditionFailedMessage(
    toolName: String,
    reason: String,
    message: String
  ) -> String {
    let payload =
      [
        "ok": false,
        "code": "execution_precondition_failed",
        "reason": reason,
        "tool": toolName,
        "message": message,
      ] as [String: Any]
    guard
      let data = try? JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys]),
      let json = String(data: data, encoding: .utf8)
    else {
      return "EXECUTION_PRECONDITION_FAILED: \(message)"
    }
    return "EXECUTION_PRECONDITION_FAILED: \(json)"
  }

  private nonisolated static func permissionRequiredMessage(
    toolName: String,
    permission: String,
    message: String
  ) -> String {
    let payload =
      [
        "ok": false,
        "code": "permission_required",
        "tool": toolName,
        "permission": permission,
        "message": message,
        "next_tool": "request_permission",
        "next_tool_arguments": ["type": permission],
      ] as [String: Any]
    guard
      let data = try? JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys]),
      let json = String(data: data, encoding: .utf8)
    else {
      return "PERMISSION_REQUIRED: \(message)"
    }
    return "PERMISSION_REQUIRED: \(json)"
  }

  /// Execute multiple tool calls and return results keyed by tool name
  static func executeAll(_ toolCalls: [ToolCall]) async -> [String: String] {
    var results: [String: String] = [:]

    for call in toolCalls {
      results[call.name] = await execute(call)
    }

    return results
  }

  // MARK: - Screen Capture

  /// Capture the current screen and return the file path
  private static func executeCaptureScreen(
    context: ScreenContextTelemetryContext,
    expectedOwnerID: String?
  ) async -> String {
    guard isExpectedOwnerCurrent(expectedOwnerID) else { return authorizedOwnerChangedResult() }
    guard CGPreflightScreenCaptureAccess() else {
      ScreenContextToolTelemetry.trackToolResult(
        toolName: "capture_screen",
        context: context,
        ok: false,
        failureCode: .permissionDenied,
        permissionTCCGranted: false
      )
      return permissionRequiredMessage(
        toolName: "capture_screen",
        permission: "screen_recording",
        message:
          "Screen Recording permission is not granted. Tell the user Omi cannot see their current screen yet and ask whether they want to grant access. Call request_permission with type=screen_recording only after they explicitly request or affirm it."
      )
    }
    guard
      let capture = performOwnerBoundPhysicalEffect(
        expectedOwnerID: expectedOwnerID,
        effect: { ScreenCaptureManager.captureScreenWithDetailTiles() }) ?? nil
    else {
      guard isExpectedOwnerCurrent(expectedOwnerID) else { return authorizedOwnerChangedResult() }
      ScreenContextToolTelemetry.trackToolResult(
        toolName: "capture_screen",
        context: context,
        ok: false,
        failureCode: .captureFailed,
        permissionTCCGranted: true
      )
      return "Error: Failed to capture screen"
    }
    ScreenContextToolTelemetry.trackToolResult(
      toolName: "capture_screen",
      context: context,
      ok: true,
      permissionTCCGranted: true
    )
    return captureScreenToolResult(
      fullPath: capture.fullImageURL.path,
      tiles: capture.tiles.map { (label: $0.label, rect: $0.rect, path: $0.url.path) }
    )
  }

  /// Format the capture_screen tool result: the full-screen path first (the
  /// original single-line contract), then native-resolution detail tiles. Vision
  /// APIs downscale a full-Retina frame until dense UI text (product titles,
  /// prices, labels) is illegible — the model then guesses instead of reading.
  /// The tile listing tells it where to re-read at native sharpness. Pure and
  /// nonisolated so it is hermetically testable.
  nonisolated static func captureScreenToolResult(
    fullPath: String,
    tiles: [(label: String, rect: CGRect, path: String)]
  ) -> String {
    guard !tiles.isEmpty else { return fullPath }
    var lines = [fullPath]
    lines.append("")
    lines.append(
      "Detail tiles (native resolution). The full screenshot above gets downscaled before you see it, "
        + "which can make small text unreadable. Before quoting or relying on small on-screen text "
        + "(titles, prices, sizes, labels) or choosing between similar-looking items, Read the tile "
        + "covering that part of the screen and take the exact text from it:")
    for tile in tiles {
      let r = tile.rect
      lines.append(
        "- \(tile.label) (x \(Int(r.minX))-\(Int(r.maxX)), y \(Int(r.minY))-\(Int(r.maxY))): \(tile.path)")
    }
    return lines.joined(separator: "\n")
  }

  private static func executeGetWorkContext(
    _ arguments: [String: Any],
    context: ScreenContextTelemetryContext,
    expectedOwnerID: String?
  ) async -> String {
    guard isExpectedOwnerCurrent(expectedOwnerID) else { return authorizedOwnerChangedResult() }
    let payloadBox = await ScreenContextWorkContextBuilder.payloadBox(arguments: RuntimeJSONPayloadBox(arguments))
    let payload = payloadBox.value
    guard isExpectedOwnerCurrent(expectedOwnerID) else { return authorizedOwnerChangedResult() }
    let telemetry = ScreenContextWorkContextBuilder.telemetryValues(from: payload)
    ScreenContextToolTelemetry.trackToolResult(
      toolName: "get_work_context",
      context: context,
      ok: telemetry.ok && telemetry.screenNowAvailable == true,
      failureCode: telemetry.failureCode,
      screenNowAvailable: telemetry.screenNowAvailable,
      timelineCount: telemetry.timelineCount,
      latestCaptureAgeSeconds: telemetry.latestCaptureAgeSeconds,
      hasOCRPreview: telemetry.hasOCRPreview,
      imageBytes: telemetry.imageBytes,
      permissionTCCGranted: CGPreflightScreenCaptureAccess()
    )
    guard
      let data = try? JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted, .sortedKeys]),
      let json = String(data: data, encoding: .utf8)
    else {
      return #"{"ok":false,"name":"get_work_context","failure_code":"unknown"}"#
    }
    return json
  }

  // MARK: - SQL Execution

  /// Blocked SQL keywords that are never allowed
  private static let blockedKeywords: Set<String> = [
    "DROP", "ALTER", "CREATE", "PRAGMA", "ATTACH", "DETACH", "VACUUM",
  ]

  /// Execute a SQL query on omi.db
  private static func executeSQL(
    _ args: [String: Any],
    expectedOwnerID: String?
  ) async -> String {
    return await executeSQL(args, dbQueue: nil, expectedOwnerID: expectedOwnerID)
  }

  static func executeSQL(
    _ args: [String: Any],
    dbQueue: DatabasePool?,
    expectedOwnerID: String?
  ) async -> String {
    guard isExpectedOwnerCurrent(expectedOwnerID) else { return authorizedOwnerChangedResult() }
    guard let query = args["query"] as? String, !query.isEmpty else {
      return "Error: query is required"
    }
    let parameters: [String]
    if let providedParameters = args["parameters"] {
      guard let values = providedParameters as? [String] else {
        return "Error: parameters must be an array of strings"
      }
      parameters = values
    } else {
      parameters = []
    }

    let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
    let upper = trimmed.uppercased()
    let readOnly = (args["read_only"] as? Bool) == true

    // Block dangerous keywords
    for keyword in blockedKeywords {
      // Match keyword at word boundary (start of string or after whitespace/punctuation)
      if upper.range(of: "\\b\(keyword)\\b", options: .regularExpression) != nil {
        return "Error: \(keyword) statements are not allowed"
      }
    }

    // Block multi-statement queries (semicolon followed by another statement)
    let statements = trimmed.components(separatedBy: ";")
      .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
      .filter { !$0.isEmpty }
    if statements.count > 1 {
      return "Error: multi-statement queries are not allowed. Send one statement at a time."
    }

    // Determine query type
    let isSelect = upper.hasPrefix("SELECT") || upper.hasPrefix("WITH")
    let isInsert = upper.hasPrefix("INSERT")
    let isUpdate = upper.hasPrefix("UPDATE")
    let isDelete = upper.hasPrefix("DELETE")
    if readOnly && !isReadOnlySQLStatement(trimmed) {
      return "Error: this SQL surface is read-only. Use SELECT or read-only WITH queries."
    }

    // Block UPDATE/DELETE without WHERE
    if (isUpdate || isDelete) && !upper.contains("WHERE") {
      return "Error: \(isUpdate ? "UPDATE" : "DELETE") without WHERE clause is not allowed"
    }

    guard isExpectedOwnerCurrent(expectedOwnerID) else { return authorizedOwnerChangedResult() }
    let databaseQueue: DatabasePool
    if let dbQueue {
      databaseQueue = dbQueue
    } else if let dbQueue = await RewindDatabase.shared.getDatabaseQueue() {
      databaseQueue = dbQueue
    } else {
      return "Error: database not available"
    }

    do {
      if isSelect {
        return try await executeSelectQuery(
          trimmed,
          upper: upper,
          parameters: parameters,
          dbQueue: databaseQueue,
          expectedOwnerID: expectedOwnerID)
      } else if isInsert || isUpdate || isDelete {
        return try await executeWriteQuery(
          trimmed,
          parameters: parameters,
          dbQueue: databaseQueue,
          expectedOwnerID: expectedOwnerID)
      } else {
        return "Error: only SELECT, INSERT, UPDATE, DELETE statements are allowed"
      }
    } catch {
      logError("Tool execute_sql failed", error: error)
      return "SQL Error: The local database could not complete that query."
    }
  }

  nonisolated static func isReadOnlySQLStatement(_ query: String) -> Bool {
    let keywordSQL = sqlForKeywordScan(query)
    let upper = keywordSQL.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
    guard upper.hasPrefix("SELECT") || upper.hasPrefix("WITH") else {
      return false
    }
    for keyword in ["INSERT", "UPDATE", "DELETE", "REPLACE"] {
      if upper.range(of: "\\b\(keyword)\\b", options: .regularExpression) != nil {
        return false
      }
    }
    return true
  }

  private nonisolated static func sqlForKeywordScan(_ query: String) -> String {
    var result = ""
    var index = query.startIndex

    while index < query.endIndex {
      let character = query[index]
      let next = query.index(after: index)
      let nextCharacter = next < query.endIndex ? query[next] : nil

      if character == "-", nextCharacter == "-" {
        index = next
        while index < query.endIndex, query[index] != "\n" {
          index = query.index(after: index)
        }
        result.append(" ")
        continue
      }

      if character == "/", nextCharacter == "*" {
        index = query.index(after: next)
        while index < query.endIndex {
          let after = query.index(after: index)
          if query[index] == "*", after < query.endIndex, query[after] == "/" {
            index = query.index(after: after)
            break
          }
          index = after
        }
        result.append(" ")
        continue
      }

      if character == "'" || character == "\"" || character == "`" {
        index = skipQuotedSQLToken(in: query, from: index, closing: character)
        result.append(" ")
        continue
      }

      if character == "[" {
        index = skipQuotedSQLToken(in: query, from: index, closing: "]")
        result.append(" ")
        continue
      }

      result.append(character)
      index = next
    }

    return result
  }

  private nonisolated static func skipQuotedSQLToken(in query: String, from start: String.Index, closing: Character)
    -> String.Index
  {
    var index = query.index(after: start)
    while index < query.endIndex {
      let character = query[index]
      let next = query.index(after: index)
      if character == closing {
        if next < query.endIndex, query[next] == closing {
          index = query.index(after: next)
          continue
        }
        return next
      }
      index = next
    }
    return query.endIndex
  }

  /// Execute a SELECT query and format results as text
  private static func executeSelectQuery(
    _ query: String,
    upper: String,
    parameters: [String],
    dbQueue: DatabasePool,
    expectedOwnerID: String?
  )
    async throws -> String
  {
    guard isExpectedOwnerCurrent(expectedOwnerID) else { return authorizedOwnerChangedResult() }
    // Auto-append LIMIT 200 if no LIMIT clause
    var finalQuery = query
    if !upper.contains("LIMIT") {
      // Remove trailing semicolon if present
      if finalQuery.hasSuffix(";") {
        finalQuery = String(finalQuery.dropLast())
      }
      finalQuery += " LIMIT 200"
    }

    let query = finalQuery
    let formatted = try await dbQueue.read { db -> (text: String, count: Int) in
      let rows = try Row.fetchAll(db, sql: query, arguments: StatementArguments(parameters))

      if rows.isEmpty {
        return ("No results", 0)
      }

      // Get column names from first row
      let columns = Array(rows[0].columnNames)
      var lines: [String] = []

      // Header
      lines.append(columns.joined(separator: " | "))
      lines.append(String(repeating: "-", count: min(columns.count * 20, 120)))

      // Rows (max 200) — Row is RandomAccessCollection of (String, DatabaseValue)
      for row in rows.prefix(200) {
        let values = row.map { (_, dbValue) -> String in
          let value: String
          switch dbValue.storage {
          case .null:
            value = "NULL"
          case .int64(let i):
            value = String(i)
          case .double(let d):
            value = String(d)
          case .string(let s):
            value = s
          case .blob(let data):
            value = "<\(data.count) bytes>"
          }
          // Truncate long cell values
          if value.count > 500 {
            return String(value.prefix(500)) + "..."
          }
          return value
        }
        lines.append(values.joined(separator: " | "))
      }

      lines.append("\n\(rows.count) row(s)")
      return (lines.joined(separator: "\n"), rows.count)
    }
    guard isExpectedOwnerCurrent(expectedOwnerID) else { return authorizedOwnerChangedResult() }

    log("Tool execute_sql returned \(formatted.count) rows")
    return formatted.text
  }

  /// Execute a write (INSERT/UPDATE/DELETE) query
  static func executeWriteQuery(
    _ query: String,
    parameters: [String] = [],
    dbQueue: DatabasePool,
    expectedOwnerID: String?,
    ownerIsCurrent: @escaping @Sendable (String?) -> Bool = { isExpectedOwnerCurrent($0) }
  ) async throws
    -> String
  {
    guard ownerIsCurrent(expectedOwnerID) else { return authorizedOwnerChangedResult() }
    let authorization = LocalMutationAuthorization {
      ownerIsCurrent(expectedOwnerID)
    }
    let changes: Int
    do {
      changes = try await authorization.withCommitLease {
        try await dbQueue.write { db -> Int in
          try authorization.require()
          try db.execute(sql: query, arguments: StatementArguments(parameters))
          try authorization.require()
          return db.changesCount
        }
      }
    } catch LocalMutationAuthorizationError.revoked {
      return authorizedOwnerChangedResult()
    }
    guard ownerIsCurrent(expectedOwnerID) else { return authorizedOwnerChangedResult() }

    log("Tool execute_sql write: \(changes) row(s) affected")

    // If the query modified the action_items table, refresh TasksStore from local cache
    let completedPostCommitEffects = await executeOwnerBoundSQLPostCommitEffects(
      changes: changes,
      query: query,
      expectedOwnerID: expectedOwnerID,
      reloadTasks: {
        await TasksStore.shared.reloadFromLocalCache(
          expectedOwnerID: expectedOwnerID,
          authorizationSnapshot: currentOwnerAuthorizationSnapshot)
      },
      retryUnsyncedTasks: {
        await TasksStore.shared.retryUnsyncedItems(
          includeRecent: true,
          expectedOwnerID: expectedOwnerID,
          authorizationSnapshot: currentOwnerAuthorizationSnapshot)
      })
    guard completedPostCommitEffects else { return authorizedOwnerChangedResult() }

    return "OK: \(changes) row(s) affected"
  }

  static func executeOwnerBoundSQLPostCommitEffects(
    changes: Int,
    query: String,
    expectedOwnerID: String?,
    ownerIsCurrent: (String?) -> Bool = { isExpectedOwnerCurrent($0) },
    reloadTasks: () async -> Void,
    retryUnsyncedTasks: () async -> Void
  ) async -> Bool {
    guard ownerIsCurrent(expectedOwnerID) else { return false }
    guard changes > 0 else { return true }
    let upper = query.uppercased()
    guard upper.contains("ACTION_ITEMS") else { return true }
    log("Tool execute_sql: action_items modified, refreshing TasksStore")
    await reloadTasks()
    guard ownerIsCurrent(expectedOwnerID) else { return false }
    if upper.contains("INSERT") {
      await retryUnsyncedTasks()
      guard ownerIsCurrent(expectedOwnerID) else { return false }
    }
    if originatingClientScope == AgentLegacyClientScope.floatingPill {
      return
        "Error: spawn_agent is unavailable from an existing floating background agent. Complete the assigned task directly in this agent."
    }
    let brief = ((args["brief"] as? String) ?? (args["query"] as? String) ?? "")
      .trimmingCharacters(in: .whitespacesAndNewlines)
    guard !brief.isEmpty else {
      return "Error: Missing brief. Pass a clear, self-contained task brief."
    }
    let title = (args["title"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines)
    let providerName = ((args["provider"] as? String) ?? "")
      .trimmingCharacters(in: .whitespacesAndNewlines)
      .lowercased()
      .replacingOccurrences(of: " ", with: "")
    guard let decision = AgentProviderRouter.dispatchDecision(providerName: providerName, brief: brief) else {
      return "Error: Unsupported provider '\(providerName)'. Supported providers: openclaw, hermes, codex, auto."
    }
    let directedProvider = decision.primary
    let routedFallbacks = decision.fallbacks
    if let directedProvider {
      let health = AgentProviderHealth.report(for: directedProvider)
      guard health.readiness == .ready else {
        return "Error: \(health.detail)"
      }
    }
    let model =
      ShortcutSettings.shared.selectedModel.isEmpty
      ? "claude-sonnet-4-6" : ShortcutSettings.shared.selectedModel
    guard
      let pill = AgentDelegationExecutor.shared.spawnResolvedDelegation(
        .init(
          originalUserText: brief,
          brief: brief,
          title: (title?.isEmpty == false) ? title : directedProvider?.displayName,
          spokenAck: nil,
          directedProvider: directedProvider,
          validateAgainstOriginalUserText: false
        ),
        model: model,
        fromVoice: false
      )
    else {
      return
        "Error: Missing self-contained brief. Pass a clear task with enough context for a background agent to execute independently."
    }
    pill.fallbackProviders = routedFallbacks
    return """
      Agent started as a floating agent pill.
      id: \(pill.id.uuidString)
      title: \(pill.title)
      status: \(pill.status.displayLabel)
      """
  }

  /// Install a missing local agent provider through the deterministic
  /// LocalAgentProviderInstaller: a native confirmation dialog showing the
  /// exact command is the REAL consent gate, then code runs the official
  /// install command via Process and verifies with the shared detector — no
  /// installer agent, so a prompt-injected call can never execute anything
  /// by itself. Idempotent for already-installed providers.
  private static func executeSetupAgentProvider(
    _ args: [String: Any],
    originatingChatMode: ChatMode?,
    originatingClientScope: String?
  ) async -> String {
    if originatingChatMode == .ask {
      return
        "Error: setup_agent_provider is unavailable in Ask mode. Switch to Act mode before installing an agent provider."
    }
    if originatingClientScope == AgentLegacyClientScope.floatingPill {
      return "Error: setup_agent_provider is unavailable from an existing floating background agent."
    }
    let providerName = AgentPillsManager.DirectedProvider.normalizedRawValue(args["provider"] as? String)
    guard let provider = AgentPillsManager.DirectedProvider(rawValue: providerName) else {
      return "Error: \(AgentPillsManager.DirectedProvider.unsupportedProviderMessage(providerName))"
    }
    return LocalAgentProviderInstaller.shared.beginInstall(for: provider)
  }

  private static func executeManageAgentPills(_ args: [String: Any]) async -> String {
    let action = ((args["action"] as? String) ?? "list")
      .trimmingCharacters(in: .whitespacesAndNewlines)
    let agentId = (args["agent_id"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines)
    return AgentPillsManager.shared.manage(action: action, agentId: agentId)
  }

  // MARK: - Local Status

  private static func executeLocalStatus(expectedOwnerID: String?) async -> String {
    guard isExpectedOwnerCurrent(expectedOwnerID) else { return authorizedOwnerChangedResult() }
    guard await RewindDatabase.shared.getDatabaseQueue() != nil else {
      return """
        {
          "ok": false,
          "mode": "local_omi_desktop",
          "database_available": false,
          "screen_history_available": false,
          "local_affordances": \(localAffordancesJSON()),
          "message": "Omi Desktop is running, but the local database is not available yet."
        }
        """
    }
    guard isExpectedOwnerCurrent(expectedOwnerID) else { return authorizedOwnerChangedResult() }

    do {
      let stats = try await RewindDatabase.shared.getStats()
      guard isExpectedOwnerCurrent(expectedOwnerID) else { return authorizedOwnerChangedResult() }
      let formatter = ISO8601DateFormatter()
      let payload: [String: Any] = [
        "ok": true,
        "mode": "local_omi_desktop",
        "database_available": true,
        "screen_history_available": stats.total > 0,
        "screenshot_count": stats.total,
        "indexed_screenshot_count": stats.indexed,
        "oldest_capture_at": stats.oldestDate.map { formatter.string(from: $0) } ?? NSNull(),
        "latest_capture_at": stats.newestDate.map { formatter.string(from: $0) } ?? NSNull(),
        "local_affordances": localAffordances,
        "recommended_first_tools": [
          "search_screen_history for fuzzy Rewind/OCR questions",
          "get_screenshot after a search result returns a screenshot_id",
          "get_daily_recap for today/yesterday/this week",
          "execute_sql for exact read-only local database questions",
        ],
      ]
      guard
        let data = try? JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted, .sortedKeys]),
        let json = String(data: data, encoding: .utf8)
      else {
        return "Local Omi Desktop is available. Screenshots: \(stats.total), indexed: \(stats.indexed)."
      }
      return json
    } catch {
      logError("Tool get_local_status failed", error: error)
      return """
        {
          "ok": false,
          "mode": "local_omi_desktop",
          "database_available": false,
          "screen_history_available": false,
          "local_affordances": \(localAffordancesJSON()),
          "message": "Failed to read local Omi status: \(error.localizedDescription)"
        }
        """
    }
  }

  private static let localAffordances = [
    "Rewind screen history and OCR search",
    "raw screenshot image retrieval by screenshot_id",
    "local transcription and conversation tables",
    "read-only SQL over the local Omi Desktop database",
    "daily activity recaps",
    "indexed files and app/window activity",
    "local goals and progress data",
    "local task search, completion, and deletion",
  ]

  private static func localAffordancesJSON() -> String {
    guard
      let data = try? JSONSerialization.data(withJSONObject: localAffordances, options: [.sortedKeys]),
      let json = String(data: data, encoding: .utf8)
    else {
      return "[]"
    }
    return json
  }

  // MARK: - Daily Recap

  /// Get a pre-formatted daily activity recap
  private static func executeDailyRecap(
    _ args: [String: Any],
    expectedOwnerID: String?
  ) async -> String {
    guard isExpectedOwnerCurrent(expectedOwnerID) else { return authorizedOwnerChangedResult() }
    let daysAgo = max(0, (args["days_ago"] as? Int) ?? 1)
    let dateLabel = daysAgo == 0 ? "Today" : daysAgo == 1 ? "Yesterday" : "Past \(daysAgo) days"

    guard let dbQueue = await RewindDatabase.shared.getDatabaseQueue() else {
      return "Error: database not available"
    }
    guard isExpectedOwnerCurrent(expectedOwnerID) else { return authorizedOwnerChangedResult() }

    // For today (daysAgo=0), upper bound is now; for past days, upper bound is start of today
    let upperBound =
      daysAgo == 0
      ? "datetime('now', 'localtime')"
      : "datetime('now', 'start of day', 'localtime')"

    do {
      let result = try await dbQueue.read { db in
        // Q1: App usage
        let apps = try Row.fetchAll(
          db,
          sql: """
            SELECT appName, COUNT(*) as screenshots, ROUND(COUNT(*) * 10.0 / 60, 1) as minutes,
                MIN(time(timestamp, 'localtime')) as first_seen, MAX(time(timestamp, 'localtime')) as last_seen
            FROM screenshots
            WHERE timestamp >= datetime('now', 'start of day', '-\(daysAgo) day', 'localtime')
                AND timestamp < \(upperBound)
                AND appName IS NOT NULL AND appName != ''
            GROUP BY appName ORDER BY screenshots DESC
            """)

        // Q2: Conversations
        let convos = try Row.fetchAll(
          db,
          sql: """
            SELECT title, overview, emoji, category, startedAt, finishedAt,
                ROUND((julianday(finishedAt) - julianday(startedAt)) * 1440, 1) as duration_min
            FROM transcription_sessions
            WHERE startedAt >= datetime('now', 'start of day', '-\(daysAgo) day', 'localtime')
                AND startedAt < \(upperBound)
                AND deleted = 0 AND discarded = 0
            ORDER BY startedAt DESC
            """)

        // Q3: Action items
        let tasks = try Row.fetchAll(
          db,
          sql: """
            SELECT description, completed, priority, createdAt FROM action_items
            WHERE createdAt >= datetime('now', 'start of day', '-\(daysAgo) day', 'localtime')
                AND createdAt < \(upperBound)
                AND deleted = 0
            ORDER BY createdAt DESC
            """)

        // Q4: Focus sessions
        let focusSessions = try Row.fetchAll(
          db,
          sql: """
            SELECT status, appOrSite, description, durationSeconds FROM focus_sessions
            WHERE createdAt >= datetime('now', 'start of day', '-\(daysAgo) day', 'localtime')
                AND createdAt < \(upperBound)
            ORDER BY createdAt DESC
            """)

        // Q5: Memories created
        let memories = try Row.fetchAll(
          db,
          sql: """
            SELECT content, category, source FROM memories
            WHERE createdAt >= datetime('now', 'start of day', '-\(daysAgo) day', 'localtime')
                AND createdAt < \(upperBound)
                AND deleted = 0
            ORDER BY createdAt DESC
            """)

        // Q6: Observations (screen context summaries)
        let observations = try Row.fetchAll(
          db,
          sql: """
            SELECT appName, currentActivity, contextSummary FROM observations
            WHERE createdAt >= datetime('now', 'start of day', '-\(daysAgo) day', 'localtime')
                AND createdAt < \(upperBound)
            ORDER BY createdAt DESC
            LIMIT 20
            """)

        // Format compact markdown
        var out = "# \(dateLabel) Recap\n\n"

        out += "## Apps (\(apps.count) apps)\n"
        if apps.isEmpty {
          out += "No screen activity recorded.\n"
        } else {
          for app in apps.prefix(20) {
            let name = app["appName"] as? String ?? "Unknown"
            let minutes = app["minutes"] as? Double ?? 0
            let screenshots = Self.rowInt(app["screenshots"]) ?? 0
            let firstSeen = app["first_seen"] as? String ?? ""
            let lastSeen = app["last_seen"] as? String ?? ""
            out +=
              "- **\(name)**: \(minutes) min (\(screenshots) captures, \(firstSeen)–\(lastSeen))\n"
          }
          if apps.count > 20 { out += "- ...and \(apps.count - 20) more apps\n" }
        }

        out += "\n## Conversations (\(convos.count))\n"
        if convos.isEmpty {
          out += "No conversations recorded.\n"
        } else {
          for convo in convos {
            let title = convo["title"] as? String ?? "Untitled"
            let overview = convo["overview"] as? String ?? "No summary"
            let emoji = convo["emoji"] as? String ?? ""
            let durMin = convo["duration_min"] as? Double ?? 0
            let dur = durMin > 0 ? " (\(durMin) min)" : ""
            out += "- \(emoji) **\(title)**\(dur): \(overview)\n"
          }
        }

        out += "\n## Tasks (\(tasks.count))\n"
        if tasks.isEmpty {
          out += "No tasks created.\n"
        } else {
          for task in tasks {
            let desc = task["description"] as? String ?? ""
            let completed = (Self.rowInt(task["completed"]) ?? 0) == 1
            let priority = task["priority"] as? String ?? ""
            let check = completed ? "[x]" : "[ ]"
            let pri = priority.isEmpty ? "" : " (\(priority))"
            out += "- \(check) \(desc)\(pri)\n"
          }
        }

        // Focus sessions
        let focused = focusSessions.filter { ($0["status"] as? String) == "focused" }
        let distracted = focusSessions.filter { ($0["status"] as? String) == "distracted" }
        if !focusSessions.isEmpty {
          out += "\n## Focus (\(focused.count) focused, \(distracted.count) distracted)\n"
          for session in focusSessions.prefix(10) {
            let status = session["status"] as? String ?? ""
            let app = session["appOrSite"] as? String ?? ""
            let desc = session["description"] as? String ?? ""
            let dur = Self.rowInt(session["durationSeconds"]) ?? 0
            let durStr = dur > 0 ? " (\(dur / 60)m)" : ""
            let icon = status == "focused" ? "+" : "-"
            out += "- \(icon) \(app)\(durStr): \(desc)\n"
          }
          if focusSessions.count > 10 {
            out += "- ...and \(focusSessions.count - 10) more sessions\n"
          }
        }

        // Memories
        if !memories.isEmpty {
          out += "\n## Memories Learned (\(memories.count))\n"
          for memory in memories.prefix(10) {
            let content = memory["content"] as? String ?? ""
            let category = memory["category"] as? String ?? ""
            let catStr = category.isEmpty ? "" : " [\(category)]"
            out += "- \(content)\(catStr)\n"
          }
          if memories.count > 10 { out += "- ...and \(memories.count - 10) more\n" }
        }

        // Observations (context summaries)
        if !observations.isEmpty {
          out += "\n## Screen Context (\(observations.count) observations)\n"
          for obs in observations.prefix(10) {
            let app = obs["appName"] as? String ?? ""
            let activity = obs["currentActivity"] as? String ?? ""
            out += "- \(app): \(activity)\n"
          }
          if observations.count > 10 {
            out += "- ...and \(observations.count - 10) more observations\n"
          }
        }

        log(
          "Tool get_daily_recap: \(apps.count) apps, \(convos.count) convos, \(tasks.count) tasks, \(focusSessions.count) focus, \(memories.count) memories, \(observations.count) observations"
        )
        return out
      }
      guard isExpectedOwnerCurrent(expectedOwnerID) else { return authorizedOwnerChangedResult() }
      return result
    } catch {
      logError("Tool get_daily_recap failed", error: error)
      return "Error: \(error.localizedDescription)"
    }
  }

  // MARK: - Semantic Search

  /// Search screenshots using vector similarity
  private static func executeSemanticSearch(
    _ args: [String: Any],
    expectedOwnerID: String?
  ) async -> String {
    guard isExpectedOwnerCurrent(expectedOwnerID) else { return authorizedOwnerChangedResult() }
    guard let query = args["query"] as? String, !query.isEmpty else {
      return "Error: query is required"
    }

    let days = max(1, intArgument(args["days"]) ?? 7)
    let appFilter = args["app_filter"] as? String
    let limit = min(max(1, intArgument(args["limit"]) ?? 15), 50)

    let calendar = Calendar.current
    let endDate = Date()
    let startDate = calendar.date(byAdding: .day, value: -days, to: endDate) ?? endDate

    do {
      let vectorResults = try await OCREmbeddingService.shared.searchSimilar(
        query: query,
        startDate: startDate,
        endDate: endDate,
        appFilter: appFilter,
        topK: max(limit * 2, 20)
      )
      guard isExpectedOwnerCurrent(expectedOwnerID) else { return authorizedOwnerChangedResult() }

      log("Tool semantic_search: vector returned \(vectorResults.count) results")

      // Filter by similarity threshold and fetch screenshot details
      let dateFormatter = DateFormatter()
      dateFormatter.dateStyle = .medium
      dateFormatter.timeStyle = .short

      var lines: [String] = []
      var count = 0

      for result in vectorResults where result.similarity > 0.3 {
        guard isExpectedOwnerCurrent(expectedOwnerID) else {
          return authorizedOwnerChangedResult()
        }
        guard
          let screenshot = try? await RewindDatabase.shared.getScreenshot(id: result.screenshotId)
        else {
          continue
        }
        guard isExpectedOwnerCurrent(expectedOwnerID) else {
          return authorizedOwnerChangedResult()
        }

        count += 1
        let dateStr = dateFormatter.string(from: screenshot.timestamp)
        let windowTitle = screenshot.windowTitle ?? ""
        let titlePart = windowTitle.isEmpty ? "" : " - \(windowTitle)"
        lines.append(
          "\n\(count). [\(dateStr)] \(screenshot.appName)\(titlePart) (screenshot_id: \(result.screenshotId), similarity: \(String(format: "%.2f", result.similarity)))"
        )

        // Include OCR text preview (truncated)
        if let ocrText = screenshot.ocrText, !ocrText.isEmpty {
          let preview = String(ocrText.prefix(300))
            .replacingOccurrences(of: "\n", with: " ")
            .trimmingCharacters(in: .whitespacesAndNewlines)
          lines.append("   Content: \(preview)")
        }

        if count >= limit { break }
      }

      if lines.isEmpty {
        return await emptySemanticSearchMessage(
          query: query,
          days: days,
          appFilter: appFilter,
          expectedOwnerID: expectedOwnerID)
      }

      lines.insert("Found \(count) screenshot(s) matching \"\(query)\":", at: 0)

      log("Tool semantic_search returned \(count) results")
      return lines.joined(separator: "\n")

    } catch {
      logError("Tool semantic_search failed", error: error)
      return "Failed to search: \(error.localizedDescription)"
    }
  }

  private static func emptySemanticSearchMessage(
    query: String,
    days: Int,
    appFilter: String?,
    expectedOwnerID: String?
  ) async -> String {
    guard isExpectedOwnerCurrent(expectedOwnerID) else { return authorizedOwnerChangedResult() }
    do {
      let stats = try await RewindDatabase.shared.getStats()
      guard isExpectedOwnerCurrent(expectedOwnerID) else { return authorizedOwnerChangedResult() }
      if stats.total == 0 {
        return """
          No screen history is available yet. Omi Desktop has not captured screenshots on this Mac, so there are no results for "\(query)".
          """
      }
      if stats.indexed == 0 {
        return """
          Omi has \(stats.total) screenshot(s), but they are not ready to search yet. Keep Omi Desktop running and try again in a bit, or use SQL for exact local checks.
          """
      }
      let appText = appFilter.map { " with app filter \"\($0)\"" } ?? ""
      return """
        No matching screen-history results for "\(query)" in the last \(days) day(s)\(appText). Local history exists (\(stats.total) screenshot(s), \(stats.indexed) indexed), so try a broader query, a wider days window, or use execute_sql for exact app/window/OCR filters.
        """
    } catch {
      return
        "No screenshots found matching \"\(query)\" in the last \(days) day(s). Local status could not be read: \(error.localizedDescription)"
    }
  }

  private static func intArgument(_ value: Any?) -> Int? {
    if let value = value as? Int { return value }
    if let value = value as? Double { return Int(value) }
    if let value = value as? String { return Int(value.trimmingCharacters(in: .whitespacesAndNewlines)) }
    return nil
  }

  /// Reads an integer value out of a GRDB `Row`. GRDB decodes SQLite INTEGER
  /// columns to `Int64`, and `Int64 as? Int` is ALWAYS nil in Swift (no numeric
  /// bridging), so a bare `row["col"] as? Int` silently falls through to its
  /// default. Prefer `Int64`, fall back to `Int` for any already-Int value.
  /// `nonisolated` so non-main-actor tests (and callers) can use this pure
  /// helper without hopping the actor.
  nonisolated static func rowInt(_ value: Any?) -> Int? {
    (value as? Int64).map(Int.init) ?? (value as? Int)
  }

  // MARK: - Task Search

  /// Vector similarity search on action_items + staged_tasks using EmbeddingService
  private static func executeSearchTasks(
    _ args: [String: Any],
    expectedOwnerID: String?
  ) async -> String {
    guard isExpectedOwnerCurrent(expectedOwnerID) else { return authorizedOwnerChangedResult() }
    guard let query = args["query"] as? String, !query.isEmpty else {
      return "Error: query is required"
    }

    let includeCompleted = (args["include_completed"] as? Bool) ?? false

    do {
      // Ensure index is loaded
      if !(await EmbeddingService.shared.indexLoaded) {
        guard isExpectedOwnerCurrent(expectedOwnerID) else {
          return authorizedOwnerChangedResult()
        }
        await EmbeddingService.shared.loadIndex()
      }
      guard isExpectedOwnerCurrent(expectedOwnerID) else { return authorizedOwnerChangedResult() }

      // Verify index actually has entries (loadIndex swallows errors)
      if !(await EmbeddingService.shared.indexLoaded) {
        return "Error: embedding index failed to load. Task vector search is unavailable."
      }

      // Embed the query text. The in-memory index is keyed by (source, id), so
      // each search result resolves deterministically against its own table
      // instead of the old staged-first/action-fallback guessing that returned an
      // unrelated task when action_item and staged_task rowids collided.
      let queryEmbedding = try await EmbeddingService.shared.embed(
        text: query, taskType: "RETRIEVAL_QUERY")
      guard isExpectedOwnerCurrent(expectedOwnerID) else { return authorizedOwnerChangedResult() }

      // Search the in-memory index (action_items + staged_tasks share this index)
      let vectorResults = await EmbeddingService.shared.searchSimilar(
        query: queryEmbedding, topK: 15)
      guard isExpectedOwnerCurrent(expectedOwnerID) else { return authorizedOwnerChangedResult() }

      var lines: [String] = []
      var count = 0

      for result in vectorResults where result.similarity > 0.3 {
        guard isExpectedOwnerCurrent(expectedOwnerID) else {
          return authorizedOwnerChangedResult()
        }
        switch result.source {
        case .staged:
          guard let staged = try? await StagedTaskStorage.shared.getStagedTask(id: result.id) else {
            continue
          }
          guard isExpectedOwnerCurrent(expectedOwnerID) else {
            return authorizedOwnerChangedResult()
          }
          if staged.deleted { continue }
          if !includeCompleted && staged.completed { continue }
          count += 1
          let check = staged.completed ? "[x]" : "[ ]"
          let sim = String(format: "%.2f", result.similarity)
          lines.append(
            "\(count). \(check) \(staged.description) (similarity: \(sim), id: \(result.id), source: staged_tasks)"
          )
        case .actionItem:
          guard let record = try? await ActionItemStorage.shared.getActionItem(id: result.id) else {
            continue
          }
          guard isExpectedOwnerCurrent(expectedOwnerID) else {
            return authorizedOwnerChangedResult()
          }
          if record.deleted { continue }
          if !includeCompleted && record.completed { continue }
          count += 1
          let check = record.completed ? "[x]" : "[ ]"
          let pri = (record.priority ?? "").isEmpty ? "" : " [\(record.priority!)]"
          let sim = String(format: "%.2f", result.similarity)
          lines.append(
            "\(count). \(check) \(record.description)\(pri) (similarity: \(sim), id: \(result.id), source: action_items)"
          )
        }

        if count >= 10 { break }
      }

      if lines.isEmpty {
        return
          "No tasks found matching \"\(query)\". The embedding index may not be loaded yet, or no tasks have embeddings."
      }

      lines.insert("Found \(count) task(s) matching \"\(query)\":", at: 0)
      log("Tool search_tasks returned \(count) results")
      return lines.joined(separator: "\n")

    } catch {
      logError("Tool search_tasks failed", error: error)
      return "Error: \(error.localizedDescription)"
    }
  }

  // MARK: - Task Tools

  /// Mark a task completed via TasksStore (handles local + API sync)
  private static func executeCompleteTask(
    _ args: [String: Any],
    expectedOwnerID: String?
  ) async -> String {
    guard isExpectedOwnerCurrent(expectedOwnerID) else {
      return authorizedOwnerChangedResult()
    }
    guard let taskId = args["task_id"] as? String, !taskId.isEmpty else {
      return "Error: task_id is required"
    }

    do {
      guard let task = try await ActionItemStorage.shared.getLocalActionItem(byBackendId: taskId)
      else {
        return "Error: task not found with id '\(taskId)'"
      }
      guard isExpectedOwnerCurrent(expectedOwnerID) else {
        return authorizedOwnerChangedResult()
      }

      if task.deleted == true {
        return "Error: task '\(task.description)' has been deleted"
      }

      if task.completed {
        log("Tool complete_task: '\(task.description)' was already completed")
        return "OK: task '\(task.description)' is already completed"
      }

      await TasksStore.shared.toggleTask(
        task,
        expectedOwnerID: expectedOwnerID,
        authorizationSnapshot: currentOwnerAuthorizationSnapshot)

      guard isExpectedOwnerCurrent(expectedOwnerID) else {
        return authorizedOwnerChangedResult()
      }

      log("Tool complete_task: marked '\(task.description)' as completed")
      return "OK: task '\(task.description)' marked as completed"
    } catch {
      logError("Tool complete_task failed", error: error)
      return "Error: \(error.localizedDescription)"
    }
  }

  /// Delete a task via TasksStore (handles local + API sync)
  private static func executeDeleteTask(
    _ args: [String: Any],
    expectedOwnerID: String?
  ) async -> String {
    guard isExpectedOwnerCurrent(expectedOwnerID) else {
      return authorizedOwnerChangedResult()
    }
    guard let taskId = args["task_id"] as? String, !taskId.isEmpty else {
      return "Error: task_id is required"
    }

    do {
      guard let task = try await ActionItemStorage.shared.getLocalActionItem(byBackendId: taskId)
      else {
        return "Error: task not found with id '\(taskId)'"
      }
      guard isExpectedOwnerCurrent(expectedOwnerID) else {
        return authorizedOwnerChangedResult()
      }

      if task.deleted == true {
        return "Error: task '\(task.description)' is already deleted"
      }

      await TasksStore.shared.deleteTask(
        task,
        expectedOwnerID: expectedOwnerID,
        authorizationSnapshot: currentOwnerAuthorizationSnapshot)

      guard isExpectedOwnerCurrent(expectedOwnerID) else {
        return authorizedOwnerChangedResult()
      }

      log("Tool delete_task: deleted '\(task.description)'")
      return "OK: task '\(task.description)' deleted"
    } catch {
      logError("Tool delete_task failed", error: error)
      return "Error: \(error.localizedDescription)"
    }
  }

  // MARK: - Onboarding Tools

  /// Request a specific macOS permission
  private static func executeRequestPermission(
    _ args: [String: Any],
    expectedOwnerID: String?,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?
  ) async -> String {
    guard
      isPermissionAuthorizationCurrent(
        expectedOwnerID,
        authorizationSnapshot: authorizationSnapshot)
    else { return authorizedOwnerChangedResult() }
    guard let type = permissionType(from: args) else {
      return permissionJSON([
        "ok": false,
        "status": "error",
        "error": "missing_permission_type",
        "valid_types": onboardingPermissionTypes,
      ])
    }

    AnalyticsManager.shared.permissionRequested(permission: type)
    let appState = onboardingAppState ?? AppState.current

    switch type {
    case "screen_recording":
      guard
        isPermissionAuthorizationCurrent(
          expectedOwnerID,
          authorizationSnapshot: authorizationSnapshot)
      else { return authorizedOwnerChangedResult() }
      appState?.screenRecordingGrantAttempts += 1
      let requestResult = await awaitCancellablePermissionRequest { completion in
        Task { @MainActor in
          guard
            isPermissionAuthorizationCurrent(
              expectedOwnerID,
              authorizationSnapshot: authorizationSnapshot)
          else {
            completion(false)
            return
          }
          let granted =
            await ScreenCaptureService
            .requestAllScreenCapturePermissionsAwaitingScreenCaptureKit()
          guard
            isPermissionAuthorizationCurrent(
              expectedOwnerID,
              authorizationSnapshot: authorizationSnapshot)
          else {
            completion(false)
            return
          }
          completion(granted)
        }
      }
      guard requestResult != nil,
        isPermissionAuthorizationCurrent(
          expectedOwnerID,
          authorizationSnapshot: authorizationSnapshot)
      else { return authorizedOwnerChangedResult() }
      _ = openPermissionPrivacySettings(
        pane: "Privacy_ScreenCapture",
        expectedOwnerID: expectedOwnerID,
        authorizationSnapshot: authorizationSnapshot)
      try? await Task.sleep(nanoseconds: 2_000_000_000)
      guard
        isPermissionAuthorizationCurrent(
          expectedOwnerID,
          authorizationSnapshot: authorizationSnapshot)
      else { return authorizedOwnerChangedResult() }
      appState?.checkScreenRecordingPermission()
      return permissionRequestResult(
        type: type,
        granted: ScreenCaptureService.checkPermission(),
        pendingMessage:
          "User needs to toggle Screen Recording for Omi in System Settings. Don't restart yet — the restart is deferred until after Full Disk Access so it happens once.",
        requiresRestart: false
      )

    case "microphone":
      guard
        isPermissionAuthorizationCurrent(
          expectedOwnerID,
          authorizationSnapshot: authorizationSnapshot)
      else { return authorizedOwnerChangedResult() }
      NSApp.activate()
      guard let granted = await requestMicrophonePermissionDirectly(),
        isPermissionAuthorizationCurrent(
          expectedOwnerID,
          authorizationSnapshot: authorizationSnapshot)
      else { return authorizedOwnerChangedResult() }
      appState?.hasMicrophonePermission = granted
      if granted, let appState, appState.hasCompletedOnboarding {
        guard
          isPermissionAuthorizationCurrent(
            expectedOwnerID,
            authorizationSnapshot: authorizationSnapshot)
        else { return authorizedOwnerChangedResult() }
        appState.startTranscription()
      }
      return permissionRequestResult(
        type: type,
        granted: granted,
        pendingMessage: "User needs to allow microphone access in the system dialog.",
        requiresRestart: false
      )

    case "notifications":
      guard
        isPermissionAuthorizationCurrent(
          expectedOwnerID,
          authorizationSnapshot: authorizationSnapshot)
      else { return authorizedOwnerChangedResult() }
      guard let granted = await requestNotificationPermissionDirectly(),
        isPermissionAuthorizationCurrent(
          expectedOwnerID,
          authorizationSnapshot: authorizationSnapshot)
      else { return authorizedOwnerChangedResult() }
      appState?.hasNotificationPermission = granted
      if !granted {
        _ = openNotificationPrivacySettings(
          expectedOwnerID: expectedOwnerID,
          authorizationSnapshot: authorizationSnapshot)
      }
      return permissionRequestResult(
        type: type,
        granted: granted,
        pendingMessage:
          "User needs to allow notifications in the system dialog or enable Omi in System Settings > Notifications.",
        requiresRestart: false
      )

    case "accessibility":
      guard
        isPermissionAuthorizationCurrent(
          expectedOwnerID,
          authorizationSnapshot: authorizationSnapshot)
      else { return authorizedOwnerChangedResult() }
      requestAccessibilityPermissionDirectly(
        expectedOwnerID: expectedOwnerID,
        authorizationSnapshot: authorizationSnapshot)
      try? await Task.sleep(nanoseconds: 2_000_000_000)
      guard
        isPermissionAuthorizationCurrent(
          expectedOwnerID,
          authorizationSnapshot: authorizationSnapshot)
      else { return authorizedOwnerChangedResult() }
      appState?.checkAccessibilityPermission()
      return permissionRequestResult(
        type: type,
        granted: AXIsProcessTrusted(),
        pendingMessage: "User needs to toggle Accessibility for Omi in System Settings.",
        requiresRestart: false
      )

    case "automation":
      guard
        let status = await triggerAutomationPermissionDirectly(
          expectedOwnerID: expectedOwnerID,
          authorizationSnapshot: authorizationSnapshot),
        isPermissionAuthorizationCurrent(
          expectedOwnerID,
          authorizationSnapshot: authorizationSnapshot)
      else { return authorizedOwnerChangedResult() }
      let granted = status == noErr
      appState?.hasAutomationPermission = granted
      appState?.automationPermissionError = automationPermissionError(for: status)
      if !granted {
        _ = openAutomationPrivacySettings(
          expectedOwnerID: expectedOwnerID,
          authorizationSnapshot: authorizationSnapshot)
      }
      return permissionRequestResult(
        type: type,
        granted: granted,
        pendingMessage: "User needs to toggle Automation for Omi in System Settings.",
        requiresRestart: false
      )

    case "full_disk_access":
      guard
        isPermissionAuthorizationCurrent(
          expectedOwnerID,
          authorizationSnapshot: authorizationSnapshot)
      else { return authorizedOwnerChangedResult() }
      _ = openPermissionPrivacySettings(
        pane: "Privacy_AllFiles",
        expectedOwnerID: expectedOwnerID,
        authorizationSnapshot: authorizationSnapshot)
      // Same drag-to-grant mechanic as Screen Recording: drop the app into the
      // Full Disk Access list to add and enable it in one gesture.
      Task { await PermissionDragGuidance.presentDragToGrantHelper() }
      try? await Task.sleep(nanoseconds: 3_000_000_000)
      guard
        isPermissionAuthorizationCurrent(
          expectedOwnerID,
          authorizationSnapshot: authorizationSnapshot)
      else { return authorizedOwnerChangedResult() }
      let granted = checkFullDiskAccessDirectly()
      appState?.hasFullDiskAccess = granted
      return permissionRequestResult(
        type: type,
        granted: granted,
        pendingMessage:
          "User needs to toggle Full Disk Access for Omi in System Settings > Privacy & Security > Full Disk Access, then quit and reopen the app. This restart also applies the Screen Recording grant.",
        requiresRestart: true
      )

    default:
      return permissionJSON([
        "ok": false,
        "status": "error",
        "error": "unknown_permission_type",
        "permission": type,
        "valid_types": onboardingPermissionTypes,
      ])
    }
  }

  /// Check status of all macOS permissions
  private static func executeCheckPermissionStatus(
    _ args: [String: Any],
    expectedOwnerID: String?,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?
  ) async -> String {
    guard
      isPermissionAuthorizationCurrent(
        expectedOwnerID,
        authorizationSnapshot: authorizationSnapshot)
    else { return authorizedOwnerChangedResult() }
    let appState = onboardingAppState ?? AppState.current
    guard
      let statuses = await currentPermissionStatuses(
        appState: appState,
        expectedOwnerID: expectedOwnerID,
        authorizationSnapshot: authorizationSnapshot)
    else { return authorizedOwnerChangedResult() }
    guard
      isPermissionAuthorizationCurrent(
        expectedOwnerID,
        authorizationSnapshot: authorizationSnapshot)
    else { return authorizedOwnerChangedResult() }
    if let type = permissionType(from: args), onboardingPermissionTypes.contains(type) {
      return permissionJSON([
        "ok": true,
        "permission": type,
        "status": statuses[type] ?? "unknown",
      ])
    }

    return permissionJSON(["ok": true, "permissions": statuses])
  }

  private static func permissionType(from args: [String: Any]) -> String? {
    let raw = (args["type"] ?? args["permission"]) as? String
    return raw?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
  }

  private static func permissionJSON(_ payload: [String: Any]) -> String {
    guard
      let data = try? JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted, .sortedKeys]),
      let json = String(data: data, encoding: .utf8)
    else {
      return "\(payload)"
    }
    return json
  }

  private static func permissionRequestResult(
    type: String,
    granted: Bool,
    pendingMessage: String,
    requiresRestart: Bool
  ) -> String {
    permissionJSON([
      "ok": granted,
      "permission": type,
      "status": granted ? "granted" : "pending",
      "message": granted ? "\(type) permission granted." : pendingMessage,
      "requires_restart": requiresRestart && !granted,
    ])
  }

  private static func permissionToolResultGranted(_ result: String) -> Bool {
    guard
      let data = result.data(using: .utf8),
      let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
      let status = json["status"] as? String
    else {
      return result.trimmingCharacters(in: .whitespacesAndNewlines) == "granted"
    }
    return status == "granted"
  }

  private static func currentPermissionStatuses(
    appState: AppState?,
    expectedOwnerID: String?,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?
  ) async -> [String: String]? {
    guard let notificationsGranted = await notificationPermissionGranted(),
      isPermissionAuthorizationCurrent(
        expectedOwnerID,
        authorizationSnapshot: authorizationSnapshot)
    else { return nil }

    let screenRecordingGranted = ScreenCaptureService.checkPermission()
    let microphoneGranted = AudioCaptureService.checkPermission()
    let accessibilityGranted = AXIsProcessTrusted()
    let automationStatus = AppState.queryAutomationPermissionStatus()
    let fullDiskAccessGranted = checkFullDiskAccessDirectly()
    guard
      isPermissionAuthorizationCurrent(
        expectedOwnerID,
        authorizationSnapshot: authorizationSnapshot)
    else { return nil }

    appState?.hasScreenRecordingPermission = ScreenRecordingPermissionPolicy.uiPermissionGranted(
      tccGranted: screenRecordingGranted)
    appState?.hasMicrophonePermission = microphoneGranted
    appState?.hasNotificationPermission = notificationsGranted
    appState?.hasAccessibilityPermission = accessibilityGranted
    appState?.hasAutomationPermission = automationStatus == noErr
    appState?.automationPermissionError = automationPermissionError(for: automationStatus)
    appState?.hasFullDiskAccess = fullDiskAccessGranted

    return onboardingPermissionStatusPayload(
      screenRecording: screenRecordingGranted,
      microphone: microphoneGranted,
      notifications: notificationsGranted,
      accessibility: accessibilityGranted,
      automation: automationStatus == noErr,
      fullDiskAccess: fullDiskAccessGranted
    )
  }

  private static func requestMicrophonePermissionDirectly() async -> Bool? {
    await awaitCancellablePermissionRequest { completion in
      AVCaptureDevice.requestAccess(for: .audio) { granted in
        completion(granted)
      }
    }
  }

  private static func notificationPermissionGranted() async -> Bool? {
    await awaitCancellablePermissionRequest { completion in
      UserNotificationCallbackBridge.authorizationStatus { authorizationStatus in
        completion(authorizationStatus == .authorized)
      }
    }
  }

  private static func requestNotificationPermissionDirectly() async -> Bool? {
    await awaitCancellablePermissionRequest { completion in
      UserNotificationCallbackBridge.requestAuthorization { result in
        completion(result.granted)
      }
    }
  }

  private static func requestAccessibilityPermissionDirectly(
    expectedOwnerID: String?,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?
  ) {
    guard
      isPermissionAuthorizationCurrent(
        expectedOwnerID,
        authorizationSnapshot: authorizationSnapshot)
    else { return }
    let options = [kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true] as CFDictionary
    let granted = AXIsProcessTrustedWithOptions(options)
    if !granted {
      _ = openPermissionPrivacySettings(
        pane: "Privacy_Accessibility",
        expectedOwnerID: expectedOwnerID,
        authorizationSnapshot: authorizationSnapshot)
    }
  }

  private static func triggerAutomationPermissionDirectly(
    expectedOwnerID: String?,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?
  ) async -> OSStatus? {
    await awaitCancellablePermissionRequest { completion in
      // The synchronous AppleScript call is the OS permission request and may
      // outlive cancellation while the TCC prompt is visible. Keep that narrow
      // request outside the tracked parent, but fence every step and route its
      // completion through the once-resume cancellation adapter above.
      Task { @MainActor in
        guard
          isPermissionAuthorizationCurrent(
            expectedOwnerID,
            authorizationSnapshot: authorizationSnapshot)
        else {
          completion(OSStatus(errAEEventNotPermitted))
          return
        }
        let launchScript = NSAppleScript(source: "launch application \"System Events\"")
        var launchError: NSDictionary?
        launchScript?.executeAndReturnError(&launchError)
        try? await Task.sleep(nanoseconds: 500_000_000)
        guard
          isPermissionAuthorizationCurrent(
            expectedOwnerID,
            authorizationSnapshot: authorizationSnapshot)
        else {
          completion(OSStatus(errAEEventNotPermitted))
          return
        }
        let script = NSAppleScript(
          source: """
            tell application "System Events"
              return name of first process whose frontmost is true
            end tell
            """)
        var error: NSDictionary?
        script?.executeAndReturnError(&error)
        guard
          isPermissionAuthorizationCurrent(
            expectedOwnerID,
            authorizationSnapshot: authorizationSnapshot)
        else {
          completion(OSStatus(errAEEventNotPermitted))
          return
        }
        completion(AppState.queryAutomationPermissionStatus())
      }
    }
  }

  private nonisolated static func automationPermissionError(for status: OSStatus) -> OSStatus {
    (status == noErr || status == -1743 || status == -1744) ? 0 : status
  }

  @MainActor
  private static func openPermissionPrivacySettings(
    pane: String,
    expectedOwnerID: String?,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?,
    open: (URL) -> Bool = { NSWorkspace.shared.open($0) }
  ) -> Bool {
    guard
      isPermissionAuthorizationCurrent(
        expectedOwnerID,
        authorizationSnapshot: authorizationSnapshot),
      let url = URL(
        string: "x-apple.systempreferences:com.apple.preference.security?\(pane)")
    else { return false }
    return open(url)
  }

  @MainActor
  private static func openNotificationPrivacySettings(
    expectedOwnerID: String?,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?,
    open: (URL) -> Bool = { NSWorkspace.shared.open($0) }
  ) -> Bool {
    guard
      isPermissionAuthorizationCurrent(
        expectedOwnerID,
        authorizationSnapshot: authorizationSnapshot)
    else { return false }
    let bundleID = Bundle.main.bundleIdentifier ?? "com.omi.computer-macos"
    guard
      let url = URL(
        string: "x-apple.systempreferences:com.apple.preference.notifications?id=\(bundleID)")
    else { return false }
    return open(url)
  }

  @MainActor
  static func openAutomationPrivacySettings(
    expectedOwnerID: String?,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil,
    ownerIsCurrent: ((String?) -> Bool)? = nil,
    open: (URL) -> Bool = { NSWorkspace.shared.open($0) }
  ) -> Bool {
    let validateOwner =
      ownerIsCurrent ?? {
        isPermissionAuthorizationCurrent($0, authorizationSnapshot: authorizationSnapshot)
      }
    guard validateOwner(expectedOwnerID) else { return false }
    guard
      let url = URL(
        string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation")
    else { return false }
    return open(url)
  }

  @MainActor
  static func publishPermissionPendingIfCurrent(
    _ permissionType: String,
    expectedOwnerID: String?,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?,
    callback: ((String) -> Void)?
  ) {
    guard
      isPermissionAuthorizationCurrent(
        expectedOwnerID,
        authorizationSnapshot: authorizationSnapshot)
    else { return }
    callback?(permissionType)
  }

  private static func checkFullDiskAccessDirectly() -> Bool {
    let home = FileManager.default.homeDirectoryForCurrentUser.path
    let protectedPaths = [
      "\(home)/Library/Safari",
      "\(home)/Library/Mail",
      "\(home)/Library/Messages",
    ]
    for path in protectedPaths {
      if FileManager.default.fileExists(atPath: path) {
        return (try? FileManager.default.contentsOfDirectory(atPath: path)) != nil
      }
    }
    return false
  }

  /// Scan files BLOCKING — triggers folder access dialogs, waits for scan, returns results
  private static func executeScanFiles(
    _: [String: Any],
    expectedOwnerID: String?
  ) async -> String {
    guard isExpectedOwnerCurrent(expectedOwnerID) else { return authorizedOwnerChangedResult() }
    let outcome = await scanLocalFiles(expectedOwnerID: expectedOwnerID)
    guard isExpectedOwnerCurrent(expectedOwnerID) else { return authorizedOwnerChangedResult() }
    fileScanFileCount = outcome.indexedFileCount
    onScanFilesCompleted?(outcome.indexedFileCount)
    return outcome.summaryText
  }

  static func scanLocalFiles(expectedOwnerID: String? = nil) async -> LocalFileScanOutcome {
    func ownerChangedOutcome() -> LocalFileScanOutcome {
      LocalFileScanOutcome(
        hasReadableUserFileTarget: false,
        didCompleteSuccessfully: false,
        indexedFileCount: 0,
        deniedUserFolders: [],
        summaryText: authorizedOwnerChangedResult())
    }
    guard isExpectedOwnerCurrent(expectedOwnerID) else { return ownerChangedOutcome() }
    let fm = FileManager.default
    let homeDir = fm.homeDirectoryForCurrentUser
    let scanTargets: [(label: String, pathForUser: String, url: URL, countsAsUserFileAccess: Bool)] = {
      var targets: [(String, String, URL, Bool)] = []

      let homeFolders = ["Downloads", "Documents", "Desktop", "Developer", "Projects"]
      for folder in homeFolders {
        let url = homeDir.appendingPathComponent(folder)
        if fm.fileExists(atPath: url.path) {
          targets.append((folder, "~/\(folder)", url, true))
        }
      }

      let applicationsURL = URL(fileURLWithPath: "/Applications")
      if fm.fileExists(atPath: applicationsURL.path) {
        targets.append(("Applications", "/Applications", applicationsURL, false))
      }

      // Apple Notes local stores (container + group container)
      let notesCandidates: [(String, String, URL, Bool)] = [
        (
          "Apple Notes (Container)",
          "~/Library/Containers/com.apple.Notes/Data/Library/Notes",
          homeDir.appendingPathComponent("Library/Containers/com.apple.Notes/Data/Library/Notes"),
          false
        ),
        (
          "Apple Notes (Group)",
          "~/Library/Group Containers/group.com.apple.notes",
          homeDir.appendingPathComponent("Library/Group Containers/group.com.apple.notes"),
          false
        ),
      ]
      for candidate in notesCandidates where fm.fileExists(atPath: candidate.2.path) {
        targets.append(candidate)
      }

      return targets
    }()

    // Pre-check folder access — this triggers macOS TCC dialogs
    var deniedFolders: [String] = []
    var deniedUserFolders: [String] = []
    var accessibleFolders: [URL] = []
    var readableUserFileTargetCount = 0
    for target in scanTargets {
      guard isExpectedOwnerCurrent(expectedOwnerID) else { return ownerChangedOutcome() }
      do {
        _ = try fm.contentsOfDirectory(
          at: target.url,
          includingPropertiesForKeys: [.fileSizeKey],
          options: [.skipsHiddenFiles]
        )
        accessibleFolders.append(target.url)
        if target.countsAsUserFileAccess {
          readableUserFileTargetCount += 1
        }
      } catch {
        let nsError = error as NSError
        if nsError.domain == NSCocoaErrorDomain && nsError.code == 257 {
          // Permission denied — TCC dialog was shown or already denied
          deniedFolders.append(target.pathForUser)
          if target.countsAsUserFileAccess {
            deniedUserFolders.append(target.pathForUser)
          }
        } else {
          // Other error (e.g. folder doesn't exist) — skip silently
          log("FileIndexer: Pre-check failed for \(target.label): \(error.localizedDescription)")
        }
      }
    }

    // Actually scan accessible folders (blocking)
    guard isExpectedOwnerCurrent(expectedOwnerID) else { return ownerChangedOutcome() }
    let count = await FileIndexerService.shared.scanFolders(accessibleFolders)
    guard isExpectedOwnerCurrent(expectedOwnerID) else { return ownerChangedOutcome() }
    log(
      "Onboarding file scan completed: \(count) files indexed, \(deniedFolders.count) folders denied"
    )

    // Build results from database
    var didCompleteSuccessfully = true
    var out: String
    do {
      out = try await getFileScanResultsFromDB(expectedOwnerID: expectedOwnerID)
      guard isExpectedOwnerCurrent(expectedOwnerID) else { return ownerChangedOutcome() }
    } catch {
      didCompleteSuccessfully = false
      out = "Error: \(error.localizedDescription)"
    }

    if !deniedFolders.isEmpty {
      out += "\n\n## FOLDER ACCESS DENIED\n"
      out += "The following folders were NOT scanned because the user didn't grant access:\n"
      for folder in deniedFolders {
        out += "- \(folder)\n"
      }
      out +=
        "\nTell the user to click 'Allow' on the macOS dialogs, then call scan_files again to pick up those folders."
    }

    return LocalFileScanOutcome(
      hasReadableUserFileTarget: readableUserFileTargetCount > 0,
      didCompleteSuccessfully: didCompleteSuccessfully,
      indexedFileCount: count,
      deniedUserFolders: deniedUserFolders,
      summaryText: out)
  }

  private enum FileScanResultsError: LocalizedError {
    case databaseNotAvailable

    var errorDescription: String? { "database not available" }
  }

  /// Get file scan results from the database
  private static func getFileScanResultsFromDB(expectedOwnerID: String?) async throws -> String {
    guard isExpectedOwnerCurrent(expectedOwnerID) else { return authorizedOwnerChangedResult() }
    guard let dbQueue = await RewindDatabase.shared.getDatabaseQueue() else {
      throw FileScanResultsError.databaseNotAvailable
    }
    guard isExpectedOwnerCurrent(expectedOwnerID) else { return authorizedOwnerChangedResult() }

    do {
      let result = try await dbQueue.read { db in
        // File type breakdown
        let typeBreakdown = try Row.fetchAll(
          db,
          sql: """
                SELECT fileType, COUNT(*) as count
                FROM indexed_files
                GROUP BY fileType
                ORDER BY count DESC
                LIMIT 10
            """)

        // Project indicators
        let projectIndicators = try Row.fetchAll(
          db,
          sql: """
                SELECT filename, path FROM indexed_files
                WHERE filename IN ('package.json', 'Cargo.toml', 'Podfile', 'go.mod',
                    'requirements.txt', 'Pipfile', 'setup.py', 'pyproject.toml',
                    'build.gradle', 'pom.xml', 'CMakeLists.txt', 'Makefile',
                    '.xcodeproj', '.xcworkspace', 'Package.swift', 'Gemfile',
                    'composer.json', 'mix.exs', 'pubspec.yaml')
                LIMIT 30
            """)

        // Recently modified files
        let recentFiles = try Row.fetchAll(
          db,
          sql: """
                SELECT filename, path, fileType, modifiedAt FROM indexed_files
                ORDER BY modifiedAt DESC
                LIMIT 15
            """)

        // Applications
        let apps = try Row.fetchAll(
          db,
          sql: """
                SELECT filename, path FROM indexed_files
                WHERE folder = '/Applications' AND fileExtension = 'app'
                ORDER BY filename
                LIMIT 30
            """)

        let totalCount = try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM indexed_files") ?? 0

        var out = "# File Scan Results (\(totalCount) files indexed)\n\n"

        out += "## File Types\n"
        for row in typeBreakdown {
          let type = row["fileType"] as? String ?? "unknown"
          let count = Self.rowInt(row["count"]) ?? 0
          out += "- \(type): \(count) files\n"
        }

        out += "\n## Project Indicators (build files found)\n"
        if projectIndicators.isEmpty {
          out += "- No project build files found\n"
        } else {
          for row in projectIndicators {
            let filename = row["filename"] as? String ?? ""
            let path = row["path"] as? String ?? ""
            // Extract project directory name
            let dir = (path as NSString).deletingLastPathComponent
            let projectName = (dir as NSString).lastPathComponent
            out += "- \(projectName)/\(filename)\n"
          }
        }

        out += "\n## Recently Modified Files\n"
        for row in recentFiles {
          let filename = row["filename"] as? String ?? ""
          let fileType = row["fileType"] as? String ?? ""
          let modifiedAt = row["modifiedAt"] as? String ?? ""
          out += "- \(filename) (\(fileType)) — modified \(modifiedAt)\n"
        }

        if !apps.isEmpty {
          out += "\n## Installed Applications\n"
          let appNames = apps.compactMap {
            ($0["filename"] as? String)?.replacingOccurrences(of: ".app", with: "")
          }
          out += appNames.joined(separator: ", ")
          out += "\n"
        }

        let taskCandidates = try Row.fetchAll(
          db,
          sql: """
                SELECT description, priority, source
                FROM action_items
                WHERE deleted = 0 AND completed = 0
                ORDER BY
                    CASE priority
                        WHEN 'high' THEN 0
                        WHEN 'medium' THEN 1
                        ELSE 2
                    END,
                    COALESCE(relevanceScore, 999) ASC,
                    createdAt DESC
                LIMIT 8
            """)

        if !taskCandidates.isEmpty {
          out += "\n## Existing Task Candidates\n"
          for row in taskCandidates {
            let description = row["description"] as? String ?? ""
            let priority = row["priority"] as? String ?? "normal"
            let source = row["source"] as? String ?? "unknown"
            out += "- [\(priority)] \(description) (source: \(source))\n"
          }
        }

        log(
          "Tool get_file_scan_results: \(totalCount) files, \(projectIndicators.count) projects, \(apps.count) apps"
        )
        return out
      }
      guard isExpectedOwnerCurrent(expectedOwnerID) else { return authorizedOwnerChangedResult() }
      return result
    } catch {
      logError("Tool get_file_scan_results failed", error: error)
      throw error
    }
  }

  /// Return email/calendar insights from background reading
  private static func executeGetEmailInsights() -> String {
    var sections: [String] = []

    if let email = emailInsightsText, !email.isEmpty {
      sections.append("## Email Insights\n\(email)")
    }
    if let calendar = calendarInsightsText, !calendar.isEmpty {
      sections.append("## Calendar Insights\n\(calendar)")
    }

    if sections.isEmpty {
      return
        "No email insights available yet. The background reading may still be in progress, or no browser with a Gmail session was found."
    }

    return sections.joined(separator: "\n\n")
  }

  /// Set user preferences (language, name)
  private static func executeSetUserPreferences(
    _ args: [String: Any],
    expectedOwnerID: String?,
    api: APIClient
  ) async -> String {
    var results: [String] = []

    if let language = args["language"] as? String, !language.isEmpty {
      let normalizedLanguage = AssistantSettings.normalizeTranscriptionLanguageCode(language)
      if let expectedOwnerID {
        _ = try? await api.updateUserLanguage(
          normalizedLanguage,
          expectedOwnerId: expectedOwnerID,
          authorizationSnapshot: currentOwnerAuthorizationSnapshot)
        guard isExpectedOwnerCurrent(expectedOwnerID) else {
          return authorizedOwnerChangedResult()
        }
      }
      AssistantSettings.shared.transcriptionLanguage = normalizedLanguage
      let supportsMulti = AssistantSettings.supportsAutoDetect(normalizedLanguage)
      AssistantSettings.shared.transcriptionAutoDetect = supportsMulti
      results.append("Language set to \(normalizedLanguage)")
    }

    if let name = args["name"] as? String, !name.isEmpty {
      guard isExpectedOwnerCurrent(expectedOwnerID) else {
        return authorizedOwnerChangedResult()
      }
      await AuthService.shared.updateGivenName(
        name,
        expectedOwnerID: expectedOwnerID,
        authorizationSnapshot: currentOwnerAuthorizationSnapshot)
      guard isExpectedOwnerCurrent(expectedOwnerID) else {
        return authorizedOwnerChangedResult()
      }
      results.append("Name updated to \(name)")
    }

    if results.isEmpty {
      return
        "No preferences were changed. Provide 'language' (code like 'en', 'es', 'ja') and/or 'name' (string)."
    }
    return results.joined(separator: ". ") + "."
  }

  // MARK: - Knowledge Graph Tool

  /// Save a knowledge graph extracted by the AI during file exploration
  private static func executeSaveKnowledgeGraph(
    _ args: [String: Any],
    expectedOwnerID: String?
  ) async -> String {
    guard isExpectedOwnerCurrent(expectedOwnerID) else { return authorizedOwnerChangedResult() }
    guard let nodesArray = args["nodes"] as? [[String: Any]] else {
      return "Error: 'nodes' array is required"
    }
    let edgesArray = args["edges"] as? [[String: Any]] ?? []

    let now = Date()
    var nodeRecords: [LocalKGNodeRecord] = []
    var edgeRecords: [LocalKGEdgeRecord] = []

    // Deduplicate nodes by label (case-insensitive)
    var seenLabels: [String: String] = [:]  // lowercase label → nodeId
    var idRemap: [String: String] = [:]  // original id → canonical id

    for node in nodesArray {
      guard let id = node["id"] as? String,
        let label = node["label"] as? String
      else { continue }

      let nodeType = node["node_type"] as? String ?? "concept"
      let aliases = node["aliases"] as? [String] ?? []
      let lowerLabel = label.lowercased()

      if let existingId = seenLabels[lowerLabel] {
        idRemap[id] = existingId
        continue
      }

      seenLabels[lowerLabel] = id
      idRemap[id] = id

      var aliasesJson: String?
      if !aliases.isEmpty, let data = try? JSONEncoder().encode(aliases) {
        aliasesJson = String(data: data, encoding: .utf8)
      }

      nodeRecords.append(
        LocalKGNodeRecord(
          nodeId: id,
          label: label,
          nodeType: nodeType,
          aliasesJson: aliasesJson,
          sourceFileIds: nil,
          createdAt: now,
          updatedAt: now
        ))
    }

    for edge in edgesArray {
      guard let sourceId = edge["source_id"] as? String,
        let targetId = edge["target_id"] as? String,
        let label = edge["label"] as? String
      else { continue }

      let remappedSource = idRemap[sourceId] ?? sourceId
      let remappedTarget = idRemap[targetId] ?? targetId

      // Skip self-referencing edges
      guard remappedSource != remappedTarget else { continue }

      let edgeId =
        "\(remappedSource)_\(remappedTarget)_\(label.lowercased().replacingOccurrences(of: " ", with: "_"))"
      edgeRecords.append(
        LocalKGEdgeRecord(
          edgeId: edgeId,
          sourceNodeId: remappedSource,
          targetNodeId: remappedTarget,
          label: label,
          createdAt: now
        ))
    }

    do {
      guard isExpectedOwnerCurrent(expectedOwnerID) else {
        return authorizedOwnerChangedResult()
      }
      try await KnowledgeGraphStorage.shared.mergeGraph(
        nodes: nodeRecords,
        edges: edgeRecords,
        authorization: LocalMutationAuthorization {
          isExpectedOwnerCurrent(expectedOwnerID)
        })
      guard isExpectedOwnerCurrent(expectedOwnerID) else {
        return authorizedOwnerChangedResult()
      }
      log("Local graph built with \(nodeRecords.count) nodes, \(edgeRecords.count) edges")
      onKnowledgeGraphUpdated?()
      return
        "OK: saved \(nodeRecords.count) nodes and \(edgeRecords.count) edges to local knowledge graph"
    } catch LocalMutationAuthorizationError.revoked {
      return authorizedOwnerChangedResult()
    } catch {
      logError("Tool save_knowledge_graph failed", error: error)
      return "Error: \(error.localizedDescription)"
    }
  }

  /// Present a follow-up question with quick-reply options to the user
  private static func executeAskFollowup(
    _ args: [String: Any],
    expectedOwnerID: String?
  ) async -> String {
    guard isExpectedOwnerCurrent(expectedOwnerID) else { return authorizedOwnerChangedResult() }
    guard let question = args["question"] as? String else {
      return "Error: 'question' parameter is required"
    }
    let options = (args["options"] as? [String]) ?? []

    // Notify the UI to render quick-reply buttons
    onQuickReplyOptions?(options)
    onQuickReplyQuestion?(question)

    return "Presented to user: \"\(question)\" with options: \(options.joined(separator: ", "))"
  }

  /// Complete the onboarding process
  private static func executeCompleteOnboarding(
    _ args: [String: Any],
    expectedOwnerID: String?
  ) async -> String {
    guard isExpectedOwnerCurrent(expectedOwnerID) else { return authorizedOwnerChangedResult() }
    guard let appState = onboardingAppState else {
      return "Error: onboarding not active"
    }

    // Log analytics for each permission
    let permissions: [(String, Bool)] = [
      ("screen_recording", appState.hasScreenRecordingPermission),
      ("microphone", appState.hasMicrophonePermission),
      ("accessibility", appState.hasAccessibilityPermission),
      ("automation", appState.hasAutomationPermission),
    ]
    for (name, granted) in permissions {
      if granted {
        AnalyticsManager.shared.permissionGranted(permission: name)
      } else {
        AnalyticsManager.shared.permissionSkipped(permission: name)
      }
    }

    // Mark that the tool was called so the "Continue to App" button shows even after restart
    OnboardingChatPersistence.markToolCompleted()

    // Call the completion callback
    onCompleteOnboarding?()

    // Clean up state
    onboardingAppState = nil
    onCompleteOnboarding = nil
    onQuickReplyOptions = nil
    onQuickReplyQuestion = nil
    onKnowledgeGraphUpdated = nil
    onScanFilesCompleted = nil
    onPermissionPending = nil
    fileScanFileCount = 0

    return "Onboarding completed successfully! The app is now set up."
  }

  // MARK: - Date Validation

  /// Validates an ISO 8601 date string has a timezone offset by parsing it.
  /// Catches format errors (missing timezone, garbage input). Calendar validity
  /// (e.g. Feb 30 -> Mar 1 normalization) is left to the backend's datetime parser.
  static func validateISODate(_ dateStr: String, paramName: String) -> (valid: String?, error: String?) {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    if formatter.date(from: dateStr) != nil {
      return (dateStr, nil)
    }
    formatter.formatOptions = [.withInternetDateTime]
    if formatter.date(from: dateStr) != nil {
      return (dateStr, nil)
    }
    return (
      nil,
      "Error: \(paramName) must be ISO format with timezone offset (e.g. 2024-01-19T15:00:00-08:00 or 2024-01-19T15:00:00+07:00). Got: \(dateStr)"
    )
  }

  // MARK: - Backend RAG Tools

  private static func executeBackendTool(
    _ toolCall: ToolCall,
    expectedOwnerID: String?,
    api: APIClient
  ) async -> String {
    do {
      let args = toolCall.arguments

      // Validate date parameters before sending to backend
      var validatedStartDate: String? = nil
      var validatedEndDate: String? = nil
      if let sd = args["start_date"] as? String {
        let result = validateISODate(sd, paramName: "start_date")
        if let error = result.error { return error }
        validatedStartDate = result.valid
      }
      if let ed = args["end_date"] as? String {
        let result = validateISODate(ed, paramName: "end_date")
        if let error = result.error { return error }
        validatedEndDate = result.valid
      }

      switch toolCall.name {
      case "get_conversations":
        let resp = try await api.toolGetConversations(
          startDate: validatedStartDate,
          endDate: validatedEndDate,
          limit: args["limit"] as? Int ?? 20,
          offset: args["offset"] as? Int ?? 0,
          includeTranscript: args["include_transcript"] as? Bool ?? true,
          expectedOwnerId: expectedOwnerID,
          authorizationSnapshot: currentOwnerAuthorizationSnapshot
        )
        return resp.resultText

      case "search_conversations":
        guard let query = args["query"] as? String, !query.isEmpty else {
          return "Error: query is required"
        }
        let resp = try await api.toolSearchConversations(
          query: query,
          startDate: validatedStartDate,
          endDate: validatedEndDate,
          limit: args["limit"] as? Int ?? 5,
          includeTranscript: args["include_transcript"] as? Bool ?? true,
          expectedOwnerId: expectedOwnerID,
          authorizationSnapshot: currentOwnerAuthorizationSnapshot
        )
        return resp.resultText

      case "get_memories":
        let resp = try await api.toolGetMemories(
          limit: args["limit"] as? Int ?? 50,
          offset: args["offset"] as? Int ?? 0,
          startDate: validatedStartDate,
          endDate: validatedEndDate,
          expectedOwnerId: expectedOwnerID,
          authorizationSnapshot: currentOwnerAuthorizationSnapshot
        )
        return resp.resultText

      case "search_memories":
        guard let query = args["query"] as? String, !query.isEmpty else {
          return "Error: query is required"
        }
        let resp = try await api.toolSearchMemories(
          query: query,
          limit: args["limit"] as? Int ?? 5,
          expectedOwnerId: expectedOwnerID,
          authorizationSnapshot: currentOwnerAuthorizationSnapshot
        )
        return resp.resultText

      case "get_action_items":
        var validatedDueStart: String? = nil
        var validatedDueEnd: String? = nil
        if let ds = args["due_start_date"] as? String {
          let result = validateISODate(ds, paramName: "due_start_date")
          if let error = result.error { return error }
          validatedDueStart = result.valid
        }
        if let de = args["due_end_date"] as? String {
          let result = validateISODate(de, paramName: "due_end_date")
          if let error = result.error { return error }
          validatedDueEnd = result.valid
        }
        let resp = try await api.toolGetActionItems(
          limit: args["limit"] as? Int ?? 50,
          offset: args["offset"] as? Int ?? 0,
          completed: args["completed"] as? Bool,
          startDate: validatedStartDate,
          endDate: validatedEndDate,
          dueStartDate: validatedDueStart,
          dueEndDate: validatedDueEnd,
          expectedOwnerId: expectedOwnerID,
          authorizationSnapshot: currentOwnerAuthorizationSnapshot
        )
        return resp.resultText

      case "create_action_item":
        guard let desc = args["description"] as? String, !desc.isEmpty else {
          return "Error: description is required"
        }
        var validatedDueAt: String? = nil
        if let da = args["due_at"] as? String {
          let result = validateISODate(da, paramName: "due_at")
          if let error = result.error { return error }
          validatedDueAt = result.valid
        }
        let resp = try await api.toolCreateActionItem(
          description: desc,
          dueAt: validatedDueAt,
          conversationId: args["conversation_id"] as? String,
          expectedOwnerId: expectedOwnerID,
          authorizationSnapshot: currentOwnerAuthorizationSnapshot
        )
        return resp.resultText

      case "update_action_item":
        guard let itemId = args["action_item_id"] as? String, !itemId.isEmpty else {
          return "Error: action_item_id is required"
        }
        var validatedUpdateDueAt: String? = nil
        if let da = args["due_at"] as? String {
          let result = validateISODate(da, paramName: "due_at")
          if let error = result.error { return error }
          validatedUpdateDueAt = result.valid
        }
        let resp = try await api.toolUpdateActionItem(
          id: itemId,
          completed: args["completed"] as? Bool,
          description: args["description"] as? String,
          dueAt: validatedUpdateDueAt,
          expectedOwnerId: expectedOwnerID,
          authorizationSnapshot: currentOwnerAuthorizationSnapshot
        )
        return resp.resultText

      case "create_calendar_event":
        guard let rawTitle = args["title"] as? String else {
          return "Error: title is required"
        }
        let title = rawTitle.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !title.isEmpty else {
          return "Error: title is required"
        }
        guard let startTime = args["start_time"] as? String, !startTime.isEmpty else {
          return "Error: start_time is required"
        }
        guard let endTime = args["end_time"] as? String, !endTime.isEmpty else {
          return "Error: end_time is required"
        }
        let validatedStart = validateISODate(startTime, paramName: "start_time")
        if let error = validatedStart.error { return error }
        let validatedEnd = validateISODate(endTime, paramName: "end_time")
        if let error = validatedEnd.error { return error }
        let resp = try await api.toolCreateCalendarEvent(
          title: title,
          startTime: validatedStart.valid ?? startTime,
          endTime: validatedEnd.valid ?? endTime,
          description: args["description"] as? String,
          location: args["location"] as? String,
          attendees: args["attendees"] as? String,
          expectedOwnerId: expectedOwnerID,
          authorizationSnapshot: currentOwnerAuthorizationSnapshot
        )
        return resp.resultText

      default:
        return "Unknown backend tool: \(toolCall.name)"
      }
    } catch {
      log("Backend tool error (\(toolCall.name)): \(error)")
      return "Error calling backend: \(error.localizedDescription)"
    }
  }
}
