//
//  SpineHourRail.swift — the day as a shape you can aim at.
//
//  Twenty-four bars, one per hour, **late night at the top and midnight at the bottom**. That is the
//  whole point of the file. The spine is newest-first, so an *ascending* rail beside it — the
//  obvious way to draw a day — would put 6 AM at the top of a column whose top row is 11 PM, and the
//  two would disagree about which way time runs. That mismatch is the thing most timeline UIs ship,
//  and it is why nobody trusts the scrubber next to their feed.
//
//  The highlight tracks the hour of the **topmost visible row**, not a fraction of the scroll. Scroll
//  percentage is a lie about a list whose rows are different heights: a day of one conversation and a
//  day of forty occupy the same rail at the same speed. Reading the row that is actually under the
//  header means the marker says the hour you are looking at, which is the only thing it could
//  usefully say.
//

import OmiTheme
import SwiftUI

struct SpineHourRail: View {
  /// One entry per hour, indexed 0…23, each 0…1 against the day's own busiest hour.
  let density: [Double]
  /// The hour under the top of the list, or nil before anything has been read.
  let currentHour: Int?
  /// The headline: how much screen capture the day being read holds, or `nil` while that day's index
  /// is still being read. `nil` is not zero — see `headlineCaption`.
  let momentCount: Int?
  /// Which day all of the above is about — "Today", "Yesterday", "Wednesday 6 August". Printed as
  /// the headline's scope line; see `headlineScope`.
  let dayTitle: String
  /// The footer: what else that day held.
  let conversationCount: Int

  /// **The order the bars are drawn in, and the whole point of this file:** latest hour first, so
  /// the rail runs the same direction as the newest-first list beside it. A value rather than a
  /// `stride` buried in a `ForEach`, because it is the one thing here a test can hold.
  nonisolated static let renderedHours: [Int] = Array(stride(from: 23, through: 0, by: -1))

  /// Labelled hours. Four is enough to orient without turning the rail into an axis.
  private static let labelledHours: Set<Int> = [0, 6, 12, 18]

  /// A bar this fraction of the peak or more is drawn heavier. Not a hue — the rail is one ink at
  /// two weights, like every other ranking in this system.
  private static let hotThreshold = 0.6

  var body: some View {
    VStack(alignment: .leading, spacing: 12) {
      VStack(alignment: .leading, spacing: 2) {
        if let scope = Self.headlineScope(dayTitle) {
          Text(scope)
            .inkStyle(.statusLabel, color: Ink.secondary)
            .fixedSize(horizontal: false, vertical: true)
        }
        Text(Self.headlineNumber(momentCount))
          .inkStyle(.stepHeadline, color: Ink.primary)
          .lineLimit(1)
          .minimumScaleFactor(0.6)
        Text(Self.headlineCaption(momentCount))
          .inkStyle(.statusLabel, color: Ink.secondary)
      }

      bars

      if let footer = Self.footer(conversationCount: conversationCount) {
        Text(footer)
          .inkStyle(.statusLabel, color: Ink.secondary)
          .fixedSize(horizontal: false, vertical: true)
      }
    }
    .frame(width: 154, alignment: .leading)
    .padding(.horizontal, 14)
    .padding(.vertical, 16)
    .accessibilityElement(children: .ignore)
    .accessibilityLabel(
      Text(
        Self.readAloud(
          momentCount: momentCount,
          dayTitle: dayTitle,
          conversationCount: conversationCount,
          currentHour: currentHour)))
  }

  /// **The rail counts one day of screen capture; the panel's corner counts the whole account.**
  /// Both used to end in "moments captured", 200 points apart, so a day with no capture read as
  /// "0 moments captured" beside "446 moments captured" and looked like the rail had failed rather
  /// than like a quiet day.
  ///
  /// **The first fix renamed the noun — "screen moments" here, "moments" there — and it did not
  /// work.** The same reader looked at the same two numbers again and asked what each one was
  /// supposed to show. A different noun only tells you the counters are *not the same* if you read
  /// both, hold them side by side across the width of the window, and infer the scope neither one
  /// states. Nothing on the rail said "one day" and nothing in the corner said "everything", so the
  /// gap between `0` and `798` still read as a contradiction.
  ///
  /// So the rule is not "name the thing counted", it is **each counter states its own scope in its
  /// own words, and is legible alone.** `headlineScope` prints the day this number belongs to —
  /// "Today", "Yesterday", "Wednesday 6 August" — above the number it scopes. It comes from
  /// `dayTitle` rather than the literal word "today", because the rail follows the topmost visible
  /// row and describes whatever day that is. Do not go back to a scope-free caption: that is this
  /// defect, twice.
  ///
  /// The other half of the original defect was the number itself. Screen days are read lazily,
  /// three at a time, and a day that has not been read yet is indistinguishable in the store from a
  /// day with nothing on it — so the rail printed a confident `0` for a day it had not looked at,
  /// beside a five-figure account total. `nil` now means "not read yet" and says so; `0` means the
  /// read came back empty, which is a claim the rail is entitled to make. A scope line must never
  /// launder that distinction into a confident zero.
  ///
  /// `nonisolated` for the same reason `renderedHours` is: this is copy to read, not chrome to draw
  /// with.
  nonisolated static func headlineCaption(_ count: Int?) -> String {
    guard let count else { return "counting screen moments" }
    return count == 1 ? "screen moment" : "screen moments"
  }

