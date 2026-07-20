import Darwin
import Foundation
import Sentry

enum DesktopHealthEventName: String {
  case authTokenStorageFallback = "auth_token_storage_fallback"
  case authSessionCleared = "auth_session_cleared"
  case transcriptionWsReconnectExhausted = "transcription_ws_reconnect_exhausted"

  case pttStarted = "ptt_started"
  case pttAudioCaptureSilentTurn = "ptt_audio_capture_silent_turn"
  case pttAudioCaptureWatchdogTriggered = "ptt_audio_capture_watchdog_triggered"
  case pttAudioCaptureDeviceRouteChanged = "ptt_audio_capture_device_route_changed"
  case pttCommitted = "ptt_committed"
  case realtimeTokenMintFailed = "realtime_token_mint_failed"
  case realtimeProviderExpectedIdleTeardown = "realtime_provider_expected_idle_teardown"
  case realtimeProviderExpectedSessionRotation = "realtime_provider_expected_session_rotation"
  case realtimeProviderPolicyClose = "realtime_provider_policy_close"
  case realtimeProviderSessionError = "realtime_provider_session_error"
  case fallbackTriggered = "fallback_triggered"
}

enum DesktopFallbackOutcome: String {
  case recovered
  case degraded
  case exhausted
}

struct DesktopHealthSnapshot: @unchecked Sendable {
  let timestamp: Date
  let event: DesktopHealthEventName
  let properties: [String: Any]

  func dictionary() -> [String: Any] {
    var dict = properties
    dict["timestamp"] = ISO8601DateFormatter.desktopDiagnostics.string(from: timestamp)
    dict["event"] = event.rawValue
    return dict
  }
}

extension ISO8601DateFormatter {
  fileprivate nonisolated(unsafe) static let desktopDiagnostics: ISO8601DateFormatter = {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return formatter
  }()
}

/// Desktop health telemetry matrix (RealtimeHub pattern — copy for new surfaces):
/// - **Local log** (`log`): always, with `failure_class` / `recovery_action` / `recovery_result`.
/// - **Ring buffer** (`record*` → `writeDiagnosticsAttachment`): always via this manager.
/// - **PostHog** (`desktopHealthEvent`): prod/beta when `trackRemotely` is true (default).
/// - **Sentry** (`logError` / `SentrySDK.capture`): only when a domain classifier marks the failure actionable.
/// Do not call `AnalyticsManager.desktopHealthEvent` directly — it bypasses the ring buffer.
final class DesktopDiagnosticsManager {
  nonisolated(unsafe) static let shared = DesktopDiagnosticsManager()

  private let lock = NSLock()
  private var snapshots: [DesktopHealthSnapshot] = []
  private let snapshotLimit = 150
  private var consecutiveNearZeroPTTTurns = 0
  private var lastPTTWatchdogIncidentAt: Date?
  private let pttWatchdogThreshold = 3
  private let pttWatchdogDedupWindow: TimeInterval = 15 * 60
  private let pttWatchdogMinimumAudioSeconds: Double = 0.35

  private init() {}

  func recordAuthTokenStorageFallback(reason: String, updateChannel: String) {
    record(
      .authTokenStorageFallback,
      properties: [
        "storage": "user_defaults",
        "reason": reason,
        "update_channel": updateChannel,
      ])
  }

  func recordAuthSessionCleared(
    reason: String,
    httpStatusCode: Int?,
    failureClass: String = "definitive_auth_failure"
  ) {
    var properties: [String: Any] = [
      "reason": reason,
      "failure_class": failureClass,
      "recovery_action": "clear_session",
      "recovery_result": "cleared",
    ]
    if let httpStatusCode {
      properties["http_status_code"] = httpStatusCode
    }
    record(.authSessionCleared, properties: properties)
  }

  func recordTranscriptionWsReconnectExhausted(
    reconnectAttempts: Int,
    streamingMode: String
  ) {
    record(
      .transcriptionWsReconnectExhausted,
      properties: [
        "reconnect_attempts": reconnectAttempts,
        "streaming_mode": streamingMode,
        "failure_class": "ws_reconnect_exhausted",
        "recovery_action": "surface_error",
        "recovery_result": "exhausted",
      ])
  }

