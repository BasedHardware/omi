import Foundation

enum ProactiveNotificationKind: String, Equatable, CaseIterable {
  /// **Decode-only.** Historical rows were journaled under a bare
  /// `notification:<uuid>` key, which reads back as this. No producer may pass
  /// it: `showNotification` requires an explicit kind, and a card with no
  /// category of its own is `.functional`, not "Notification".
  case general
  /// A system notice that is not a proactive observation — screen-recording
  /// reset, a support reply, an onboarding test ping. It is ungated by the five
  /// category toggles, exactly as `.general` was.
  case functional
  /// Trial/plan messaging. Never journaled: it is product copy about billing,
  /// not something Omi observed.
  case trial
  /// First-run permission help. Never journaled, for the same reason.
  case onboarding
  /// The daily recap's once-a-day announcement. Never journaled: the recap's
  /// transcript presence is the dedicated `ChatDailyRecapRow` day boundary, and
  /// INV-CHAT-1 makes the recap chrome rather than a turn — a journaled bell
  /// card would be a second, degraded copy (title truncated, no day stats) of
  /// a row the transcript already renders.
  case dailyRecap = "daily_recap"
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
    // The JIT ambient lane's focus nudge replaces the legacy focus-nudge assistant
    // and keeps its badge and Settings toggle.
    case "focus_nudge": return .suggestion
    case "insight": return .insight
    case "task_candidate": return .task
    case "resurface": return .resurface
    // An unrecognised director decision is a system notice, not an
    // uncategorised observation: `.general` is decode-only.
    default: return .functional
    }
  }

  static func from(assistantId: String) -> Self {
    switch assistantId {
    case "suggestion": return .suggestion
    case "insight": return .insight
    case "task", "context_reminder": return .task
    case "memory-extraction": return .memory
    case "goals": return .goal
    case "meeting-notes": return .meetingNotes
    case "integration_connect": return .integration
    case "trial": return .trial
    case "onboarding": return .onboarding
    case "daily_recap": return .dailyRecap
    default: return .functional
    }
  }

  /// Kinds whose cards are presentation only and must never enter the chat
  /// journal. See `FloatingControlBarManager.persistNotificationMessageIfNeeded`.
  var isJournaled: Bool {
    switch self {
    case .trial, .onboarding, .dailyRecap: return false
    case .general, .functional, .suggestion, .insight, .task, .memory, .goal, .meetingNotes,
      .resurface, .integration:
      return true
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
    // `.general` is decode-only and unreachable from a producer, so this branch
    // exists to keep the historical bare key round-tripping, never to mint one.
    guard kind != .general else { return proactiveNotificationContinuityKey(id: id) }
    return "\(proactiveNotificationContinuityKeyPrefix)\(kind.rawValue):\(id.uuidString)"
  }

  static func isProactiveNotification(_ message: ChatMessage) -> Bool {
    guard message.sender != .user, let key = message.clientTurnId else { return false }
    return key.hasPrefix(proactiveNotificationContinuityKeyPrefix)
  }

  /// Last UUID segment of `notification:` / `notification:<kind>:<uuid>`.
  static func notificationID(fromContinuityKey key: String?) -> UUID? {
    guard let key, key.hasPrefix(proactiveNotificationContinuityKeyPrefix) else { return nil }
    let suffix = key.dropFirst(proactiveNotificationContinuityKeyPrefix.count)
    let raw: Substring
    if let separator = suffix.lastIndex(of: ":") {
      raw = suffix[suffix.index(after: separator)...]
    } else {
      raw = suffix
    }
    return UUID(uuidString: String(raw))
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
