import Foundation

enum InterjectReplyHint {
  /// "hold ⌥ to reply" from the user's actual PTT shortcut tokens.
  static func text(tokens: [String]) -> String {
    let shortcut = tokens.joined()
    if shortcut.isEmpty {
      return "hold Option to reply"
    }
    return "hold \(shortcut) to reply"
  }

  static func listeningChip(title: String) -> String {
    let trimmed = title.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return "replying to the last card" }
    return "replying to: \(trimmed)"
  }
}
