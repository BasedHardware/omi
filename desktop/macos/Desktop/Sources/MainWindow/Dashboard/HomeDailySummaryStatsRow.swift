import OmiTheme
import SwiftUI

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
