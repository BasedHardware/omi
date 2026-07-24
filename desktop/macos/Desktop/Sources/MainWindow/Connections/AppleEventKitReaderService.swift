@preconcurrency import EventKit
import Foundation

enum AppleEventKitSource: String, Sendable {
  case calendar
  case reminders
}

enum AppleEventKitAuthorization: String, Equatable, Sendable {
  case notDetermined = "not_determined"
  case restricted
  case denied
  case writeOnly = "write_only"
  case fullAccess = "full_access"

  static func current(for source: AppleEventKitSource) -> AppleEventKitAuthorization {
    let entityType: EKEntityType = source == .calendar ? .event : .reminder
    return from(EKEventStore.authorizationStatus(for: entityType))
  }

  static func from(_ status: EKAuthorizationStatus) -> AppleEventKitAuthorization {
    switch status {
    case .notDetermined:
      return .notDetermined
    case .restricted:
      return .restricted
    case .denied:
      return .denied
    case .writeOnly:
      return .writeOnly
    case .fullAccess, .authorized:
      return .fullAccess
    @unknown default:
      return .denied
    }
  }
}

struct AppleEventKitFetchParameters: Equatable, Sendable {
  let daysBack: Int
  let daysForward: Int
  let maxResults: Int

  static func normalized(daysBack: Int, daysForward: Int, maxResults: Int) -> Self {
    Self(
      daysBack: min(max(daysBack, 0), 3650),
      daysForward: min(max(daysForward, 0), 3650),
      maxResults: min(max(maxResults, 1), 2500)
    )
  }
}

struct AppleRemindersSyncResult: Equatable, Sendable {
  let total: Int
  let exported: Int
  let updated: Int
  let deleted: Int
}

@MainActor
protocol AppleEventKitStore: AnyObject {
  func authorizationStatus(for source: AppleEventKitSource) -> EKAuthorizationStatus
  func requestFullAccessToEvents() async throws -> Bool
  func requestFullAccessToReminders() async throws -> Bool
  func calendarEvents(start: Date, end: Date) -> [EKEvent]
  func newReminder() -> EKReminder
  func calendarItem(withIdentifier identifier: String) -> EKCalendarItem?
  func defaultCalendarForNewReminders() -> EKCalendar?
  /// Persists the reminder and returns the stable EventKit identifier used for later sync.
  @discardableResult
  func saveReminder(_ reminder: EKReminder, commit: Bool) throws -> String
  func commit() throws
}

@MainActor
extension EKEventStore: AppleEventKitStore {
  func authorizationStatus(for source: AppleEventKitSource) -> EKAuthorizationStatus {
    EKEventStore.authorizationStatus(for: source == .calendar ? .event : .reminder)
  }

  func calendarEvents(start: Date, end: Date) -> [EKEvent] {
    events(matching: predicateForEvents(withStart: start, end: end, calendars: nil))
  }

  func newReminder() -> EKReminder {
    EKReminder(eventStore: self)
  }

  @discardableResult
  func saveReminder(_ reminder: EKReminder, commit: Bool) throws -> String {
    try save(reminder, commit: commit)
    return reminder.calendarItemIdentifier
  }
}

enum AppleEventKitConnectionStatus: Equatable, Sendable {
  case connected
  case needsAccess(message: String, reasonCode: String)
  case error(message: String, reasonCode: String)
}

enum AppleEventKitReaderError: LocalizedError, Equatable, Sendable {
  case accessDenied(AppleEventKitSource)
  case accessRestricted(AppleEventKitSource)
  case fullAccessRequired(AppleEventKitSource)
  case readFailed(AppleEventKitSource, String)

  var errorDescription: String? {
    switch self {
    case .accessDenied(let source):
      return "Omi doesn't have access to Apple \(source.displayName). Allow access in System Settings, then try again."
    case .accessRestricted(let source):
      return "Apple \(source.displayName) access is restricted on this Mac."
    case .fullAccessRequired(let source):
      return "Omi needs full Apple \(source.displayName) access to import your data."
    case .readFailed(let source, let reason):
      return "Apple \(source.displayName) couldn't be read: \(reason)"
    }
  }
}

extension AppleEventKitSource {
  fileprivate var displayName: String {
    switch self {
    case .calendar: return "Calendar"
    case .reminders: return "Reminders"
    }
  }

  fileprivate var sourceType: String {
    switch self {
    case .calendar: return "apple_calendar"
    case .reminders: return "apple_reminders"
    }
  }
}

@MainActor
protocol AppleRemindersSyncing: AnyObject {
  func getPendingAppleRemindersSync() async throws -> AppleRemindersPendingSync
  func syncAppleReminders(_ updates: [AppleRemindersSyncUpdate]) async throws
  func deleteSyncedActionItem(id: String) async throws
}

