import Foundation

/// The single identity normalizer for visit detection, bucket lookup, task dedupe,
/// suggestion grounding, and contextual resurfacing. Raw titles remain stored next
/// to this value; this representation is only an identity lookup key.
enum ContextTitleNormalizer {
  static func normalize(_ title: String?, appName: String? = nil) -> String? {
    guard var result = title?.trimmingCharacters(in: .whitespacesAndNewlines), !result.isEmpty else {
      return nil
    }

    result = result.unicodeScalars.filter { !($0.value >= 0x2800 && $0.value <= 0x28FF) }
      .reduce(into: "") { $0.append(String($1)) }
    let progressCharacters: Set<Character> = [
      "✳", "↻", "◐", "◑", "◒", "◓", "◴", "◷", "◶", "◵", "◰", "◳", "◲", "◱",
      "▖", "▘", "▝", "▗",
    ]
    result = String(result.filter { !progressCharacters.contains($0) })
    result = replacing(#"\b\d{1,2}:\d{2}(:\d{2})?\b"#, in: result)
    result = replacing(#"\b\d+[×x]\d+\b"#, in: result)

    let app = appName?.lowercased() ?? ""
    let isMessagingApp =
      app.contains("telegram") || app.contains("slack") || app.contains("discord")
    let isBrowser =
      app.contains("chrome") || app.contains("safari") || app.contains("firefox")
      || app.contains("arc") || app.contains("edge") || app.contains("brave")
      || app.contains("vivaldi") || app.contains("opera")

    if isMessagingApp || isBrowser {
      // A *leading* `(4) ` is the web unread badge, never identity: `(4) Home / X`
      // and `Home / X` are one page. Titles do not otherwise begin with a bare
      // parenthesized number, so this stays safe outside messaging apps — unlike
      // the trailing form below, where `Issue (123)` is genuinely identity.
      result = replacing(#"^\s*\(\d+\)\s*"#, in: result)
      result = replacing(#"^\s*\[\d+\]\s*"#, in: result)
    }
    if isMessagingApp {
      // Messaging apps append unread counts to the conversation title. Keep this
      // app-scoped: `(123)` in a document title is identity, not cosmetic noise.
      result = replacing(#"\s*\(\d+\)\s*$"#, in: result)
      result = replacing(#"\s*\[\d+\]\s*$"#, in: result)
      // `item(s)` covers Slack's web title, which reads "- 1 new item" rather
      // than "- 1 new message" and so never matched the original pattern.
      result = replacing(#"\s*[-–—]\s*\d+\s+(new\s+)?(messages?|items?)\s*$"#, in: result)
    }
    if app.contains("terminal") || app.contains("iterm") || app.contains("warp") {
      result = replacing(#"\s+[-–—]\s+(zsh|bash|fish)\s*$"#, in: result)
    }

    result = replacing(#"\s+"#, in: result, with: " ")
      .trimmingCharacters(in: .whitespacesAndNewlines)
    return result.isEmpty ? nil : result
  }

  /// Returns nil when the title normalizes to blank/noise-only so untitled windows of the
  /// same app never share a colliding `"app::"` identity or reference hash.
  static func identityKey(appName: String, windowTitle: String?) -> String? {
    guard let normalized = normalize(windowTitle, appName: appName) else { return nil }
    return "\(appName.lowercased())::\(normalized.lowercased())"
  }

  /// Exact pre-flag TaskAssistant dedupe semantics, centralized here so the
  /// private fourth normalizer is gone without changing rollback behavior.
  static func legacyTaskIdentityKey(appName: String, windowTitle: String?) -> String {
    var title = windowTitle?.lowercased() ?? ""
    if let range = title.range(of: #"\s*\(\d+\)\s*$"#, options: .regularExpression) {
      title.removeSubrange(range)
    }
    title = title.split(whereSeparator: { $0.isWhitespace }).joined(separator: " ")
    return "\(appName.lowercased())::\(title)"
  }

  private static func replacing(_ pattern: String, in value: String, with replacement: String = "") -> String {
    value.replacingOccurrences(of: pattern, with: replacement, options: [.regularExpression, .caseInsensitive])
  }
}