  func recordWalPersistenceDegraded(reason: String, recoveryAction: String, recoveryResult: String) {
    recordFallback(
      area: "wal_persistence",
      from: "disk",
      to: "memory",
      reason: reason,
      outcome: .degraded,
      extra: [
        "failure_class": "wal_persistence_degraded",
        "recovery_action": recoveryAction,
        "recovery_result": recoveryResult,
      ])
  }

  func recordWalWriteFailed(walId: String, reason: String) {
    recordFallback(
      area: "wal_persistence",
      from: "disk",
      to: "memory",
      reason: "wal_write_failed",
      outcome: .degraded,
      extra: [
        "wal_id": walId,
        "detail_reason": reason,
        "failure_class": "wal_write_failed",
        "recovery_action": "retain_frames",
        "recovery_result": "degraded",
      ])
  }

  func recordWalUploadFailed(walId: String, reason: String) {
    recordFallback(
      area: "wal_upload",
      from: "disk",
      to: "pending",
      reason: "upload_failed",
      outcome: .degraded,
      extra: [
        "wal_id": walId,
        "detail_reason": reason,
        "failure_class": "wal_upload_failed",
        "recovery_action": "leave_pending",
        "recovery_result": "degraded",
      ])
  }

  func recordAgentRuntimeStaleAliveCheck() {
    recordFallback(
      area: "agent_runtime",
      from: "alive_latch",
      to: "termination_cleanup",
      reason: "stale_alive_latch",
      outcome: .degraded,
      extra: [
        "failure_class": "stale_alive_latch",
        "recovery_action": "route_to_termination",
        "recovery_result": "degraded",
      ])
  }

  func recordAgentRuntimeUnexpectedExit(exitCode: Int32, oom: Bool) {
    recordFallback(
      area: "agent_runtime",
      from: "running",
      to: "stopped",
      reason: oom ? "out_of_memory" : "process_exited",
      outcome: .degraded,
      extra: [
        "exit_code": Int(exitCode),
        "oom": oom,
        "failure_class": oom ? "out_of_memory" : "process_exited",
        "recovery_action": "restart_on_next_send",
        "recovery_result": "degraded",
      ])
  }

  func recordApiAuthRetry(endpoint: String, outcome: String) {
    let fallbackOutcome: DesktopFallbackOutcome =
      outcome == "succeeded" ? .recovered : (outcome == "retrying" ? .degraded : .exhausted)
    recordFallback(
      area: "api_auth",
      from: "expired_token",
      to: outcome == "succeeded" ? "refreshed_token" : "reauth",
      reason: "http_401",
      outcome: fallbackOutcome,
      extra: [
        "endpoint": endpoint,
        "retry_outcome": outcome,
        "failure_class": "auth_retry",
        "recovery_action": "refresh_token",
        "recovery_result": fallbackOutcome.rawValue,
      ])
  }

  func recordDbLockContention(source: String) {
    recordFallback(
      area: "db_lock",
      from: "query",
      to: "backoff",
      reason: "db_lock_contention",
      outcome: .degraded,
      extra: [
        "source": source,
        "failure_class": "db_lock_contention",
        "recovery_action": "backoff",
        "recovery_result": "degraded",
      ])
  }

  func recordChatBridgeModeSwitchTimeout(waitSeconds: Int) {
    recordFallback(
      area: "chat_bridge",
      from: "mode_switch",
      to: "continue_waiting",
      reason: "mode_switch_timeout",
      outcome: .degraded,
      extra: [
        "wait_seconds": waitSeconds,
        "failure_class": "mode_switch_timeout",
        "recovery_action": "clear_waiters",
        "recovery_result": "degraded",
      ])
  }

  func recordBleDecodeDegraded(codec: String, failures: Int) {
    recordFallback(
      area: "ble_audio",
      from: "decode",
      to: "raw_capture",
      reason: "ble_decode_failed",
      outcome: .degraded,
      extra: [
        "codec": codec,
        "consecutive_failures": failures,
        "failure_class": "ble_decode_degraded",
        "recovery_action": "continue_raw_capture",
        "recovery_result": "degraded",
      ])
  }