  /// The day the headline number belongs to, printed above it — the rail's half of "state your own
  /// scope".
  ///
  /// It gets its own line rather than riding along with the noun because the day is not always a
  /// short word: at the rail's real content width of 154 pt, "screen moments today" fits at 129 pt
  /// of SF Pro 12 but "screen moments Wednesday 6 August" is nearly twice the column, and a scope
  /// that wraps or truncates is not a scope. Alone, every day this can print stays on one line —
  /// "Today" 34 pt, "Yesterday" 56 pt, "Wednesday 6 August" 120 pt, and the year-stamped form for
  /// older days 153 pt.
  ///
  /// `nil` when there is no day yet: an empty account has no scope to claim, and inventing one
  /// would be the confident-zero mistake in a second place.
  nonisolated static func headlineScope(_ dayTitle: String) -> String? {
    let trimmed = dayTitle.trimmingCharacters(in: .whitespacesAndNewlines)
    return trimmed.isEmpty ? nil : trimmed
  }

  /// An em dash rather than a `0` for the uncounted case: a placeholder that cannot be misread as a
  /// measurement.
  nonisolated static func headlineNumber(_ count: Int?) -> String {
    guard let count else { return "—" }
    return SpineFormat.number(count)
  }

  /// What else the day held. **The day's name used to lead this line** — "Today · 6 conversations"
  /// — which is where the rail's only scope word lived, twenty-four bars below the number it was
  /// supposed to scope. It has moved up to `headlineScope`; repeating it here would put "Today" on
  /// the rail twice, and a scope stated twice is a scope nobody reads once.
  ///
  /// `nil` rather than an empty string when the day holds no conversations, so the rail drops the
  /// line instead of drawing a blank one and speaking a sentence with a hole in it.
  nonisolated static func footer(conversationCount: Int) -> String? {
    guard conversationCount > 0 else { return nil }
    return SpineFormat.plural(conversationCount, "conversation", "conversations")
  }

  /// The whole rail as one spoken sentence, because the whole rail is one accessibility element.
  ///
  /// It has to say what is drawn: the scope leads here exactly as it leads on screen, so a reader
  /// who cannot see the two counters side by side is told which one this is — which is the entire
  /// point of the fix, and the case where comparing them across the window was never possible.
  nonisolated static func readAloud(
    momentCount: Int?,
    dayTitle: String,
    conversationCount: Int,
    currentHour: Int?
  ) -> String {
    // The em dash is a visual placeholder; spoken, it has to be the sentence it stands for.
    let count =
      momentCount == nil
      ? "Counting screen moments"
      : "\(headlineNumber(momentCount)) \(headlineCaption(momentCount))"
    var text = headlineScope(dayTitle).map { "\($0): \(count)." } ?? "\(count)."
    if let footer = footer(conversationCount: conversationCount) { text += " \(footer)." }
    if let currentHour { text += " Reading \(SpineFormat.hourLabel(currentHour))." }
    return text
  }

  /// The bars themselves, drawn 23 → 0 top to bottom.
  private var bars: some View {
    VStack(alignment: .leading, spacing: 0) {
      ForEach(Self.renderedHours, id: \.self) { hour in
        SpineHourBar(
          hour: hour,
          weight: density.indices.contains(hour) ? density[hour] : 0,
          isHot: (density.indices.contains(hour) ? density[hour] : 0) >= Self.hotThreshold,
          isCurrent: hour == currentHour,
          label: Self.labelledHours.contains(hour) ? SpineFormat.hourLabel(hour) : nil
        )
        .frame(maxHeight: .infinity)
      }
    }
    .frame(maxHeight: .infinity)
  }
}

/// One hour.
struct SpineHourBar: View {
  let hour: Int
  let weight: Double
  let isHot: Bool
  let isCurrent: Bool
  let label: String?

  /// The shortest a bar is ever drawn. An hour with nothing in it is still an hour, and a gap in the
  /// column would read as the rail having ended.
  private static let minimumWidth: CGFloat = 14
  private static let maximumExtra: CGFloat = 78

  /// The hour being read, when it is not one of the four the rail labels anyway.
  ///
  /// **The marker is the bar itself, not a band behind it.** A full-width wash across the current
  /// row was the first attempt and it read as a stray scrollbar — a long dark rule among short pale
  /// pills looks like chrome that escaped, not like "you are here". Now the current hour is simply
  /// the darkest bar with its hour named beside it: one object getting heavier, which is how every
  /// other ranking in this system is drawn, and unmistakably part of the rail.
  private var caption: String? {
    if let label { return label }
    return isCurrent ? SpineFormat.hourLabel(hour) : nil
  }

  var body: some View {
    HStack(spacing: 7) {
      Capsule()
        .fill(Ink.primary.opacity(isCurrent ? 0.85 : (isHot ? 0.42 : 0.2)))
        .frame(width: Self.minimumWidth + CGFloat(weight) * Self.maximumExtra, height: isCurrent ? 6 : 5)
      if let caption {
        Text(caption)
          .font(.system(size: 9, weight: isCurrent ? .semibold : .regular))
          .tracking(0.6)
          .foregroundStyle(isCurrent ? Ink.primary : Ink.secondary)
          .lineLimit(1)
          .fixedSize()
      }
    }
    .frame(maxWidth: .infinity, alignment: .leading)
  }
}
