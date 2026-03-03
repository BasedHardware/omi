import Foundation
import EventKit
import Flutter

class AppleRemindersService {
    private let eventStore = EKEventStore()

    private func hasRemindersAccess() -> Bool {
        let status = EKEventStore.authorizationStatus(for: .reminder)
        if #available(iOS 17.0, *) {
            return status == .fullAccess || status == .writeOnly || status == .authorized
        } else {
            return status == .authorized
        }
    }

    func handleMethodCall(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
        switch call.method {
        case "hasPermission":
            hasRemindersPermission(result: result)
        case "requestPermission":
            requestRemindersPermission(result: result)
        case "addReminder":
            addReminder(call: call, result: result)
        case "getReminders":
            getReminders(call: call, result: result)
        case "completeReminder":
            completeReminder(call: call, result: result)
        case "syncFromFCM":
            syncFromFCM(call: call, result: result)
        default:
            result(FlutterMethodNotImplemented)
        }
    }

    static let syncedItemsKey = "omi_synced_action_items"
    static let iso8601DateFormatter = ISO8601DateFormatter()

    /// Core batch sync logic shared by both the foreground MethodChannel path
    /// and the background silent-push path (called from AppDelegate).
    /// Returns the list of action item IDs that were successfully created as reminders.
    func syncBatchFromJSON(_ itemsJson: String) -> [String] {
        guard let data = itemsJson.data(using: .utf8),
              let items = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]],
              !items.isEmpty else {
            return []
        }

        guard hasRemindersAccess() else { return [] }
        guard let calendar = eventStore.defaultCalendarForNewReminders() else { return [] }

        var syncedIds = Set(UserDefaults.standard.stringArray(forKey: AppleRemindersService.syncedItemsKey) ?? [])
        var exportedIds: [String] = []

        for item in items {
            guard let actionItemId = item["id"] as? String,
                  let reminderTitle = item["description"] as? String else {
                continue
            }

            if syncedIds.contains(actionItemId) { continue }

            let dueDate: Date? = {
                if let dueDateStr = item["due_at"] as? String, !dueDateStr.isEmpty {
                    return AppleRemindersService.iso8601DateFormatter.date(from: dueDateStr)
                }
                return nil
            }()

            let reminder = EKReminder(eventStore: eventStore)
            reminder.title = reminderTitle
            reminder.notes = "From Omi"
            reminder.calendar = calendar

            if let due = dueDate {
                reminder.dueDateComponents = Calendar.current.dateComponents(
                    [.year, .month, .day, .hour, .minute], from: due
                )
            }

            do {
                try eventStore.save(reminder, commit: false)
                syncedIds.insert(actionItemId)
                exportedIds.append(actionItemId)
            } catch {
                continue
            }
        }

        // Single commit for all reminders
        if !exportedIds.isEmpty {
            do {
                try eventStore.commit()
            } catch {
                return []
            }
        }

        // Persist dedup set
        var syncedArray = Array(syncedIds)
        if syncedArray.count > 100 {
            syncedArray = Array(syncedArray.suffix(100))
        }
        UserDefaults.standard.set(syncedArray, forKey: AppleRemindersService.syncedItemsKey)

        return exportedIds
    }

    /// Handle sync triggered from Flutter foreground FCM handler via MethodChannel.
    private func syncFromFCM(call: FlutterMethodCall, result: @escaping FlutterResult) {
        guard let args = call.arguments as? [String: Any],
              let itemsJson = args["items"] as? String else {
            result(FlutterError(code: "INVALID_ARGUMENTS", message: "Missing or invalid items payload", details: nil))
            return
        }
        result(syncBatchFromJSON(itemsJson))
    }

    private func hasRemindersPermission(result: @escaping FlutterResult) {
        result(hasRemindersAccess())
    }

    private func requestRemindersPermission(result: @escaping FlutterResult) {
        if hasRemindersAccess() {
            result(true)
            return
        }

        let status = EKEventStore.authorizationStatus(for: .reminder)
        if status == .denied || status == .restricted {
            result(false)
            return
        }

        Task {
            do {
                var granted: Bool
                if #available(iOS 17.0, *) {
                    granted = try await eventStore.requestFullAccessToReminders()
                } else {
                    granted = try await eventStore.requestAccess(to: .reminder)
                }
                DispatchQueue.main.async { result(granted) }
            } catch {
                DispatchQueue.main.async { result(false) }
            }
        }
    }

    private func addReminder(call: FlutterMethodCall, result: @escaping FlutterResult) {
        guard let args = call.arguments as? [String: Any] else {
            result(FlutterError(code: "INVALID_ARGUMENTS", message: "Invalid arguments", details: nil))
            return
        }

        guard let title = args["title"] as? String else {
            result(FlutterError(code: "MISSING_TITLE", message: "Title is required", details: nil))
            return
        }

        let notes = args["notes"] as? String
        let listName = args["listName"] as? String ?? "Reminders"
        let dueDate: Date? = {
            if let dueDateMs = args["dueDate"] as? Int64 {
                return Date(timeIntervalSince1970: TimeInterval(dueDateMs) / 1000.0)
            }
            return nil
        }()

        // Check permission
        guard hasRemindersAccess() else {
            result(FlutterError(code: "PERMISSION_DENIED", message: "Reminders permission not granted", details: nil))
            return
        }

        // Find or create the calendar
        var targetCalendar: EKCalendar?

        // Look for existing calendar with the specified name
        let calendars = eventStore.calendars(for: .reminder)
        targetCalendar = calendars.first { $0.title == listName }

        // If not found, create a new calendar
        if targetCalendar == nil {
            targetCalendar = EKCalendar(for: .reminder, eventStore: eventStore)
            targetCalendar?.title = listName
            targetCalendar?.cgColor = UIColor.systemBlue.cgColor

            // Set the source (usually the local source)
            if let localSource = eventStore.sources.first(where: { $0.sourceType == .local }) {
                targetCalendar?.source = localSource
            } else if let defaultSource = eventStore.defaultCalendarForNewReminders()?.source {
                targetCalendar?.source = defaultSource
            }

            do {
                try eventStore.saveCalendar(targetCalendar!, commit: true)
            } catch {
                // Fall back to default calendar
                targetCalendar = eventStore.defaultCalendarForNewReminders()
            }
        }

        guard let calendar = targetCalendar else {
            result(FlutterError(code: "NO_CALENDAR", message: "Could not find or create calendar", details: nil))
            return
        }

        // Create the reminder
        let reminder = EKReminder(eventStore: eventStore)
        reminder.title = title
        reminder.notes = notes
        reminder.calendar = calendar

        if let dueDate = dueDate {
            let dueDateComponents = Calendar.current.dateComponents([.year, .month, .day, .hour, .minute], from: dueDate)
            reminder.dueDateComponents = dueDateComponents
        }

        // Save the reminder
        do {
            try eventStore.save(reminder, commit: true)
            result(true)
        } catch {
            result(FlutterError(code: "SAVE_FAILED", message: "Failed to save reminder: \(error.localizedDescription)", details: nil))
        }
    }

    private func getReminders(call: FlutterMethodCall, result: @escaping FlutterResult) {
        guard let args = call.arguments as? [String: Any] else {
            result(FlutterError(code: "INVALID_ARGUMENTS", message: "Invalid arguments", details: nil))
            return
        }

        let listName = args["listName"] as? String ?? "Reminders"

        // Check permission
        guard hasRemindersAccess() else {
            result([])
            return
        }

        // Find the calendar
        let calendars = eventStore.calendars(for: .reminder)
        guard let targetCalendar = calendars.first(where: { $0.title == listName }) else {
            result([])
            return
        }

        let predicate = eventStore.predicateForReminders(in: [targetCalendar])

        eventStore.fetchReminders(matching: predicate) { reminders in
            DispatchQueue.main.async {
                let reminderTitles = reminders?.compactMap { $0.title } ?? []
                result(reminderTitles)
            }
        }
    }

    private func completeReminder(call: FlutterMethodCall, result: @escaping FlutterResult) {
        guard let args = call.arguments as? [String: Any] else {
            result(FlutterError(code: "INVALID_ARGUMENTS", message: "Invalid arguments", details: nil))
            return
        }

        guard let title = args["title"] as? String else {
            result(FlutterError(code: "MISSING_TITLE", message: "Title is required", details: nil))
            return
        }

        let listName = args["listName"] as? String ?? "Reminders"

        // Check permission
        guard hasRemindersAccess() else {
            result(false)
            return
        }

        // Find the calendar
        let calendars = eventStore.calendars(for: .reminder)
        guard let targetCalendar = calendars.first(where: { $0.title == listName }) else {
            result(false)
            return
        }

        let predicate = eventStore.predicateForReminders(in: [targetCalendar])

        eventStore.fetchReminders(matching: predicate) { reminders in
            DispatchQueue.main.async {
                guard let targetReminder = reminders?.first(where: { $0.title == title && !$0.isCompleted }) else {
                    result(false)
                    return
                }

                targetReminder.isCompleted = true

                do {
                    try self.eventStore.save(targetReminder, commit: true)
                    result(true)
                } catch {
                    result(false)
                }
            }
        }
    }
}
