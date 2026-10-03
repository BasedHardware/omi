import Foundation
import XCTest

@testable import Omi_Computer

final class ProactivityWireTests: XCTestCase {
  struct Fixture: Decodable {
    let feed: OmiAPI.ProactivityFeedResponse
    let outcome: OmiAPI.ProactivityOutcomeResponse
  }

  func testSharedFeedAndOutcome() throws {
    var root = URL(fileURLWithPath: #filePath)
    for _ in 0..<5 { root.deleteLastPathComponent() }
    let data = try Data(contentsOf: root.appendingPathComponent("contracts/parity/proactivity_v2.json"))
    let fixture = try JSONDecoder().decode(Fixture.self, from: data)
    XCTAssertEqual(fixture.feed.items.first?.producer, "future_registered_producer")
    XCTAssertEqual(fixture.feed.items.first?.target.id, "synthetic-task")
    XCTAssertEqual(fixture.feed.items.first?.createdAt, "2026-10-03T12:00:00Z")
    XCTAssertTrue(fixture.outcome.acted24h)
    XCTAssertFalse(fixture.outcome.negative)
  }

  func testNullItemsAreRejected() {
    let data = Data(
      #"{"enabled":true,"items":null,"has_more":false,"next_cursor":"","server_time":"2026-10-03T12:00:00Z"}"#.utf8)
    XCTAssertThrowsError(try JSONDecoder().decode(OmiAPI.ProactivityFeedResponse.self, from: data))
  }
}
