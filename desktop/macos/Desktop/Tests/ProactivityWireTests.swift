import Foundation
import XCTest

@testable import Omi_Computer

final class ProactivityWireTests: XCTestCase {
  struct Fixture: Decodable {
    let feed: OmiAPI.ProactivityFeedResponse
    let outcome: OmiAPI.ProactivityOutcomeResponse
    let producer_items: [OmiAPI.ProactivityFeedItem]
    let mentor_push: [String: String]
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

  @MainActor
  func testProducerTargetsAndIdentityOnlyPushShareConsumerContract() throws {
    var root = URL(fileURLWithPath: #filePath)
    for _ in 0..<5 { root.deleteLastPathComponent() }
    let data = try Data(contentsOf: root.appendingPathComponent("contracts/parity/proactivity_v2.json"))
    let fixture = try JSONDecoder().decode(Fixture.self, from: data)
    XCTAssertEqual(
      fixture.producer_items.map { ProactivityNotificationAdapter.target(for: $0) },
      [.conversation("synthetic-conversation"), .actionItem("synthetic-task")])
    var event = fixture.mentor_push
    event["type"] = "proactivity_v2"
    XCTAssertTrue(ProactivityFeedConsumer.isListenWakeup(event))
    XCTAssertFalse(ProactivityFeedConsumer.isListenWakeup(["type": "proactive_message", "app_id": "mentor"]))
    event.removeValue(forKey: "item_id")
    XCTAssertFalse(ProactivityFeedConsumer.isListenWakeup(event))
  }

  func testNullItemsAreRejected() {
    let data = Data(
      #"{"enabled":true,"items":null,"has_more":false,"next_cursor":"","server_time":"2026-10-03T12:00:00Z"}"#.utf8)
    XCTAssertThrowsError(try JSONDecoder().decode(OmiAPI.ProactivityFeedResponse.self, from: data))
  }
}
