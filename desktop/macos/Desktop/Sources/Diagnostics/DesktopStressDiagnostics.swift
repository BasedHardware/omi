import Foundation

enum DesktopStressScenario: String, CaseIterable, Codable {
  case pttVoiced = "ptt_voiced"
  case pttSilent = "ptt_silent"
  case chatBridge = "chat_bridge"
  case subagentLaunch = "subagent_launch"
}

enum DesktopStressTerminalReason: String, CaseIterable, Codable {
  case pttVoicedSuccess = "ptt_voiced_success"
  case pttSilentRejected = "ptt_silent_rejected"
  case chatBridgeSuccess = "chat_bridge_success"
  case subagentLaunchSuccess = "subagent_launch_success"
  case tooShortTap = "too_short_tap"
  case audioFramesMissing = "audio_frames_missing"
  case silentAudio = "silent_audio"
  case realtimeTokenMintFailure = "realtime_token_mint_failure"
  case providerFallback = "provider_fallback"
  case bridgeLaunchFailure = "bridge_launch_failure"
  case responseAlreadyRunning = "response_already_running"
  case voiceOutputOverlap = "voice_output_overlap"
  case realtimeNoResponseTimeout = "realtime_no_response_timeout"
  case deferredCommitTimeout = "deferred_commit_timeout"
  case bargeInReplacementTimeout = "barge_in_replacement_timeout"
  case staleProviderAudioAfterInterrupt = "stale_provider_audio_after_interrupt"

  var isReleaseGateFailure: Bool {
    switch self {
    case .pttVoicedSuccess, .pttSilentRejected, .chatBridgeSuccess, .subagentLaunchSuccess, .providerFallback:
      return false
    case .tooShortTap, .audioFramesMissing, .silentAudio, .realtimeTokenMintFailure,
      .bridgeLaunchFailure, .responseAlreadyRunning, .voiceOutputOverlap,
      .realtimeNoResponseTimeout, .deferredCommitTimeout, .bargeInReplacementTimeout,
      .staleProviderAudioAfterInterrupt:
      return true
    }
  }
}

struct DesktopStressDiagnosticEvent: Codable, Equatable {
  let runID: String
  let iteration: Int
  let scenario: DesktopStressScenario
  let terminalReason: DesktopStressTerminalReason
  let timestamp: String
  let durationMs: Int?
  let details: [String: String]

  enum CodingKeys: String, CodingKey {
    case runID = "run_id"
    case iteration
    case scenario
    case terminalReason = "terminal_reason"
    case timestamp
    case durationMs = "duration_ms"
    case details
  }

  init(
    runID: String,
    iteration: Int,
    scenario: DesktopStressScenario,
    terminalReason: DesktopStressTerminalReason,
    timestamp: String = DesktopStressDiagnosticEvent.currentTimestamp(),
    durationMs: Int? = nil,
    details: [String: String] = [:]
  ) {
    self.runID = runID
    self.iteration = iteration
    self.scenario = scenario
    self.terminalReason = terminalReason
    self.timestamp = timestamp
    self.durationMs = durationMs
    self.details = details
  }

  static func currentTimestamp() -> String {
    ISO8601DateFormatter.desktopStressDiagnostics.string(from: Date())
  }
}

struct DesktopStressRunSummary: Codable, Equatable {
  let totalEvents: Int
  let passedReleaseGate: Bool
  let terminalReasonCounts: [String: Int]
  let scenarioCounts: [String: Int]
  let forbiddenTerminalReasons: [String]

  enum CodingKeys: String, CodingKey {
    case totalEvents = "total_events"
    case passedReleaseGate = "passed_release_gate"
    case terminalReasonCounts = "terminal_reason_counts"
    case scenarioCounts = "scenario_counts"
    case forbiddenTerminalReasons = "forbidden_terminal_reasons"
  }

  init(events: [DesktopStressDiagnosticEvent]) {
    let terminalCounts = Dictionary(grouping: events, by: { $0.terminalReason.rawValue })
      .mapValues { $0.count }
    let scenarios = Dictionary(grouping: events, by: { $0.scenario.rawValue })
      .mapValues { $0.count }
    let forbidden = DesktopStressTerminalReason.allCases.filter {
      ($0.isReleaseGateFailure) && (terminalCounts[$0.rawValue, default: 0] > 0)
    }.map {
      $0.rawValue
    }

    totalEvents = events.count
    terminalReasonCounts = terminalCounts
    scenarioCounts = scenarios
    forbiddenTerminalReasons = forbidden
    passedReleaseGate = !events.isEmpty && forbiddenTerminalReasons.isEmpty
  }
}

extension ISO8601DateFormatter {
  fileprivate nonisolated(unsafe) static let desktopStressDiagnostics: ISO8601DateFormatter = {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return formatter
  }()
}
