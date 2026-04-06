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

    static let iso8601DateFormatter = ISO8601DateFormatter()

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
        case "getRemindersStatus":
            getRemindersStatus(call: call, result: result)
        case "updateReminder":
            updateReminder(call: call, result: result)
        case "deleteReminder":
            deleteReminder(call: call, result: result)
        default:
            result(FlutterMethodNotImplemented)
        }
    }

    // MARK: - Batch Sync (FCM path)

    /// Core batch sync logic shared by both the foreground MethodChannel path
    /// and the background silent-push path (called from AppDelegate).
    /// Returns an array of mappings: [{"actionItemId": "...", "calendarItemIdentifier": "..."}]
    func syncBatchFromJSON(_ itemsJson: String) -> [[String: String]] {
        guard let data = itemsJson.data(using: .utf8),
              let items = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]],
              !items.isEmpty else {
            return []
        }

        guard hasRemindersAccess() else { return [] }
        guard let calendar = eventStore.defaultCalendarForNewReminders() else { return [] }

        var createdReminders: [(EKReminder, String)] = [] // (reminder, actionItemId)

        for item in items {
            guard let actionItemId = item["id"] as? String,
                  let reminderTitle = item["description"] as? String else {
                continue
            }

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
                createdReminders.append((reminder, actionItemId))
            } catch {
                continue
            }
        }

        guard !createdReminders.isEmpty else { return [] }

        do {
            try eventStore.commit()
        } catch {
            return []
        }

        // Build mappings with calendarItemIdentifier
        return createdReminders.map { reminder, actionItemId in
            [
                "actionItemId": actionItemId,
                "calendarItemIdentifier": reminder.calendarItemIdentifier
            ]
        }
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

    // MARK: - Bidirectional Sync Methods

    /// Batch lookup reminder status by calendarItemIdentifier.
    /// Input: {"mappings": {"actionItemId": "calendarItemIdentifier", ...}}
    /// Output: {"actionItemId": {"exists": bool, "completed": bool, "title": str, ...}, ...}
    private func getRemindersStatus(call: FlutterMethodCall, result: @escaping FlutterResult) {
        guard let args = call.arguments as? [String: Any],
              let mappings = args["mappings"] as? [String: String] else {
            result(FlutterError(code: "INVALID_ARGUMENTS", message: "Missing mappings", details: nil))
            return
        }

        guard hasRemindersAccess() else {
            result(FlutterError(code: "PERMISSION_DENIED", message: "No reminders access", details: nil))
            return
        }

        var statuses: [String: [String: Any]] = [:]

        for (actionItemId, calendarItemId) in mappings {
            guard let calendarItem = eventStore.calendarItem(withIdentifier: calendarItemId),
                  let reminder = calendarItem as? EKReminder else {
                statuses[actionItemId] = ["exists": false]
                continue
            }

            var status: [String: Any] = [
                "exists": true,
                "completed": reminder.isCompleted,
                "title": reminder.title ?? "",
            ]

            if let completionDate = reminder.completionDate {
                status["completionDate"] = AppleRemindersService.iso8601DateFormatter.string(from: completionDate)
            }

            if let dueDateComponents = reminder.dueDateComponents,
               let dueDate = Calendar.current.date(from: dueDateComponents) {
                status["dueDate"] = AppleRemindersService.iso8601DateFormatter.string(from: dueDate)
            }

            if let lastModified = reminder.lastModifiedDate {
                status["lastModifiedDate"] = AppleRemindersService.iso8601DateFormatter.string(from: lastModified)
            }

            statuses[actionItemId] = status
        }

        result(statuses)
    }

    /// Update an existing reminder by calendarItemIdentifier.
    private func updateReminder(call: FlutterMethodCall, result: @escaping FlutterResult) {
        guard let args = call.arguments as? [String: Any],
              let calendarItemId = args["calendarItemIdentifier"] as? String else {
            result(FlutterError(code: "INVALID_ARGUMENTS", message: "Missing calendarItemIdentifier", details: nil))
            return
        }

        guard hasRemindersAccess() else {
            result(["success": false, "exists": false])
            return
        }

        guard let calendarItem = eventStore.calendarItem(withIdentifier: calendarItemId),
              let reminder = calendarItem as? EKReminder else {
            result(["success": false, "exists": false])
            return
        }

        if let title = args["title"] as? String {
            reminder.title = title
        }

        if let completed = args["completed"] as? Bool {
            reminder.isCompleted = completed
            if completed {
                reminder.completionDate = Date()
            }
        }

        if let dueDateMs = args["dueDate"] as? Int64 {
            let dueDate = Date(timeIntervalSince1970: TimeInterval(dueDateMs) / 1000.0)
            reminder.dueDateComponents = Calendar.current.dateComponents(
                [.year, .month, .day, .hour, .minute], from: dueDate
            )
        }

        do {
            try eventStore.save(reminder, commit: true)
            result(["success": true, "exists": true])
        } catch {
            result(["success": false, "exists": true])
        }
    }

    /// Delete a reminder by calendarItemIdentifier. Idempotent.
    private func deleteReminder(call: FlutterMethodCall, result: @escaping FlutterResult) {
        guard let args = call.arguments as? [String: Any],
              let calendarItemId = args["calendarItemIdentifier"] as? String else {
            result(FlutterError(code: "INVALID_ARGUMENTS", message: "Missing calendarItemIdentifier", details: nil))
            return
        }

        guard hasRemindersAccess() else {
            result(["success": false, "existed": false])
            return
        }

        guard let calendarItem = eventStore.calendarItem(withIdentifier: calendarItemId),
              let reminder = calendarItem as? EKReminder else {
            // Already gone — idempotent success
            result(["success": true, "existed": false])
            return
        }

        do {
            try eventStore.remove(reminder, commit: true)
            result(["success": true, "existed": true])
        } catch {
            result(["success": false, "existed": true])
        }
    }

    // MARK: - Permission Methods

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

    // MARK: - Single Reminder CRUD

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

        guard hasRemindersAccess() else {
            result(FlutterError(code: "PERMISSION_DENIED", message: "Reminders permission not granted", details: nil))
            return
        }

        // Find or create the calendar
        var targetCalendar: EKCalendar?
        let calendars = eventStore.calendars(for: .reminder)
        targetCalendar = calendars.first { $0.title == listName }

        if targetCalendar == nil {
            targetCalendar = EKCalendar(for: .reminder, eventStore: eventStore)
            targetCalendar?.title = listName
            targetCalendar?.cgColor = UIColor.systemBlue.cgColor

            if let defaultSource = eventStore.defaultCalendarForNewReminders()?.source {
                targetCalendar?.source = defaultSource
            }

            do {
                try eventStore.saveCalendar(targetCalendar!, commit: true)
            } catch {
                targetCalendar = eventStore.defaultCalendarForNewReminders()
            }
        }

        guard let calendar = targetCalendar else {
            result(FlutterError(code: "NO_CALENDAR", message: "Could not find or create calendar", details: nil))
            return
        }

        let reminder = EKReminder(eventStore: eventStore)
        reminder.title = title
        reminder.notes = notes
        reminder.calendar = calendar

        if let dueDate = dueDate {
            reminder.dueDateComponents = Calendar.current.dateComponents(
                [.year, .month, .day, .hour, .minute], from: dueDate
            )
        }

        do {
            try eventStore.save(reminder, commit: true)
            // Return the calendarItemIdentifier for storage
            result(reminder.calendarItemIdentifier)
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

        guard hasRemindersAccess() else {
            result([])
            return
        }

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

        guard hasRemindersAccess() else {
            result(false)
            return
        }

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
