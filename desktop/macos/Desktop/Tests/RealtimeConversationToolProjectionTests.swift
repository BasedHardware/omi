import Foundation
import XCTest

@testable import Omi_Computer

final class RealtimeConversationToolProjectionTests: XCTestCase {
  func testProjectionAppliesOnlyToRealtimeVoiceSurfaces() {
    XCTAssertTrue(RealtimeConversationToolProjection.applies(to: "realtime_voice"))
    XCTAssertTrue(RealtimeConversationToolProjection.applies(to: "realtime"))
    XCTAssertFalse(RealtimeConversationToolProjection.applies(to: "main_chat"))
    XCTAssertFalse(RealtimeConversationToolProjection.applies(to: nil))
  }

  func testRealtimeRequestLimitDefaultsAndCapsBeforeBackendRead() {
    XCTAssertEqual(RealtimeConversationToolProjection.requestLimit(nil), 5)
    XCTAssertEqual(RealtimeConversationToolProjection.requestLimit(0), 1)
    XCTAssertEqual(RealtimeConversationToolProjection.requestLimit(4), 4)
    XCTAssertEqual(RealtimeConversationToolProjection.requestLimit(100), 8)
  }

  func testStructuredProjectionFitsRelayBudgetWithoutDuplicatedCitationGuide() throws {
    let sources = (1...12).map { index in
      APIClient.ToolSource(
        kind: "conversation",
        sourceID: "conversation-\(index)",
        title: String(repeating: "Title \(index) ", count: 30),
        preview: String(repeating: "🧠 detailed summary \(index) ", count: 80),
        createdAt: "2026-08-28T23:\(String(format: "%02d", index)):00Z",
        momentTimestampMs: nil,
        appName: nil,
        url: nil)
    }
    let response = APIClient.ToolResponse(
      toolName: "get_conversations",
      resultText: "FULL_RESULT_SHOULD_NOT_BE_DUPLICATED\nCitation guide JSON",
      isError: false,
      sources: sources)

    let result = RealtimeConversationToolProjection.makeResult(response, limit: 100)
    let object = try XCTUnwrap(
      JSONSerialization.jsonObject(with: Data(result.utf8)) as? [String: Any])
    let items = try XCTUnwrap(object["items"] as? [[String: Any]])

    XCTAssertEqual(object["ok"] as? Bool, true)
    XCTAssertEqual(object["order"] as? String, "newest_first")
    XCTAssertEqual(items.count, 8)
    XCTAssertLessThan(result.utf8.count, 6_500)
    XCTAssertFalse(result.contains("FULL_RESULT_SHOULD_NOT_BE_DUPLICATED"))
    XCTAssertFalse(result.contains("Citation guide JSON"))
    XCTAssertFalse(result.contains("source_id"))
    XCTAssertLessThanOrEqual((items[0]["title"] as? String)?.utf8.count ?? .max, 160)
    XCTAssertLessThanOrEqual((items[0]["summary"] as? String)?.utf8.count ?? .max, 420)
  }

  func testLegacyTextFallbackRemainsBoundedAndSuccessful() throws {
    let response = APIClient.ToolResponse(
      toolName: "get_conversations",
      resultText: String(repeating: "recent conversation ", count: 1_000),
      isError: false,
      sources: nil)

    let result = RealtimeConversationToolProjection.makeResult(response, limit: 5)
    let object = try XCTUnwrap(
      JSONSerialization.jsonObject(with: Data(result.utf8)) as? [String: Any])
    let text = try XCTUnwrap(object["text"] as? String)

    XCTAssertEqual(object["ok"] as? Bool, true)
    XCTAssertLessThanOrEqual(text.utf8.count, 5_500)
    XCTAssertLessThan(result.utf8.count, 6_000)
  }

  func testBackendErrorIsPreservedInsteadOfPresentedAsEmptySuccess() throws {
    let response = APIClient.ToolResponse(
      toolName: "search_conversations",
      resultText: "Error retrieving conversations: unavailable",
      isError: true,
      sources: [])

    let result = RealtimeConversationToolProjection.makeResult(response, limit: 5)
    let object = try XCTUnwrap(
      JSONSerialization.jsonObject(with: Data(result.utf8)) as? [String: Any])

    XCTAssertEqual(object["ok"] as? Bool, false)
    XCTAssertEqual(object["error"] as? String, "Error retrieving conversations: unavailable")
  }
}
