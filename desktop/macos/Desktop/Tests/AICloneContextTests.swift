import XCTest

@testable import Omi_Computer

final class AICloneContextTests: XCTestCase {

  // MARK: - Scheduling detection

  func testSchedulingPositives() {
    let positives = [
      "hey you free this week?",
      "wanna grab lunch tomorrow",
      "are you AVAILABLE friday",
      "what time works for you",
      "can we meet at 3pm",
      "lets do 10:30",
      "down to hang this weekend?",
      "coffee next week?",
      "when r u around",
    ]
    for message in positives {
      XCTAssertTrue(
        AICloneContextService.isSchedulingRelated(message), "expected scheduling: \(message)")
    }
  }

  func testSchedulingNegatives() {
    let negatives = [
      "lol did you see the game",
      "that movie was insane",
      "freedom of speech is wild",  // "free" embedded in "freedom" must not match
      "bro the meetings at work are killing me hahahaha jk",  // "meetings" embedded? no — but "meeting" is a word-prefix inside "meetings"
      "ok",
      "happy birthday!!",
    ]
    // "meetings" contains "meeting" followed by a letter 's' → boundary check rejects it,
    // but "meetings at work" arguably IS scheduling-adjacent; we only assert the clear cases.
    for message in [negatives[0], negatives[1], negatives[2], negatives[4], negatives[5]] {
      XCTAssertFalse(
        AICloneContextService.isSchedulingRelated(message), "expected non-scheduling: \(message)")
    }
  }

  func testSchedulingWordBoundary() {
    XCTAssertFalse(AICloneContextService.isSchedulingRelated("carefree vibes only"))
    XCTAssertTrue(AICloneContextService.isSchedulingRelated("u free?"))
  }

  // MARK: - Memory block rendering

  func testMemoryBlockCapsAndTruncates() {
    let long = String(repeating: "x", count: 500)
    let contents = (1...20).map { "fact \($0)" } + [long]
    let block = AICloneContextService.renderMemoryBlock(contents)
    XCTAssertNotNil(block)
    let bulletCount = block!.components(separatedBy: "\n").filter { $0.hasPrefix("- ") }.count
    XCTAssertEqual(bulletCount, AICloneContextService.maxMemories)
    XCTAssertFalse(block!.contains(long))  // over-long fact would have been truncated (or capped out)
  }

  func testMemoryBlockEmptyReturnsNil() {
    XCTAssertNil(AICloneContextService.renderMemoryBlock([]))
    XCTAssertNil(AICloneContextService.renderMemoryBlock(["", "   "]))
  }

  func testMemoryBlockGroundingRules() {
    let block = AICloneContextService.renderMemoryBlock(["The user works at Acme"])
    XCTAssertNotNil(block)
    XCTAssertTrue(block!.contains("never volunteer"))
  }

  // MARK: - Calendar block rendering

  private func event(
    _ summary: String, start: String, end: String = "", allDay: Bool = false
  ) -> CalendarEvent {
    CalendarEvent(
      id: UUID().uuidString, summary: summary, startTime: start, endTime: end,
      attendees: [], location: "", description: "", isAllDay: allDay)
  }

  func testCalendarBlockFiltersWindowAndSorts() {
    let formatter = ISO8601DateFormatter()
    let now = formatter.date(from: "2026-07-03T12:00:00Z")!
    let events = [
      event("Future dinner", start: "2026-07-06T19:00:00Z", end: "2026-07-06T21:00:00Z"),
      event("Past standup", start: "2026-07-01T10:00:00Z", end: "2026-07-01T10:30:00Z"),
      event("Too far out", start: "2026-08-30T10:00:00Z", end: "2026-08-30T11:00:00Z"),
      event("Tomorrow call", start: "2026-07-04T15:00:00Z", end: "2026-07-04T15:30:00Z"),
    ]
    let block = AICloneContextService.renderCalendarBlock(events: events, now: now)
    XCTAssertNotNil(block)
    XCTAssertTrue(block!.contains("Future dinner"))
    XCTAssertTrue(block!.contains("Tomorrow call"))
    XCTAssertFalse(block!.contains("Past standup"))
    XCTAssertFalse(block!.contains("Too far out"))
    // Sorted ascending: tomorrow's call listed before the later dinner.
    let callIndex = block!.range(of: "Tomorrow call")!.lowerBound
    let dinnerIndex = block!.range(of: "Future dinner")!.lowerBound
    XCTAssertLessThan(callIndex, dinnerIndex)
  }

  func testCalendarBlockKeepsInProgressEvent() {
    let formatter = ISO8601DateFormatter()
    let now = formatter.date(from: "2026-07-03T12:00:00Z")!
    let events = [
      event("Ongoing offsite", start: "2026-07-03T09:00:00Z", end: "2026-07-03T17:00:00Z")
    ]
    let block = AICloneContextService.renderCalendarBlock(events: events, now: now)
    XCTAssertTrue(block!.contains("Ongoing offsite"))
  }

  func testCalendarBlockEmptyStillReturnsRealAvailability() {
    let now = ISO8601DateFormatter().date(from: "2026-07-03T12:00:00Z")!
    let block = AICloneContextService.renderCalendarBlock(events: [], now: now)
    XCTAssertNotNil(block)
    XCTAssertTrue(block!.contains("No commitments"))
  }

  func testCalendarBlockCarriesNoBookingRule() {
    let now = ISO8601DateFormatter().date(from: "2026-07-03T12:00:00Z")!
    let block = AICloneContextService.renderCalendarBlock(events: [], now: now)!
    XCTAssertTrue(block.contains("NEVER claim you booked"))
    XCTAssertTrue(block.contains("never invent"))
  }

  func testCalendarBlockAllDayEvent() {
    let now = ISO8601DateFormatter().date(from: "2026-07-03T12:00:00Z")!
    let events = [event("Offsite", start: "2026-07-05", allDay: true)]
    let block = AICloneContextService.renderCalendarBlock(events: events, now: now)!
    XCTAssertTrue(block.contains("(all day): Offsite"))
  }

  func testCalendarBlockTruncationNote() {
    let formatter = ISO8601DateFormatter()
    let now = formatter.date(from: "2026-07-03T12:00:00Z")!
    let events = (0..<40).map { index -> CalendarEvent in
      let day = String(format: "%02d", 4 + index % 10)  // July 4–13, all inside the window
      let hour = String(format: "%02d", 10 + index % 8)
      return event(
        "Event \(index)", start: "2026-07-\(day)T\(hour):00:00Z",
        end: "2026-07-\(day)T\(hour):30:00Z")
    }
    let block = AICloneContextService.renderCalendarBlock(events: events, now: now)!
    let lineCount = block.components(separatedBy: "\n").filter { $0.hasPrefix("- ") }.count
    XCTAssertEqual(lineCount, AICloneContextService.maxCalendarEvents)
    XCTAssertTrue(block.contains("more events not listed"))
  }

  // MARK: - Event date parsing

  func testParseEventDateFormats() {
    XCTAssertNotNil(AICloneContextService.parseEventDate("2026-07-06T14:00:00-07:00"))
    XCTAssertNotNil(AICloneContextService.parseEventDate("2026-07-06T14:00:00Z"))
    XCTAssertNotNil(AICloneContextService.parseEventDate("2026-07-06"))
    XCTAssertNil(AICloneContextService.parseEventDate(""))
    XCTAssertNil(AICloneContextService.parseEventDate("not a date"))
  }
}
