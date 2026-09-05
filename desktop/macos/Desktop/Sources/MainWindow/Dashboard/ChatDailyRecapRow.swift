import OmiTheme
import SwiftUI

/// The daily recap, where it belongs in Chat: **in history.**
///
/// The transcript renders one of these rows at the day boundary the recap is about — before the
/// first message on or after the recap's date — so it scrolls with the thread like any other row.
/// It is a quiet, full-width history marker, not chrome pinned over the viewport: nothing is
/// inset for it, nothing floats, and it cannot move the live edge, which is why the pinned bar's
/// admission and inset machinery (INV-CHAT-2's banner constraints) no longer exists in Chat.
///
/// **Below the messages in hierarchy, on purpose.** Left-aligned text one step smaller than the
/// bubble's, a soft fill with no border, and a trailing chevron — a marker in the thread, not
/// another card. Centered bordered prose reads as an answer; the day boundary is the quieter
/// thing. A doorway, not the experience: day label, one-line headline, at most two lines of
/// overview — the full record, its badges, and its actions live on `DailyRecapPage`, which
/// clicking opens through the typed recap route.
struct ChatDailyRecapRow: View {
  let record: DailySummaryRecord

  /// Injected so the day label is deterministic in tests.
  private let now: () -> Date

  init(record: DailySummaryRecord, now: @escaping () -> Date = Date.init) {
    self.record = record
    self.now = now
  }

  var body: some View {
    Button {
      // Identity only: the page re-reads the record from the shared store or the API.
      ChatFirstShellNavigation.shared.openDailyRecap(
        DailyRecapRouteRef(recordID: record.id, date: record.date ?? ""))
      AnalyticsManager.shared.trackDailySummary(.expanded)
    } label: {
      VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
        HStack(spacing: OmiSpacing.xs) {
          Text(dayLabel)
            .scaledFont(size: OmiType.micro, weight: .semibold)
            .foregroundStyle(Ink.secondary)
            .tracking(0.6)
          Spacer(minLength: OmiSpacing.sm)
          Image(systemName: "chevron.right")
            .scaledFont(size: OmiType.micro, weight: .semibold)
            .foregroundStyle(Ink.secondary)
        }
        Text(nonEmpty(record.headline) ?? "Your day in review")
          .scaledFont(size: OmiType.caption, weight: .medium)
          .foregroundStyle(Ink.primary)
          .lineLimit(1)
          .truncationMode(.tail)
        if let overview = nonEmpty(record.overview) {
          Text(overview)
            .scaledFont(size: OmiType.caption)
            .foregroundStyle(Ink.secondary)
            .lineLimit(2)
            .fixedSize(horizontal: false, vertical: true)
            .multilineTextAlignment(.leading)
        }
      }
      .frame(maxWidth: .infinity, alignment: .leading)
      .padding(.horizontal, OmiSpacing.md)
      .padding(.vertical, OmiSpacing.sm)
      .background(RoundedRectangle(cornerRadius: 8, style: .continuous).fill(Ink.rowFill))
      .contentShape(.rect(cornerRadius: 8))
    }
    .buttonStyle(.plain)
    .accessibilityIdentifier("chat-daily-recap-row")
    .accessibilityLabel(Text("Open the daily recap"))
    .help("Open the full recap for \(dayLabel)")
  }

  /// "Yesterday · 🚀" — the day the recap is about, not the day it was written.
  private var dayLabel: String {
    let emoji = nonEmpty(record.dayEmoji) ?? "📅"
    let day =
      ChatDailySummaryPresentation.dateLabel(for: record.date, now: now()) ?? "Your day"
    return "\(day) · \(emoji)"
  }

  private func nonEmpty(_ value: String?) -> String? {
    guard let value, !value.isEmpty else { return nil }
    return value
  }
}

/// Where the recap row goes, decided once and tested without a view.
///
/// The row anchors **above the first message on or after the recap's day** — it is a day boundary
/// in the thread, so it must sit where that day begins. Two shapes of thread render nothing at
/// all, because either would draw the marker at a place the transcript cannot back up:
///
/// - **No message in the loaded window is on or after the recap's day.** The boundary is below
///   what is loaded (or the thread is empty); a marker at the live edge would claim a day the
///   visible history does not contain.
/// - **The boundary is at the very top of the loaded window while older messages exist above
///   it.** The day may begin further up; anchoring at the first loaded row would put the marker
///   above messages from the same day whenever more history loads.
enum ChatDailyRecapRowPlacement {
  static func anchorMessageID(
    in messages: [ChatMessage],
    recapDate: String?,
    hasOlderMessagesAbove: Bool,
    calendar: Calendar = .current
  ) -> String? {
    guard let day = ChatDailySummaryPresentation.day(from: recapDate, calendar: calendar) else {
      return nil
    }
    let dayStart = calendar.startOfDay(for: day)
    guard
      let index = messages.firstIndex(where: { calendar.startOfDay(for: $0.createdAt) >= dayStart })
    else { return nil }
    if index == 0, hasOlderMessagesAbove { return nil }
    return messages[index].id
  }
}
