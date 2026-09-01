import OmiTheme
import SwiftUI

/// The daily summary on the Home hub: the same record mobile renders, with the stats row.
///
/// Resting state is one glance: emoji, date, headline, and the numbers. "More" opens the overview,
/// the day's action items, and the topic highlights in place; nothing navigates away, because the
/// hub is the resting surface and the summary is a read, not a task.
struct HomeDailySummarySection: View {
  @ObservedObject var store: HomeDailySummaryStore

  @State private var isExpanded = false
  @State private var isHovering = false

  var body: some View {
    Group {
      if let summary = store.latest {
        card(summary)
          .transition(.opacity.combined(with: .move(edge: .bottom)))
      }
    }
    .task { await store.refreshIfNeeded() }
    .omiAnimation(.easeOut(duration: 0.2), value: isExpanded)
  }

  private func card(_ summary: DailySummaryRecord) -> some View {
    VStack(alignment: .leading, spacing: OmiSpacing.md) {
      header(summary)

      if let stats = summary.stats {
        HomeDailySummaryStatsRow(stats: stats)
      }

      if isExpanded {
        expandedBody(summary)
      } else if let overview = summary.overview, !overview.isEmpty {
        Text(overview)
          .scaledFont(size: OmiType.body)
          .foregroundStyle(HomePalette.secondary)
          .lineLimit(2)
          .fixedSize(horizontal: false, vertical: true)
      }
    }
    .padding(.horizontal, OmiSpacing.lg)
    .padding(.vertical, OmiSpacing.md + 2)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(
      RoundedRectangle(cornerRadius: 13, style: .continuous)
        .fill(isHovering ? HomePalette.tileHover : Ink.rowFill)
    )
    .overlay(
      RoundedRectangle(cornerRadius: 13, style: .continuous)
        .stroke(isHovering ? Ink.hairline : Ink.separator, lineWidth: 1)
    )
    .contentShape(.rect(cornerRadius: 13))
    .onHover { isHovering = $0 }
    .accessibilityElement(children: .contain)
    .accessibilityIdentifier("home-daily-summary")
  }

  private func header(_ summary: DailySummaryRecord) -> some View {
    HStack(alignment: .firstTextBaseline, spacing: OmiSpacing.sm) {
      Text(summary.dayEmoji?.isEmpty == false ? summary.dayEmoji! : "📅")
        .scaledFont(size: OmiType.subheading)
      VStack(alignment: .leading, spacing: 2) {
        Text(Self.eyebrow(for: summary.date))
          .scaledFont(size: OmiType.micro, weight: .semibold)
          .foregroundStyle(HomePalette.muted)
          .tracking(0.6)
        Text(summary.headline?.isEmpty == false ? summary.headline! : "Your day in review")
          .scaledFont(size: OmiType.subheading, weight: .semibold)
          .foregroundStyle(HomePalette.ink)
          .lineLimit(isExpanded ? nil : 1)
      }
      Spacer(minLength: OmiSpacing.sm)
      Button(isExpanded ? "Less" : "More") { isExpanded.toggle() }
        .buttonStyle(.plain)
        .scaledFont(size: OmiType.caption, weight: .medium)
        .foregroundStyle(HomePalette.secondary)
        .accessibilityIdentifier("home-daily-summary-toggle")
    }
  }

  @ViewBuilder
  private func expandedBody(_ summary: DailySummaryRecord) -> some View {
    if let overview = summary.overview, !overview.isEmpty {
      Text(overview)
        .scaledFont(size: OmiType.body)
        .foregroundStyle(HomePalette.secondary)
        .fixedSize(horizontal: false, vertical: true)
    }

    let items = (summary.actionItems ?? []).filter { !($0.description ?? "").isEmpty }
    if !items.isEmpty {
      VStack(alignment: .leading, spacing: OmiSpacing.xs) {
        Text("Action items")
          .scaledFont(size: OmiType.micro, weight: .semibold)
          .foregroundStyle(HomePalette.muted)
          .tracking(0.6)
        ForEach(Array(items.prefix(5).enumerated()), id: \.offset) { _, item in
          HStack(alignment: .firstTextBaseline, spacing: OmiSpacing.sm) {
            Image(systemName: item.completed == true ? "checkmark.circle.fill" : "circle")
              .scaledFont(size: OmiType.caption, weight: .medium)
              .foregroundStyle(item.completed == true ? HomePalette.green : HomePalette.muted)
            Text(item.description ?? "")
              .scaledFont(size: OmiType.body)
              .foregroundStyle(HomePalette.ink)
              .strikethrough(item.completed == true, color: HomePalette.muted)
              .fixedSize(horizontal: false, vertical: true)
          }
        }
      }
    }

    let highlights = (summary.highlights ?? []).filter { !($0.summary ?? "").isEmpty }
    if !highlights.isEmpty {
      VStack(alignment: .leading, spacing: OmiSpacing.xs) {
        Text("Highlights")
          .scaledFont(size: OmiType.micro, weight: .semibold)
          .foregroundStyle(HomePalette.muted)
          .tracking(0.6)
        ForEach(Array(highlights.prefix(3).enumerated()), id: \.offset) { _, highlight in
          HStack(alignment: .firstTextBaseline, spacing: OmiSpacing.sm) {
            Text(highlight.emoji?.isEmpty == false ? highlight.emoji! : "•")
              .scaledFont(size: OmiType.caption)
            VStack(alignment: .leading, spacing: 1) {
              if let topic = highlight.topic, !topic.isEmpty {
                Text(topic)
                  .scaledFont(size: OmiType.body, weight: .medium)
                  .foregroundStyle(HomePalette.ink)
              }
              Text(highlight.summary ?? "")
                .scaledFont(size: OmiType.body)
                .foregroundStyle(HomePalette.secondary)
                .fixedSize(horizontal: false, vertical: true)
            }
          }
        }
      }
    }
  }

