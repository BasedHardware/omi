import Foundation

enum AgentFailureTranscriptFormatter {
  static func errorText(for projection: AgentRunProjection) -> String? {
    switch projection.status {
    case .failed, .timedOut, .orphaned:
      return projection.failure?.displayMessage
        ?? projection.errorMessage
        ?? projection.statusText
        ?? "Agent failed"
    case .idle, .queued, .starting, .running, .waitingInput, .waitingApproval, .cancelling, .succeeded, .cancelled:
      return nil
    }
  }

  static func transcriptText(for errorText: String) -> String? {
    let trimmed = errorText.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return nil }
    if trimmed.lowercased().hasPrefix("failed:") {
      return trimmed
    }
    return "Failed: \(trimmed)"
  }
}
