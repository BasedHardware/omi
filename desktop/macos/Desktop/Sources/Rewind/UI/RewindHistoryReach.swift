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
  static func spanLabel(days: [Date], surveyed: Bool, calendar: Calendar = .current) -> String {
    guard surveyed else { return "Checking how far back your capture goes…" }
    guard let newest = days.first, let oldest = days.last else { return "No screen capture yet" }

    let formatter = DateFormatter()
    formatter.calendar = calendar
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
