import Foundation

/// Copy policy for the one chat row a proactive notification journals into.
extension FloatingControlBarManager {
  /// The director's copy contract (5a076e10b3) makes the title AND the message both
  /// name the same specific referent — measured as the only shape that keeps each
  /// field useful on its own surface. Journaled together into one chat row, that
  /// contract reads as saying everything twice ("Latest Omi desktop app download
  /// link" / "The latest Omi desktop app download link is …"), so the headline is
  /// kept only when it adds words the body does not already carry.
  nonisolated static func notificationJournalText(title: String, body: String) -> String {
    let headline = title.trimmingCharacters(in: .whitespacesAndNewlines)
    let detail = body.trimmingCharacters(in: .whitespacesAndNewlines)
    if headline.isEmpty { return detail }
    if detail.isEmpty || detail == headline { return headline }
    if bodyRestatesTitle(title: headline, body: detail) { return detail }
    return "\(headline)\n\(detail)"
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
