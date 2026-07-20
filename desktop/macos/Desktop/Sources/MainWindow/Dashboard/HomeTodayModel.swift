import Foundation

/// Pure composition logic for the Home greeting line and its proof sub-line.
///
/// The sub-line is the single on-canvas summary of what Omi delivered today
/// (capture status itself lives only in the header chips). Kept free of UI
/// and stores so every branch is hermetically testable.
enum HomeGreetingComposer {

  struct TodayCounts: Equatable {
    var conversations: Int?
    var memories: Int?
    var tasks: Int?
    var screens: Int?

    /// True once every source has reported (no nil left).
    var isComplete: Bool {
      conversations != nil && memories != nil && tasks != nil && screens != nil
    }

    var total: Int {
      (conversations ?? 0) + (memories ?? 0) + (tasks ?? 0) + (screens ?? 0)
    }
  }

  enum SegmentDestination: Equatable {
    case conversations
    case memories
    case tasks
    case rewind
  }

  struct Segment: Equatable {
    let text: String
    let destination: SegmentDestination?
  }

  static func greeting(name: String?, hour: Int) -> String {
    let daypart: String
    switch hour {
    case 5..<12: daypart = "Good morning"
    case 12..<18: daypart = "Good afternoon"
    default: daypart = "Good evening"
    }
    let trimmed = name?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    // "there" is the legacy signed-in-without-a-name placeholder; a bare
    // greeting reads intentional, a placeholder does not.
    guard !trimmed.isEmpty, trimmed.lowercased() != "there" else { return "\(daypart)." }
    return "\(daypart), \(trimmed)."
  }

  /// The proof sub-line. Only non-zero counts render; the morning case
  /// (nothing today yet, real history) leads with the lifetime memory instead
  /// of a row of zeros.
  static func proofSegments(
    today: TodayCounts,
    lifetimeConversations: Int?
  ) -> [Segment] {
    var segments: [Segment] = []
    if let conversations = today.conversations, conversations > 0 {
      segments.append(
        Segment(
          text: "\(conversations) conversation\(conversations == 1 ? "" : "s")",
          destination: .conversations
        ))
    }
    if let memories = today.memories, memories > 0 {
      segments.append(
        Segment(text: "\(memories) memor\(memories == 1 ? "y" : "ies")", destination: .memories))
    }
    if let tasks = today.tasks, tasks > 0 {
      segments.append(Segment(text: "\(tasks) task\(tasks == 1 ? "" : "s")", destination: .tasks))
    }
    if let screens = today.screens, screens > 0 {
      segments.append(Segment(text: "\(formattedCount(screens)) screens", destination: .rewind))
    }

    if !segments.isEmpty {
      segments.append(Segment(text: "today", destination: nil))
      return segments
    }

    if let lifetime = lifetimeConversations, lifetime > 0 {
      return [
        Segment(text: "Quiet so far today —", destination: nil),
        Segment(
          text: "\(formattedCount(lifetime)) conversation\(lifetime == 1 ? "" : "s") remembered",
          destination: .conversations
        ),
      ]
    }

    return [Segment(text: "Omi learns as you work — nothing captured yet today.", destination: nil)]
  }

  static func formattedCount(_ count: Int) -> String {
    if count >= 10_000 {
      let thousands = Double(count) / 1000.0
      return String(format: "%.0fk", thousands)
    }
    let formatter = NumberFormatter()
    formatter.numberStyle = .decimal
    return formatter.string(from: NSNumber(value: count)) ?? String(count)
  }
}

/// Quality gate for memory texts surfaced on the first-win hero.
///
/// The legacy onboarding batch import writes one memory per scanned file, so
/// "newest first" can surface a bare filename as the introduction to Omi.
/// Filter to human-readable sentences about the user.
enum FirstWinMemoryFilter {

  static func isDisplayable(_ text: String) -> Bool {
    let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
    guard trimmed.count >= 12, trimmed.count <= 240 else { return false }
    // File-path-shaped: multiple path separators or a tilde-rooted path.
    if trimmed.hasPrefix("~/") || trimmed.hasPrefix("/") { return false }
    if trimmed.components(separatedBy: "/").count > 2 { return false }
    if trimmed.components(separatedBy: "\\").count > 2 { return false }
    // A lone filename with an extension and no sentence structure.
    let wordCount = trimmed.split(whereSeparator: { $0.isWhitespace }).count
    if wordCount < 3 { return false }
    return true
  }

  static func displayable(_ texts: [String], limit: Int) -> [String] {
    var seen = Set<String>()
    var result: [String] = []
    for text in texts {
      let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
      guard isDisplayable(trimmed), seen.insert(trimmed.lowercased()).inserted else { continue }
      result.append(trimmed)
      if result.count >= limit { break }
    }
    return result
  }
}
