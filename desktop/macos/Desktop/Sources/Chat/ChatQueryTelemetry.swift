import Foundation

enum ChatQueryErrorClass: String, Equatable, Sendable {
  case agentError = "agent_error"
  case agentRuntime = "agent_runtime"
  case attachmentUpload = "attachment_upload"
  case authentication
  case bridgeUnavailable = "bridge_unavailable"
  case browserExtensionMissing = "browser_extension_missing"
  case concurrentRequest = "concurrent_request"
  case encoding
  case quota
  case resourceExhausted = "resource_exhausted"
  case sessionSetup = "session_setup"
  case timeout
  case toolStall = "tool_stall"
  case transientNetwork = "transient_network"
  case unknown
}

enum ChatQueryCancellationReason: String, Equatable, Sendable {
  case superseded
  case taskCancelled = "task_cancelled"
  case userStop = "user_stop"
}

enum ChatTurnStopReason: Equatable, Sendable {
  case browserExtensionMissing
  case superseded
  case userStop
}

enum ChatQueryFailureDisposition: Equatable, Sendable {
  case cancelled(ChatQueryCancellationReason)
  case failed(ChatQueryErrorClass)

  var presentsUserError: Bool {
    guard case .failed = self else { return false }
    return true
  }

  static func classify(
    _ error: Error,
    watchdogFired: Bool = false,
    toolStallAbortFired: Bool = false
  ) -> ChatQueryFailureDisposition {
    if let bridgeError = error as? BridgeError {
      switch bridgeError {
      case .stopped:
        if toolStallAbortFired { return .failed(.toolStall) }
        if watchdogFired { return .failed(.timeout) }
        return .cancelled(.userStop)
      case .timeout:
        return .failed(.timeout)
      case .authMissing:
        return .failed(.authentication)
      case .agentError where bridgeError.isSessionAuthenticationFailure:
        return .failed(.authentication)
      case .nodeNotFound, .bridgeScriptNotFound, .notRunning, .processExited, .restarting:
        return .failed(.bridgeUnavailable)
      case .outOfMemory:
        return .failed(.resourceExhausted)
      case .encodingError:
        return .failed(.encoding)
      case .requestAlreadyActive:
        return .failed(.concurrentRequest)
      case .quotaExceeded:
        return .failed(.quota)
      case .agentRuntimeFailure:
        return .failed(.agentRuntime)
      case .agentError:
        return .failed(.agentError)
      }
    }

    if error is CancellationError {
      return .cancelled(.taskCancelled)
    }

    let nsError = error as NSError
    if nsError.domain == NSURLErrorDomain || nsError.domain == NSPOSIXErrorDomain {
      return .failed(.transientNetwork)
    }
    return .failed(.unknown)
  }
}

struct ChatQueryTelemetryContext: Equatable, Sendable {
  let attemptId: String
  let surface: String
  let harness: String
  let runtimeSurface: String?
  let inputLengthBucket: String
  let attachmentCount: Int
  let hasImage: Bool

  init(
    attemptId: String,
    surface: String,
    harness: String,
    runtimeSurface: String? = nil,
    inputLengthBucket: String = "unknown",
    attachmentCount: Int = 0,
    hasImage: Bool = false
  ) {
    self.attemptId = attemptId
    self.surface = surface
    self.harness = harness
    self.runtimeSurface = runtimeSurface
    self.inputLengthBucket = inputLengthBucket
    self.attachmentCount = attachmentCount
    self.hasImage = hasImage
  }
}

enum ChatTelemetryDimension {
  private static let allowedToolNames: Set<String> = {
    let generated = GeneratedToolCapabilities.capabilities.map { $0.toolName.lowercased() }
    let runtimeBuiltins = [
      "bash", "browser", "computer", "edit", "glob", "grep", "image", "multiedit",
      "notebookedit", "playwright", "read", "shell", "skill", "task", "todowrite",
      "webfetch", "websearch", "write",
    ]
    return Set(generated + runtimeBuiltins)
  }()

  private static let allowedScreenFailureCodes = Set(ScreenContextFailureCode.allCases.map(\.rawValue))

  /// Convert adapter display labels into a closed, content-free tool dimension.
  /// Examples such as `WebSearch: "private query"`, `Read: /private/path`, and
  /// `mcp__omi-tools__search_memories` become `websearch`, `read`, and
  /// `search_memories`. Unknown tools collapse to `other`.
  static func toolName(_ rawValue: String) -> String {
    let withoutMCPPrefix: String
    if rawValue.hasPrefix("mcp__") {
      withoutMCPPrefix = String(rawValue.split(separator: "__").last ?? Substring(rawValue))
    } else {
      withoutMCPPrefix = rawValue
    }
    let base = withoutMCPPrefix
      .split(separator: ":", maxSplits: 1)
      .first
      .map(String.init)?
      .trimmingCharacters(in: .whitespacesAndNewlines)
      .lowercased() ?? ""
    guard allowedToolNames.contains(base) else { return "other" }
    return base
  }

