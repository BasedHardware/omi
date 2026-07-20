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

  func testReminderMemoryContentKeepsCompletionDueDateAndList() {
    let dueAt = Date(timeIntervalSince1970: 1_753_084_800)
    let reminder = AppleReminderRecord(
      id: "reminder-1",
      title: "Send proposal",
      notes: "Attach estimate",
      dueAt: dueAt,
      completedAt: nil,
      isCompleted: false,
      priority: 1,
      listTitle: "Work"
    )

    let content = AppleEventKitReaderService.reminderContent(reminder)
    XCTAssertTrue(content.contains("Apple Reminder — Send proposal"))
    XCTAssertTrue(content.contains("Incomplete"))
    XCTAssertTrue(content.contains("List: Work"))
    XCTAssertTrue(content.contains("Notes: Attach estimate"))
  }

  @MainActor
  func testConnectionsExposeDistinctAppleSourcesWithoutReplacingGoogleCalendar() {
    XCTAssertEqual(ImportConnector.all.first { $0.id == "calendar" }?.subtitle, "Google Calendar")
    XCTAssertEqual(ImportConnector.all.first { $0.id == "apple-calendar" }?.title, "Apple Calendar")
    XCTAssertEqual(ImportConnector.all.first { $0.id == "apple-reminders" }?.title, "Apple Reminders")
    XCTAssertEqual(ImportConnector.all.first { $0.id == "apple-notes" }?.title, "Apple Notes")
  }
}