@MainActor
final class APIClientAppleRemindersSync: AppleRemindersSyncing {
  private let client: APIClient

  init(client: APIClient = .shared) {
    self.client = client
  }

  func getPendingAppleRemindersSync() async throws -> AppleRemindersPendingSync {
    try await client.getPendingAppleRemindersSync()
  }

  func syncAppleReminders(_ updates: [AppleRemindersSyncUpdate]) async throws {
    try await client.syncAppleReminders(updates)
  }

  func deleteSyncedActionItem(id: String) async throws {
    try await client.deleteActionItem(id: id)
  }
}

@MainActor
final class AppleEventKitReaderService {
  static let shared = AppleEventKitReaderService()

  private let eventStore: any AppleEventKitStore
  private let remindersSync: any AppleRemindersSyncing

  init(
    eventStore: any AppleEventKitStore = EKEventStore(),
    remindersSync: any AppleRemindersSyncing = APIClientAppleRemindersSync()
  ) {
    self.eventStore = eventStore
    self.remindersSync = remindersSync
  }

  func connectionStatus(for source: AppleEventKitSource) async -> AppleEventKitConnectionStatus {
    do {
      try await ensureAccess(to: source, requestIfNeeded: false)
      return .connected
    } catch let error as AppleEventKitReaderError {
      switch error {
      case .accessDenied:
        return .needsAccess(message: error.localizedDescription, reasonCode: "denied")
      case .accessRestricted:
        return .needsAccess(message: error.localizedDescription, reasonCode: "restricted")
      case .fullAccessRequired:
        return .needsAccess(message: error.localizedDescription, reasonCode: "full_access_required")
      case .readFailed:
        return .error(message: error.localizedDescription, reasonCode: "read_failed")
      }
    } catch {
      return .error(message: error.localizedDescription, reasonCode: "read_failed")
    }
  }

  func readCalendarEvents(
    daysBack: Int = 365,
    daysForward: Int = 30,
    maxResults: Int = 500,
    requestAccess: Bool = true
  ) async throws -> [CalendarEvent] {
    try await ensureAccess(to: .calendar, requestIfNeeded: requestAccess)
    let parameters = AppleEventKitFetchParameters.normalized(
      daysBack: daysBack,
      daysForward: daysForward,
      maxResults: maxResults
    )
    let calendar = Calendar.current
    let now = Date()
    let start = calendar.date(byAdding: .day, value: -parameters.daysBack, to: now) ?? now
    let end = calendar.date(byAdding: .day, value: parameters.daysForward, to: now) ?? now
    let formatter = ISO8601DateFormatter()

    return eventStore.calendarEvents(start: start, end: end)
      .sorted { $0.startDate > $1.startDate }
      .prefix(parameters.maxResults)
      .map { event in
        CalendarEvent(
          id: event.eventIdentifier ?? event.calendarItemIdentifier,
          summary: event.title ?? "Untitled event",
          startTime: formatter.string(from: event.startDate),
          endTime: formatter.string(from: event.endDate),
          attendees: event.attendees?.compactMap(\.name) ?? [],
          location: event.location ?? "",
          description: event.notes ?? "",
          isAllDay: event.isAllDay
        )
      }
  }

  func saveCalendarAsMemories(events: [CalendarEvent]) async -> (saved: Int, failed: Int) {
    let artifacts = events.map { event in
      let content = Self.calendarContent(event)
      return ImportEvidenceBatchItem(
        externalId: "apple_calendar:\(event.id)",
        title: event.summary,
        snippet: content,
        content: content,
        metadata: ["import_kind": "event", "start_time": event.startTime, "location": event.location]
      )
    }
    return await OnboardingImportEvidenceService.save(
      artifacts,
      sourceType: AppleEventKitSource.calendar.sourceType,
      logPrefix: "AppleEventKitReaderService"
    )
  }

