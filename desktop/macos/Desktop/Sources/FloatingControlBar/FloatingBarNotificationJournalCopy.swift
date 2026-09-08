import Foundation

/// Copy policy for proactive notifications across the floating-bar card and the
/// one chat row they journal into.
///
/// Two independent redundancies showed up live:
/// 1. The director's title/body contract names the same referent twice
///    (`notificationJournalText` already drops a headline the body restates).
/// 2. Several producers use the Settings category as the title (`Focus`,
///    `Insight`, `Memory Saved`). The chat row already prints that category as
///    `ProactiveNotificationBadge.label`, so journaling it as a first line made
///    the row say "Focus / Focus / meet with…".
enum ProactiveNotificationCopy {
  /// Headlines that only name the Settings category (or a known alias). The
  /// chat badge already carries that word; keeping it as a title is chrome.
  static func isCategoryChrome(_ text: String, kind: ProactiveNotificationKind? = nil) -> Bool {
    let normalized = normalizeHeadline(text)
    guard !normalized.isEmpty else { return true }
    if let kind {
      return chromeHeadlines(for: kind).contains(normalized)
    }
    return allChromeHeadlines.contains(normalized)
  }

  /// The body a chat row should render under the category badge. Strips a
  /// journaled first line that is only category chrome, and kind-specific
  /// prefixes such as `New memory:`, so already-persisted history is repaired
  /// without rewriting the journal.
  static func displayBody(_ text: String, kind: ProactiveNotificationKind) -> String {
    let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return trimmed }
    let parts = splitFirstLine(trimmed)
    var body = trimmed
    if isCategoryChrome(parts.first, kind: kind) {
      body = parts.rest
    }
    body = stripBodyChrome(body, kind: kind)
    return body.isEmpty ? trimmed : body
  }

  /// Body prefixes that only restated the category. Applied both when journaling
  /// and when rendering already-journaled rows.
  static func stripBodyChrome(_ text: String, kind: ProactiveNotificationKind) -> String {
    var result = text.trimmingCharacters(in: .whitespacesAndNewlines)
    switch kind {
    case .memory:
      result = stripPrefix(result, "new memory:")
    default:
      break
    }
    return result
  }

  /// Lines the generic floating-bar card should draw. A category-only title
  /// becomes a quiet caption so the actual content is the heading, matching the
  /// Focus suggestion card and the meeting-share card.
  struct CardLines: Equatable {
    let caption: String?
    let heading: String
    let detail: String?
    let systemImage: String

    static func of(title: String, message: String, kind: ProactiveNotificationKind) -> Self {
      let badge = ProactiveNotificationBadge(kind: kind)
      let headline = title.trimmingCharacters(in: .whitespacesAndNewlines)
      let body = ProactiveNotificationCopy.stripBodyChrome(
        message.trimmingCharacters(in: .whitespacesAndNewlines), kind: kind)

      if ProactiveNotificationCopy.isCategoryChrome(headline, kind: kind) {
        if body.isEmpty {
          return Self(
            caption: nil,
            heading: headline.isEmpty ? badge.label : headline,
            detail: nil,
            systemImage: badge.systemImage)
        }
        return Self(caption: badge.label, heading: body, detail: nil, systemImage: badge.systemImage)
      }

      let heading = headline.isEmpty ? body : headline
      let detail = (body.isEmpty || body == heading) ? nil : body
      return Self(caption: nil, heading: heading, detail: detail, systemImage: badge.systemImage)
    }
  }

  fileprivate static func chromeHeadlines(for kind: ProactiveNotificationKind) -> Set<String> {
    switch kind {
    case .suggestion:
      return ["focus", "suggestion", "suggested by omi"]
    case .insight, .resurface:
      return ["insight"]
    case .goal:
      return ["insight", "new goal"]
    case .task, .meetingNotes:
      return ["task"]
    case .memory:
      return ["memory", "memory saved"]
    case .integration:
      return ["integration"]
    case .general, .functional, .trial, .onboarding, .dailyRecap:
      return ["notification"]
    }
  }

  private static let allChromeHeadlines: Set<String> = {
    var all = Set<String>()
    for kind in ProactiveNotificationKind.allCases {
      all.formUnion(chromeHeadlines(for: kind))
    }
    return all
  }()

  static func normalizeHeadline(_ text: String) -> String {
    var value = text.trimmingCharacters(in: .whitespacesAndNewlines)
    while let first = value.first, "#*_`".contains(first) {
      value.removeFirst()
      value = value.trimmingCharacters(in: .whitespacesAndNewlines)
    }
    while let last = value.last, "*_`".contains(last) {
      value.removeLast()
      value = value.trimmingCharacters(in: .whitespacesAndNewlines)
    }
    return value.lowercased()
      .split(whereSeparator: \.isWhitespace)
      .joined(separator: " ")
  }

  private static func splitFirstLine(_ text: String) -> (first: String, rest: String) {
    guard let newline = text.firstIndex(of: "\n") else {
      return (text, "")
    }
    let first = String(text[..<newline]).trimmingCharacters(in: .whitespacesAndNewlines)
    let rest = String(text[text.index(after: newline)...])
      .trimmingCharacters(in: .whitespacesAndNewlines)
    return (first, rest)
  }

  private static func stripPrefix(_ text: String, _ prefix: String) -> String {
    guard text.lowercased().hasPrefix(prefix) else { return text }
    return String(text.dropFirst(prefix.count)).trimmingCharacters(in: .whitespacesAndNewlines)
  }
}

