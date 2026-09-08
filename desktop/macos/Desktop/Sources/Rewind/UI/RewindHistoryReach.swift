//
//  RewindHistoryReach.swift — how far back Rewind goes, said out loud.
//
//  Rewind plays one day at a time, which makes "how much do I have" a question the surface has to
//  answer in words rather than by being scrolled. Two different absences have to survive that
//  translation and they are *not* the same claim:
//
//    • the capture database has not been surveyed yet — the honest word is "checking"
//    • the survey finished and found nothing — the honest word is "none"
//
//  Collapsing them prints a confident "no screen capture" over an account with months of it, which
//  is the exact defect this surface has already been fixed for once on the hour rail. The `surveyed`
//  flag is that distinction, made explicit at the boundary rather than inferred from an empty array.
//
//  Pure and free of SwiftUI so the wording is a hermetic test rather than a screenshot.
//

import Foundation

enum RewindHistoryReach {

  /// One line stating the true span of retained capture.
  ///
  /// - Parameters:
  ///   - days: local start-of-day instants that hold capture, newest first.
  ///   - surveyed: whether the walk over the capture database has finished at least once.
  ///   - calendar: the calendar the days were bucketed in — and, therefore, the one they are named in.
  ///   - locale: how the resulting dates are worded; the user's, so the label reads in their language.
  static func spanLabel(
    days: [Date], surveyed: Bool, calendar: Calendar = .current, locale: Locale = .current
  ) -> String {
    guard surveyed else { return "Checking how far back your capture goes…" }
    guard let newest = days.first, let oldest = days.last else { return "No screen capture yet" }

    let formatter = DateFormatter()
    formatter.calendar = calendar
    // **A day has to be named in the zone it was bucketed in.** `days` are start-of-day instants
    // produced by `capturedDayStarts(calendar:)`, so they mean midnight *in that calendar's zone*.
    // `DateFormatter.timeZone` does not follow `formatter.calendar`: left unset it is the machine's,
    // and rendering another zone's midnight in the machine's zone prints the day before or the day
    // after for every caller whose calendar is not `.current` — `SpineStore` already passes its own.
    // The label would then disagree with the day the popover jumps to, which is the whole contract.
    formatter.timeZone = calendar.timeZone
    formatter.locale = locale
    formatter.dateStyle = .medium
    formatter.timeStyle = .none

    if days.count == 1 {
      return "1 day of capture · \(formatter.string(from: newest))"
    }
    return "\(days.count) days of capture · \(formatter.string(from: oldest)) – \(formatter.string(from: newest))"
  }

  /// Why the span stops where it does — the deletion window, or the absence of one.
  ///
  /// The span alone reads as a fact about the user's habits ("I only have a week") when it is
  /// really a fact about a setting they can change. Naming the setting next to the span is the
  /// difference between a limit and a mystery.
  static func retentionNote(retentionDays: Int) -> String {
    if RewindSettings.isUnlimited(retentionDays: retentionDays) {
      return "Keeping everything — nothing is deleted"
    }
    let unit = retentionDays == 1 ? "day" : "days"
    return "Capture older than \(retentionDays) \(unit) is deleted"
  }
}