  func syncReminders() async throws -> AppleRemindersSyncResult {
    try await ensureAccess(to: .reminders, requestIfNeeded: true)
    let pending = try await remindersSync.getPendingAppleRemindersSync()
    let formatter = ISO8601DateFormatter()
    var updates: [AppleRemindersSyncUpdate] = []
    var exported = 0

    if !pending.pendingExport.isEmpty {
      guard let calendar = eventStore.defaultCalendarForNewReminders() else {
        throw AppleEventKitReaderError.readFailed(.reminders, "No writable reminders list is available.")
      }
      // Acknowledge each export immediately after EventKit commit so a mid-batch
      // network failure cannot re-create already-persisted Apple reminders.
      for item in pending.pendingExport {
        let reminder = eventStore.newReminder()
        reminder.title = item.description_
        reminder.notes = "From Omi"
        reminder.calendar = calendar
        if let dueAt = item.dueAt.flatMap(Self.parseDate) {
          reminder.dueDateComponents = Calendar.current.dateComponents(
            [.year, .month, .day, .hour, .minute], from: dueAt)
        }
        let reminderID = try eventStore.saveReminder(reminder, commit: true)
        try await remindersSync.syncAppleReminders(
          [
            AppleRemindersSyncUpdate(
              id: item.id,
              exported: true,
              exportPlatform: "apple_reminders",
              appleReminderId: reminderID
            )
          ]
        )
        exported += 1
      }
    }

    var changed = 0
    var deletedIDs: [String] = []
    for item in pending.syncedItems {
      guard let reminderID = item.appleReminderId else { continue }
      guard let reminder = eventStore.calendarItem(withIdentifier: reminderID) as? EKReminder else {
        deletedIDs.append(item.id)
        continue
      }

      let backendUpdatedAt = item.updatedAt.flatMap(Self.parseDate)
      let appleIsNewer =
        reminder.lastModifiedDate.map { modified in
          backendUpdatedAt.map { modified > $0 } ?? true
        } ?? false
      var update = AppleRemindersSyncUpdate(id: item.id)
      var itemChanged = false
      if reminder.isCompleted && !item.completed {
        update.completed = true
      } else if item.completed && !reminder.isCompleted {
        reminder.isCompleted = true
        reminder.completionDate = Date()
        try eventStore.saveReminder(reminder, commit: true)
        itemChanged = true
      }

      if appleIsNewer {
        if let title = reminder.title, !title.isEmpty, title != item.description_ { update.description = title }
        if let dueAt = reminder.dueDateComponents.flatMap({ Calendar.current.date(from: $0) }) {
          update.dueAt = formatter.string(from: dueAt)
        }
      } else {
        var needsSave = false
        if reminder.title != item.description_ {
          reminder.title = item.description_
          needsSave = true
        }
        if let dueAt = item.dueAt.flatMap(Self.parseDate) {
          let currentDue = reminder.dueDateComponents.flatMap { Calendar.current.date(from: $0) }
          if currentDue.map({ abs($0.timeIntervalSince(dueAt)) > 60 }) ?? true {
            reminder.dueDateComponents = Calendar.current.dateComponents(
              [.year, .month, .day, .hour, .minute], from: dueAt)
            needsSave = true
          }
        }
        if needsSave {
          try eventStore.saveReminder(reminder, commit: true)
          itemChanged = true
        }
      }
      if update.description != nil || update.completed != nil || update.dueAt != nil {
        updates.append(update)
        itemChanged = true
      }
      if itemChanged { changed += 1 }
    }

    try await remindersSync.syncAppleReminders(updates)
    for id in deletedIDs { try await remindersSync.deleteSyncedActionItem(id: id) }
    return AppleRemindersSyncResult(
      total: max(0, exported + pending.syncedItems.count - deletedIDs.count),
      exported: exported,
      updated: changed,
      deleted: deletedIDs.count
    )
  }

  nonisolated static func calendarContent(_ event: CalendarEvent) -> String {
    var parts = ["Apple Calendar event — \(event.summary)"]
    if !event.startTime.isEmpty { parts.append("Starts: \(event.startTime)") }
    if !event.location.isEmpty { parts.append("Location: \(event.location)") }
    if !event.attendees.isEmpty { parts.append("With: \(event.attendees.prefix(5).joined(separator: ", "))") }
    if !event.description.isEmpty { parts.append("Notes: \(event.description)") }
    return parts.joined(separator: " | ")
  }

  nonisolated static func parseDate(_ value: String) -> Date? {
    let formatter = ISO8601DateFormatter()
    if let date = formatter.date(from: value) { return date }
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return formatter.date(from: value)
  }

  private func ensureAccess(to source: AppleEventKitSource, requestIfNeeded: Bool) async throws {
    let authorization = AppleEventKitAuthorization.from(eventStore.authorizationStatus(for: source))
    switch authorization {
    case .fullAccess:
      return
    case .notDetermined where requestIfNeeded:
      let granted: Bool
      do {
        switch source {
        case .calendar:
          granted = try await eventStore.requestFullAccessToEvents()
        case .reminders:
          granted = try await eventStore.requestFullAccessToReminders()
        }
      } catch {
        throw AppleEventKitReaderError.readFailed(source, error.localizedDescription)
      }
      guard granted else { throw AppleEventKitReaderError.accessDenied(source) }
    case .restricted:
      throw AppleEventKitReaderError.accessRestricted(source)
    case .denied:
      throw AppleEventKitReaderError.accessDenied(source)
    case .notDetermined, .writeOnly:
      throw AppleEventKitReaderError.fullAccessRequired(source)
    }
  }
}
