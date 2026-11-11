import XCTest

@testable import Omi_Computer

/// The grant path replaces a browser-cookie read that produced `CalendarEvent`
/// directly, so the wire shape has to decode into the same value — a silent
/// field drop here would quietly degrade every memory built from an event.
final class GoogleCalendarGrantEventTests: XCTestCase {
  private func decode(_ json: String) throws -> [GoogleCalendarGrantEvent] {
    try JSONDecoder().decode([GoogleCalendarGrantEvent].self, from: Data(json.utf8))
  }

  func testDecodesBackendEventIntoCalendarEvent() throws {
    let events = try decode(
      """
      [{
        "event_id": "evt-1",
        "title": "Design review",
        "attendees": ["Dana", "Ren"],
        "attendee_emails": ["dana@example.com"],
        "start_time": "2026-08-26T15:00:00Z",
        "end_time": "2026-08-26T16:00:00Z",
        "html_link": "https://calendar.google.com/event?eid=1",
        "location": "Room 4",
        "description": "Walk through the new connector flow.",
        "all_day": false
      }]
      """
    )

    let event = try XCTUnwrap(events.first).asCalendarEvent
    XCTAssertEqual(event.id, "evt-1")
    XCTAssertEqual(event.summary, "Design review")
    XCTAssertEqual(event.attendees, ["Dana", "Ren"])
    XCTAssertEqual(event.startTime, "2026-08-26T15:00:00Z")
    XCTAssertEqual(event.endTime, "2026-08-26T16:00:00Z")
    XCTAssertEqual(event.location, "Room 4")
    XCTAssertEqual(event.description, "Walk through the new connector flow.")
    XCTAssertFalse(event.isAllDay)
  }

  func testDecodesAllDayEvent() throws {
    let events = try decode(
      """
      [{
        "event_id": "evt-2",
        "title": "Offsite",
        "attendees": [],
        "attendee_emails": [],
        "start_time": "2026-08-26T00:00:00Z",
        "end_time": "2026-08-26T23:59:59Z",
        "location": "",
        "description": "",
        "all_day": true
      }]
      """
    )

    let event = try XCTUnwrap(events.first).asCalendarEvent
    XCTAssertTrue(event.isAllDay)
    XCTAssertEqual(event.attendees, [])
    XCTAssertEqual(event.location, "")
  }
}
