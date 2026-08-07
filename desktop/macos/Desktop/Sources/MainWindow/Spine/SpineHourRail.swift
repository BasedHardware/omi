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
  /// The headline: how much was captured on the day being read.
  let momentCount: Int
  /// The footer: what else that day held.
  let dayTitle: String
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
        Text(SpineFormat.number(momentCount))
          .inkStyle(.stepHeadline, color: Ink.primary)
          .lineLimit(1)
          .minimumScaleFactor(0.6)
        Text(Self.headlineCaption(momentCount))
          .inkStyle(.statusLabel, color: Ink.secondary)
      }

      bars

      Text(footer)
        .inkStyle(.statusLabel, color: Ink.secondary)
        .fixedSize(horizontal: false, vertical: true)
    }
    .frame(width: 154, alignment: .leading)
    .padding(.horizontal, 14)
    .padding(.vertical, 16)
    .accessibilityElement(children: .ignore)
    .accessibilityLabel(Text(readAloud))
  }

  /// **The rail counts one day; the panel's corner counts the whole account.** Both used to end in
  /// "moments captured", 200 points apart, so a day with no capture read as "0 moments captured"
  /// beside "446 moments captured" and looked like the rail had failed rather than like a quiet day.
  /// Naming the thing being counted is what tells them apart — the number stays the number.
  static func headlineCaption(_ count: Int) -> String {
    count == 1 ? "screen moment" : "screen moments"
  }

  private var footer: String {
    var parts = [dayTitle]
    if conversationCount > 0 {
      parts.append(SpineFormat.plural(conversationCount, "conversation", "conversations"))
    }
    return parts.joined(separator: " · ")
  }

  private var readAloud: String {
    var text =
      "\(SpineFormat.number(momentCount)) \(Self.headlineCaption(momentCount)). \(footer)."
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