  static func screenFailureCode(_ rawValue: String) -> String {
    let normalized = rawValue.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    return allowedScreenFailureCodes.contains(normalized)
      ? normalized
      : ScreenContextFailureCode.unknown.rawValue
  }
}

struct ChatQueryCompletionMetrics: Equatable, Sendable {
  let toolCallCount: Int
  let toolNames: [String]
  let costUsd: Double
  let responseLength: Int
  let screenToolRequested: Bool
  let screenToolSucceeded: Bool
  let screenToolApprovalRequired: Bool
  let screenToolFailureCodes: [String]
  let runtimeRunId: String?
  let runtimeAttemptId: String?

  init(
    toolCallCount: Int,
    toolNames: [String],
    costUsd: Double,
    responseLength: Int,
    screenToolRequested: Bool,
    screenToolSucceeded: Bool,
    screenToolApprovalRequired: Bool,
    screenToolFailureCodes: [String],
    runtimeRunId: String? = nil,
    runtimeAttemptId: String? = nil
  ) {
    self.toolCallCount = max(0, toolCallCount)
    self.toolNames = Array(Set(toolNames.map(ChatTelemetryDimension.toolName))).sorted().prefix(20).map { $0 }
    self.costUsd = max(0, costUsd)
    self.responseLength = max(0, responseLength)
    self.screenToolRequested = screenToolRequested
    self.screenToolSucceeded = screenToolSucceeded
    self.screenToolApprovalRequired = screenToolApprovalRequired
    self.screenToolFailureCodes = Array(
      Set(screenToolFailureCodes.map(ChatTelemetryDimension.screenFailureCode))
    ).sorted().prefix(20).map { $0 }
    self.runtimeRunId = runtimeRunId.map { String($0.prefix(128)) }
    self.runtimeAttemptId = runtimeAttemptId.map { String($0.prefix(128)) }
  }
}

enum ChatQueryTelemetryEvent: Equatable, Sendable {
  case started(ChatQueryTelemetryContext)
  case completed(ChatQueryTelemetryContext, durationMs: Int, metrics: ChatQueryCompletionMetrics)
  case failed(
    ChatQueryTelemetryContext,
    durationMs: Int,
    errorClass: ChatQueryErrorClass,
    partialResponse: Bool
  )
  case cancelled(
    ChatQueryTelemetryContext,
    durationMs: Int,
    reason: ChatQueryCancellationReason,
    partialResponse: Bool
  )
}

struct ChatQueryAnalyticsPayload {
  let eventName: String
  let properties: [String: Any]
}

extension ChatQueryTelemetryEvent {
  /// Converts the typed lifecycle event to an allowlisted PostHog schema.
  /// Raw prompts, response text, and exception messages cannot enter this map.
  var analyticsPayload: ChatQueryAnalyticsPayload {
    let context: ChatQueryTelemetryContext
    let eventName: String
    var properties: [String: Any]

    switch self {
    case .started(let eventContext):
      eventName = "chat_agent_query_started"
      context = eventContext
      properties = [:]
    case .completed(let eventContext, let durationMs, let metrics):
      eventName = "chat_agent_query_completed"
      context = eventContext
      properties = [
        "duration_ms": durationMs,
        "tool_call_count": metrics.toolCallCount,
        "tool_names": metrics.toolNames.joined(separator: ","),
        "cost_usd": metrics.costUsd,
        "response_length": metrics.responseLength,
        "screen_tool_requested": metrics.screenToolRequested,
        "screen_tool_succeeded": metrics.screenToolSucceeded,
        "screen_tool_approval_required": metrics.screenToolApprovalRequired,
        "screen_tool_failure_codes": metrics.screenToolFailureCodes.joined(separator: ","),
      ]
      if let runtimeRunId = metrics.runtimeRunId {
        properties["runtime_run_id"] = runtimeRunId
      }
      if let runtimeAttemptId = metrics.runtimeAttemptId {
        properties["runtime_attempt_id"] = runtimeAttemptId
      }
    case .failed(let eventContext, let durationMs, let errorClass, let partialResponse):
      eventName = "chat_agent_error"
      context = eventContext
      properties = [
        "duration_ms": durationMs,
        "error_class": errorClass.rawValue,
        "partial_response": partialResponse,
      ]
    case .cancelled(let eventContext, let durationMs, let reason, let partialResponse):
      eventName = "chat_agent_query_cancelled"
      context = eventContext
      properties = [
        "duration_ms": durationMs,
        "cancel_reason": reason.rawValue,
        "partial_response": partialResponse,
      ]
    }

    properties["attempt_id"] = context.attemptId
    properties["surface"] = context.surface
    properties["harness"] = context.harness
    properties["input_length_bucket"] = context.inputLengthBucket
    properties["attachment_count"] = context.attachmentCount
    properties["has_image"] = context.hasImage
    if let runtimeSurface = context.runtimeSurface {
      properties["runtime_surface"] = runtimeSurface
    }
    properties["telemetry_schema_version"] = 2
    if case .failed(_, _, let errorClass, _) = self {
      // One-release compatibility alias for existing PostHog breakdowns.
      // It is bounded and contains the same value as `error_class`, never the
      // raw exception. Remove after LXEMscAj and Hermes exports migrate to v2.
      properties["error"] = errorClass.rawValue
    }
    return ChatQueryAnalyticsPayload(eventName: eventName, properties: properties)
  }
}

