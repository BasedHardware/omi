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
}

@MainActor
private final class AppleEventKitStoreStub: AppleEventKitStore {
  let authorizationStatus: EKAuthorizationStatus
  var events: [EKEvent] = []
  var grantsCalendarAccess = true
  var calendarAccessRequests = 0

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

  func reminders() async -> [EKReminder] { [] }

  func newReminder() -> EKReminder { EKReminder(eventStore: EKEventStore()) }

  func calendarItem(withIdentifier identifier: String) -> EKCalendarItem? { nil }

  func defaultCalendarForNewReminders() -> EKCalendar? { nil }

  func save(_ reminder: EKReminder, commit: Bool) throws {}

  func commit() throws {}
}
