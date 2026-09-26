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
/// thing. A doorway, not the experience: day label, the day's emoji beside a one-line headline,
/// at most three lines of overview, and the day's stats as a strip of micro chips (the same
/// numbers the Activity day card shows, at bubble-row weight) — the full record and its actions
/// live on `DailyRecapPage`, which clicking opens through the typed recap route.
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
        // The page's header shape, at row weight: the day's emoji beside the
        // title, so the card reads as *the* recap rather than another notice.
        HStack(spacing: OmiSpacing.xs) {
          Text(nonEmpty(record.dayEmoji) ?? "📅")
            .scaledFont(size: OmiType.subheading)
          Text(nonEmpty(record.headline) ?? "Your day in review")
            .scaledFont(size: OmiType.caption, weight: .semibold)
            .foregroundStyle(Ink.primary)
            .lineLimit(1)
            .truncationMode(.tail)
        }
        if let overview = nonEmpty(record.overview) {
          Text(overview)
            .scaledFont(size: OmiType.caption)
            .foregroundStyle(Ink.secondary)
            .lineLimit(3)
            .fixedSize(horizontal: false, vertical: true)
            .multilineTextAlignment(.leading)
        }
        if let stats = record.stats {
          statsStrip(stats)
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

  /// The day's numbers at bubble-row weight: one micro chip per stat, hugging
  /// its content, no scroll — six fit the narrowest chat column. Same data the
  /// Activity day card shows; the page is where they get room to breathe.
  private func statsStrip(_ stats: DailySummaryRecord.Stats) -> some View {
    let chips = HomeDailySummaryStatsRow.chips(for: stats)
    return Group {
      if !chips.isEmpty {
        HStack(spacing: OmiSpacing.xxs) {
          ForEach(chips) { chip in
            HStack(spacing: 3) {
              Image(systemName: chip.symbol)
                .scaledFont(size: OmiType.micro, weight: .semibold)
                .foregroundStyle(Ink.secondary)
              Text(chip.value)
                .scaledFont(size: OmiType.micro, weight: .bold)
                .monospacedDigit()
                .foregroundStyle(Ink.primary)
              Text(chip.label)
                .scaledFont(size: OmiType.micro)
                .foregroundStyle(Ink.secondary)
            }
            .lineLimit(1)
            .padding(.horizontal, 5)
            .padding(.vertical, 2)
            .background(Capsule().fill(Ink.rowFill.opacity(0.6)))
          }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Day stats")
      }
    }
  }

  /// "Yesterday" — the day the recap is about, not the day it was written. The
  /// day's emoji sits beside the title above, the way the page's header does.
  private var dayLabel: String {
    ChatDailySummaryPresentation.dateLabel(for: record.date, now: now()) ?? "Your day"
  }

  private func nonEmpty(_ value: String?) -> String? {
    guard let value, !value.isEmpty else { return nil }
    return value
  }
}

/// Where the recap row goes, decided once and tested without a view.
///
/// The row anchors **above the first message on or after the recap's day** — it is a day boundary
/// in the thread, so it must sit where that day begins. Two shapes of thread place it
/// differently, and one renders nothing at all:
///
/// - **No message in the loaded window is on or after the recap's day.** The recap is newer than
///   everything loaded, so it is the newest thing in the thread: the marker takes the live edge,
///   above the last row. (The row carries its own day label, so it claims nothing about the
///   messages it sits below.)
/// - **The boundary is at the very top of the loaded window while older messages exist above
///   it.** The day may begin further up; anchoring at the first loaded row would put the marker
///   above messages from the same day whenever more history loads, so it waits.
/// - **An empty thread** renders nothing — the empty state owns that surface.
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
    else { return messages.last?.id }
    if index == 0, hasOlderMessagesAbove { return nil }
    return messages[index].id
  }
}
