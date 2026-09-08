import Foundation

/// Produces a presentation-only transcript for agent lifecycle receipts.
///
/// The kernel's session, run, and pill identifiers remain in structured blocks
/// for lifecycle linking and recovery. They are implementation details, though,
/// so they must not also leak through an assistant's free-form launch prose.
enum AgentLifecycleTranscriptProjection {
  static func project(_ message: ChatMessage) -> ChatMessage {
    guard message.sender == .ai else { return message }

    let identifiers = internalIdentifiers(in: message.contentBlocks)
    let hasLifecycleReceipt = message.contentBlocks.contains { block in
      switch block {
      case .agentSpawn, .agentCompletion:
        return true
      default:
        return false
      }
    }
    guard hasLifecycleReceipt else { return message }

    let hasSpawnReceipt = message.contentBlocks.contains { block in
      if case .agentSpawn = block { return true }
      return false
    }
    var projected = message
    projected.text = visibleText(
      message.text,
      identifiers: identifiers,
      hasSpawnReceipt: hasSpawnReceipt
    )
    projected.contentBlocks = message.contentBlocks.map { block in
      guard case .text(let id, let text) = block else { return block }
      return .text(
        id: id,
        text: visibleText(
          text,
          identifiers: identifiers,
          hasSpawnReceipt: hasSpawnReceipt
        )
      )
    }
    return projected
  }

  /// Removes a duplicate launch paragraph only when the message already has a
  /// structured spawn receipt. In all other prose, only exact, known internal
  /// identifiers are removed; user text and arbitrary code are not pattern
  /// matched or rewritten.
  static func visibleText(
    _ text: String,
    identifiers: Set<String>,
    hasSpawnReceipt: Bool
  ) -> String {
    guard !text.isEmpty else { return text }

    return
      text
      .components(separatedBy: "\n\n")
      .compactMap { paragraph -> String? in
        if hasSpawnReceipt, isReceiptOnlySpawnAnnouncement(paragraph) {
          return nil
        }
        return redactExactIdentifiers(in: paragraph, identifiers: identifiers)
      }
      .joined(separator: "\n\n")
      .trimmingCharacters(in: .whitespacesAndNewlines)
  }

  private static func internalIdentifiers(in blocks: [ChatContentBlock]) -> Set<String> {
    var identifiers = Set<String>()
    for block in blocks {
      switch block {
      case .agentSpawn(_, let pillID, let sessionID, let runID, _, _, _):
        insert(runID, into: &identifiers)
        insert(sessionID, into: &identifiers)
        if let pillID { identifiers.insert(pillID.uuidString) }
      case .agentCompletion(_, let pillID, let sessionID, let runID, _, _, _, _):
        insert(runID, into: &identifiers)
        insert(sessionID, into: &identifiers)
        if let pillID { identifiers.insert(pillID.uuidString) }
      default:
        continue
      }
    }
    return identifiers
  }

  private static func insert(_ value: String?, into identifiers: inout Set<String>) {
    let trimmed = value?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    guard !trimmed.isEmpty else { return }
    identifiers.insert(trimmed)
  }

  /// Keep a complete paragraph only when it is solely the redundant launch
  /// receipt. Model output can append a useful result to the same paragraph,
  /// and hiding that result would make the projection lossy.
  private static func isReceiptOnlySpawnAnnouncement(_ text: String) -> Bool {
    let lowercased = text.lowercased()
    let explicitLaunchPhrases = [
      "subagent spawned",
      "sub-agent spawned",
      "agent spawned",
      "started a subagent",
      "started a sub-agent",
      "launched a subagent",
      "launched a sub-agent",
      "spun up a subagent",
      "spun up a sub-agent",
    ]
    let isLaunchAnnouncement =
      explicitLaunchPhrases.contains(where: { lowercased.contains($0) })
      || (lowercased.contains("floating pill")
        && (lowercased.contains("running") || lowercased.contains("spawn")))
    guard isLaunchAnnouncement else { return false }

    // This deliberately errs on showing some redundant wording over ever
    // dropping a real result. The known lifecycle phrases do not contain
    // any of these result signals.
    let resultSignals = [
      "result:", "answer:", "found ", "returned ", "output:",
      "summary:", "reply:", "responded ", "produced ",
    ]
    return !resultSignals.contains(where: { lowercased.contains($0) })
  }

  private static func redactExactIdentifiers(in text: String, identifiers: Set<String>) -> String {
    identifiers
      .sorted { $0.count > $1.count }
      .reduce(text) { result, identifier in
        result
          .replacingOccurrences(
            of: "(\(identifier))",
            with: "",
            options: .caseInsensitive
          )
          .replacingOccurrences(
            of: identifier,
            with: "",
            options: .caseInsensitive
          )
      }
  }
}
