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
    result = replacing(#"\(\d+\)"#, in: result)
    result = replacing(#"\[\d+\]"#, in: result)

    let app = appName?.lowercased() ?? ""
    if app.contains("telegram") || app.contains("slack") || app.contains("discord") {
      result = replacing(#"\s*[-–—]\s*\d+\s+(new\s+)?messages?\s*$"#, in: result)
    }
    if app.contains("terminal") || app.contains("iterm") || app.contains("warp") {
      result = replacing(#"\s+[-–—]\s+(zsh|bash|fish)\s*$"#, in: result)
    }

    result = replacing(#"\s+"#, in: result, with: " ")
      .trimmingCharacters(in: .whitespacesAndNewlines)
    return result.isEmpty ? nil : result
  }

  static func identityKey(appName: String, windowTitle: String?) -> String {
    "\(appName.lowercased())::\((normalize(windowTitle, appName: appName) ?? "").lowercased())"
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
