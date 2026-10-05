import XCTest

@testable import Omi_Computer

/// An action-item row's owner, due date and context: each shown when known, absent (never
/// "Unknown") when not, and kept across the summary cache's JSON round trip.
final class ActionItemRowMetadataTests: XCTestCase {
  private var calendar: Calendar {
    var calendar = Calendar(identifier: .gregorian)
    calendar.timeZone = TimeZone(identifier: "UTC")!
    return calendar
  }

  private let now = ISO8601DateFormatter().date(from: "2026-10-05T12:00:00Z")!

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

  func testWireFieldsDecodeAndSurviveTheCacheRoundTrip() throws {
    let json = """
      {"description": "Share the provider info", "completed": false, "capture_owner": "other",
       "owner_name": "Eddie Thai", "due_at": "2026-10-07T16:00:00Z",
       "context": "Eddie said they would follow up."}
      """
    let decoded = try JSONDecoder().decode(ActionItem.self, from: Data(json.utf8))
    XCTAssertEqual(decoded.ownerName, "Eddie Thai")
    XCTAssertEqual(decoded.dueAt, ISO8601DateFormatter().date(from: "2026-10-07T16:00:00Z"))
    XCTAssertEqual(decoded.context, "Eddie said they would follow up.")

    let reread = try JSONDecoder().decode(ActionItem.self, from: JSONEncoder().encode(decoded))
    XCTAssertEqual(reread, decoded)
  }

  func testLegacyCachedRowWithoutTheFieldsStillDecodes() throws {
    let decoded = try JSONDecoder().decode(
      ActionItem.self, from: Data(#"{"description": "Old item", "completed": true}"#.utf8))
    XCTAssertNil(decoded.ownerName)
    XCTAssertNil(decoded.dueAt)
    XCTAssertNil(decoded.context)
  }
}