  /// "Daily summary · Mon, Sep 1" from the backend's `YYYY-MM-DD`; falls back to the bare label when
  /// the date is missing or malformed rather than showing a parsing artifact.
  nonisolated static func eyebrow(
    for date: String?, calendar: Calendar = .current, locale: Locale = .current
  ) -> String {
    let label = "DAILY SUMMARY"
    guard let date else { return label }
    let parts = date.split(separator: "-").compactMap { Int($0) }
    guard parts.count == 3,
      let day = calendar.date(from: DateComponents(year: parts[0], month: parts[1], day: parts[2]))
    else { return label }
    let formatter = DateFormatter()
    formatter.calendar = calendar
    // The day was built in the calendar's zone; format it there too, or a UTC midnight renders as
    // the previous evening in every zone west of it.
    formatter.timeZone = calendar.timeZone
    formatter.locale = locale
    formatter.setLocalizedDateFormatFromTemplate("EEE MMM d")
    return "\(label) · \(formatter.string(from: day).uppercased())"
  }
}

/// The numbers, as chips. Only stats the backend actually filled are shown, so a day without
/// desktop usage still reads cleanly instead of showing a row of zeros.
struct HomeDailySummaryStatsRow: View {
  let stats: DailySummaryRecord.Stats

  struct Chip: Identifiable, Equatable {
    let id: String
    let symbol: String
    let value: String
    let label: String
  }

  var body: some View {
    let chips = Self.chips(for: stats)
    if !chips.isEmpty {
      HStack(spacing: OmiSpacing.xs) {
        ForEach(chips) { chip in
          HStack(spacing: OmiSpacing.xxs) {
            Image(systemName: chip.symbol)
              .scaledFont(size: OmiType.micro, weight: .semibold)
              .foregroundStyle(HomePalette.muted)
            Text(chip.value)
              .scaledFont(size: OmiType.caption, weight: .semibold)
              .monospacedDigit()
              .foregroundStyle(HomePalette.ink)
            Text(chip.label)
              .scaledFont(size: OmiType.caption)
              .foregroundStyle(HomePalette.secondary)
          }
          .padding(.horizontal, OmiSpacing.sm + 1)
          .padding(.vertical, OmiSpacing.xxs + 1)
          .background(Capsule().fill(Ink.rowFill))
          .accessibilityElement(children: .combine)
          .accessibilityLabel("\(chip.value) \(chip.label)")
        }
      }
      .accessibilityIdentifier("home-daily-summary-stats")
    }
  }

  /// Pure so the row's contents are testable: a nil or zero stat produces no chip, durations
  /// render as `2h 10m` / `45m`, and the order is fixed (time watched, moments, conversations,
  /// listening minutes, memories, tasks).
  nonisolated static func chips(for stats: DailySummaryRecord.Stats) -> [Chip] {
    var chips: [Chip] = []
    if let minutes = stats.watchingMinutes, minutes > 0 {
      chips.append(Chip(id: "watching", symbol: "eye", value: duration(minutes), label: "watching"))
    }
    if let moments = stats.proactiveMoments, moments > 0 {
      chips.append(Chip(id: "moments", symbol: "bell", value: "\(moments)", label: moments == 1 ? "moment" : "moments"))
    }
    if let conversations = stats.totalConversations, conversations > 0 {
      chips.append(
        Chip(
          id: "conversations", symbol: "bubble.left.and.bubble.right", value: "\(conversations)",
          label: conversations == 1 ? "conversation" : "conversations"))
    }
    if let minutes = stats.totalDurationMinutes, minutes > 0 {
      chips.append(Chip(id: "listening", symbol: "waveform", value: duration(minutes), label: "listening"))
    }
    if let memories = stats.memoriesCreated, memories > 0 {
      chips.append(
        Chip(id: "memories", symbol: "sparkles", value: "\(memories)", label: memories == 1 ? "memory" : "memories"))
    }
    let tasks = stats.actionItemsCreated ?? stats.actionItemsCount
    if let tasks, tasks > 0 {
      chips.append(
        Chip(id: "tasks", symbol: "checkmark.circle", value: "\(tasks)", label: tasks == 1 ? "task" : "tasks"))
    }
    return chips
  }

  nonisolated static func duration(_ minutes: Int) -> String {
    let hours = minutes / 60
    let rest = minutes % 60
    if hours == 0 { return "\(rest)m" }
    if rest == 0 { return "\(hours)h" }
    return "\(hours)h \(rest)m"
  }
}
