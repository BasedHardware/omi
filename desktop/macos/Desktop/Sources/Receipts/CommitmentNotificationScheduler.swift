import Foundation
import UserNotifications

/// Schedules local macOS notifications for commitment deadlines.
/// This is the first component in the app to use `UNTimeIntervalNotificationTrigger`
/// for time-based scheduling (existing notifications are all immediate).
struct CommitmentNotificationScheduler {
  static let shared = CommitmentNotificationScheduler()

  private let reminderLeadTime: TimeInterval = 60 * 60 * 2  // 2 hours before deadline
  private let notificationPrefix = "commitment-deadline-"

  private init() {}

  // MARK: - Scheduling

  /// Schedule a reminder notification for a commitment deadline.
  /// Fires 2 hours before the deadline (or immediately if < 2h away).
  func scheduleReminder(for commitment: CommitmentRecord) {
    guard let id = commitment.id,
          let deadline = commitment.deadline else { return }

    let identifier = notificationPrefix + "\(id)"
    cancelReminder(commitmentId: id)

    let fireDate = deadline.addingTimeInterval(-reminderLeadTime)
    let interval = fireDate.timeIntervalSinceNow

    guard interval > 1 else {
      scheduleImmediateReminder(for: commitment)
      return
    }

    let content = UNMutableNotificationContent()
    content.title = "Commitment Due Soon"
    content.body = commitment.text
    content.sound = .default
    content.categoryIdentifier = "omi.trackable"

    let trigger = UNTimeIntervalNotificationTrigger(timeInterval: interval, repeats: false)
    let request = UNNotificationRequest(
      identifier: identifier,
      content: content,
      trigger: trigger
    )

    UNUserNotificationCenter.current().add(request) { error in
      if let error = error {
        log("CommitmentNotificationScheduler: Failed to schedule: \(error.localizedDescription)")
      }
    }
  }

  /// Send an immediate reminder (deadline is within the lead time or already passed).
  private func scheduleImmediateReminder(for commitment: CommitmentRecord) {
    guard let id = commitment.id else { return }

    let content = UNMutableNotificationContent()
    content.title = "Commitment Due Now"
    content.body = commitment.text
    content.sound = .default
    content.categoryIdentifier = "omi.trackable"

    let request = UNNotificationRequest(
      identifier: notificationPrefix + "\(id)",
      content: content,
      trigger: nil
    )

    UNUserNotificationCenter.current().add(request) { error in
      if let error = error {
        log("CommitmentNotificationScheduler: Failed to send immediate: \(error.localizedDescription)")
      }
    }
  }

  // MARK: - Cancellation

  func cancelReminder(commitmentId: Int64) {
    let identifier = notificationPrefix + "\(commitmentId)"
    UNUserNotificationCenter.current().removePendingNotificationRequests(
      withIdentifiers: [identifier]
    )
  }

  /// Cancel all scheduled commitment notifications.
  func cancelAll() {
    let center = UNUserNotificationCenter.current()
    center.getPendingNotificationRequests { requests in
      let ids = requests
        .filter { $0.identifier.hasPrefix("commitment-deadline-") }
        .map { $0.identifier }
      if !ids.isEmpty {
        center.removePendingNotificationRequests(withIdentifiers: ids)
      }
    }
  }

  // MARK: - Missed Commitment Notification

  /// Notify the user that a commitment deadline passed without fulfillment.
  func notifyMissed(_ commitment: CommitmentRecord) {
    guard let id = commitment.id else { return }

    let content = UNMutableNotificationContent()
    content.title = "Commitment Missed"
    content.body = "Deadline passed: \(commitment.text)"
    content.sound = .default
    content.categoryIdentifier = "omi.trackable"

    let request = UNNotificationRequest(
      identifier: notificationPrefix + "missed-\(id)",
      content: content,
      trigger: nil
    )

    UNUserNotificationCenter.current().add(request) { error in
      if let error = error {
        log("CommitmentNotificationScheduler: Failed to notify missed: \(error.localizedDescription)")
      }
    }
  }
}
