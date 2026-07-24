import EventKit
import XCTest

@testable import Omi_Computer

final class AppleEventKitReaderServiceTests: XCTestCase {
  func testAuthorizationMappingRequiresFullReadAccess() {
    XCTAssertEqual(AppleEventKitAuthorization.from(.notDetermined), .notDetermined)
    XCTAssertEqual(AppleEventKitAuthorization.from(.restricted), .restricted)
    XCTAssertEqual(AppleEventKitAuthorization.from(.denied), .denied)
    XCTAssertEqual(AppleEventKitAuthorization.from(.writeOnly), .writeOnly)
    XCTAssertEqual(AppleEventKitAuthorization.from(.fullAccess), .fullAccess)
  }

  func testFetchParametersClampAtTrustBoundary() {
    XCTAssertEqual(
      AppleEventKitFetchParameters.normalized(daysBack: -1, daysForward: -2, maxResults: 0),
      AppleEventKitFetchParameters(daysBack: 0, daysForward: 0, maxResults: 1)
    )
    XCTAssertEqual(
      AppleEventKitFetchParameters.normalized(daysBack: 9999, daysForward: 9999, maxResults: 9999),
      AppleEventKitFetchParameters(daysBack: 3650, daysForward: 3650, maxResults: 2500)
    )
  }

  @MainActor
  func testCalendarReadMapsEventKitEvent() async throws {
    let store = AppleEventKitStoreStub(authorizationStatus: .fullAccess)
    let event = EKEvent(eventStore: EKEventStore())
    event.title = "Design review"
    event.startDate = Date(timeIntervalSince1970: 1_753_084_800)
    event.endDate = Date(timeIntervalSince1970: 1_753_088_400)
    event.location = "Studio"
    event.notes = "Bring mockups"
    store.events = [event]

    let events = try await AppleEventKitReaderService(eventStore: store).readCalendarEvents(requestAccess: false)

    XCTAssertEqual(events.count, 1)
    XCTAssertEqual(events[0].summary, "Design review")
    XCTAssertEqual(events[0].location, "Studio")
    XCTAssertEqual(events[0].description, "Bring mockups")
  }

  @MainActor
  func testCalendarReadReportsDeniedAccess() async {
    let store = AppleEventKitStoreStub(authorizationStatus: .notDetermined)
    store.grantsCalendarAccess = false

    do {
      _ = try await AppleEventKitReaderService(eventStore: store).readCalendarEvents()
      XCTFail("Expected denied access")
    } catch {
      XCTAssertEqual(error as? AppleEventKitReaderError, .accessDenied(.calendar))
      XCTAssertEqual(store.calendarAccessRequests, 1)
    }
  }

  func testCalendarMemoryContentKeepsRelevantFields() {
    let event = CalendarEvent(
      id: "event-1",
      summary: "Design review",
      startTime: "2026-07-20T14:00:00Z",
      endTime: "2026-07-20T15:00:00Z",
      attendees: ["Ada"],
      location: "Studio",
      description: "Bring mockups",
      isAllDay: false
    )

    XCTAssertEqual(
      AppleEventKitReaderService.calendarContent(event),
      "Apple Calendar event — Design review | Starts: 2026-07-20T14:00:00Z | Location: Studio | With: Ada | Notes: Bring mockups"
    )
  }

  @MainActor
  func testConnectionsExposeDistinctAppleSourcesWithoutReplacingGoogleCalendar() {
    XCTAssertEqual(ImportConnector.all.first { $0.id == "calendar" }?.subtitle, "Google Calendar")
    XCTAssertEqual(ImportConnector.all.first { $0.id == "apple-calendar" }?.title, "Apple Calendar")
    XCTAssertEqual(ImportConnector.all.first { $0.id == "apple-reminders" }?.title, "Apple Reminders")
    XCTAssertEqual(ImportConnector.all.first { $0.id == "apple-notes" }?.title, "Apple Notes")
  }

  @MainActor
  func testExportAcknowledgesEachReminderBeforeContinuing() async throws {
    let store = AppleEventKitStoreStub(authorizationStatus: .fullAccess)
    store.defaultCalendar = EKCalendar(for: .reminder, eventStore: EKEventStore())
    let sync = AppleRemindersSyncStub(
      pending: AppleRemindersPendingSync(
        pendingExport: [
          .fixture(id: "item-1", description: "Buy milk"),
          .fixture(id: "item-2", description: "Ship release"),
        ],
        syncedItems: []
      )
    )
    sync.failAfterSyncCalls = 1

    do {
      _ = try await AppleEventKitReaderService(eventStore: store, remindersSync: sync).syncReminders()
      XCTFail("Expected second backend ack to fail")
    } catch {
      XCTAssertEqual(error as? AppleRemindersSyncStub.Error, .forcedFailure)
    }

    // Both Apple reminders were created, but only the first backend ack landed —
    // so a retry will not recreate item-1.
    XCTAssertEqual(store.savedReminderTitles, ["Buy milk", "Ship release"])
    XCTAssertEqual(sync.syncBatches.count, 1)
    XCTAssertEqual(sync.syncBatches[0].map(\.id), ["item-1"])
    XCTAssertEqual(sync.syncBatches[0].first?.exported, true)
    XCTAssertEqual(sync.syncBatches[0].first?.appleReminderId, "stub-reminder-1")
  }

