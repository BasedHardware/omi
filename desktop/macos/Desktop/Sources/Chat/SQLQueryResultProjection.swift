import Foundation
@preconcurrency import GRDB

enum SQLQueryResultProjection {
  private static let maxRows = 200
  private static let maxCellCharacters = 500
  private static let maxOutputCharacters = 12_000

  nonisolated static func format(rows: [Row], query: String) -> (text: String, count: Int) {
    guard let firstRow = rows.first else {
      let hint =
        referencesScreenshots(query)
        ? ". For recent-work or document/page/file location, call get_work_context before another screenshots query."
        : ""
      return ("No results\(hint)", 0)
    }

    let columns = Array(firstRow.columnNames)
    if projectsUnboundedOCR(query, columns: columns) {
      return (
        "Raw ocrText columns are not returned. For recent-work or document/page/file location, call get_work_context. For explicit low-level OCR inspection, select a bounded preview such as substr(ocrText, 1, 200) AS preview.",
        rows.count
      )
    }

    var lines = [columns.joined(separator: " | ")]
    lines.append(String(repeating: "-", count: min(columns.count * 20, 120)))
    var characterCount = lines.reduce(0) { $0 + $1.count + 1 }
    var renderedRows = 0
    var truncated = false

    for row in rows.prefix(maxRows) {
      let line = row.map { (_, value) in renderedValue(value) }.joined(separator: " | ")
      guard characterCount + line.count + 1 <= maxOutputCharacters else {
        truncated = true
        break
      }
      lines.append(line)
      characterCount += line.count + 1
      renderedRows += 1
    }

    if renderedRows < rows.count { truncated = true }
    if truncated {
      lines.append(
        "Result truncated after \(renderedRows) row(s) to protect chat context. Refine the projection or aggregate the result."
      )
    }
    lines.append("\n\(rows.count) row(s)")
    return (lines.joined(separator: "\n"), rows.count)
  }

  private nonisolated static func referencesScreenshots(_ query: String) -> Bool {
    query.range(of: #"\bscreenshots\b"#, options: [.regularExpression, .caseInsensitive]) != nil
  }

  private nonisolated static func projectsUnboundedOCR(_ query: String, columns: [String]) -> Bool {
    if columns.contains(where: { $0.caseInsensitiveCompare("ocrText") == .orderedSame }) {
      return true
    }

    // Result-column names alone miss aliases such as `ocrText AS body`, which would be enough to restore the bulk
    // context leak this boundary prevents. Remove the explicitly bounded/statistical forms, then reject any
    // remaining OCR reference in a SELECT projection; predicates remain available for exact filtering.
    let selectOptions: NSRegularExpression.Options = [.caseInsensitive, .dotMatchesLineSeparators]
    guard
      let selectRegex = try? NSRegularExpression(
        pattern: #"\bselect\b(.*?)\bfrom\b"#,
        options: selectOptions
      )
    else {
      return false
    }
    let queryRange = NSRange(query.startIndex..<query.endIndex, in: query)
    let allowedPatterns = [
      #"\bsubstr\s*\(\s*(?:[A-Za-z_][A-Za-z0-9_]*\.)?ocrText\s*,\s*\d+\s*,\s*(?:[1-9]\d?|[1-4]\d{2}|500)\s*\)"#,
      #"\blength\s*\(\s*(?:[A-Za-z_][A-Za-z0-9_]*\.)?ocrText\s*\)"#,
      #"\bcount\s*\(\s*(?:distinct\s+)?(?:[A-Za-z_][A-Za-z0-9_]*\.)?ocrText\s*\)"#,
    ]
    let allowedRegexes = allowedPatterns.compactMap {
      try? NSRegularExpression(pattern: $0, options: [.caseInsensitive])
    }
    let rawOCRRegex = try? NSRegularExpression(
      pattern: #"\b(?:[A-Za-z_][A-Za-z0-9_]*\.)?ocrText\b"#,
      options: [.caseInsensitive]
    )

    return selectRegex.matches(in: query, range: queryRange).contains { match in
      guard let projectionRange = Range(match.range(at: 1), in: query) else { return false }
      var projection = String(query[projectionRange])
      for regex in allowedRegexes {
        let range = NSRange(projection.startIndex..<projection.endIndex, in: projection)
        projection = regex.stringByReplacingMatches(in: projection, range: range, withTemplate: "")
      }
      let range = NSRange(projection.startIndex..<projection.endIndex, in: projection)
      return rawOCRRegex?.firstMatch(in: projection, range: range) != nil
    }
  }

  private nonisolated static func renderedValue(_ databaseValue: DatabaseValue) -> String {
    let value: String
    switch databaseValue.storage {
    case .null:
      value = "NULL"
    case .int64(let integer):
      value = String(integer)
    case .double(let double):
      value = String(double)
    case .string(let string):
      value = string
    case .blob(let data):
      value = "<\(data.count) bytes>"
    }
    guard value.count > maxCellCharacters else { return value }
    return String(value.prefix(maxCellCharacters)) + "..."
  }
}
