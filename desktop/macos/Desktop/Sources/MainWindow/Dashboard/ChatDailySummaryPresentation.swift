import Foundation

/// Pure text rules for the daily summary card in Chat.
///
/// Mobile shows the day as a pill ("Today", "Yesterday", or the weekday and date) rather than the
/// raw `YYYY-MM-DD` the backend sends. The rules live here, away from any view, because the only
/// thing that can go wrong with them is arithmetic: a UTC-midnight date rendered in the wrong zone
/// reads as the previous evening, and "Yesterday" computed by subtracting 86 400 seconds is wrong
/// on the two days a year that are not 24 hours long. Both are calendar questions, so both are
/// answered with `Calendar.dateComponents` against an injected `now`.
enum ChatDailySummaryPresentation {
  /// The backend's day, as a `Date` at the start of that day in `calendar`'s zone.
  /// Returns nil for a missing or malformed `date`, which is how the card hides the pill instead of
  /// rendering a parsing artifact.
  static func day(from date: String?, calendar: Calendar = .current) -> Date? {
    guard let date else { return nil }
    let parts = date.split(separator: "-")
    guard parts.count == 3 else { return nil }
    let numbers = parts.compactMap { Int($0) }
    guard numbers.count == 3, numbers[1] >= 1, numbers[1] <= 12, numbers[2] >= 1, numbers[2] <= 31
    else { return nil }
    return calendar.date(
      from: DateComponents(year: numbers[0], month: numbers[1], day: numbers[2]))
  }

  /// "Today" / "Yesterday" / "Mon, Aug 31". Nil when the date is missing or malformed.
  ///
  /// The day difference is counted in whole calendar days, so a summary written just before
  /// midnight is still "Yesterday" the next morning regardless of DST, and a month boundary is
  /// just another day boundary.
  static func dateLabel(
    for date: String?,
    now: Date,
    calendar: Calendar = .current,
    locale: Locale = .current
  ) -> String? {
    guard let day = day(from: date, calendar: calendar) else { return nil }
    let today = calendar.startOfDay(for: now)
    let days = calendar.dateComponents([.day], from: calendar.startOfDay(for: day), to: today).day
    switch days {
    case 0: return "Today"
    case 1: return "Yesterday"
    default:
      let formatter = DateFormatter()
      formatter.calendar = calendar
      // The day was built in the calendar's zone; format it there too, or every zone west of UTC
      // renders the previous evening.
      formatter.timeZone = calendar.timeZone
      formatter.locale = locale
      formatter.setLocalizedDateFormatFromTemplate("EEE MMM d")
      return formatter.string(from: day)
    }
  }

  /// The follow-up the chip prefills. It names the day the summary is about, because "What did I do
  /// today?" against yesterday's summary would be a different question than the card just answered.
  static func followUpQuestion(for date: String?, now: Date, calendar: Calendar = .current) -> String {
    guard let day = day(from: date, calendar: calendar),
      calendar.isDate(day, inSameDayAs: now)
    else { return "What did I do yesterday?" }
    return "What did I do today?"
  }

  /// Longest overview that still reads as a banner rather than a wall of text.
  static let cardBodyLimit = 140

  /// The notch card's body: the overview, cut at a word boundary. Returns nil when there is no
  /// overview, so the caller can fall back rather than post an empty card.
  static func cardBody(for overview: String?, limit: Int = cardBodyLimit) -> String? {
    let trimmed = (overview ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return nil }
    guard trimmed.count > limit else { return trimmed }
    let head = trimmed.prefix(limit)
    let cut = head.lastIndex(where: { $0 == " " }).map { head[head.startIndex..<$0] } ?? head
    return String(cut).trimmingCharacters(in: .whitespacesAndNewlines) + "…"
  }

  /// The notch card's title: the day emoji and the headline, with a stable fallback when the
  /// backend sent neither.
  static func cardTitle(for record: DailySummaryRecord) -> String {
    let emoji = (record.dayEmoji ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
    let headline = (record.headline ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
    let text = headline.isEmpty ? "Your day in review" : headline
    return emoji.isEmpty ? text : "\(emoji) \(text)"
  }
}
