import Foundation

/// Applies the excluded-app predicate to model-generated, read-only SQL.
///
/// This is intentionally a small lexer rather than a regular expression. A model can quote a
/// SQLite identifier with double quotes, backticks, or brackets, and table references can be
/// separated by comments. Rewriting only tokens outside literals/comments prevents an app name
/// such as `screenshots` in OCR text from being modified. If a table-valued or malformed table
/// reference cannot be rewritten safely, return a valid empty SELECT so the caller fails closed.
enum InsightSQLPrivacy {
  private static let failClosedQuery = "SELECT 1 WHERE 0"

  private enum TokenKind: Equatable {
    case word
    case quotedIdentifier
    case stringLiteral
    case symbol
    case whitespace
    case comment
  }

  private struct Token {
    let kind: TokenKind
    let raw: String
    let range: NSRange
    let closed: Bool
  }

  private static let clauseKeywords: Set<String> = [
    "as", "cross", "except", "full", "group", "having", "inner", "intersect", "join", "left", "limit", "natural", "on",
    "order", "outer", "right", "union", "using", "where", "window",
  ]

  /// Tables derived from the screenshots table whose data is also subject to
  /// the excluded-app predicate.  The FTS virtual table exposes OCR text that
  /// would otherwise bypass the ``screenshots`` rewrite.
  private static let screenshotDerivedTables: Set<String> = ["screenshots_fts"]