  func recordAutomationBridgeBindFailed(port: Int, reason: String) {
    recordFallback(
      area: "automation_bridge",
      from: "unbound",
      to: "bind_failed",
      reason: "bind_failed",
      outcome: .exhausted,
      extra: [
        "port": port,
        "detail_reason": reason,
        "failure_class": "bind_failed",
        "recovery_action": "retry_exhausted",
        "recovery_result": "exhausted",
      ])
  }

  func recordPTTStarted(mode: String, hubActive: Bool, micPermissionGranted: Bool) {
    record(
      .pttStarted,
      properties: [
        "mode": mode,
        "hub_active": hubActive,
        "tcc_microphone_granted": micPermissionGranted,
      ],
      trackRemotely: false)
  }

  func recordPTTSilentTurn(
    source: String,
    mode: String,
    audioSeconds: Double,
    voicedSeconds: Double?,
    peak: Int,
    rms: Int,
    deviceDescription: String?,
    micPermissionGranted: Bool,
    hubActive: Bool,
    recoveryAction: String = "none",
    recoveryResult: String = "not_attempted"
  ) {
    let nearZero = peak <= 5 && rms <= 5
    let watchdogEligible = audioSeconds >= pttWatchdogMinimumAudioSeconds
    if nearZero && micPermissionGranted && watchdogEligible {
      consecutiveNearZeroPTTTurns += 1
    } else if peak > 50 || rms > 20 {
      consecutiveNearZeroPTTTurns = 0
    }

    var properties: [String: Any] = [
      "source": source,
      "mode": mode,
      "hub_active": hubActive,
      "turn_audio_seconds": rounded(audioSeconds),
      "peak": peak,
      "rms": rms,
      "is_near_zero": nearZero,
      "watchdog_eligible": watchdogEligible,
      "consecutive_silent_turns": consecutiveNearZeroPTTTurns,
      "tcc_microphone_granted": micPermissionGranted,
      "input_device_class": classifyInputDevice(deviceDescription),
      "recovery_action": recoveryAction,
      "recovery_result": recoveryResult,
    ]
    if let voicedSeconds {
      properties["voiced_audio_seconds"] = rounded(voicedSeconds)
    }

    record(.pttAudioCaptureSilentTurn, properties: properties)

    guard nearZero && micPermissionGranted && watchdogEligible && consecutiveNearZeroPTTTurns >= pttWatchdogThreshold
    else { return }
    recordPTTWatchdogTriggered(latestProperties: properties)
  }

  func recordPTTCommitted(mode: String, hubActive: Bool) {
    consecutiveNearZeroPTTTurns = 0
    record(
      .pttCommitted,
      properties: [
        "mode": mode,
        "hub_active": hubActive,
      ],
      trackRemotely: false)
  }

  func recordVoiceTurnTerminal(
    reason: String,
    route: String,
    staleEventCount: Int,
    invalidTransitionCount: Int
  ) {
    let breadcrumb = Breadcrumb(level: .info, category: "voice.turn.terminal")
    breadcrumb.message = "Voice turn reached terminal state"
    breadcrumb.data = [
      "terminal_reason": reason,
      "route": route,
      "stale_event_count": staleEventCount,
      "invalid_transition_count": invalidTransitionCount,
    ]
    SentrySDK.addBreadcrumb(breadcrumb)
  }

  func recordVoiceTurnAnomaly(kind: String, phase: String, route: String) {
    let breadcrumb = Breadcrumb(level: .warning, category: "voice.turn.anomaly")
    breadcrumb.message = "Voice turn rejected an anomalous event"
    breadcrumb.data = [
      "kind": kind,
      "phase": phase,
      "route": route,
    ]
    SentrySDK.addBreadcrumb(breadcrumb)
  }

  func recordPTTDeviceRouteChanged(recoveryAction: String, recoveryResult: String) {
    record(
      .pttAudioCaptureDeviceRouteChanged,
      properties: [
        "recovery_action": recoveryAction,
        "recovery_result": recoveryResult,
      ])
  }

