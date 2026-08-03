import Foundation

/// The cohort Conversations destination is a strict Omi-device archive, not
/// a general conversation browser. A task can refer to a desktop or phone
/// conversation too, so the link is present only for the one task provenance
/// that is known to resolve inside that archive. Unknown provenance fails
/// closed instead of exposing a misleading destination.
enum ChatFirstCaptureLinkPolicy {
  static func captureID(for task: TaskActionItem) -> String? {
    guard task.source == "transcription:omi",
      let conversationID = task.conversationId
    else { return nil }

    let normalized = conversationID.trimmingCharacters(in: .whitespacesAndNewlines)
    return normalized.isEmpty ? nil : normalized
  }
}
