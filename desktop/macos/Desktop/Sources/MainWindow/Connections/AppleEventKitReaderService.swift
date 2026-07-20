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

struct AppleReminderRecord: Equatable, Identifiable, Sendable {
  let id: String
  let title: String
  let notes: String
  let dueAt: Date?
  let completedAt: Date?
  let isCompleted: Bool
  let priority: Int
  let listTitle: String
}

enum AppleEventKitConnectionStatus: Equatable, Sendable {
  case connected(itemCount: Int)
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
final class AppleEventKitReaderService {
  static let shared = AppleEventKitReaderService()

  private let eventStore: EKEventStore

  init(eventStore: EKEventStore = EKEventStore()) {
    self.eventStore = eventStore
  }

  func connectionStatus(
    for source: AppleEventKitSource,
    daysBack: Int = 1,
    daysForward: Int = 1,
    maxResults: Int = 1
  ) async -> AppleEventKitConnectionStatus {
    do {
      switch source {
      case .calendar:
        let count = try await readCalendarEvents(
          daysBack: daysBack,
          daysForward: daysForward,
          maxResults: maxResults,
          requestAccess: false
        ).count
        return .connected(itemCount: count)
      case .reminders:
        let count = try await readReminders(maxResults: maxResults, requestAccess: false).count
        return .connected(itemCount: count)
      }
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
    let predicate = eventStore.predicateForEvents(withStart: start, end: end, calendars: nil)
    let formatter = ISO8601DateFormatter()

    return eventStore.events(matching: predicate)
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

  func readReminders(maxResults: Int = 500, requestAccess: Bool = true) async throws -> [AppleReminderRecord] {
    try await ensureAccess(to: .reminders, requestIfNeeded: requestAccess)
    let limit = min(max(maxResults, 1), 2500)
    let predicate = eventStore.predicateForReminders(in: nil)
    let reminders = await withCheckedContinuation { continuation in
      eventStore.fetchReminders(matching: predicate) { reminders in
        continuation.resume(returning: reminders ?? [])
      }
    }

    return
      reminders
      .sorted { ($0.lastModifiedDate ?? .distantPast) > ($1.lastModifiedDate ?? .distantPast) }
      .prefix(limit)
      .map { reminder in
        AppleReminderRecord(
          id: reminder.calendarItemIdentifier,
          title: reminder.title ?? "Untitled reminder",
          notes: reminder.notes ?? "",
          dueAt: reminder.dueDateComponents.flatMap { Calendar.current.date(from: $0) },
          completedAt: reminder.completionDate,
          isCompleted: reminder.isCompleted,
          priority: reminder.priority,
          listTitle: reminder.calendar.title
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

  func saveRemindersAsMemories(reminders: [AppleReminderRecord]) async -> (saved: Int, failed: Int) {
    let artifacts = reminders.map { reminder in
      let content = Self.reminderContent(reminder)
      return ImportEvidenceBatchItem(
        externalId: "apple_reminders:\(reminder.id)",
        occurredAt: reminder.completedAt ?? reminder.dueAt,
        title: reminder.title,
        snippet: content,
        content: content,
        metadata: [
          "import_kind": "reminder",
          "completed": reminder.isCompleted ? "true" : "false",
          "list": reminder.listTitle,
        ]
      )
    }
    return await OnboardingImportEvidenceService.save(
      artifacts,
      sourceType: AppleEventKitSource.reminders.sourceType,
      logPrefix: "AppleEventKitReaderService"
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

  nonisolated static func reminderContent(_ reminder: AppleReminderRecord) -> String {
    var parts = ["Apple Reminder — \(reminder.title)"]
    parts.append(reminder.isCompleted ? "Completed" : "Incomplete")
    if let dueAt = reminder.dueAt { parts.append("Due: \(ISO8601DateFormatter().string(from: dueAt))") }
    if !reminder.listTitle.isEmpty { parts.append("List: \(reminder.listTitle)") }
    if !reminder.notes.isEmpty { parts.append("Notes: \(reminder.notes)") }
    return parts.joined(separator: " | ")
  }

  private func ensureAccess(to source: AppleEventKitSource, requestIfNeeded: Bool) async throws {
    let authorization = AppleEventKitAuthorization.current(for: source)
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