  /// Shared fallback / resilience telemetry. Prefer this over inventing new
  /// `DesktopHealthEventName` cases for provider/mode switches.
  ///
  /// - Parameters match the backend `record_fallback` contract.
  /// - `outcome`: recovered (full UX restored), degraded (continues with hit),
  ///   exhausted (no acceptable path left).
  /// - Always tracks remotely on prod/beta so ops can see silent UX heals.
  func recordFallback(
    area: String,
    from: String,
    to: String,
    reason: String,
    outcome: DesktopFallbackOutcome,
    extra: [String: Any] = [:]
  ) {
    var properties: [String: Any] = [
      "area": bucketFallbackArea(area),
      "from": safeFallbackLabel(from, default: "none"),
      "to": safeFallbackLabel(to, default: "none"),
      "reason": bucketFallbackReason(reason),
      "outcome": outcome.rawValue,
    ]
    for (key, value) in sanitized(extra) {
      if properties[key] == nil {
        properties[key] = value
      }
    }
    record(.fallbackTriggered, properties: properties, trackRemotely: true)
  }

  func recordRealtimeTokenMintFailed(
    provider: String,
    reason: String,
    phase: String,
    httpStatusCode: Int? = nil,
    backendRoute: String? = nil,
    upstreamStatusCode: Int? = nil,
    providerCode: String? = nil,
    retryable: Bool? = nil
  ) {
    var properties: [String: Any] = [
      "provider": safeProvider(provider),
      "reason": reason,
      "phase": phase,
    ]
    if let httpStatusCode {
      properties["http_status_code"] = httpStatusCode
    }
    if let backendRoute {
      properties["backend_route"] = backendRoute
    }
    if let upstreamStatusCode {
      properties["upstream_status_code"] = upstreamStatusCode
    }
    if let providerCode {
      properties["provider_code"] = providerCode
    }
    if let retryable {
      properties["retryable"] = retryable
    }
    record(
      .realtimeTokenMintFailed,
      properties: properties)
  }

  func recordRealtimeProviderClose(
    provider: String,
    category: String?,
    aliveFor: TimeInterval,
    activeTurn: Bool,
    authMode: CredentialAuthMode?,
    failureClass: CredentialFailureClass?
  ) {
    let normalizedCategory = category ?? failureClass?.logValue ?? "unclassified"
    let event: DesktopHealthEventName
    switch normalizedCategory {
    case RealtimeHubCloseCategory.expectedIdleTeardown.rawValue:
      event = .realtimeProviderExpectedIdleTeardown
    case RealtimeHubCloseCategory.expectedSessionRotation.rawValue:
      event = .realtimeProviderExpectedSessionRotation
    case RealtimeHubCloseCategory.providerPolicyCloseFast.rawValue,
      CredentialFailureClass.providerPolicyClose(provider: .openai).logValue:
      event = .realtimeProviderPolicyClose
    default:
      event = .realtimeProviderSessionError
    }
    var properties: [String: Any] = [
      "provider": safeProvider(provider),
      "category": normalizedCategory,
      "alive_for_seconds": Int(aliveFor),
      "active_turn": activeTurn,
    ]
    if normalizedCategory == RealtimeHubCloseCategory.expectedSessionRotation.rawValue {
      properties["recovery_action"] = "rotate_realtime_session"
      properties["recovery_result"] = activeTurn ? "turn_terminated_and_rewarm_started" : "rewarm_started"
    }
    if let authMode {
      properties["auth_mode"] = authMode.rawValue
    }
    if let failureClass {
      properties["failure_class"] = failureClass.logValue
      if let httpStatusCode = failureClass.httpStatusCode {
        properties["http_status_code"] = httpStatusCode
      }
    }
    record(
      event,
      properties: properties)
  }

  func currentSnapshotsForSentry() -> [[String: Any]] {
    lock.lock()
    let current = snapshots.map { $0.dictionary() }
    lock.unlock()
    return current
  }

