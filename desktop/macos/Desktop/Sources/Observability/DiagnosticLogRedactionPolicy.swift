import Foundation

enum DiagnosticLogRedactionPolicy {
  static let maximumLineLengthForRegexRedaction = 16 * 1024

  static func shouldSkipRegexRedaction(_ line: String) -> Bool {
    line.utf8.count > maximumLineLengthForRegexRedaction
  }
}
