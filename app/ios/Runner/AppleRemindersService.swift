import Foundation
import EventKit
import Flutter

class AppleRemindersService {
    private let eventStore = EKEventStore()
    
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
        default:
            result(FlutterMethodNotImplemented)
        }
    }
    
    private func hasRemindersPermission(result: @escaping FlutterResult) {
        let status = EKEventStore.authorizationStatus(for: .reminder)
        result(status == .authorized)
    }
    
    private func requestRemindersPermission(result: @escaping FlutterResult) {
        let status = EKEventStore.authorizationStatus(for: .reminder)
        
        if status == .authorized {
            result(true)
            return
        }
        
        if status == .denied || status == .restricted {
            result(false)
            return
        }
        
        // Request permission
        eventStore.requestAccess(to: .reminder) { granted, error in
            DispatchQueue.main.async {
                if let error = error {
                    print("Error requesting reminders permission: \(error.localizedDescription)")
                    result(false)
                    return
                }
                result(granted)
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
        let status = EKEventStore.authorizationStatus(for: .reminder)
        guard status == .authorized else {
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
                print("Error creating calendar: \(error.localizedDescription)")
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
            print("Error saving reminder: \(error.localizedDescription)")
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
        let status = EKEventStore.authorizationStatus(for: .reminder)
        guard status == .authorized else {
            result([]) // Return empty array if no permission
            return
        }
        
        // Find the calendar
        let calendars = eventStore.calendars(for: .reminder)
        guard let targetCalendar = calendars.first(where: { $0.title == listName }) else {
            result([]) // Return empty array if calendar not found
            return
        }
        
        // Create predicate to fetch reminders from this calendar
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
        let status = EKEventStore.authorizationStatus(for: .reminder)
        guard status == .authorized else {
            result(false) // Return false if no permission
            return
        }
        
        // Find the calendar
        let calendars = eventStore.calendars(for: .reminder)
        guard let targetCalendar = calendars.first(where: { $0.title == listName }) else {
            result(false) // Return false if calendar not found
            return
        }
        
        // Create predicate to fetch reminders from this calendar
        let predicate = eventStore.predicateForReminders(in: [targetCalendar])
        
        eventStore.fetchReminders(matching: predicate) { reminders in
            DispatchQueue.main.async {
                guard let targetReminder = reminders?.first(where: { $0.title == title && !$0.isCompleted }) else {
                    result(false) // Reminder not found or already completed
                    return
                }
                
                // Mark the reminder as completed
                targetReminder.isCompleted = true
                
                do {
                    try self.eventStore.save(targetReminder, commit: true)
                    result(true)
                } catch {
                    print("Error completing reminder: \(error.localizedDescription)")
                    result(false)
                }
            }
        }
    }
} 