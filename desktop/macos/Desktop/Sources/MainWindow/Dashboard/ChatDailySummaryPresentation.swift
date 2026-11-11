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
    dateLabel(
      for: date, now: now, calendar: calendar, locale: locale,
      olderFormat: "EEE MMM d")
  }

  /// The dedicated recap page's eyebrow: "Today" / "Yesterday" / the full weekday and date
  /// ("Wednesday, September 3"). Same arithmetic as `dateLabel`, one format wider — the page is
  /// the full record, so its date names the day instead of abbreviating it.
  static func pageDateLabel(
    for date: String?,
    now: Date,
    calendar: Calendar = .current,
    locale: Locale = .current
  ) -> String? {
    dateLabel(
      for: date, now: now, calendar: calendar, locale: locale,
      olderFormat: "EEEE, MMMM d")
  }

  /// The shared day-difference arithmetic behind both labels. The difference is counted in whole
  /// calendar days, so a summary written just before midnight is still "Yesterday" the next
  /// morning regardless of DST, and a month boundary is just another day boundary. The older-day
  /// format is the only thing the two callers disagree on.
  private static func dateLabel(
    for date: String?,
    now: Date,
    calendar: Calendar,
    locale: Locale,
    olderFormat: String
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
      formatter.setLocalizedDateFormatFromTemplate(olderFormat)
      return formatter.string(from: day)
    }
  }

  /// The follow-up the chip prefills. It names the day the summary is about, because "What did I do
  /// today?" against yesterday's summary would be a different question than the card just answered.
  static func followUpQuestion(
    for date: String?, now: Date, calendar: Calendar = .current, locale: Locale = .current
  ) -> String {
    switch dateLabel(for: date, now: now, calendar: calendar, locale: locale) {
    case "Today": return "What did I do today?"
    case nil, "Yesterday": return "What did I do yesterday?"
    // A summary from further back names its day, so the chip asks about the day the card shows
    // rather than about a yesterday the summary is not about.
    case .some(let label): return "What did I do on \(label)?"
    }
  }

  /// True when the summary's day is more than two whole calendar days before today.
  /// Uses the same `Calendar.dateComponents` arithmetic as `dateLabel` — a 86 400-second
  /// subtraction is wrong on the two days a year that are not 24 hours long.
  static func isStale(_ date: String?, now: Date, calendar: Calendar = .current) -> Bool {
    guard let day = day(from: date, calendar: calendar) else { return false }
    let today = calendar.startOfDay(for: now)
    let days = calendar.dateComponents([.day], from: calendar.startOfDay(for: day), to: today).day
    return (days ?? 0) > 2
  }

  /// The eyebrow when `isStale` is true. It **keeps the day** and adds the age: dropping the date
  /// would leave the reader unable to tell which day a stale recap is even about, which is a worse
  /// failure than the one staleness copy exists to fix.
  static func staleLabel(
    for date: String?, now: Date, calendar: Calendar = .current, locale: Locale = .current
  ) -> String {
    guard let label = dateLabel(for: date, now: now, calendar: calendar, locale: locale) else {
      return "Several days old"
    }
    return "\(label) · several days old"
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

  // MARK: - Section projection

  /// Pure so the "render only what is there" rule is testable without a view: an empty section is
  /// never drawn. Shared by every surface that renders a recap, so their sections cannot drift.
  nonisolated static func highlights(in summary: DailySummaryRecord) -> [DailySummaryRecord.Highlight] {
    (summary.highlights ?? []).filter { !($0.summary ?? "").isEmpty }
  }

  nonisolated static func actionItems(in summary: DailySummaryRecord) -> [DailySummaryRecord.ActionItem] {
    (summary.actionItems ?? []).filter { !($0.description ?? "").isEmpty }
  }

  /// The review rows, and only from `memories_learned`.
  ///
  /// Deliberately never falls back to `knowledge_nuggets`: a nugget is LLM prose with no memory
  /// behind it, so a ✓ on one would mutate nothing and a ✗ would teach extraction nothing. A day
  /// with no qualifying memory shows no section, which is the honest empty state.
  nonisolated static func memoriesLearned(in summary: DailySummaryRecord) -> [MemoryReviewItem] {
    summary.memoriesLearned
      .filter {
        // Trimmed, not merely non-empty: a blank-but-present id would render a row whose ✓ / ✗ /
        // Fix address no memory at all.
        !$0.memoryID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
          && !$0.content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
      }
      .prefix(MemoryReviewSection.maxRows)
      .map(MemoryReviewItem.init)
  }

  /// Identity for a recap's memory-review section.
  ///
  /// The section holds one `MemoryReviewCardStore`, and the store captures its rows at init. A
  /// summary regenerated for the same day keeps its id, so keying on the id alone kept the old
  /// store alive: new memories never appeared and corrected ones kept the text the record no
  /// longer contained. Folding the rows in rebuilds the section exactly when they change.
  nonisolated static func reviewSectionIdentity(
    summaryID: String, items: [MemoryReviewItem]
  ) -> String {
    let rows = items.map { "\($0.memoryID)\u{1F}\($0.content)" }.joined(separator: "\u{1E}")
    return "memory-review-\(summaryID)\u{1E}\(rows)"
  }

  // MARK: - Actions

  /// The follow-up affordance's whole action, separated from any view so it is testable: place the
  /// question in the composer and stop. It never sends — the reader reads the recap, then decides
  /// whether to ask. `MainChatNavigationRequestStore` is the one prefill seam both shells'
  /// composers consume; a second path would race the first for the draft.
  @MainActor
  static func requestFollowUp(_ question: String) {
    MainChatNavigationRequestStore.shared.request(draft: question)
    AnalyticsManager.shared.trackDailySummary(.followUpTapped)
  }

  // MARK: - Generation failures

  /// The one line a recap writer shows when the server did not produce a record.
  ///
  /// The backend's status codes are the contract, and three of them are answers rather than
  /// failures: 400 is a decline — the day carries no conversation the recap can be written from;
  /// 409 is another writer (almost always the nightly run) mid-generation; 429 is the spend
  /// cooldown. Folding those into "Couldn't generate" read as a broken button on exactly the
  /// days where the button had worked and the honest answer was "nothing recorded yet".
  /// Anything else — a 5xx, a dropped connection, a decode failure — is `fallback`.
  static func generationFailureMessage(for error: Error, fallback: String) -> String {
    guard case APIError.httpError(let statusCode, _) = error else { return fallback }
    switch statusCode {
    case 400:
      return "Nothing to summarize yet — a recap needs a recorded conversation from this day."
    case 409:
      return "Already being generated — check back in a moment."
    case 429:
      return "Just generated — wait a moment before trying again."
    default:
      return fallback
    }
  }
}
