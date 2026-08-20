import Foundation

enum ProactiveNotificationKind: String, Equatable {
  case general
  case suggestion
  case insight
  case task
  case memory
  case goal
  case meetingNotes = "meeting_notes"
  case resurface
  case integration

  static func from(decisionType: String) -> Self {
    switch decisionType {
    // Director "suggest" decisions are generic tips, which the user-facing taxonomy
    // files under Insight; `.suggestion` is reserved for the focus-nudge assistant.
    case "suggest": return .insight
    case "insight": return .insight
    case "task_candidate": return .task
    case "resurface": return .resurface
    default: return .general
    }
  }

  static func from(assistantId: String) -> Self {
    switch assistantId {
    case "suggestion": return .suggestion
    case "insight": return .insight
    case "task": return .task
    case "memory-extraction": return .memory
    case "goals": return .goal
    case "meeting-notes": return .meetingNotes
    case "integration_connect": return .integration
    default: return .general
    }
  }
}

/// Pure INV-6 continuity helpers — prefer these over ad-hoc UI string/resource logic.
/// Behavioral tests call these APIs; source tripwires guard forbidden dual-write patterns.
enum ChatContinuityInvariants {
  /// Every proactive notification enters the transcript under this continuity
  /// key (INV-6 rule 5, origin `proactive_notification`). It is written by
  /// `FloatingControlBarManager.persistNotificationMessageIfNeeded`, journaled
  /// into turn metadata, and read back as `ChatMessage.clientTurnId` — so it is
  /// the one piece of structured identity that survives a reload and says a turn
  /// was unprompted. The renderer must ask here rather than guess from position:
  /// "assistant row with no user row above it" is also true of the second block
  /// of an ordinary turn.
  static let proactiveNotificationContinuityKeyPrefix = "notification:"

  static func proactiveNotificationContinuityKey(id: UUID) -> String {
    "\(proactiveNotificationContinuityKeyPrefix)\(id.uuidString)"
  }

  static func proactiveNotificationContinuityKey(id: UUID, kind: ProactiveNotificationKind) -> String {
    guard kind != .general else { return proactiveNotificationContinuityKey(id: id) }
    return "\(proactiveNotificationContinuityKeyPrefix)\(kind.rawValue):\(id.uuidString)"
  }

  static func isProactiveNotification(_ message: ChatMessage) -> Bool {
    guard message.sender != .user, let key = message.clientTurnId else { return false }
    return key.hasPrefix(proactiveNotificationContinuityKeyPrefix)
  }

  static func proactiveNotificationKind(_ message: ChatMessage) -> ProactiveNotificationKind? {
    guard isProactiveNotification(message), let key = message.clientTurnId else { return nil }
    let suffix = key.dropFirst(proactiveNotificationContinuityKeyPrefix.count)
    guard let separator = suffix.firstIndex(of: ":") else { return .general }
    return ProactiveNotificationKind(rawValue: String(suffix[..<separator])) ?? .general
  }

  /// Collapsed agent-card / list header preview prefers the prompt/objective.
  /// Response output belongs in the expanded body, not the one-line preview.
  static func agentPreviewText(prompt: String, output: String) -> String {
    let promptTrimmed = prompt.trimmingCharacters(in: .whitespacesAndNewlines)
    if !promptTrimmed.isEmpty {
      return promptTrimmed
    }
    return output.trimmingCharacters(in: .whitespacesAndNewlines)
  }

  /// Keep compact agent cards from repeating the objective when a generated
  /// title already embeds it (for example, "Delegated: <objective>").
  static func agentCardPreviewText(title: String, prompt: String, output: String) -> String {
    let preview = agentPreviewText(prompt: prompt, output: output)
    guard !preview.isEmpty else { return "" }
    let normalizedTitle = title.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    let normalizedPreview = preview.lowercased()
    return normalizedTitle.hasSuffix(normalizedPreview) ? "" : preview
  }

  /// Floating/notch viewport may only surface resources owned by viewport message ids.
  /// Historical timeline resources outside the cursor must not appear as orphans.
  static func resourcesBelongingToMessages(
    messages: [ChatMessage],
    messageIds: Set<String>
  ) -> [ChatResource] {
    guard !messageIds.isEmpty else { return [] }
    var seen = Set<String>()
    var resources: [ChatResource] = []
    for message in messages where messageIds.contains(message.id) {
      for resource in message.displayResources where seen.insert(resource.id).inserted {
        resources.append(resource)
      }
    }
    return resources
  }
}
