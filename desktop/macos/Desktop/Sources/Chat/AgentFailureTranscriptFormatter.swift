import Foundation

enum AgentFailureTranscriptFormatter {
  static let genericSpawnFailure = "Agent couldn't start — check OpenClaw setup"

  static func errorText(for projection: AgentRunProjection) -> String? {
    switch projection.status {
    case .failed, .timedOut, .orphaned:
      let raw =
        projection.failure?.displayMessage
        ?? projection.errorMessage
        ?? projection.statusText
        ?? "Agent failed"
      return userFacingFailure(raw, harnessMode: harnessMode(from: projection))
    case .idle, .queued, .starting, .running, .waitingInput, .waitingApproval, .cancelling, .succeeded, .cancelled:
      return nil
    }
  }

  static func transcriptText(for errorText: String) -> String? {
    let trimmed = errorText.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return nil }
    let sanitized = userFacingFailure(trimmed, harnessMode: nil)
    if sanitized.lowercased().hasPrefix("failed:") {
      return sanitized
    }
    return "Failed: \(sanitized)"
  }

  /// Strip HTTP/URLSession guts; map missing OpenClaw/Hermes adapters to setup copy.
  static func userFacingFailure(
    _ errorText: String,
    harnessMode: AgentHarnessMode? = nil,
    directedProvider: AgentPillsManager.DirectedProvider? = nil
  ) -> String {
    let trimmed = errorText.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return genericSpawnFailure }

    if looksLikeSetupNeeded(trimmed) {
      if let directedProvider {
        return directedProvider.setupNeededStatus
      }
      if let harnessMode {
        switch harnessMode {
        case .openclaw: return AgentPillsManager.DirectedProvider.openclaw.setupNeededStatus
        case .hermes: return AgentPillsManager.DirectedProvider.hermes.setupNeededStatus
        case .codex: return AgentPillsManager.DirectedProvider.codex.setupNeededStatus
        default: break
        }
      }
      let lower = trimmed.lowercased()
      if lower.contains("hermes") {
        return AgentPillsManager.DirectedProvider.hermes.setupNeededStatus
      }
      if lower.contains("openclaw") || lower.contains("open claw") {
        return AgentPillsManager.DirectedProvider.openclaw.setupNeededStatus
      }
      if lower.contains("codex") {
        return AgentPillsManager.DirectedProvider.codex.setupNeededStatus
      }
      return genericSpawnFailure
    }

    if looksLikeRawTransportGuts(trimmed) {
      return genericSpawnFailure
    }

    // Prefer short, non-technical copy already authored for the UI.
    if trimmed.count <= 120,
      !trimmed.contains("http"),
      !trimmed.contains("URLSession"),
      !trimmed.contains("NSURLError")
    {
      return trimmed
    }
    return genericSpawnFailure
  }

  static func userFacingFailure(
    for error: Error,
    harnessMode: AgentHarnessMode? = nil,
    directedProvider: AgentPillsManager.DirectedProvider? = nil
  ) -> String {
    if let runtime = error as? BridgeError, case .agentRuntimeFailure(let failure) = runtime {
      let inferred = harnessModeFromAdapterId(failure.adapterId)
      return userFacingFailure(
        failure.displayMessage,
        harnessMode: harnessMode ?? inferred,
        directedProvider: directedProvider)
    }
    let raw = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
    return userFacingFailure(raw, harnessMode: harnessMode, directedProvider: directedProvider)
  }

  private static func looksLikeSetupNeeded(_ text: String) -> Bool {
    let lower = text.lowercased()
    if lower.contains("needs setup") { return true }
    if lower.contains("omi_openclaw_adapter") || lower.contains("omi_hermes_adapter") || lower.contains("omi_codex_adapter") { return true }
    if lower.contains("adapter")
      && (lower.contains("missing") || lower.contains("unavailable") || lower.contains("not found")
        || lower.contains("not configured") || lower.contains("no such file"))
    {
      return true
    }
    if (lower.contains("openclaw") || lower.contains("hermes") || lower.contains("codex"))
      && (lower.contains("not found") || lower.contains("not installed")
        || lower.contains("not configured") || lower.contains("no such file"))
    {
      return true
    }
    return false
  }

  private static func looksLikeRawTransportGuts(_ text: String) -> Bool {
    let lower = text.lowercased()
    return lower.contains("urlsession")
      || lower.contains("nsurlerror")
      || lower.contains("http://")
      || lower.contains("https://")
      || lower.contains("(-1001)")
      || lower.contains("(-1009)")
      || lower.contains("status code")
      || lower.contains("task failed")
  }

  private static func harnessMode(from projection: AgentRunProjection) -> AgentHarnessMode? {
    if let adapterId = projection.failure?.adapterId {
      return harnessModeFromAdapterId(adapterId)
    }
    return nil
  }

  private static func harnessModeFromAdapterId(_ adapterId: String?) -> AgentHarnessMode? {
    guard let adapterId else { return nil }
    return AgentRuntimeRouting.harnessMode(from: adapterId)
  }
}
