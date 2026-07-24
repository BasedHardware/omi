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
  case pttAudioCaptureLifecycle = "ptt_audio_capture_lifecycle"
  case voiceTurnStarted = "voice_turn_started"
  case voiceTurnTerminal = "voice_turn_terminal"
  case voiceToolLatency = "voice_tool_latency"
  case realtimeTokenMintFailed = "realtime_token_mint_failed"
  case realtimeProviderExpectedIdleTeardown = "realtime_provider_expected_idle_teardown"
  case realtimeProviderExpectedSessionRotation = "realtime_provider_expected_session_rotation"
  case realtimeProviderPolicyClose = "realtime_provider_policy_close"
  case realtimeProviderSessionError = "realtime_provider_session_error"
  case userVisibleIssue = "user_visible_issue"
  case betaDiagnosticTrail = "beta_diagnostic_trail"
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
  private var betaTrailSnapshots: [DesktopHealthSnapshot] = []
  private let snapshotLimit = 150
  /// Wall-clock start of each in-flight realtime voice tool call, keyed by the
  /// hub's transport key. A start/stop timer for `voice_tool_latency`; cleared
  /// on turn reset so it can't grow unbounded.
  private var voiceToolStarts: [String: Date] = [:]
  private let betaTrailSnapshotLimit = 50
  private var consecutiveNearZeroPTTTurns = 0
  private var lastPTTWatchdogIncidentAt: Date?
  private var lastUserVisibleSentryIncidentAt: [String: Date] = [:]
  private let pttWatchdogThreshold = 3
  private let pttWatchdogDedupWindow: TimeInterval = 15 * 60
  private let userVisibleSentryDedupWindow: TimeInterval = 60
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

  /// Per-tool wall time on a realtime voice turn: from the provider's tool
  /// request to the result being returned — i.e. the "dead air" the user hears
  /// while a tool runs. Instruments where voice latency actually goes (fast
  /// local reads vs. slow backend/RAG round-trips) so optimization targets the
  /// real cost instead of a guess. Bounded dimensions only: `tool_name` and
  /// `provider` are a fixed low-cardinality set; no arguments or output content.
  func recordVoiceToolLatency(toolName: String, provider: String, durationMs: Double, resultBytes: Int) {
    record(
      .voiceToolLatency,
      properties: [
        "tool_name": toolName,
        "provider": provider,
        "duration_ms": rounded(durationMs),
        "result_bytes": resultBytes,
      ])
  }

  /// Start a `voice_tool_latency` timer for a realtime tool call (the hub's
  /// transport key). Kept here rather than on the hub so the 1500-line
  /// RealtimeHubController does not grow.
  func markVoiceToolStart(key: String) {
    lock.lock()
    voiceToolStarts[key] = Date()
    lock.unlock()
  }

  /// Stop the timer for `key` and emit `voice_tool_latency`. No-op if no start
  /// was recorded (stale/dropped result).
  func finishVoiceToolLatency(key: String, toolName: String, provider: String, resultBytes: Int) {
    lock.lock()
    let start = voiceToolStarts.removeValue(forKey: key)
    lock.unlock()
    guard let start else { return }
    recordVoiceToolLatency(
      toolName: toolName,
      provider: provider,
      durationMs: Date().timeIntervalSince(start) * 1000,
      resultBytes: resultBytes)
  }

  /// Drop any in-flight voice tool timers — called on realtime turn reset.
  func clearVoiceToolStarts() {
    lock.lock()
    voiceToolStarts.removeAll()
    lock.unlock()
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

    if nearZero && micPermissionGranted && watchdogEligible {
      recordUserVisibleIssue(
        area: "ptt",
        failureClass: "silent_capture",
        phase: "audio_capture",
        extra: properties)
    }

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
  /// Record one bounded PTT attempt lifecycle snapshot (see
  /// `PTTAttemptLifecycleRecorder`). Routes through the shared ring buffer + Sentry
  /// attachment path. Emitted remotely (PostHog) for EVERY terminal disposition —
  /// including `failureClass == .committed` — so a release-health query has the
  /// full attempt denominator (success + the causally distinct excluded/failure
  /// classes), not only classified failures. Short tap / quiet discard / user
  /// cancel are bounded `failure_class` values distinct from `capture_never_operational`,
  /// so they cannot inflate a capture-failure rate. This is the authoritative,
  /// privacy-bounded PTT terminal-outcome funnel (#10425); the ambiguous
  /// `floating_bar_ptt_ended` `had_transcript` event is retained only for backward
  /// compatibility and must not be read as a success/failure denominator.
  func recordPTTAttemptLifecycle(_ snapshot: PTTAttemptLifecycleRecorder.Snapshot) {
    record(
      .pttAudioCaptureLifecycle,
      properties: snapshot.properties,
      trackRemotely: true)
  }

  /// Records a typed chat failure as a fleet-health metric. The existing bounded
  /// `logError` path owns the matching Sentry incident to avoid duplicate capture.
  func recordChatFailure(errorClass: String) {
    recordUserVisibleIssue(
      area: "chat",
      failureClass: errorClass,
      phase: "query",
      captureSentry: false)
  }

  /// Records a global-hotkey registration failure surfaced by Carbon
  /// `RegisterEventHotKey`.
  ///
  /// This is a hard-terminal failure — the shortcut will not fire on this machine
  /// (typically another app, or a macOS System Settings > Keyboard > Shortcuts
  /// entry — even a disabled one — already owns the combination). Because no
  /// provider, mode, or correctness path switches and there is nothing to fail
  /// open to, the telemetry contract routes this through the incident path, not
  /// `recordFallback`. `isConflict` distinguishes `eventHotKeyExistsErr` (-9878),
  /// which is a property of the user's machine, from other `OSStatus` values.
  func recordHotkeyRegistrationFailed(osStatus: Int, keycode: Int, modifiers: Int, isConflict: Bool) {
    recordUserVisibleIssue(
      area: "startup",
      failureClass: isConflict ? "hotkey_conflict" : "unknown",
      phase: "startup",
      extra: [
        "osstatus": osStatus,
        "keycode": keycode,
        "modifiers": modifiers,
      ])
  }

  /// Records a beta-only typed error trail entry. The caller passes free-form local
  /// log text only for local classification; no message or error description is
  /// retained in the trail or cloud attachment.
  func recordBetaLogError(
    message: String,
    error: Error?,
    enabled: Bool = BetaEnhancedDiagnosticsConfiguration.isEnabled
  ) {
    guard enabled else { return }
    let nsError = error as NSError?
    let snapshot = DesktopHealthSnapshot(
      timestamp: Date(),
      event: .betaDiagnosticTrail,
      properties: commonProperties().merging(
        sanitized([
          "component": betaComponent(for: message),
          "operation": "error",
          "phase": "handling",
          "outcome": "failed",
          "failure_class": betaFailureClass(for: nsError),
          "error_domain": betaErrorDomain(nsError?.domain),
          "error_code": betaErrorCode(nsError?.code),
        ])
      ) { _, new in new })
    lock.lock()
    betaTrailSnapshots.append(snapshot)
    if betaTrailSnapshots.count > betaTrailSnapshotLimit {
      betaTrailSnapshots.removeFirst(betaTrailSnapshots.count - betaTrailSnapshotLimit)
    }
    lock.unlock()
  }

  func recordVoiceTurnStarted(turnID: String, intent: String) {
    record(
      .voiceTurnStarted,
      properties: [
        "attempt_id": turnID,
        "intent": intent,
        "telemetry_schema_version": 1,
      ])
  }

  func recordVoiceTurnTerminal(
    turnID: String,
    reason: String,
    route: String,
    intent: String,
    durationMs: Int?,
    answerDelivered: Bool,
    staleEventCount: Int,
    invalidTransitionCount: Int
  ) {
    var properties: [String: Any] = [
      "attempt_id": turnID,
      "terminal_reason": reason,
      "outcome": Self.voiceTurnOutcome(for: reason),
      "response_outcome": Self.voiceResponseOutcome(for: reason, answerDelivered: answerDelivered),
      "route": route,
      "intent": intent,
      "stale_event_count": staleEventCount,
      "invalid_transition_count": invalidTransitionCount,
      "telemetry_schema_version": 1,
    ]
    if let durationMs {
      properties["duration_ms"] = max(0, durationMs)
    }
    record(.voiceTurnTerminal, properties: properties)

    let breadcrumb = Breadcrumb(level: .info, category: "voice.turn.terminal")
    breadcrumb.message = "Voice turn reached terminal state"
    breadcrumb.data = properties
    SentrySDK.addBreadcrumb(breadcrumb)
  }

  static func voiceTurnOutcome(for reason: String) -> String {
    switch reason {
    case "success":
      return "success"
    case "too_short", "silent_rejected", "cancelled", "owner_changed",
      "interrupted_by_barge_in", "explicit_interrupt", "cleanup":
      return "excluded"
    default:
      return "failure"
    }
  }

  static func voiceResponseOutcome(for reason: String, answerDelivered: Bool) -> String {
    if answerDelivered || reason == "success" {
      return "success"
    }
    return voiceTurnOutcome(for: reason)
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

  /// Realtime token-mint failure. `phase` is bucketed to a closed set (`warm` =
  /// background pre-warm vs `barge_in_replacement` = replacement during an active
  /// turn) so a release-health query has a bounded warm-vs-active dimension (#10425).
  /// `outcome`/`mintAttemptId` are optional: a mint failure is point-in-time, so its
  /// terminal fate (recovered/degraded/exhausted) is carried by the correlated
  /// `fallback_triggered`{area=realtime_hub} event; `mint_attempt_id` lets a query
  /// join the two without provider/time heuristics.
  func recordRealtimeTokenMintFailed(
    provider: String,
    reason: String,
    phase: String,
    httpStatusCode: Int? = nil,
    backendRoute: String? = nil,
    upstreamStatusCode: Int? = nil,
    providerCode: String? = nil,
    retryable: Bool? = nil,
    outcome: DesktopFallbackOutcome? = nil,
    mintAttemptId: String? = nil
  ) {
    var properties: [String: Any] = [
      "provider": safeProvider(provider),
      "reason": reason,
      "phase": bucketRealtimePhase(phase),
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
    if let outcome {
      properties["outcome"] = outcome.rawValue
    }
    if let mintAttemptId, !mintAttemptId.isEmpty {
      properties["mint_attempt_id"] = mintAttemptId
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
    // Bounded release-health dimension: a single `expected` flag + `lifecycle_class`
    // so a release-regression rollup can exclude normal idle teardown / planned
    // session rotation without enumerating the two `realtime_provider_expected_*`
    // event names (#10425). Expected lifecycle stays inspectable, never an error.
    let expectedLifecycle =
      event == .realtimeProviderExpectedIdleTeardown
      || event == .realtimeProviderExpectedSessionRotation
    var properties: [String: Any] = [
      "provider": safeProvider(provider),
      "category": normalizedCategory,
      "alive_for_seconds": Int(aliveFor),
      "active_turn": activeTurn,
      "expected": expectedLifecycle,
      "lifecycle_class": expectedLifecycle ? "expected" : "error",
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

  private func currentCloudSnapshotsForSentry(
    includeBetaDiagnostics: Bool = BetaEnhancedDiagnosticsConfiguration.isEnabled
  ) -> [[String: Any]] {
    lock.lock()
    var current = snapshots.map { cloudSafeSnapshot($0, includeBetaDiagnostics: includeBetaDiagnostics) }
    if includeBetaDiagnostics {
      current.append(
        contentsOf: betaTrailSnapshots.map {
          cloudSafeSnapshot($0, includeBetaDiagnostics: true)
        })
    }
    lock.unlock()
    return current
  }

  private func currentSnapshotsForLocalExport() -> [[String: Any]] {
    currentSnapshotsForSentry()
  }

  private func cloudSafeSnapshot(
    _ snapshot: DesktopHealthSnapshot,
    includeBetaDiagnostics: Bool
  ) -> [String: Any] {
    var result: [String: Any] = [
      "timestamp": ISO8601DateFormatter.desktopDiagnostics.string(from: snapshot.timestamp),
      "event": snapshot.event.rawValue,
    ]

    let includesTypedIncidentContext =
      snapshot.event == .userVisibleIssue
      || snapshot.event == .pttAudioCaptureWatchdogTriggered
      || snapshot.event == .pttAudioCaptureLifecycle
      || (includeBetaDiagnostics && snapshot.event == .betaDiagnosticTrail)
    guard includesTypedIncidentContext else {
      return result
    }

    for key in DesktopDiagnosticsManager.cloudIncidentSnapshotKeys {
      if let value = snapshot.properties[key] {
        result[key] = value
      }
    }
    return result
  }

  private static let cloudIncidentSnapshotKeys: Set<String> = [
    "area", "failure_class", "phase", "build", "build_number", "os_version", "device_model",
    "source", "mode", "hub_active", "turn_audio_seconds", "voiced_audio_seconds", "peak", "rms",
    "is_near_zero", "watchdog_eligible", "consecutive_silent_turns", "tcc_microphone_granted",
    "input_device_class", "recovery_action", "recovery_result", "threshold",
    "component", "operation", "outcome", "error_domain", "error_code",
    "osstatus", "keycode", "modifiers",
    // PTT attempt lifecycle correlation (PTTAttemptLifecycleRecorder).
    "attempt_id", "capture_start_outcome", "capture_start_status_class",
    "ms_to_first_audio_bucket", "ms_to_first_usable_frame_bucket",
    "first_chunks_energy_bucket", "turn_disposition",
    "input_route_class", "input_route_source", "route_changed_during_attempt",
    "recovery_triggered", "recovery_attempt_id", "recovery_outcome_of_next_turn",
    "judgeable", "telemetry_schema_version",
  ]
  /// Exact-match property keys that must never appear on a health snapshot
  /// (local ring buffer or remote PostHog). Bounded cousins like
  /// `transcript_length`, `failure_class`, or `error_code` are intentionally NOT
  /// listed and survive the filter.
  private static let contentBearingPropertyKeys: Set<String> = [
    "transcript", "transcript_text", "audio", "audio_data", "pcm", "prompt", "prompt_text",
    "response", "response_text", "message", "error_message", "error_description", "error_desc",
    "localized_description", "description", "detail", "detail_reason", "detail_message",
    "reason_detail", "content", "title", "notification_title", "window_title", "screen_title",
  ]

  func writeDiagnosticsAttachment() -> URL? {
    let payload: [String: Any] = [
      "generated_at": ISO8601DateFormatter.desktopDiagnostics.string(from: Date()),
      "privacy": "safe_operational_fields_only",
      "snapshots": currentSnapshotsForSentry(),
    ]
    return writeDiagnosticsPayload(payload, prefix: "omi-desktop-diagnostics")
  }

  /// Creates a bounded, redacted local-context attachment for a cloud incident.
  /// This intentionally replaces raw `omi.log` uploads: the attachment includes
  /// safe health snapshots and a scrubbed tail only, never the entire log file.
  func writeIncidentDiagnosticsAttachment(
    incidentID: String = UUID().uuidString,
    area: String,
    failureClass: String,
    phase: String,
    logPath: String = omiLogFilePath(),
    maxLogLines: Int = 200,
    includeBetaDiagnostics: Bool = BetaEnhancedDiagnosticsConfiguration.isEnabled
  ) -> URL? {
    let incident = incidentProperties(
      id: incidentID,
      area: area,
      failureClass: failureClass,
      phase: phase)
    var payload: [String: Any] = [
      "generated_at": ISO8601DateFormatter.desktopDiagnostics.string(from: Date()),
      "privacy": "redacted_incident_context",
      "incident": incident,
      "snapshots": currentCloudSnapshotsForSentry(includeBetaDiagnostics: includeBetaDiagnostics),
    ]
    // Beta uploads the independently assembled typed trail only. The free-form
    // local-log tail remains available exclusively to the existing non-beta path.
    if !includeBetaDiagnostics {
      payload["redacted_log_tail"] = redactedLogTail(
        logPath: logPath,
        maxLines: maxLogLines,
        strictCloudRedaction: true)
    }
    return writeDiagnosticsPayload(payload, prefix: "omi-desktop-incident")
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

    let snapshots = currentSnapshotsForLocalExport()
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
  private func redactedLogTail(
    logPath: String,
    maxLines: Int,
    strictCloudRedaction: Bool = false
  ) -> String {
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
    return tail.map {
      redactSensitive(String($0), strictCloudRedaction: strictCloudRedaction)
    }.joined(separator: "\n")
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
      // Email addresses and absolute filesystem paths are operationally unnecessary
      // in a cloud diagnostic attachment.
      ("(?i)[A-Z0-9._%+-]+@[A-Z0-9.-]+\\.[A-Z]{2,}", "[redacted-email]"),
      ("/(?:Users|private|tmp|var|Applications)/[^\\s\\\"']+", "/[redacted-path]"),
      // URLs can contain query parameters and opaque resource identifiers.
      ("https?://[^\\s\\\"']+", "https://[redacted-url]"),
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

  private static let safeOperationalLogMarkers = [
    "ptt", "audio_capture", "audiocapture", "silent capture", "voiceturn", "voice turn",
    "realtime", "sentry", "desktopdiagnostics", "app crash", "crash recovery",
    "chat telemetry event=",
  ]

  private static let contentBearingLogMarkers = [
    "conversation", "transcript", "prompt", "response", "message", "memory", "title",
    "window", "screen", "ocr", "clipboard",
  ]

  private func redactSensitive(_ line: String, strictCloudRedaction: Bool = false) -> String {
    let normalized = line.lowercased()
    if strictCloudRedaction, normalized.contains("device=[") {
      return "[redacted-device-bearing-log-line]"
    }
    if strictCloudRedaction,
      DesktopDiagnosticsManager.contentBearingLogMarkers.contains(where: normalized.contains)
    {
      return "[redacted-content-bearing-log-line]"
    }
    if strictCloudRedaction,
      !DesktopDiagnosticsManager.safeOperationalLogMarkers.contains(where: normalized.contains)
    {
      return "[redacted-unclassified-log-line]"
    }

    var result = line
    for (regex, template) in DesktopDiagnosticsManager.redactionPatterns {
      let range = NSRange(result.startIndex..., in: result)
      result = regex.stringByReplacingMatches(in: result, range: range, withTemplate: template)
    }
    return result
  }

  #if DEBUG
    func resetForTests() {
      lock.lock()
      snapshots.removeAll()
      betaTrailSnapshots.removeAll()
      consecutiveNearZeroPTTTurns = 0
      lastPTTWatchdogIncidentAt = nil
      lastUserVisibleSentryIncidentAt.removeAll()
      lock.unlock()
    }
  #endif

  private func shouldCaptureIncident(area: String, failureClass: String) -> Bool {
    let key = "\(area):\(failureClass)"
    let now = Date()
    lock.lock()
    defer { lock.unlock() }
    if let last = lastUserVisibleSentryIncidentAt[key],
      now.timeIntervalSince(last) < userVisibleSentryDedupWindow
    {
      return false
    }
    lastUserVisibleSentryIncidentAt[key] = now
    return true
  }

  private func recordUserVisibleIssue(
    area: String,
    failureClass: String,
    phase: String,
    extra: [String: Any] = [:],
    captureSentry: Bool = true
  ) {
    let incidentID = UUID().uuidString
    var properties: [String: Any] = [
      "area": safeIncidentArea(area),
      "failure_class": safeIncidentLabel(failureClass),
      "phase": safeIncidentPhase(phase),
    ]
    let allowedExtras = sanitized(extra).filter {
      DesktopDiagnosticsManager.allowedIncidentExtraKeys.contains($0.key)
    }
    for (key, value) in allowedExtras where properties[key] == nil {
      properties[key] = value
    }
    record(.userVisibleIssue, properties: properties)

    let sentryProperties = properties.merging(["incident_id": incidentID]) { _, new in new }
    guard captureSentry,
      !AppBuild.isNonProduction,
      shouldCaptureIncident(
        area: properties["area"] as? String ?? "other",
        failureClass: properties["failure_class"] as? String ?? "other"),
      let attachmentURL = writeIncidentDiagnosticsAttachment(
        incidentID: incidentID,
        area: area,
        failureClass: failureClass,
        phase: phase)
    else { return }
    defer { try? FileManager.default.removeItem(at: attachmentURL) }

    SentrySDK.capture(message: "Desktop user-visible issue") { scope in
      scope.setLevel(.warning)
      scope.setTag(value: properties["area"] as? String ?? "other", key: "diagnostic_area")
      scope.setTag(value: properties["failure_class"] as? String ?? "other", key: "failure_class")
      scope.setContext(value: sentryProperties, key: "desktop_incident")
      scope.addAttachment(
        Attachment(
          path: attachmentURL.path,
          filename: "desktop-incident-diagnostics.json",
          contentType: "application/json"))
    }
  }

  private func incidentProperties(
    id: String,
    area: String,
    failureClass: String,
    phase: String
  ) -> [String: String] {
    [
      "incident_id": id,
      "area": safeIncidentArea(area),
      "failure_class": safeIncidentLabel(failureClass),
      "phase": safeIncidentPhase(phase),
    ]
  }

  private func writeDiagnosticsPayload(_ payload: [String: Any], prefix: String) -> URL? {
    guard JSONSerialization.isValidJSONObject(payload),
      let data = try? JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted])
    else { return nil }
    let url = FileManager.default.temporaryDirectory
      .appendingPathComponent("\(prefix)-\(UUID().uuidString).json")
    do {
      try data.write(to: url, options: .atomic)
      return url
    } catch {
      log("DesktopDiagnostics: failed to write diagnostics attachment")
      return nil
    }
  }

  private func record(
    _ event: DesktopHealthEventName,
    properties: [String: Any],
    trackRemotely: Bool = true
  ) {
    // Defense-in-depth privacy guard (#10425): no health snapshot — local ring buffer
    // or remote PostHog `desktop_health_event` — may carry raw transcript/audio/
    // prompt/response/free-form text. Drop any content-bearing key a caller might
    // accidentally thread through `extra`. Exact-match only so bounded keys like
    // `transcript_length` survive; this is the single chokepoint for every emit.
    let safeProperties = commonProperties().merging(sanitized(properties)) { _, new in new }
      .filter { !DesktopDiagnosticsManager.contentBearingPropertyKeys.contains($0.key) }
    let snapshot = DesktopHealthSnapshot(
      timestamp: Date(),
      event: event,
      properties: safeProperties)

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
    // The initial user-visible silent-capture incident owns the Sentry attachment.
    // Keep this threshold event in PostHog without duplicating an incident upload.
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

  private func betaComponent(for message: String) -> String {
    let value = message.lowercased()
    if value.contains("chat") || value.contains("bridge") { return "chat" }
    if value.contains("realtime") || value.contains("omni") { return "realtime" }
    if value.contains("ptt") || value.contains("audio") || value.contains("transcription") { return "audio" }
    if value.contains("bluetooth") || value.contains("wifi") || value.contains("device") { return "device" }
    if value.contains("auth") || value.contains("sign") { return "auth" }
    if value.contains("sync") || value.contains("wal") { return "sync" }
    if value.contains("update") || value.contains("sparkle") { return "update" }
    if value.contains("rewind") || value.contains("screen") { return "capture" }
    return "app"
  }

  private func betaFailureClass(for error: NSError?) -> String {
    guard let error else { return "unknown" }
    if error.domain == NSURLErrorDomain {
      switch error.code {
      case NSURLErrorTimedOut: return "timeout"
      case NSURLErrorNotConnectedToInternet, NSURLErrorCannotConnectToHost: return "network_unavailable"
      default: return "network_error"
      }
    }
    if error.domain == NSPOSIXErrorDomain { return "posix_error" }
    if error.domain == NSCocoaErrorDomain { return "cocoa_error" }
    return "other"
  }

  private func betaErrorDomain(_ domain: String?) -> String {
    switch domain {
    case NSURLErrorDomain: return "url"
    case NSPOSIXErrorDomain: return "posix"
    case NSCocoaErrorDomain: return "cocoa"
    case nil: return "none"
    default: return "other"
    }
  }

  private func betaErrorCode(_ code: Int?) -> Int {
    guard let code else { return 0 }
    return max(-9_999, min(9_999, code))
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

  private func safeIncidentArea(_ area: String) -> String {
    switch area {
    case "ptt", "chat", "realtime", "crash", "startup": return area
    default: return "other"
    }
  }

  private func safeIncidentPhase(_ phase: String) -> String {
    switch phase {
    case "audio_capture", "transcript", "query", "runtime", "session", "startup", "other": return phase
    default: return "other"
    }
  }

  private func safeIncidentLabel(_ label: String) -> String {
    let allowed: Set<String> = [
      "silent_capture", "tool_stall", "agent_error", "agent_runtime", "attachment_upload",
      "authentication", "bridge_unavailable", "bridge_start_failed", "browser_extension_missing",
      "concurrent_request", "encoding", "quota", "resource_exhausted", "session_setup",
      "hotkey_conflict", "timeout", "transient_network", "unknown", "user_report",
    ]
    return allowed.contains(label) ? label : "other"
  }

  private static let allowedIncidentExtraKeys: Set<String> = [
    "source", "mode", "hub_active",
    "turn_audio_seconds", "voiced_audio_seconds",
    "peak", "rms", "is_near_zero", "watchdog_eligible", "consecutive_silent_turns",
    "tcc_microphone_granted", "input_device_class", "recovery_action", "recovery_result",
    "osstatus", "keycode", "modifiers",
  ]

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
    // Named owners for paths that previously collapsed into `area=other` (#10425):
    // screen-capture health flap, memory device-scope, desktop update policy,
    // out-of-turn TTS, task workflow control, and auth-token storage. Keeping them
    // out of `other` lets a release-health query separate a benign screen-capture
    // flap from a genuinely degraded path.
    "screen_capture",
    "memory_scope",
    "desktop_update",
    "tts_fallback",
    "task_workflow",
    "auth_storage",
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
  /// Closed set for the realtime token-mint `phase` dimension (#10425): a release
  /// query can rely on `warm` (background pre-warm) vs `barge_in_replacement`
  /// (socket replacement during an active turn) instead of an open string.
  private static let allowedRealtimeMintPhases: Set<String> = [
    "warm",
    "barge_in_replacement",
    "other",
  ]

  private func bucketRealtimePhase(_ phase: String) -> String {
    let label = safeFallbackLabel(phase, default: "other")
    return Self.allowedRealtimeMintPhases.contains(label) ? label : "other"
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