  @MainActor
  func testMissingAppleReminderDeletesOmiActionItem() async throws {
    let store = AppleEventKitStoreStub(authorizationStatus: .fullAccess)
    let sync = AppleRemindersSyncStub(
      pending: AppleRemindersPendingSync(
        pendingExport: [],
        syncedItems: [
          .fixture(id: "item-gone", description: "Deleted elsewhere", appleReminderId: "missing-reminder")
        ]
      )
    )

    let result = try await AppleEventKitReaderService(eventStore: store, remindersSync: sync).syncReminders()

    XCTAssertEqual(result.deleted, 1)
    XCTAssertEqual(sync.deletedIDs, ["item-gone"])
  }

  @MainActor
  func testAppleCompletionPropagatesToBackend() async throws {
    let store = AppleEventKitStoreStub(authorizationStatus: .fullAccess)
    let reminder = store.makeReminder(id: "reminder-1", title: "Done locally", completed: true)
    let sync = AppleRemindersSyncStub(
      pending: AppleRemindersPendingSync(
        pendingExport: [],
        syncedItems: [
          .fixture(
            id: "item-1",
            description: "Done locally",
            completed: false,
            appleReminderId: "reminder-1"
          )
        ]
      )
    )

    let result = try await AppleEventKitReaderService(eventStore: store, remindersSync: sync).syncReminders()

    XCTAssertEqual(result.updated, 1)
    XCTAssertEqual(sync.syncBatches.count, 1)
    XCTAssertEqual(sync.syncBatches[0].first?.id, "item-1")
    XCTAssertEqual(sync.syncBatches[0].first?.completed, true)
    XCTAssertTrue(reminder.isCompleted)
  }
}

@MainActor
private final class AppleEventKitStoreStub: AppleEventKitStore {
  let authorizationStatus: EKAuthorizationStatus
  var events: [EKEvent] = []
  var grantsCalendarAccess = true
  var calendarAccessRequests = 0
  var defaultCalendar: EKCalendar?
  var remindersByID: [String: EKReminder] = [:]
  private(set) var savedReminderTitles: [String] = []
  private var nextReminderIndex = 0

  init(authorizationStatus: EKAuthorizationStatus) {
    self.authorizationStatus = authorizationStatus
  }

  func authorizationStatus(for source: AppleEventKitSource) -> EKAuthorizationStatus {
    authorizationStatus
  }

  func requestFullAccessToEvents() async throws -> Bool {
    calendarAccessRequests += 1
    return grantsCalendarAccess
  }

  func requestFullAccessToReminders() async throws -> Bool { true }

  func calendarEvents(start: Date, end: Date) -> [EKEvent] { events }

  func newReminder() -> EKReminder {
    EKReminder(eventStore: EKEventStore())
  }

  func calendarItem(withIdentifier identifier: String) -> EKCalendarItem? {
    remindersByID[identifier]
  }

  func defaultCalendarForNewReminders() -> EKCalendar? { defaultCalendar }

  @discardableResult
  func saveReminder(_ reminder: EKReminder, commit: Bool) throws -> String {
    nextReminderIndex += 1
    let id = "stub-reminder-\(nextReminderIndex)"
    remindersByID[id] = reminder
    if let title = reminder.title {
      savedReminderTitles.append(title)
    }
    return id
  }

  func commit() throws {}

  func makeReminder(id: String, title: String, completed: Bool) -> EKReminder {
    let reminder = EKReminder(eventStore: EKEventStore())
    reminder.title = title
    reminder.isCompleted = completed
    remindersByID[id] = reminder
    return reminder
  }
}

@MainActor
private final class AppleRemindersSyncStub: AppleRemindersSyncing {
  enum Error: Swift.Error, Equatable { case forcedFailure }

  var pending: AppleRemindersPendingSync
  var failAfterSyncCalls: Int?
  private(set) var syncBatches: [[AppleRemindersSyncUpdate]] = []
  private(set) var deletedIDs: [String] = []

  init(pending: AppleRemindersPendingSync) {
    self.pending = pending
  }

  func getPendingAppleRemindersSync() async throws -> AppleRemindersPendingSync { pending }

  func syncAppleReminders(_ updates: [AppleRemindersSyncUpdate]) async throws {
    if updates.isEmpty { return }
    if let failAfterSyncCalls, syncBatches.count >= failAfterSyncCalls {
      throw Error.forcedFailure
    }
    syncBatches.append(updates)
  }

  func deleteSyncedActionItem(id: String) async throws {
    deletedIDs.append(id)
  }
}

extension OmiAPI.ActionItemResponse {
  fileprivate static func fixture(
    id: String,
    description: String,
    completed: Bool = false,
    appleReminderId: String? = nil
  ) -> Self {
    Self(
      appleReminderId: appleReminderId,
      completed: completed,
      completedAt: nil,
      conversationId: nil,
      createdAt: nil,
      description_: description,
      dueAt: nil,
      dueConfidence: nil,
      exportDate: nil,
      exportPlatform: appleReminderId == nil ? nil : "apple_reminders",
      exported: appleReminderId != nil,
      goalId: nil,
      id: id,
      indentLevel: nil,
      isLocked: nil,
      owner: nil,
      priority: nil,
      provenance: nil,
      recurrenceParentId: nil,
      recurrenceRule: nil,
      sortOrder: nil,
      source: nil,
      status: nil,
      supersededBy: nil,
      taskId: nil,
      updatedAt: nil,
      workstreamId: nil
    )
  }
}
