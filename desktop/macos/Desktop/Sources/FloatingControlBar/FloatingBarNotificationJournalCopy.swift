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
  /// as restating it. A title contributing even one new token keeps its own line.
  nonisolated static func bodyRestatesTitle(title: String, body: String) -> Bool {
    let titleTokens = copyTokens(title)
    guard !titleTokens.isEmpty else { return true }
    let bodyTokens = Set(copyTokens(body))
    return titleTokens.allSatisfy(bodyTokens.contains)
  }

  private nonisolated static func copyTokens(_ text: String) -> [String] {
    text.lowercased()
      .components(separatedBy: CharacterSet.alphanumerics.inverted)
      .filter { !$0.isEmpty }
  }
}