/// Owns the analytics lifecycle for one preflight-cleared chat query.
///
/// The query starts after local concurrency/quota checks and includes bridge,
/// session, and attachment setup so failures in those user-visible stages stay
/// in the denominator. It emits one `started` event and at most one terminal
/// event, even when the watchdog and bridge catch path race. User-initiated Stop
/// is a cancellation, not an error.
@MainActor
final class ChatQueryTelemetryAttempt {
  typealias EventSink = @MainActor (ChatQueryTelemetryEvent) -> Void

  let context: ChatQueryTelemetryContext

  private let elapsedMilliseconds: () -> Int
  private let eventSink: EventSink
  private(set) var isTerminal = false

  init(
    attemptId: String = UUID().uuidString,
    surface: String,
    harness: String,
    runtimeSurface: String? = nil,
    inputLength: Int = 0,
    attachmentCount: Int = 0,
    hasImage: Bool = false,
    elapsedMilliseconds: (() -> Int)? = nil,
    eventSink: EventSink? = nil
  ) {
    self.context = ChatQueryTelemetryContext(
      attemptId: attemptId,
      surface: String(surface.prefix(64)),
      harness: String(harness.prefix(64)),
      runtimeSurface: runtimeSurface.map { String($0.prefix(64)) },
      inputLengthBucket: Self.inputLengthBucket(inputLength),
      attachmentCount: min(max(0, attachmentCount), 20),
      hasImage: hasImage
    )
    if let elapsedMilliseconds {
      self.elapsedMilliseconds = elapsedMilliseconds
    } else {
      let startedAt = ContinuousClock.now
      self.elapsedMilliseconds = {
        let components = (ContinuousClock.now - startedAt).components
        let milliseconds = Int(components.seconds) * 1_000
          + Int(components.attoseconds / 1_000_000_000_000_000)
        return max(0, milliseconds)
      }
    }
    self.eventSink = eventSink ?? { AnalyticsManager.shared.chatQueryTelemetry($0) }
    self.eventSink(.started(context))
  }

  @discardableResult
  func complete(metrics: ChatQueryCompletionMetrics) -> Bool {
    guard beginTerminalEvent() else { return false }
    eventSink(.completed(context, durationMs: durationMs(), metrics: metrics))
    return true
  }

  @discardableResult
  func finish(
    error: Error,
    watchdogFired: Bool = false,
    toolStallAbortFired: Bool = false,
    partialResponse: Bool
  ) -> Bool {
    switch ChatQueryFailureDisposition.classify(
      error,
      watchdogFired: watchdogFired,
      toolStallAbortFired: toolStallAbortFired
    ) {
    case .failed(let errorClass):
      return fail(errorClass: errorClass, partialResponse: partialResponse)
    case .cancelled(let reason):
      return cancel(reason: reason, partialResponse: partialResponse)
    }
  }

  @discardableResult
  func finish(
    stopReason: ChatTurnStopReason,
    partialResponse: Bool = false
  ) -> Bool {
    switch stopReason {
    case .browserExtensionMissing:
      return fail(errorClass: .browserExtensionMissing, partialResponse: partialResponse)
    case .superseded:
      return cancel(reason: .superseded, partialResponse: partialResponse)
    case .userStop:
      return cancel(reason: .userStop, partialResponse: partialResponse)
    }
  }

  @discardableResult
  func fail(errorClass: ChatQueryErrorClass, partialResponse: Bool = false) -> Bool {
    guard beginTerminalEvent() else { return false }
    eventSink(
      .failed(
        context,
        durationMs: durationMs(),
        errorClass: errorClass,
        partialResponse: partialResponse
      )
    )
    return true
  }

  @discardableResult
  func cancel(
    reason: ChatQueryCancellationReason,
    partialResponse: Bool = false
  ) -> Bool {
    guard beginTerminalEvent() else { return false }
    eventSink(
      .cancelled(
        context,
        durationMs: durationMs(),
        reason: reason,
        partialResponse: partialResponse
      )
    )
    return true
  }

  private func beginTerminalEvent() -> Bool {
    guard !isTerminal else { return false }
    isTerminal = true
    return true
  }

  private func durationMs() -> Int {
    max(0, elapsedMilliseconds())
  }

  nonisolated private static func inputLengthBucket(_ length: Int) -> String {
    switch max(0, length) {
    case 0..<100: return "0_99"
    case 100..<500: return "100_499"
    case 500..<2_000: return "500_1999"
    default: return "2000_plus"
    }
  }
}
