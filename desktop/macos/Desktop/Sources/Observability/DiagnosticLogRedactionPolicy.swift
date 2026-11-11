import Foundation

enum DiagnosticLogRedactionPolicy {
  /// A single line larger than this is too costly to run the redaction regexes
  /// over and carries little diagnostic value — the export replaces it with a
  /// placeholder rather than partially scrubbing it, so a secret embedded in a
  /// huge line cannot slip through incomplete regex matching.
  static let maximumLineLengthForRegexRedaction = 16 * 1024

  static func shouldSkipRegexRedaction(_ line: String) -> Bool {
    line.utf8.count > maximumLineLengthForRegexRedaction
  }
}