/// Copy policy for the one chat row a proactive notification journals into.
extension FloatingControlBarManager {
  /// The director's copy contract (5a076e10b3) makes the title AND the message both
  /// name the same specific referent — measured as the only shape that keeps each
  /// field useful on its own surface. Journaled together into one chat row, that
  /// contract reads as saying everything twice ("Latest Omi desktop app download
  /// link" / "The latest Omi desktop app download link is …"), so the headline is
  /// kept only when it adds words the body does not already carry.
  ///
  /// A second, later redundancy: several producers used the Settings category as
  /// the title (`Focus`, `Insight`, `Memory Saved`). The chat row already draws
  /// that category as a badge, so a category-only title is dropped the same way.
  nonisolated static func notificationJournalText(
    title: String, body: String, kind: ProactiveNotificationKind? = nil
  ) -> String {
    let headline = title.trimmingCharacters(in: .whitespacesAndNewlines)
    var detail = body.trimmingCharacters(in: .whitespacesAndNewlines)
    if let kind {
      detail = ProactiveNotificationCopy.stripBodyChrome(detail, kind: kind)
    }
    if headline.isEmpty { return detail }
    if ProactiveNotificationCopy.isCategoryChrome(headline, kind: kind) {
      return detail.isEmpty ? headline : detail
    }
    if detail.isEmpty || detail == headline { return headline }
    if bodyRestatesTitle(title: headline, body: detail) { return detail }
    return "\(headline)\n\(detail)"
  }

  /// Body a chat-history row should render under the category badge. Historical
  /// rows already contain a redundant first line; this repairs them without a
  /// journal rewrite.
  nonisolated static func chatDisplayText(_ text: String, kind: ProactiveNotificationKind) -> String {
    ProactiveNotificationCopy.displayBody(text, kind: kind)
  }

  /// Lines the generic floating-bar card should draw for this title/message/kind.
  nonisolated static func notificationCardCopy(
    title: String, message: String, kind: ProactiveNotificationKind
  ) -> ProactiveNotificationCopy.CardLines {
    .of(title: title, message: message, kind: kind)
  }

  /// Whether every content-bearing token of the title already appears in the body,
  /// compared case-insensitively with punctuation (smart quotes, dashes, commas)
  /// stripped — so a body that quotes, inflects, or reorders the title still counts
  /// as restating it. Function words are ignored on both sides: live beta rows
  /// ("Latest Omi desktop link for David at scalingforever.com" over a body that
  /// says the same thing with "to" instead of "for"/"at") kept their redundant
  /// headline because a preposition was the title's only "novel" token. A title
  /// contributing even one new CONTENT token keeps its own line.
  nonisolated static func bodyRestatesTitle(title: String, body: String) -> Bool {
    let titleTokens = copyTokens(title).filter { !Self.functionWords.contains($0) }
    guard !titleTokens.isEmpty else { return true }
    let bodyTokens = Set(copyTokens(body))
    return titleTokens.allSatisfy(bodyTokens.contains)
  }

  /// English function words that carry no referent of their own. Deliberately
  /// small: an over-broad list would let a title that genuinely adds meaning
  /// ("draft FOR the board" vs a body about a different draft) be swallowed.
  private nonisolated static let functionWords: Set<String> = [
    "a", "an", "the", "for", "to", "at", "of", "in", "on", "with", "and", "or",
    "is", "are", "was", "were", "be", "your", "you", "it", "its", "this", "that",
    "from", "by", "about", "into", "as",
  ]

  private nonisolated static func copyTokens(_ text: String) -> [String] {
    text.lowercased()
      .components(separatedBy: CharacterSet.alphanumerics.inverted)
      .filter { !$0.isEmpty }
  }
}
