import Foundation

/// Completion-driven recurrence date arithmetic, independent of task storage.
///
/// Preserve sequential calendar addition: a month-end clamp or a daylight
/// saving adjustment becomes the input to the following occurrence. Jumping
/// several periods directly from the original date is not equivalent.
enum TaskRecurrenceDatePolicy {
  typealias DateAddition = (Calendar.Component, Int, Date) -> Date?

  static func nextDueDate(
    from dueDate: Date,
    rule: String,
    now: Date,
    calendar: Calendar,
    addDate: DateAddition? = nil
  ) -> Date? {
    guard dueDate.timeIntervalSinceReferenceDate.isFinite,
      now.timeIntervalSinceReferenceDate.isFinite
    else { return nil }

    let addition =
      addDate ?? { component, value, date in
        calendar.date(byAdding: component, value: value, to: date)
      }

    func advance(_ date: Date, component: Calendar.Component, value: Int) -> Date? {
      guard let next = addition(component, value, date),
        next.timeIntervalSinceReferenceDate.isFinite,
        next > date
      else { return nil }
      return next
    }

    func nextOccurrence(after date: Date) -> Date? {
      switch rule {
      case "daily":
        return advance(date, component: .day, value: 1)
      case "weekdays":
        guard var next = advance(date, component: .day, value: 1) else { return nil }
        while calendar.isDateInWeekend(next) {
          guard let following = advance(next, component: .day, value: 1) else { return nil }
          next = following
        }
        return next
      case "weekly":
        return advance(date, component: .weekOfYear, value: 1)
      case "biweekly":
        return advance(date, component: .weekOfYear, value: 2)
      case "monthly":
        return advance(date, component: .month, value: 1)
      default:
        return nil
      }
    }

    guard var next = nextOccurrence(after: dueDate) else { return nil }
    // Missed occurrences are skipped, not materialized. Equality deliberately
    // remains eligible, matching the existing completion path's `< now` rule.
    while next < now {
      guard let following = nextOccurrence(after: next) else { return nil }
      next = following
    }
    return next
  }
}