  static func filtered(_ query: String, excludedApps: Set<String>) -> String {
    guard !excludedApps.isEmpty else { return query }
    let quoted = excludedApps.sorted().map { "'\($0.replacingOccurrences(of: "'", with: "''"))'" }
      .joined(separator: ",")
    let tokens = lex(query)
    let significant = tokens.indices.filter { tokens[$0].kind != .whitespace && tokens[$0].kind != .comment }
    var replacements: [(NSRange, String)] = []

    var position = 0
    while position < significant.count {
      let operationIndex = significant[position]
      let operation = tokens[operationIndex]
      guard operation.kind == .word, ["from", "join"].contains(operation.raw.lowercased()) else {
        position += 1
        continue
      }

      var tablePosition = position + 1
      guard tablePosition < significant.count else { return failClosedQuery }

      // Accept one schema qualifier (`main.screenshots`, including quoted identifiers and
      // comments/whitespace around the dot) and normalize all schemas to the local table.
      if tablePosition + 2 < significant.count,
        isIdentifier(tokens[significant[tablePosition]]),
        tokens[significant[tablePosition + 1]].raw == ".",
        isIdentifier(tokens[significant[tablePosition + 2]])
      {
        tablePosition += 2
      }

      let table = tokens[significant[tablePosition]]
      guard isIdentifier(table), table.closed else { return failClosedQuery }
      let tableName = unquotedIdentifier(table.raw).lowercased()
      guard tableName == "screenshots" else {
        // screenshot-derived tables (e.g. screenshots_fts) expose the same OCR
        // data and cannot be safely rewritten with a simple subquery. Fail
        // closed so excluded-app content is never reachable.
        if screenshotDerivedTables.contains(tableName) {
          return failClosedQuery
        }
        position += 1
        continue
      }

      var endPosition = tablePosition
      var alias: String?
      let afterTable = tablePosition + 1
      if afterTable < significant.count {
        let next = tokens[significant[afterTable]]
        if next.raw == "(" || next.raw == "." {
          // A table-valued function or a malformed qualified table is outside this safe
          // rewrite's contract. Do not hand the unfiltered query to the SQL executor.
          return failClosedQuery
        }
        if next.kind == .word, next.raw.lowercased() == "as" {
          let aliasPosition = afterTable + 1
          guard aliasPosition < significant.count else { return failClosedQuery }
          let aliasToken = tokens[significant[aliasPosition]]
          guard isIdentifier(aliasToken), aliasToken.closed else { return failClosedQuery }
          alias = aliasToken.raw
          endPosition = aliasPosition
        } else if isIdentifier(next), !clauseKeywords.contains(next.raw.lowercased()) {
          alias = next.raw
          endPosition = afterTable
        }
      }

      let start = tokens[operationIndex].range.location
      let endToken = tokens[significant[endPosition]]
      let end = endToken.range.location + endToken.range.length
      let aliasClause = alias.map { " AS \($0)" } ?? " AS screenshots"
      let replacement = "\(operation.raw) (SELECT * FROM screenshots WHERE appName NOT IN (\(quoted)))\(aliasClause)"
      replacements.append((NSRange(location: start, length: end - start), replacement))
      position = endPosition + 1
    }

    guard !replacements.isEmpty else { return query }
    var result = query
    for (range, replacement) in replacements.reversed() {
      guard let swiftRange = Range(range, in: result) else { return failClosedQuery }
      result.replaceSubrange(swiftRange, with: replacement)
    }
    return result
  }

  private static func isIdentifier(_ token: Token) -> Bool {
    token.kind == .word || token.kind == .quotedIdentifier
  }

  private static func unquotedIdentifier(_ raw: String) -> String {
    guard raw.count >= 2 else { return raw }
    let first = raw.first
    let last = raw.last
    switch (first, last) {
    case ("\"", "\""):
      return String(raw.dropFirst().dropLast()).replacingOccurrences(of: "\"\"", with: "\"")
    case ("`", "`"):
      return String(raw.dropFirst().dropLast()).replacingOccurrences(of: "``", with: "`")
    case ("[", "]"):
      return String(raw.dropFirst().dropLast()).replacingOccurrences(of: "]]", with: "]")
    default:
      return raw
    }
  }

  private static func lex(_ query: String) -> [Token] {
    let source = query as NSString
    var tokens: [Token] = []
    var index = 0

    func character(_ offset: Int) -> unichar { source.character(at: offset) }
    func isWhitespace(_ value: unichar) -> Bool {
      value == 9 || value == 10 || value == 11 || value == 12 || value == 13 || value == 32
    }
    func isWordStart(_ value: unichar) -> Bool {
      (value >= 65 && value <= 90) || (value >= 97 && value <= 122) || value == 95 || value == 36
    }
    func isWordContinuation(_ value: unichar) -> Bool {
      isWordStart(value) || (value >= 48 && value <= 57)
    }

    while index < source.length {
      let start = index
      let value = character(index)
      if isWhitespace(value) {
        repeat { index += 1 } while index < source.length && isWhitespace(character(index))
        tokens.append(
          Token(
            kind: .whitespace, raw: source.substring(with: NSRange(location: start, length: index - start)),
            range: NSRange(location: start, length: index - start), closed: true))
        continue
      }
      if value == 45 && index + 1 < source.length && character(index + 1) == 45 {
        index += 2
        while index < source.length && character(index) != 10 && character(index) != 13 { index += 1 }
        tokens.append(
          Token(
            kind: .comment, raw: source.substring(with: NSRange(location: start, length: index - start)),
            range: NSRange(location: start, length: index - start), closed: true))
        continue
      }
      if value == 47 && index + 1 < source.length && character(index + 1) == 42 {
        index += 2
        var closed = false
        while index + 1 < source.length {
          if character(index) == 42 && character(index + 1) == 47 {
            index += 2
            closed = true
            break
          }
          index += 1
        }
        if !closed { index = source.length }
        tokens.append(
          Token(
            kind: .comment, raw: source.substring(with: NSRange(location: start, length: index - start)),
            range: NSRange(location: start, length: index - start), closed: closed))
        continue
      }
      if value == 39 {
        index += 1
        var closed = false
        while index < source.length {
          if character(index) == 39 {
            if index + 1 < source.length && character(index + 1) == 39 {
              index += 2
            } else {
              index += 1
              closed = true
              break
            }
          } else {
            index += 1
          }
        }
        tokens.append(
          Token(
            kind: .stringLiteral, raw: source.substring(with: NSRange(location: start, length: index - start)),
            range: NSRange(location: start, length: index - start), closed: closed))
        continue
      }
      if value == 34 || value == 96 || value == 91 {
        let closing: unichar = value == 91 ? 93 : value
        index += 1
        var closed = false
        while index < source.length {
          if character(index) == closing {
            if index + 1 < source.length && character(index + 1) == closing {
              index += 2
            } else {
              index += 1
              closed = true
              break
            }
          } else {
            index += 1
          }
        }
        tokens.append(
          Token(
            kind: .quotedIdentifier, raw: source.substring(with: NSRange(location: start, length: index - start)),
            range: NSRange(location: start, length: index - start), closed: closed))
        continue
      }
      if isWordStart(value) {
        index += 1
        while index < source.length && isWordContinuation(character(index)) { index += 1 }
        tokens.append(
          Token(
            kind: .word, raw: source.substring(with: NSRange(location: start, length: index - start)),
            range: NSRange(location: start, length: index - start), closed: true))
        continue
      }
      index += 1
      tokens.append(
        Token(
          kind: .symbol, raw: source.substring(with: NSRange(location: start, length: 1)),
          range: NSRange(location: start, length: 1), closed: true))
    }
    return tokens
  }
}
