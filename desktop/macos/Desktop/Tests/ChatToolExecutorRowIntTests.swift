import XCTest

@testable import Omi_Computer

/// Regression coverage for `ChatToolExecutor.rowInt`. GRDB decodes SQLite
/// INTEGER columns (including COUNT/MIN/MAX aggregates) to `Int64`, and
/// `Int64 as? Int` is ALWAYS nil in Swift — no numeric bridging. So the daily
/// recap / file-scan tools that read row integers with a bare `row["col"] as? Int`
/// silently reported 0 captures, unchecked ("done") tasks as not done, 0m focus
/// durations, and "0 files" per type. `rowInt` reads the value correctly.
final class ChatToolExecutorRowIntTests: XCTestCase {
  private func source(_ index: Int) -> APIClient.ToolSource {
    APIClient.ToolSource(
      kind: ChatCitationReference.Kind.conversation.rawValue,
      sourceID: "conversation-\(index)",
      title: "Planning \(index)",
      preview: "Overview \(index)",
      createdAt: "2026-09-01T12:0\(index):00Z",
      momentTimestampMs: nil,
      appName: "Omi",
      url: nil)
  }

  private func object(_ result: String) throws -> [String: Any] {
    try XCTUnwrap(JSONSerialization.jsonObject(with: Data(result.utf8)) as? [String: Any])
  }

  func testDailyRecapTypedResultCarriesFiftyConversationItems() throws {
    let conversations: [[String: Any]] = (1...50).map { index in
      ["title": "Conversation \(index)", "summary": "Overview \(index)"]
    }
    let result = ChatToolExecutor.typedReadToolResult(
      toolName: "get_daily_recap",
      sections: [["name": "conversations", "total": 50, "items": conversations]],
      totals: ["conversations": 50])
    let object = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(result.utf8)) as? [String: Any])
    XCTAssertEqual(object["ok"] as? Bool, true)
    XCTAssertEqual(object["tool"] as? String, "get_daily_recap")
    let totals = try XCTUnwrap(object["totals"] as? [String: Int])
    XCTAssertEqual(totals["conversations"], 50)
    let sections = try XCTUnwrap(object["sections"] as? [[String: Any]])
    let section = try XCTUnwrap(sections.first { ($0["name"] as? String) == "conversations" })
    let items = try XCTUnwrap(section["items"] as? [[String: Any]])
    XCTAssertEqual(items.count, 50)
    XCTAssertEqual(items.first?["title"] as? String, "Conversation 1")
    XCTAssertEqual(items.last?["title"] as? String, "Conversation 50")
  }

  func testBackendReadWithNilSourcesPreservesRenderedText() throws {
    let result = ChatToolExecutor.typedBackendReadToolResult(
      toolName: "search_conversations",
      resultText: "Conversation search found Ada and the compiler discussion.",
      sources: nil,
      references: [])
    let sections = try XCTUnwrap(try object(result)["sections"] as? [[String: Any]])
    XCTAssertEqual(sections.first?["name"] as? String, "text")
    XCTAssertEqual(
      sections.first?["items"] as? [String], ["Conversation search found Ada and the compiler discussion."])
  }

  func testBackendReadWithEmptySourcesPreservesRenderedText() throws {
    let result = ChatToolExecutor.typedBackendReadToolResult(
      toolName: "get_memories",
      resultText: "No memories matched the selected date range.",
      sources: [],
      references: [])
    let sections = try XCTUnwrap(try object(result)["sections"] as? [[String: Any]])
    XCTAssertEqual(sections.first?["total"] as? Int, 1)
    XCTAssertEqual(sections.first?["items"] as? [String], ["No memories matched the selected date range."])
  }

  func testConversationSegmentsCarryOverviewAndTranscriptContent() throws {
    let rendered = """
      Conversation #1
      01 Sep 2026 at 12:00 EDT (Work)
      Compiler planning
      Overview: Ada proposed the release plan.
      Transcript:
      Ada: Keep the typed boundary.

      Conversation #2
      01 Sep 2026 at 11:00 EDT (Work)
      Runtime review
      Overview: Grace reviewed the projector.
      Transcript:
      Grace: Preserve the full conversation evidence.
      """
    let result = ChatToolExecutor.typedBackendReadToolResult(
      toolName: "search_conversations",
      resultText: rendered,
      sources: [source(1), source(2)],
      references: [])
    let sections = try XCTUnwrap(try object(result)["sections"] as? [[String: Any]])
    let items = try XCTUnwrap(sections.first?["items"] as? [[String: Any]])
    XCTAssertEqual(items.count, 2)
    XCTAssertTrue((items[0]["content"] as? String ?? "").contains("Ada: Keep the typed boundary."))
    XCTAssertTrue((items[1]["content"] as? String ?? "").contains("Grace reviewed the projector."))
    XCTAssertNil(sections.first { ($0["name"] as? String) == "text" })
  }

  func testRenderedRecordSegmentsRejectsAnInvalidConvertedRange() {
    let result = ChatToolExecutor.renderedRecordSegmentsForTesting(
      "Conversation #1\nHello",
      matchRanges: [NSRange(location: 10_000, length: 1)],
      expectedCount: 1)
    XCTAssertNil(result)
  }

  func testRealtimeConversationDefaultsAvoidTranscriptFetchCost() {
    let realtime = ChatToolExecutor.backendConversationDefaults(surfaceKind: "realtime_voice")
    XCTAssertEqual(realtime.limit, 5)
    XCTAssertFalse(realtime.includeTranscript)

    let chat = ChatToolExecutor.backendConversationDefaults(surfaceKind: "main_chat")
    XCTAssertEqual(chat.limit, 20)
    XCTAssertTrue(chat.includeTranscript)
  }

  func testUnresolvedCitationMarkersAreRemoved() {
    let reference = ChatCitationReference(
      ordinal: 41,
      kind: .conversation,
      sourceID: "conversation-1")
    let result = ChatToolExecutor.resolvingCitationMarkers(
      in: "First {{cite:1}} second {{cite:2}}",
      references: [reference])
    XCTAssertEqual(result, "First [41] second")
  }

  func testInt64AsIntNeverBridges() {
    // The exact defect the helper exists to work around. Cast from an `Any`
    // box (as production does with a GRDB row value) — spelling `Int64 as? Int`
    // directly is diagnosed as an always-failing cast under -warnings-as-errors.
    let boxed: Any = Int64(7)
    XCTAssertNil(boxed as? Int)
  }

  func testRowIntExtractsInt64Value() {
    XCTAssertEqual(ChatToolExecutor.rowInt(Int64(7)), 7)
    XCTAssertEqual(ChatToolExecutor.rowInt(Int64(0)), 0)
    XCTAssertEqual(ChatToolExecutor.rowInt(Int64(-3)), -3)
  }

  func testRowIntFallsBackToPlainInt() {
    // Defensive: an already-`Int` value still reads.
    XCTAssertEqual(ChatToolExecutor.rowInt(Int(42)), 42)
  }

  func testRowIntReturnsNilForMissingOrNonInteger() {
    XCTAssertNil(ChatToolExecutor.rowInt(nil))
    XCTAssertNil(ChatToolExecutor.rowInt("123"))
    XCTAssertNil(ChatToolExecutor.rowInt(3.5))
  }
}
