import Foundation

/// Prevent machine tokens in previously saved replies from rendering or being spoken.
enum LegacyReplyTokenSanitizer {
  private static let opener = "[[interject:"
  static func spokenText(from text: String) -> String {
    let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
    guard trimmed.hasPrefix(opener), let close = trimmed.range(of: "]]") else { return text }
    return trimmed[close.upperBound...].trimmingCharacters(in: .whitespacesAndNewlines)
  }
  static func displayText(from text: String) -> String {
    let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
    if trimmed.hasPrefix(opener) {
      return trimmed.range(of: "]]") == nil ? "" : spokenText(from: text)
    }
    if trimmed.count >= 3, opener.hasPrefix(trimmed) { return "" }
    return text
  }
}
