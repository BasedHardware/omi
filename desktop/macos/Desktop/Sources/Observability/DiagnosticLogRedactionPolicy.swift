import Foundation

enum DiagnosticLogRedactionPolicy {
  static func shouldSkipRegexRedaction(_ line: String) -> Bool {
    line.utf8.count > 16 * 1024
  }
}
