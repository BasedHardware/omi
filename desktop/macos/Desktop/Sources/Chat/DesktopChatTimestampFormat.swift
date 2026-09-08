import Foundation
@preconcurrency import GRDB

/// Single formatter for timestamps that reach the chat model.
///
/// SQLite DATETIME / GRDB `Date` cells are UTC-naive. Presenting that wall-clock
/// as if it were local made Desktop Chat quote 7:59 PM for a 3:59 PM Eastern
/// event (#12321). Format in an injected `TimeZone` and always include a zone
/// token so the model cannot invent an unlabeled local time.
enum DesktopChatTimestampFormat {
  /// `2026-08-27 3:59:51 PM EDT (America/New_York)`
  static func userFacing(_ date: Date, timeZone: TimeZone) -> String {
    let formatter = DateFormatter()
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.calendar = Calendar(identifier: .gregorian)
    formatter.timeZone = timeZone
    formatter.dateFormat = "yyyy-MM-dd h:mm:ss a zzz"
    return "\(formatter.string(from: date)) (\(timeZone.identifier))"
  }

  static func isTimestampColumn(_ name: String) -> Bool {
    let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return false }
    if trimmed.compare("timestamp", options: .caseInsensitive) == .orderedSame { return true }
    if trimmed.compare("ts", options: .caseInsensitive) == .orderedSame { return true }
    if trimmed.hasSuffix("At") || trimmed.hasSuffix("Date") { return true }
    let lower = trimmed.lowercased()
    return lower.hasSuffix("_at") || lower.hasSuffix("_date")
  }

  /// Convert a UTC-naive SQL cell when the column is a datetime field.
  /// Returns nil to keep the raw rendering (NULL, numbers that are not dates, OCR, …).
  static func formatSQLCell(
    column: String,
    value: DatabaseValue,
    timeZone: TimeZone
  ) -> String? {
    guard isTimestampColumn(column) else { return nil }
    if value.isNull { return nil }
    if let date = Date.fromDatabaseValue(value) {
      return userFacing(date, timeZone: timeZone)
    }
    switch value.storage {
    case .string(let string):
      guard let date = parseUTCNaiveDate(string) else { return nil }
      return userFacing(date, timeZone: timeZone)
    case .int64(let integer):
      guard let date = parseEpoch(integer) else { return nil }
      return userFacing(date, timeZone: timeZone)
    case .double(let double):
      guard let date = parseEpoch(double) else { return nil }
      return userFacing(date, timeZone: timeZone)
    default:
      return nil
    }
  }

  /// Local calendar-day bounds expressed as UTC instants so WHERE clauses stay UTC-vs-UTC.
  enum SQLDayBounds {
    static func startAsUTC(daysAgo: Int) -> String {
      let clampedDaysAgo = max(0, daysAgo)
      if clampedDaysAgo == 0 {
        return "datetime('now', 'localtime', 'start of day', 'utc')"
      }
      return "datetime('now', 'localtime', 'start of day', '-\(clampedDaysAgo) day', 'utc')"
    }

    static func exclusiveEndAsUTC(daysAgo: Int) -> String {
      max(0, daysAgo) == 0
        ? "datetime('now')"
        : "datetime('now', 'localtime', 'start of day', 'utc')"
    }
  }

  private static func parseUTCNaiveDate(_ raw: String) -> Date? {
    let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return nil }
    let iso = ISO8601DateFormatter()
    iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    if let date = iso.date(from: trimmed) { return date }
    iso.formatOptions = [.withInternetDateTime]
    if let date = iso.date(from: trimmed) { return date }

    let formatter = DateFormatter()
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.calendar = Calendar(identifier: .gregorian)
    formatter.timeZone = TimeZone(secondsFromGMT: 0)
    for pattern in [
      "yyyy-MM-dd HH:mm:ss.SSS", "yyyy-MM-dd HH:mm:ss", "yyyy-MM-dd'T'HH:mm:ss.SSS", "yyyy-MM-dd'T'HH:mm:ss",
    ] {
      formatter.dateFormat = pattern
      if let date = formatter.date(from: trimmed) { return date }
    }
    return nil
  }

  private static func parseEpoch(_ value: Int64) -> Date? {
    parseEpoch(Double(value))
  }

  private static func parseEpoch(_ value: Double) -> Date? {
    if value >= 1_000_000_000_000 {
      return Date(timeIntervalSince1970: value / 1000)
    }
    if value >= 1_000_000_000 {
      return Date(timeIntervalSince1970: value)
    }
    return nil
  }
}