  func writeDiagnosticsAttachment() -> URL? {
    let payload: [String: Any] = [
      "generated_at": ISO8601DateFormatter.desktopDiagnostics.string(from: Date()),
      "privacy": "safe_operational_fields_only",
      "snapshots": currentSnapshotsForSentry(),
    ]
    guard JSONSerialization.isValidJSONObject(payload),
      let data = try? JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted])
    else { return nil }
    let url = FileManager.default.temporaryDirectory
      .appendingPathComponent("omi-desktop-diagnostics-\(UUID().uuidString).json")
    do {
      try data.write(to: url, options: .atomic)
      return url
    } catch {
      log("DesktopDiagnostics: failed to write diagnostics attachment")
      return nil
    }
  }

  // MARK: - Local (offline) diagnostics export

  /// Build a redacted, offline diagnostics bundle and write it to `url`.
  ///
  /// Unlike the Sentry path, this works with no network and without a crash
  /// reporter — it backs the local "Save Diagnostics…" export so users can share
  /// a report manually (BL-023 / SET-03). The bundle carries app/version/OS
  /// metadata, the already-sanitized health snapshots, and a redacted tail of the
  /// local log. Returns `true` on success.
  @discardableResult
  func writeLocalDiagnosticsBundle(
    to url: URL,
    logPath: String = omiLogFilePath(),
    maxLogLines: Int = 500
  ) -> Bool {
    let text = buildLocalDiagnosticsText(logPath: logPath, maxLogLines: maxLogLines)
    guard let data = text.data(using: .utf8) else { return false }
    do {
      try data.write(to: url, options: .atomic)
      return true
    } catch {
      log("DesktopDiagnostics: failed to write local diagnostics bundle")
      return false
    }
  }

  /// Render the redacted diagnostics bundle as plain text (metadata header,
  /// sanitized health snapshots, redacted recent log tail). Exposed for testing
  /// the redaction guarantee without disk I/O.
  func buildLocalDiagnosticsText(logPath: String, maxLogLines: Int = 500) -> String {
    var sections: [String] = []

    let meta = commonProperties()
    var header = ["# Omi Desktop Diagnostics"]
    header.append("generated_at: \(ISO8601DateFormatter.desktopDiagnostics.string(from: Date()))")
    header.append("privacy: redacted_local_export")
    for key in ["build", "build_number", "os_version", "device_model", "system_audio_mode"] {
      if let value = meta[key] {
        header.append("\(key): \(value)")
      }
    }
    sections.append(header.joined(separator: "\n"))

    let snapshots = currentSnapshotsForSentry()
    if JSONSerialization.isValidJSONObject(snapshots),
      let data = try? JSONSerialization.data(withJSONObject: snapshots, options: [.prettyPrinted]),
      let json = String(data: data, encoding: .utf8)
    {
      sections.append("## Health snapshots\n\(json)")
    }

    let tail = redactedLogTail(logPath: logPath, maxLines: maxLogLines)
    sections.append("## Recent log (redacted, last \(maxLogLines) lines)\n\(tail)")

    return sections.joined(separator: "\n\n") + "\n"
  }

  /// Read up to `maxLines` from the end of the log file, redacting anything that
  /// looks like a secret (tokens, JWTs, credential kv pairs) line by line.
  private func redactedLogTail(logPath: String, maxLines: Int) -> String {
    guard let handle = FileHandle(forReadingAtPath: logPath) else {
      return "(no readable log file at \(logPath))"
    }
    defer { handle.closeFile() }
    // Read only a bounded tail from the end rather than loading the whole log
    // into memory, so export latency and memory stay predictable on large logs.
    // 512 KB comfortably covers maxLines (default 500) of log text.
    let maxTailBytes: UInt64 = 512 * 1024
    let fileSize = handle.seekToEndOfFile()
    let start = fileSize > maxTailBytes ? fileSize - maxTailBytes : 0
    handle.seek(toFileOffset: start)
    let data = handle.readDataToEndOfFile()
    // Lenient decode: a byte-offset seek can split a multibyte character, so
    // substitute rather than fail; the possibly-partial first line is dropped.
    var content = String(decoding: data, as: UTF8.self)
    if start > 0, let newline = content.firstIndex(of: "\n") {
      content = String(content[content.index(after: newline)...])
    }
    let lines = content.split(separator: "\n", omittingEmptySubsequences: false)
    let tail = lines.suffix(max(0, maxLines))
    return tail.map { redactSensitive(String($0)) }.joined(separator: "\n")
  }

  /// Defensive best-effort redaction. The desktop log is not expected to contain
  /// raw credentials, but a manually-shared export must never leak one, so we
  /// mask common token shapes before including any log text.
  private static let redactionPatterns: [(NSRegularExpression, String)] = {
    let specs: [(String, String)] = [
      // JWT: three base64url segments starting with a typical header.
      ("eyJ[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+", "[redacted-jwt]"),
      // Authorization: Bearer <token>
      ("(?i)(bearer)\\s+[A-Za-z0-9._~+/=-]{8,}", "$1 [redacted]"),
      // Authorization: Basic <base64 credentials>. Anchored to the header prefix
      // so benign phrases like "basic settings" aren't over-redacted.
      ("(?i)(authorization:\\s*basic)\\s+[A-Za-z0-9+/=]{8,}", "$1 [redacted]"),
      // Bare OpenAI-style API keys.
      ("sk-[A-Za-z0-9_-]{20,}", "sk-[redacted]"),
      // key=..., token: ..., password="..." in query strings, JSON, or kv logs.
      (
        "(?i)(api[_-]?key|access[_-]?token|refresh[_-]?token|id[_-]?token|token|password|passwd|secret|client[_-]?secret|authorization)([\"']?\\s*[=:]\\s*[\"']?)[A-Za-z0-9._~+/=-]{6,}",
        "$1$2[redacted]"
      ),
    ]
    return specs.compactMap { pattern, template in
      (try? NSRegularExpression(pattern: pattern)).map { ($0, template) }
    }
  }()

  private func redactSensitive(_ line: String) -> String {
    var result = line
    for (regex, template) in DesktopDiagnosticsManager.redactionPatterns {
      let range = NSRange(result.startIndex..., in: result)
      result = regex.stringByReplacingMatches(in: result, range: range, withTemplate: template)
    }
    return result
  }

  func resetForTests() {
    lock.lock()
    snapshots.removeAll()
    consecutiveNearZeroPTTTurns = 0
    lastPTTWatchdogIncidentAt = nil
    lock.unlock()
  }

  private func record(
    _ event: DesktopHealthEventName,
    properties: [String: Any],
    trackRemotely: Bool = true
  ) {
    let snapshot = DesktopHealthSnapshot(
      timestamp: Date(),
      event: event,
      properties: commonProperties().merging(sanitized(properties)) { _, new in new })

    lock.lock()
    snapshots.append(snapshot)
    if snapshots.count > snapshotLimit {
      snapshots.removeFirst(snapshots.count - snapshotLimit)
    }
    lock.unlock()

    guard trackRemotely else { return }
    Task { @MainActor in
      AnalyticsManager.shared.desktopHealthEvent(
        name: event.rawValue,
        properties: snapshot.dictionary())
    }
  }

  private func recordPTTWatchdogTriggered(latestProperties: [String: Any]) {
    let now = Date()
    if let last = lastPTTWatchdogIncidentAt, now.timeIntervalSince(last) < pttWatchdogDedupWindow {
      return
    }
    lastPTTWatchdogIncidentAt = now

    let properties = latestProperties.merging([
      "threshold": pttWatchdogThreshold,
      "recovery_action": "prompt_restart",
      "recovery_result": "not_attempted",
    ]) { _, new in new }
    record(.pttAudioCaptureWatchdogTriggered, properties: properties)

    SentrySDK.capture(message: "PTT Silent Capture Watchdog Triggered") { scope in
      scope.setLevel(.warning)
      scope.setTag(value: "ptt_silent_capture_watchdog", key: "diagnostic")
      scope.setContext(value: properties, key: "audio_capture")
      scope.setContext(
        value: ["snapshots": self.currentSnapshotsForSentry()],
        key: "desktop_health_snapshots")
    }
  }

  private func commonProperties() -> [String: Any] {
    var properties: [String: Any] = [
      "build": Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "unknown",
      "build_number": Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "unknown",
      "os_version": osVersionString(),
      "device_model": deviceModel(),
    ]
    properties["system_audio_mode"] =
      UserDefaults.standard.string(forKey: "systemAudioCaptureMode") ?? "onlyDuringMeetings"
    return properties
  }

  private func sanitized(_ properties: [String: Any]) -> [String: Any] {
    var safe: [String: Any] = [:]
    for (key, value) in properties {
      switch value {
      case let string as String:
        safe[key] = String(string.prefix(96))
      case let int as Int:
        safe[key] = int
      case let double as Double:
        safe[key] = rounded(double)
      case let bool as Bool:
        safe[key] = bool
      default:
        continue
      }
    }
    return safe
  }

  private func rounded(_ value: Double) -> Double {
    (value * 100).rounded() / 100
  }

  private func classifyInputDevice(_ description: String?) -> String {
    let lower = (description ?? "").lowercased()
    if lower.contains("built-in") { return "built_in_mic" }
    if lower.contains("bluetooth") { return "bluetooth_headset" }
    if lower.contains("virtual") || lower.contains("aggregate") { return "virtual_audio_device" }
    if lower.isEmpty || lower == "?" { return "unknown" }
    return "external_or_default_mic"
  }

  private func safeProvider(_ provider: String) -> String {
    switch provider.lowercased() {
    case "openai", "gemini": return provider.lowercased()
    default: return "unknown"
    }
  }

  private static let allowedFallbackAreas: Set<String> = [
    "sync_dispatch",
    "pusher",
    "stt_selection",
    "vad",
    "audio_merge",
    "webhook",
    "realtime_hub",
    "ptt_cascade",
    "gemini_model",
    "gemini_proxy",
    "gemini_stream_proxy",
    "redis_ratelimit",
    "silent_mic",
    "wal_persistence",
    "wal_upload",
    "agent_runtime",
    "api_auth",
    "db_lock",
    "chat_bridge",
    "ble_audio",
    "automation_bridge",
    "transcription_retry",
    "task_reconcile",
    "other",
  ]

  private static let allowedFallbackReasons: Set<String> = [
    "timeout",
    "provider_5xx",
    "provider_429",
    "enqueue_failed",
    "config_incomplete",
    "circuit_open",
    "capability_mismatch",
    "auth",
    "quota",
    "local_heal",
    "policy",
    "dispatch_disabled",
    "byok",
    "other",
    "none",
    "wal_directory_unavailable",
    "wal_write_failed",
    "upload_failed",
    "stale_alive_latch",
    "out_of_memory",
    "process_exited",
    "http_401",
    "db_lock_contention",
    "mode_switch_timeout",
    "ble_decode_failed",
    "bind_failed",
    "db_backoff",
  ]

  private func bucketFallbackArea(_ area: String) -> String {
    let label = safeFallbackLabel(area, default: "other")
    return Self.allowedFallbackAreas.contains(label) ? label : "other"
  }

  private func bucketFallbackReason(_ reason: String) -> String {
    let label = safeFallbackLabel(reason, default: "other")
    return Self.allowedFallbackReasons.contains(label) ? label : "other"
  }

  private func safeFallbackLabel(_ value: String, default defaultValue: String) -> String {
    let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    let source = trimmed.isEmpty ? defaultValue : trimmed
    let allowed = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "._:-"))
    let normalized = String(
      source.unicodeScalars.map { allowed.contains($0) ? Character($0) : "_" })
    let clipped = String(normalized.prefix(64))
    return clipped.isEmpty ? defaultValue : clipped
  }

  private func osVersionString() -> String {
    let version = ProcessInfo.processInfo.operatingSystemVersion
    return "\(version.majorVersion).\(version.minorVersion).\(version.patchVersion)"
  }

  private func deviceModel() -> String {
    var size = 0
    sysctlbyname("hw.model", nil, &size, nil, 0)
    guard size > 0 else { return "unknown" }
    var model = [CChar](repeating: 0, count: size)
    sysctlbyname("hw.model", &model, &size, nil, 0)
    return model.withUnsafeBufferPointer { buffer in
      buffer.baseAddress.map { String(cString: $0) } ?? "unknown"
    }
  }
}
