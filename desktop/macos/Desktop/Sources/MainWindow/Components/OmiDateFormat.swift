//
//  OmiDateFormat.swift — every user-visible date, time and duration.
//
//  The Memories hub alone had nine hand-written formats: "Sep 23, 2026 from 10:17 AM to 11:19 AM",
//  "Yesterday, 10:43 AM", "Wednesday 23 September" (British order beside US order one tab over), a
//  lowercase "yesterday 3:04 PM", "MMM d", and transcript offsets that read "62:05" for an hour-long
//  meeting. Every one of them was a fixed `dateFormat` string, so none respected the user's locale
//  or 24-hour clock.
//
//  These are the styles. Each is built on `Date.FormatStyle`, which follows the system locale and
//  clock setting, and each is a pure function of its inputs (`now`, `calendar`, `locale`) so a test
//  can pin it. New UI picks a style here; it does not construct a `DateFormatter`.
//
//  See `docs/ux-contract.md` (INV-UI-2).
//

import Foundation

enum OmiDateFormat {
  /// "10:43 AM" — a time on a day the context already names (a row inside a "Today" group).
  static func time(
    _ date: Date, calendar: Calendar = .autoupdatingCurrent, locale: Locale = .autoupdatingCurrent
  ) -> String {
    date.formatted(style(calendar, locale).hour().minute())
  }

  /// A `Date.FormatStyle` in the caller's calendar, time zone and locale. Every style below starts
  /// here, so the day a date is *grouped* under and the day it is *printed* as can never disagree.
  private static func style(_ calendar: Calendar, _ locale: Locale) -> Date.FormatStyle {
    Date.FormatStyle(locale: locale, calendar: calendar, timeZone: calendar.timeZone)
  }

  /// A group header: "Today", "Yesterday", "Wednesday, Sep 23", or "Sep 23, 2025" in another year.
  static func dayHeader(
    _ date: Date, now: Date = Date(), calendar: Calendar = .autoupdatingCurrent,
    locale: Locale = .autoupdatingCurrent
  ) -> String {
    if calendar.isDate(date, inSameDayAs: now) { return "Today" }
    if let yesterday = calendar.date(byAdding: .day, value: -1, to: now),
      calendar.isDate(date, inSameDayAs: yesterday)
    {
      return "Yesterday"
    }
    if calendar.isDate(date, equalTo: now, toGranularity: .year) {
      return date.formatted(style(calendar, locale).weekday(.wide).month(.abbreviated).day())
    }
    return date.formatted(style(calendar, locale).month(.abbreviated).day().year())
  }

  /// A timestamp that stands on its own (no group header to lean on):
  /// "10:43 AM", "Yesterday, 10:43 AM", "Sep 21, 10:43 AM", "Sep 21, 2025, 10:43 AM".
  static func timestamp(
    _ date: Date, now: Date = Date(), calendar: Calendar = .autoupdatingCurrent,
    locale: Locale = .autoupdatingCurrent
  ) -> String {
    if calendar.isDate(date, inSameDayAs: now) { return time(date, calendar: calendar, locale: locale) }
    if let yesterday = calendar.date(byAdding: .day, value: -1, to: now),
      calendar.isDate(date, inSameDayAs: yesterday)
    {
      return "Yesterday, \(time(date, calendar: calendar, locale: locale))"
    }
    if calendar.isDate(date, equalTo: now, toGranularity: .year) {
      return date.formatted(style(calendar, locale).month(.abbreviated).day().hour().minute())
    }
    return date.formatted(style(calendar, locale).month(.abbreviated).day().year().hour().minute())
  }

  /// A span: "Sep 23, 2026, 10:17 – 11:19 AM". A missing end reads as the start alone.
  static func range(
    _ start: Date, _ end: Date?, calendar: Calendar = .autoupdatingCurrent, locale: Locale = .autoupdatingCurrent
  ) -> String {
    guard let end, end > start else {
      return start.formatted(style(calendar, locale).month(.abbreviated).day().year().hour().minute())
    }
    let interval = Date.IntervalFormatStyle(
      date: .abbreviated, time: .shortened, locale: locale, calendar: calendar, timeZone: calendar.timeZone)
    return (start..<end).formatted(interval)
  }

  /// "just now", "5 min ago", "2 hr ago", "yesterday" — for freshness, never as the only date.
  static func relative(_ date: Date, now: Date = Date(), locale: Locale = .autoupdatingCurrent) -> String {
    if abs(now.timeIntervalSince(date)) < 60 { return "just now" }
    return date.formatted(.relative(presentation: .named, unitsStyle: .abbreviated).locale(locale))
  }

  /// A position inside a recording: "3:38", "1:02:05". Hours appear once the recording needs them,
  /// so an hour-long meeting never reads "62:05".
  static func offset(_ seconds: Double) -> String {
    let total = max(0, Int(seconds.rounded(.down)))
    let hours = total / 3600
    let minutes = (total % 3600) / 60
    let secs = total % 60
    if hours > 0 { return String(format: "%d:%02d:%02d", hours, minutes, secs) }
    return String(format: "%d:%02d", minutes, secs)
  }

  /// A length: "8s", "42m 10s", "1h 5m".
  static func duration(_ seconds: Double) -> String {
    let total = max(0, Int(seconds.rounded(.down)))
    if total < 60 { return "\(total)s" }
    let hours = total / 3600
    let minutes = (total % 3600) / 60
    if hours == 0 { return "\(minutes)m \(total % 60)s" }
    return minutes == 0 ? "\(hours)h" : "\(hours)h \(minutes)m"
  }
}
