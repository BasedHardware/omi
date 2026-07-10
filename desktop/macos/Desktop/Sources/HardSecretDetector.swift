import Foundation

struct HardSecretDetection: Equatable {
  let category: String
  let range: Range<String.Index>
}

enum HardSecretDetector {
  private struct Pattern {
    let category: String
    let regex: NSRegularExpression
  }

  private static let patterns: [Pattern] = [
    Pattern(
      category: "private_key",
      regex: try! NSRegularExpression(
        pattern: #"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"#,
        options: []
      )
    ),
    Pattern(
      category: "private_key",
      regex: try! NSRegularExpression(
        pattern: #"-----BEGIN [A-Z ]*PRIVATE KEY-----"#,
        options: []
      )
    ),
    Pattern(
      category: "database_url",
      regex: try! NSRegularExpression(
        pattern: #"\b[a-z][a-z0-9+.-]*://[^/\s:@]+:[^@\s]+@[^/\s]+[^\s]*"#,
        options: [.caseInsensitive]
      )
    ),
    Pattern(
      category: "api_key",
      regex: try! NSRegularExpression(
        pattern: #"\b(?:sk[-_][A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16})\b"#,
        options: []
      )
    ),
    Pattern(
      category: "one_time_code",
      regex: try! NSRegularExpression(
        pattern: #"\b(?:one[- ]?time code|verification code|2fa code|mfa code|otp)\s+(?:is\s+)?['"]?([0-9]{4,8})\b"#,
        options: [.caseInsensitive]
      )
    ),
    Pattern(
      category: "token",
      regex: try! NSRegularExpression(
        pattern: #"\b(?:token|auth[_-]?token|access[_-]?token|bearer)\s*[:=]\s*['"]?([A-Za-z0-9._~+/=-]{16,})"#,
        options: [.caseInsensitive]
      )
    ),
    Pattern(
      category: "password",
      regex: try! NSRegularExpression(
        pattern: #"\b(?:password|passwd|pwd)\s*[:=]\s*['"]?([^'"\s]{8,})"#,
        options: [.caseInsensitive]
      )
    ),
    Pattern(
      category: "cookie",
      regex: try! NSRegularExpression(
        pattern: #"\b(?:session|cookie)\s*[:=]\s*['"]?([A-Za-z0-9._~+/=-]{16,})"#,
        options: [.caseInsensitive]
      )
    ),
  ]

  static func detections(in text: String) -> [HardSecretDetection] {
    let nsRange = NSRange(text.startIndex..<text.endIndex, in: text)
    var detections: [HardSecretDetection] = []
    for pattern in patterns {
      for match in pattern.regex.matches(in: text, options: [], range: nsRange) {
        guard let range = Range(match.range, in: text) else { continue }
        detections.append(HardSecretDetection(category: pattern.category, range: range))
      }
    }
    return detections
  }

  static func containsHardSecret(_ text: String) -> Bool {
    !detections(in: text).isEmpty
  }

  static func categories(in text: String) -> [String] {
    Array(Set(detections(in: text).map(\.category))).sorted()
  }
}
