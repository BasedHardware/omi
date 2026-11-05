import EventKit
import Foundation
import OmiCore

/// Apple Reminders through EventKit, in a list named "Omi" (created once, then found by its
/// identifier, so renaming it keeps working and no second list appears). Without that list the
/// default reminders list is used, as in Flutter's `AppleRemindersService`.
@MainActor
public final class EventKitReminders: RemindersAdapter {
    private let store = EKEventStore()
    private let defaults: UserDefaults
    private static let listKey = "omi.reminders.listIdentifier"
    static let listTitle = "Omi"

    public init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
    }

    public var hasAccess: Bool {
        EKEventStore.authorizationStatus(for: .reminder) == .fullAccess
    }

    public func requestAccess() async -> Bool {
        let granted = await (try? UncheckedStore(store: store).requestFullAccess()) ?? false
        // A store made before access was granted does not see the lists until reset.
        if granted { store.reset() }
        return granted
    }

    public func add(title: String, notes: String?, dueAt: Date?) throws -> String {
        guard let list = omiList() else { throw CocoaError(.fileNoSuchFile) }
        let reminder = EKReminder(eventStore: store)
        reminder.title = title
        reminder.notes = notes
        reminder.calendar = list
        reminder.dueDateComponents = dueAt.map(Self.components)
        try store.save(reminder, commit: true)
        return reminder.calendarItemIdentifier
    }

    public func reminder(_ id: String) -> ReminderSnapshot? {
        guard let reminder = store.calendarItem(withIdentifier: id) as? EKReminder else { return nil }
        return ReminderSnapshot(
            title: reminder.title ?? "",
            isCompleted: reminder.isCompleted,
            dueAt: reminder.dueDateComponents.flatMap { Calendar.current.date(from: $0) },
            lastModified: reminder.lastModifiedDate
        )
    }

    public func update(_ id: String, title: String?, due: TaskSyncUpdate.Due, completed: Bool?) throws {
        guard let reminder = store.calendarItem(withIdentifier: id) as? EKReminder else { return }
        if let title { reminder.title = title }
        if case let .set(date) = due { reminder.dueDateComponents = date.map(Self.components) }
        if let completed { reminder.isCompleted = completed }
        try store.save(reminder, commit: true)
    }

    private func omiList() -> EKCalendar? {
        if let id = defaults.string(forKey: Self.listKey), let list = store.calendar(withIdentifier: id) { return list }
        if let found = store.calendars(for: .reminder).first(where: { $0.title == Self.listTitle && $0.allowsContentModifications }) {
            defaults.set(found.calendarIdentifier, forKey: Self.listKey)
            return found
        }
        let fallback = store.defaultCalendarForNewReminders()
        guard let source = fallback?.source ?? store.sources.first(where: { $0.sourceType == .local }) else { return fallback }
        let list = EKCalendar(for: .reminder, eventStore: store)
        list.title = Self.listTitle
        list.source = source
        do {
            try store.saveCalendar(list, commit: true)
            defaults.set(list.calendarIdentifier, forKey: Self.listKey)
            return list
        } catch {
            return fallback
        }
    }

    private static func components(_ date: Date) -> DateComponents {
        Calendar.current.dateComponents([.year, .month, .day, .hour, .minute], from: date)
    }
}

/// `EKEventStore` is thread-safe but not marked `Sendable`; the permission prompt is its only async call.
private struct UncheckedStore: @unchecked Sendable {
    let store: EKEventStore

    func requestFullAccess() async throws -> Bool {
        try await store.requestFullAccessToReminders()
    }
}
