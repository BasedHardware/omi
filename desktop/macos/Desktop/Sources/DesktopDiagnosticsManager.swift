import Foundation
import Sentry
import Darwin

enum DesktopHealthEventName: String {
  case pttStarted = "ptt_started"
  case pttAudioCaptureSilentTurn = "ptt_audio_capture_silent_turn"
  case pttAudioCaptureWatchdogTriggered = "ptt_audio_capture_watchdog_triggered"
  case pttAudioCaptureDeviceRouteChanged = "ptt_audio_capture_device_route_changed"
  case pttCommitted = "ptt_committed"
  case realtimeTokenMintFailed = "realtime_token_mint_failed"
  case realtimeProviderExpectedIdleTeardown = "realtime_provider_expected_idle_teardown"
  case realtimeProviderPolicyClose = "realtime_provider_policy_close"
  case realtimeProviderSessionError = "realtime_provider_session_error"
}

struct DesktopHealthSnapshot {
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

private extension ISO8601DateFormatter {
  static let desktopDiagnostics: ISO8601DateFormatter = {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return formatter
  }()
}

final class DesktopDiagnosticsManager {
  static let shared = DesktopDiagnosticsManager()

  private let lock = NSLock()
  private var snapshots: [DesktopHealthSnapshot] = []
  private let snapshotLimit = 150
  private var consecutiveNearZeroPTTTurns = 0
  private var lastPTTWatchdogIncidentAt: Date?
  private let pttWatchdogThreshold = 3
  private let pttWatchdogDedupWindow: TimeInterval = 15 * 60
  private let pttWatchdogMinimumAudioSeconds: Double = 0.35

  private init() {}

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

  func recordPTTDeviceRouteChanged(recoveryAction: String, recoveryResult: String) {
    record(
      .pttAudioCaptureDeviceRouteChanged,
      properties: [
        "recovery_action": recoveryAction,
        "recovery_result": recoveryResult,
      ])
  }

  func recordRealtimeTokenMintFailed(
    provider: String,
    reason: String,
    phase: String,
    httpStatusCode: Int? = nil
  ) {
    var properties: [String: Any] = [
      "provider": safeProvider(provider),
      "reason": reason,
      "phase": phase,
    ]
    if let httpStatusCode {
      properties["http_status_code"] = httpStatusCode
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

  #if DEBUG
  func resetForTests() {
    lock.lock()
    snapshots.removeAll()
    consecutiveNearZeroPTTTurns = 0
    lastPTTWatchdogIncidentAt = nil
    lock.unlock()
  }
  #endif

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
    return String(cString: model)
  }
}
