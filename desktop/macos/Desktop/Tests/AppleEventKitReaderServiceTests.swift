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
    XCTAssertEqual(
      ImportConnector.all.first { $0.id == "apple-calendar" }?.description,
      "Import local events; notes, attendees, and locations are saved as memories."
    )
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
      _ = try await AppleEventKitReaderService(
        eventStore: store, remindersSync: sync, exportJournal: try makeExportJournal()
      ).syncReminders()
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
  func testFailedAckDoesNotDuplicateAppleReminderOnRetry() async throws {
    let store = AppleEventKitStoreStub(authorizationStatus: .fullAccess)
    store.defaultCalendar = EKCalendar(for: .reminder, eventStore: EKEventStore())
    let journal = try makeExportJournal()
    let pending = AppleRemindersPendingSync(
      pendingExport: [.fixture(id: "item-1", description: "Buy milk")],
      syncedItems: []
    )
    let sync = AppleRemindersSyncStub(pending: pending, failAfterSyncCalls: 0)

    do {
      _ = try await AppleEventKitReaderService(
        eventStore: store, remindersSync: sync, exportJournal: journal
      ).syncReminders()
      XCTFail("Expected backend ack to fail")
    } catch {
      XCTAssertEqual(error as? AppleRemindersSyncStub.Error, .forcedFailure)
    }

    XCTAssertEqual(store.savedReminderTitles, ["Buy milk"])
    XCTAssertTrue(sync.syncBatches.isEmpty)

    // The backend row is still pending_export because the ack never landed.
    sync.failAfterSyncCalls = nil
    let result = try await AppleEventKitReaderService(
      eventStore: store, remindersSync: sync, exportJournal: journal
    ).syncReminders()

    XCTAssertEqual(result.exported, 1)
    XCTAssertEqual(store.savedReminderTitles, ["Buy milk"])
    XCTAssertEqual(sync.syncBatches.count, 1)
    XCTAssertEqual(sync.syncBatches[0].first?.appleReminderId, "stub-reminder-1")
    XCTAssertNil(journal.reminderID(forItemID: "item-1"))
  }

  @MainActor
  func testJournaledExportAppliesLatestPendingFieldsBeforeAck() async throws {
    let store = AppleEventKitStoreStub(authorizationStatus: .fullAccess)
    store.defaultCalendar = EKCalendar(for: .reminder, eventStore: EKEventStore())
    let journal = try makeExportJournal()
    let pending = AppleRemindersPendingSync(
      pendingExport: [.fixture(id: "item-1", description: "Buy milk")],
      syncedItems: []
    )
    let sync = AppleRemindersSyncStub(pending: pending, failAfterSyncCalls: 0)

    _ = try? await AppleEventKitReaderService(
      eventStore: store, remindersSync: sync, exportJournal: journal
    ).syncReminders()

    let reminder = try XCTUnwrap(store.remindersByID["stub-reminder-1"])
    XCTAssertEqual(reminder.title, "Buy milk")
    XCTAssertFalse(reminder.isCompleted)
    XCTAssertNil(reminder.dueDateComponents)

    sync.pending = AppleRemindersPendingSync(
      pendingExport: [
        .fixture(
          id: "item-1",
          description: "Buy oat milk",
          completed: true,
          dueAt: "2026-08-15T15:00:00Z"
        )
      ],
      syncedItems: []
    )
    sync.failAfterSyncCalls = nil

    let result = try await AppleEventKitReaderService(
      eventStore: store, remindersSync: sync, exportJournal: journal
    ).syncReminders()

    XCTAssertEqual(result.exported, 1)
    XCTAssertEqual(reminder.title, "Buy oat milk")
    XCTAssertTrue(reminder.isCompleted)
    let expectedDue = try XCTUnwrap(AppleEventKitReaderService.parseDate("2026-08-15T15:00:00Z"))
    let appleDue = try XCTUnwrap(reminder.dueDateComponents.flatMap { Calendar.current.date(from: $0) })
    XCTAssertLessThan(abs(appleDue.timeIntervalSince(expectedDue)), 60)
    XCTAssertEqual(sync.syncBatches.count, 1)
    XCTAssertEqual(sync.syncBatches[0].first?.appleReminderId, "stub-reminder-1")
    XCTAssertNil(journal.reminderID(forItemID: "item-1"))
  }

  @MainActor
  func testDeletedAppleReminderIsRecreatedOnceAfterFailedAck() async throws {
    let store = AppleEventKitStoreStub(authorizationStatus: .fullAccess)
    store.defaultCalendar = EKCalendar(for: .reminder, eventStore: EKEventStore())
    let journal = try makeExportJournal()
    let pending = AppleRemindersPendingSync(
      pendingExport: [.fixture(id: "item-1", description: "Buy milk")],
      syncedItems: []
    )
    let sync = AppleRemindersSyncStub(pending: pending, failAfterSyncCalls: 0)

    _ = try? await AppleEventKitReaderService(
      eventStore: store, remindersSync: sync, exportJournal: journal
    ).syncReminders()
    store.remindersByID.removeValue(forKey: "stub-reminder-1")

    sync.failAfterSyncCalls = nil
    _ = try await AppleEventKitReaderService(
      eventStore: store, remindersSync: sync, exportJournal: journal
    ).syncReminders()

    XCTAssertEqual(store.savedReminderTitles, ["Buy milk", "Buy milk"])
    XCTAssertEqual(sync.syncBatches[0].first?.appleReminderId, "stub-reminder-2")
  }

  @MainActor
  func testExportJournalDropsEntriesNoLongerPendingExport() async throws {
    let store = AppleEventKitStoreStub(authorizationStatus: .fullAccess)
    let journal = try makeExportJournal()
    journal.record(reminderID: "stale-reminder", forItemID: "item-gone")
    let sync = AppleRemindersSyncStub(
      pending: AppleRemindersPendingSync(pendingExport: [], syncedItems: [])
    )

    _ = try await AppleEventKitReaderService(
      eventStore: store, remindersSync: sync, exportJournal: journal
    ).syncReminders()

    XCTAssertNil(journal.reminderID(forItemID: "item-gone"))
  }

  @MainActor
  func testExportJournalIsScopedPerSignedInAccount() throws {
    let suiteName = "apple-reminders-export-journal-scope-\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
    addTeardownBlock { defaults.removePersistentDomain(forName: suiteName) }
    let journal = DefaultsAppleRemindersExportJournal(defaults: defaults)

    defaults.set("user-a", forKey: .authUserId)
    journal.record(reminderID: "reminder-a", forItemID: "shared-item-id")

    defaults.set("user-b", forKey: .authUserId)
    XCTAssertNil(journal.reminderID(forItemID: "shared-item-id"))

    defaults.set("user-a", forKey: .authUserId)
    XCTAssertEqual(journal.reminderID(forItemID: "shared-item-id"), "reminder-a")
  }

  @MainActor
  func testExportRetryDoesNotReuseAnotherAccountsJournaledReminder() async throws {
    let suiteName = "apple-reminders-export-journal-cross-user-\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
    addTeardownBlock { defaults.removePersistentDomain(forName: suiteName) }
    let journal = DefaultsAppleRemindersExportJournal(defaults: defaults)
    let store = AppleEventKitStoreStub(authorizationStatus: .fullAccess)
    store.defaultCalendar = EKCalendar(for: .reminder, eventStore: EKEventStore())

    defaults.set("user-a", forKey: .authUserId)
    journal.record(reminderID: "user-a-reminder", forItemID: "shared-item-id")
    _ = store.makeReminder(id: "user-a-reminder", title: "User A task", completed: false)

    defaults.set("user-b", forKey: .authUserId)
    let sync = AppleRemindersSyncStub(
      pending: AppleRemindersPendingSync(
        pendingExport: [.fixture(id: "shared-item-id", description: "User B task")],
        syncedItems: []
      )
    )
    let result = try await AppleEventKitReaderService(
      eventStore: store, remindersSync: sync, exportJournal: journal
    ).syncReminders()

    XCTAssertEqual(result.exported, 1)
    XCTAssertEqual(store.savedReminderTitles, ["User B task"])
    XCTAssertEqual(sync.syncBatches[0].first?.appleReminderId, "stub-reminder-1")
    XCTAssertNotEqual(sync.syncBatches[0].first?.appleReminderId, "user-a-reminder")

    defaults.set("user-a", forKey: .authUserId)
    XCTAssertEqual(journal.reminderID(forItemID: "shared-item-id"), "user-a-reminder")
  }

  @MainActor
  private func makeExportJournal(userID: String = "test-user") throws -> DefaultsAppleRemindersExportJournal {
    let suiteName = "apple-reminders-export-journal-\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
    defaults.set(userID, forKey: .authUserId)
    addTeardownBlock { defaults.removePersistentDomain(forName: suiteName) }
    return DefaultsAppleRemindersExportJournal(defaults: defaults)
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
    XCTAssertTrue(sync.syncBatches.isEmpty)
  }

  @MainActor
  func testExistingAppleReminderDoesNotDeleteOmiActionItem() async throws {
    let store = AppleEventKitStoreStub(authorizationStatus: .fullAccess)
    _ = store.makeReminder(id: "reminder-1", title: "Still here", completed: false)
    let sync = AppleRemindersSyncStub(
      pending: AppleRemindersPendingSync(
        pendingExport: [],
        syncedItems: [
          .fixture(id: "item-1", description: "Still here", appleReminderId: "reminder-1")
        ]
      )
    )

    let result = try await AppleEventKitReaderService(eventStore: store, remindersSync: sync).syncReminders()

    XCTAssertEqual(result.deleted, 0)
    XCTAssertTrue(sync.deletedIDs.isEmpty)
  }

  @MainActor
  func testMultipleMissingAppleRemindersDeleteAllLinkedActionItems() async throws {
    let store = AppleEventKitStoreStub(authorizationStatus: .fullAccess)
    let sync = AppleRemindersSyncStub(
      pending: AppleRemindersPendingSync(
        pendingExport: [],
        syncedItems: [
          .fixture(id: "item-a", description: "First", appleReminderId: "missing-a"),
          .fixture(id: "item-b", description: "Second", appleReminderId: "missing-b"),
        ]
      )
    )

    let result = try await AppleEventKitReaderService(eventStore: store, remindersSync: sync).syncReminders()

    XCTAssertEqual(result.deleted, 2)
    XCTAssertEqual(sync.deletedIDs, ["item-a", "item-b"])
  }

  @MainActor
  func testMissingAppleReminderDeleteFailurePropagates() async {
    let store = AppleEventKitStoreStub(authorizationStatus: .fullAccess)
    let sync = AppleRemindersSyncStub(
      pending: AppleRemindersPendingSync(
        pendingExport: [],
        syncedItems: [
          .fixture(id: "item-gone", description: "Deleted elsewhere", appleReminderId: "missing-reminder")
        ]
      ),
      failDeleteForIDs: ["item-gone"]
    )

    do {
      _ = try await AppleEventKitReaderService(eventStore: store, remindersSync: sync).syncReminders()
      XCTFail("Expected delete failure to propagate")
    } catch {
      XCTAssertEqual(error as? AppleRemindersSyncStub.Error, .deleteFailed("item-gone"))
    }

    XCTAssertEqual(sync.deletedIDs, ["item-gone"])
  }

  @MainActor
  func testAppleCompletionPropagatesToBackend() async throws {
    let store = AppleEventKitStoreStub(authorizationStatus: .fullAccess)
    let reminder = store.makeReminder(id: "reminder-1", title: "Done locally", completed: true)
    store.lastModifiedByID["reminder-1"] = Date(timeIntervalSince1970: 1_900_000_000)
    let sync = AppleRemindersSyncStub(
      pending: AppleRemindersPendingSync(
        pendingExport: [],
        syncedItems: [
          .fixture(
            id: "item-1",
            description: "Done locally",
            completed: false,
            appleReminderId: "reminder-1",
            updatedAt: "2026-07-20T12:00:00Z"
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

  @MainActor
  func testAppleReopenPropagatesToBackendWhenAppleIsNewer() async throws {
    let store = AppleEventKitStoreStub(authorizationStatus: .fullAccess)
    let reminder = store.makeReminder(id: "reminder-1", title: "Reopened locally", completed: false)
    store.lastModifiedByID["reminder-1"] = Date(timeIntervalSince1970: 1_900_000_000)
    let sync = AppleRemindersSyncStub(
      pending: AppleRemindersPendingSync(
        pendingExport: [],
        syncedItems: [
          .fixture(
            id: "item-1",
            description: "Reopened locally",
            completed: true,
            appleReminderId: "reminder-1",
            updatedAt: "2026-07-20T12:00:00Z"
          )
        ]
      )
    )

    let result = try await AppleEventKitReaderService(eventStore: store, remindersSync: sync).syncReminders()

    XCTAssertEqual(result.updated, 1)
    XCTAssertEqual(sync.syncBatches[0].first?.completed, false)
    XCTAssertFalse(reminder.isCompleted)
  }

  @MainActor
  func testOmiReopenClearsAppleCompletionWhenOmiIsNewer() async throws {
    let store = AppleEventKitStoreStub(authorizationStatus: .fullAccess)
    let reminder = store.makeReminder(id: "reminder-1", title: "Reopened in Omi", completed: true)
    store.lastModifiedByID["reminder-1"] = Date(timeIntervalSince1970: 1_700_000_000)
    let sync = AppleRemindersSyncStub(
      pending: AppleRemindersPendingSync(
        pendingExport: [],
        syncedItems: [
          .fixture(
            id: "item-1",
            description: "Reopened in Omi",
            completed: false,
            appleReminderId: "reminder-1",
            updatedAt: "2026-07-20T12:00:00Z"
          )
        ]
      )
    )

    let result = try await AppleEventKitReaderService(eventStore: store, remindersSync: sync).syncReminders()

    XCTAssertEqual(result.updated, 1)
    XCTAssertTrue(sync.syncBatches.isEmpty)
    XCTAssertFalse(reminder.isCompleted)
    XCTAssertNil(reminder.completionDate)
  }

  @MainActor
  func testOmiDueDateClearRemovesAppleReminderDueDate() async throws {
    let store = AppleEventKitStoreStub(authorizationStatus: .fullAccess)
    let due = Date(timeIntervalSince1970: 1_800_000_000)
    let reminder = store.makeReminder(
      id: "reminder-1",
      title: "Ship it",
      completed: false,
      dueDate: due
    )
    // Apple has no last-modified override → Omi wins the conflict direction.
    let sync = AppleRemindersSyncStub(
      pending: AppleRemindersPendingSync(
        pendingExport: [],
        syncedItems: [
          .fixture(
            id: "item-1",
            description: "Ship it",
            appleReminderId: "reminder-1",
            dueAt: nil,
            updatedAt: "2026-07-20T12:00:00Z"
          )
        ]
      )
    )

    let result = try await AppleEventKitReaderService(eventStore: store, remindersSync: sync).syncReminders()

    XCTAssertEqual(result.updated, 1)
    XCTAssertNil(reminder.dueDateComponents)
    XCTAssertTrue(sync.syncBatches.isEmpty)
  }

  @MainActor
  func testAppleDueDateClearPropagatesClearDueAtToBackend() async throws {
    let store = AppleEventKitStoreStub(authorizationStatus: .fullAccess)
    _ = store.makeReminder(id: "reminder-1", title: "Ship it", completed: false, dueDate: nil)
    // Apple is newer than the backend row that still has a due date.
    store.lastModifiedByID["reminder-1"] = Date(timeIntervalSince1970: 1_900_000_000)
    let sync = AppleRemindersSyncStub(
      pending: AppleRemindersPendingSync(
        pendingExport: [],
        syncedItems: [
          .fixture(
            id: "item-1",
            description: "Ship it",
            appleReminderId: "reminder-1",
            dueAt: "2026-07-20T15:00:00Z",
            updatedAt: "2026-07-19T12:00:00Z"
          )
        ]
      )
    )

    let result = try await AppleEventKitReaderService(eventStore: store, remindersSync: sync).syncReminders()

    XCTAssertEqual(result.updated, 1)
    XCTAssertEqual(sync.syncBatches.count, 1)
    XCTAssertEqual(sync.syncBatches[0].first?.id, "item-1")
    XCTAssertEqual(sync.syncBatches[0].first?.clearDueAt, true)
    XCTAssertNil(sync.syncBatches[0].first?.dueAt)
  }

  @MainActor
  func testAppleTitleClearPropagatesEmptyDescriptionToBackend() async throws {
    let store = AppleEventKitStoreStub(authorizationStatus: .fullAccess)
    let reminder = store.makeReminder(id: "reminder-1", title: "Ship it", completed: false)
    reminder.title = ""
    // Apple is newer than the backend row that still has the old title.
    store.lastModifiedByID["reminder-1"] = Date(timeIntervalSince1970: 1_900_000_000)
    let sync = AppleRemindersSyncStub(
      pending: AppleRemindersPendingSync(
        pendingExport: [],
        syncedItems: [
          .fixture(
            id: "item-1",
            description: "Ship it",
            appleReminderId: "reminder-1",
            updatedAt: "2026-07-19T12:00:00Z"
          )
        ]
      )
    )

    let result = try await AppleEventKitReaderService(eventStore: store, remindersSync: sync).syncReminders()

    XCTAssertEqual(result.updated, 1)
    XCTAssertEqual(sync.syncBatches.count, 1)
    XCTAssertEqual(sync.syncBatches[0].first?.id, "item-1")
    XCTAssertEqual(sync.syncBatches[0].first?.description, "")
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
  var lastModifiedByID: [String: Date] = [:]
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

  func lastModifiedDate(forReminderIdentifier identifier: String, reminder: EKReminder) -> Date? {
    lastModifiedByID[identifier] ?? reminder.lastModifiedDate
  }

  func makeReminder(id: String, title: String, completed: Bool, dueDate: Date? = nil) -> EKReminder {
    let reminder = EKReminder(eventStore: EKEventStore())
    reminder.title = title
    reminder.isCompleted = completed
    if let dueDate {
      reminder.dueDateComponents = Calendar.current.dateComponents(
        [.year, .month, .day, .hour, .minute], from: dueDate)
    }
    remindersByID[id] = reminder
    return reminder
  }
}

@MainActor
private final class AppleRemindersSyncStub: AppleRemindersSyncing {
  enum Error: Swift.Error, Equatable {
    case forcedFailure
    case deleteFailed(String)
  }

  var pending: AppleRemindersPendingSync
  var failAfterSyncCalls: Int?
  var failDeleteForIDs: Set<String> = []
  private(set) var syncBatches: [[AppleRemindersSyncUpdate]] = []
  private(set) var deletedIDs: [String] = []

  init(
    pending: AppleRemindersPendingSync,
    failAfterSyncCalls: Int? = nil,
    failDeleteForIDs: Set<String> = []
  ) {
    self.pending = pending
    self.failAfterSyncCalls = failAfterSyncCalls
    self.failDeleteForIDs = failDeleteForIDs
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
    if failDeleteForIDs.contains(id) {
      throw Error.deleteFailed(id)
    }
  }
}

extension OmiAPI.ActionItemResponse {
  fileprivate static func fixture(
    id: String,
    description: String,
    completed: Bool = false,
    appleReminderId: String? = nil,
    dueAt: String? = nil,
    updatedAt: String? = nil
  ) -> Self {
    Self(
      appleReminderId: appleReminderId,
      completed: completed,
      completedAt: nil,
      conversationId: nil,
      createdAt: nil,
      description_: description,
      dueAt: dueAt,
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
      updatedAt: updatedAt,
      workstreamId: nil
    )
  }
}
