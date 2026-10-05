import XCTest

@testable import Omi_Computer

/// An action-item row's owner, due date and context: each shown when known, absent (never
/// "Unknown") when not, and kept across the summary cache's JSON round trip.
final class ActionItemRowMetadataTests: XCTestCase {
  func testSuggestedAppsDisclosureStartsCollapsed() {
    XCTAssertFalse(ConversationSuggestedAppsDisclosure.initiallyExpanded)
  }

  private var calendar: Calendar {
    var calendar = Calendar(identifier: .gregorian)
    calendar.timeZone = TimeZone(secondsFromGMT: 0) ?? .gmt
    return calendar
  }

  /// 2026-10-05T12:00:00Z.
  private let now = Date(timeIntervalSince1970: 1_791_201_600)

  func testItemWithNothingKnownHasNoMetadata() {
    let metadata = ActionItemRowMetadata(
      ActionItem(description: "Send the deck", completed: false, deleted: false), now: now, calendar: calendar)
    XCTAssertEqual(metadata, ActionItemRowMetadata(owner: nil, due: nil, context: nil))
    XCTAssertFalse(metadata.hasOwnerOrDue)
  }

  func testReadersOwnItemIsYouAndOthersKeepTheirName() {
    let mine = ActionItem(
      description: "x", completed: false, deleted: false, captureOwner: "user", ownerName: "David")
    let theirs = ActionItem(
      description: "x", completed: false, deleted: false, captureOwner: "other", ownerName: "Eddie Thai")
    XCTAssertEqual(ActionItemRowMetadata(mine, now: now, calendar: calendar).owner, "You")
    XCTAssertEqual(ActionItemRowMetadata(theirs, now: now, calendar: calendar).owner, "Eddie Thai")
    XCTAssertEqual(ActionItemRowMetadata.initials("Eddie Thai"), "ET")
    XCTAssertEqual(ActionItemRowMetadata.initials("David"), "D")
  }

  func testBlankOrEmailShapedOwnerIsLeftOut() {
    for name in ["  ", "eddie@example.com"] {
      let item = ActionItem(description: "x", completed: false, deleted: false, ownerName: name)
      XCTAssertNil(ActionItemRowMetadata(item, now: now, calendar: calendar).owner, name)
    }
  }

  func testDueReadsAsADayAndContextIsTrimmed() {
    let item = ActionItem(
      description: "x", completed: false, deleted: false, dueAt: now, context: "  Eddie will forward it. ")
    let metadata = ActionItemRowMetadata(item, now: now, calendar: calendar)
    XCTAssertEqual(metadata.due, "Due Today")
    XCTAssertEqual(metadata.context, "Eddie will forward it.")
  }

  func testTentativeDueDateAddsMarker() {
    let item = ActionItem(
      description: "x", completed: false, deleted: false, dueAt: now, dueCertainty: "tentative")
    XCTAssertEqual(ActionItemRowMetadata(item, now: now, calendar: calendar).due, "Due ~Today")
  }

  func testWireFieldsDecodeAndSurviveTheCacheRoundTrip() throws {
    let json = """
      {"description": "Share the provider info", "completed": false, "capture_owner": "other",
       "owner_name": "Eddie Thai", "due_at": "2026-10-07T16:00:00Z",
       "due_certainty": "tentative",
       "context": "Eddie said they would follow up."}
      """
    let decoded = try JSONDecoder().decode(ActionItem.self, from: Data(json.utf8))
    XCTAssertEqual(decoded.ownerName, "Eddie Thai")
    XCTAssertEqual(decoded.dueAt, ISO8601DateFormatter().date(from: "2026-10-07T16:00:00Z"))
    XCTAssertEqual(decoded.context, "Eddie said they would follow up.")
    XCTAssertEqual(decoded.dueCertainty, "tentative")

    let reread = try JSONDecoder().decode(ActionItem.self, from: JSONEncoder().encode(decoded))
    XCTAssertEqual(reread, decoded)
  }

  func testLegacyCachedRowWithoutTheFieldsStillDecodes() throws {
    let decoded = try JSONDecoder().decode(
      ActionItem.self, from: Data(#"{"description": "Old item", "completed": true}"#.utf8))
    XCTAssertNil(decoded.ownerName)
    XCTAssertNil(decoded.dueAt)
    XCTAssertNil(decoded.dueCertainty)
    XCTAssertNil(decoded.context)
  }

  func testStructuredEncodeKeepsActionItemMetadata() throws {
    let due = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-10-07T16:00:00Z"))
    let structured = Structured(
      title: "Planning",
      overview: "Overview",
      emoji: "🧭",
      category: "work",
      actionItems: [
        ActionItem(
          description: "Share the provider info", completed: false, deleted: false,
          captureOwner: "other", ownerName: "Eddie Thai", dueAt: due,
          dueCertainty: "tentative", context: "Eddie said they would follow up.")
      ],
      events: [],
      sections: []
    )
    let decoded = try JSONDecoder().decode(Structured.self, from: JSONEncoder().encode(structured))
    XCTAssertEqual(decoded.actionItems.count, 1)
    let item = decoded.actionItems[0]
    XCTAssertEqual(item.ownerName, "Eddie Thai")
    XCTAssertEqual(item.captureOwner, "other")
    XCTAssertEqual(item.dueAt, due)
    XCTAssertEqual(item.dueCertainty, "tentative")
    XCTAssertEqual(item.context, "Eddie said they would follow up.")
  }
}
