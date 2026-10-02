import Foundation
import XCTest

@testable import Omi_Computer

final class ScreenTaskPipelineTests: XCTestCase {
  private func ocr(_ lines: [(String, Double)]) -> OCRResult {
    OCRResult(
      fullText: lines.map { $0.0 }.joined(separator: "\n"),
      blocks: lines.map {
        OCRTextBlock(text: $0.0, x: $0.1, y: 0.5, width: 0.1, height: 0.02, confidence: 1)
      }, processedAt: Date(timeIntervalSince1970: 0))
  }

  @MainActor func testFlagDefaultsOffWithoutPostHogAdmission() {
    XCTAssertFalse(ScreenTaskFeature.isEnabled)
  }

  func testMainPaneDedupeIgnoresSidebarAndLayoutJitterButPassesNovelTask() {
    let first = ScreenTaskDedupe.lines(
      ocr: ocr([("Unread 7", 0.05), ("Please send Alex the draft", 0.5)]), app: "Telegram")
    let jitter = ScreenTaskDedupe.lines(
      ocr: ocr([("Unread 8", 0.05), ("please  send Alex the draft!", 0.51)]), app: "Telegram")
    var dedupe = ScreenTaskDedupe()
    let now = Date(timeIntervalSince1970: 100)
    XCTAssertFalse(dedupe.shouldSkip(key: "owner:1:Telegram", lines: first, now: now))
    dedupe.record(key: "owner:1:Telegram", lines: first, now: now)
    XCTAssertTrue(dedupe.shouldSkip(key: "owner:1:Telegram", lines: jitter, now: now.addingTimeInterval(10)))
    XCTAssertFalse(dedupe.shouldSkip(key: "owner:1:Telegram", lines: first.union(["also send the budget"]), now: now))
    XCTAssertFalse(dedupe.shouldSkip(key: "owner:2:Telegram", lines: first, now: now))
    XCTAssertFalse(dedupe.shouldSkip(key: "owner:1:Telegram", lines: first, now: now.addingTimeInterval(61)))
    XCTAssertFalse(dedupe.shouldSkip(key: "owner:1:Telegram", lines: [], now: now))
  }

  func testScrollingAwayCanSkipButChangedDeadlineCannot() {
    var dedupe = ScreenTaskDedupe()
    let now = Date(timeIntervalSince1970: 100)
    dedupe.record(key: "app", lines: ["send report friday", "older line"], now: now)
    XCTAssertTrue(dedupe.shouldSkip(key: "app", lines: ["send report friday"], now: now))
    XCTAssertFalse(dedupe.shouldSkip(key: "app", lines: ["send report monday"], now: now))
    XCTAssertFalse(dedupe.shouldSkip(key: "app", lines: ["do not send report friday"], now: now))
  }

  private func row(_ id: String?, _ description: String, status: String = "active") -> TaskSearchResult {
    TaskSearchResult(
      taskID: id, description: description, status: status, similarity: 0.9, matchType: "vector", relevanceScore: nil)
  }

  func testContextUsesOnlyEightRelatedRowsAndStagedIDsAreNeverTargets() throws {
    let vector = (0..<12).map { row("task-\($0)", "related task \($0)") }
    let selected = ScreenTaskContext.select(keywords: vector + [vector[0]], query: "related task")
    XCTAssertEqual(selected.count, 8)
    let body = try ScreenTaskPrompt.request(
      jpeg: Data([1, 2]), app: "Telegram", profile: "synthetic user", tasks: selected, today: "2026-10-02")
    let payload = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
    let config = try XCTUnwrap(payload["generationConfig"] as? [String: Any])
    XCTAssertEqual(config["thinkingConfig"] as? [String: String], ["thinkingLevel": "low"])
    let contents = try XCTUnwrap(payload["contents"] as? [[String: Any]])
    let parts = try XCTUnwrap(contents[0]["parts"] as? [[String: Any]])
    XCTAssertFalse((parts[0]["text"] as? String ?? "").contains("task-8"))
    XCTAssertEqual((parts[1]["inlineData"] as? [String: String])?["data"], Data([1, 2]).base64EncodedString())
  }

  private func response(relation: String, id: String, capture: String = "direct_request") throws -> ScreenTaskResponse {
    let item: [String: Any] = [
      "title": "Send Alex the updated project budget document", "description": "context", "deadline": "2026-10-05",
      "priority": "medium", "confidence": 0.9, "relation": relation, "related_id": id, "evidence": "visible ask",
      "capture_kind": capture, "owner": "user", "concrete_deliverable": true, "public_broadcast": false,
      "direct_mention": true, "ownership_confidence": 0.8, "tags": ["work"], "source_category": "direct_request",
      "source_subcategory": "message",
    ]
    let data = try JSONSerialization.data(withJSONObject: [
      "screen_kind": "open_conversation", "context_summary": "conversation", "current_activity": "reading",
      "tasks": [item],
    ])
    return try JSONDecoder().decode(ScreenTaskResponse.self, from: data)
  }

  func testCanonicalDuplicateRefinementAndCompletionFactsSurviveMapping() throws {
    for relation in ["duplicate", "refines", "completes"] {
      let response = try response(
        relation: relation, id: "canonical", capture: relation == "completes" ? "already_done" : "direct_request")
      let results = try response.results(
        app: "Messages", context: [row("canonical", "Send budget")], today: "2026-10-02")
      let task = try XCTUnwrap(results.first?.task)
      XCTAssertEqual(task.owner, "user")
      XCTAssertEqual(task.ownershipConfidence, 0.8)
      XCTAssertEqual(task.sourceCategory, "direct_request")
      XCTAssertEqual(task.sourceApp, "Messages")
      XCTAssertEqual(task.inferredDeadline, "2026-10-05")
      XCTAssertEqual(task.directMention, true)
      XCTAssertEqual(task.duplicateOf, relation == "duplicate" ? "canonical" : nil)
      XCTAssertEqual(task.refinesTask, relation == "duplicate" ? nil : "canonical")
      XCTAssertEqual(task.alreadyDone, relation == "completes")
    }
  }

  func testUnknownOrStagedRelationCannotUpdateAnExistingTask() throws {
    let result = try response(relation: "refines", id: "unknown")
    XCTAssertThrowsError(
      try result.results(app: "Messages", context: [row(nil, "Local staged task")], today: "2026-10-02"))
    XCTAssertThrowsError(
      try response(relation: "completes", id: "canonical").results(
        app: "Messages", context: [row("canonical", "Known task")], today: "2026-10-02"))
  }

  func testEmptyResponsePreservesActivityObservation() throws {
    let data = Data(
      #"{"screen_kind":"other","context_summary":"reading","current_activity":"browsing","tasks":[]}"#.utf8)
    let response = try JSONDecoder().decode(ScreenTaskResponse.self, from: data)
    let results = try response.results(app: "Browser", context: [], today: "2026-10-02")
    XCTAssertEqual(results.count, 1)
    XCTAssertFalse(results[0].hasNewTask)
    XCTAssertNil(results[0].task)
    XCTAssertEqual(results[0].contextSummary, "reading")
  }

  func testLocalContextRanksStagedAndActiveCandidatesTogether() {
    let candidates = [row("low", "send generic email"), row(nil, "send Alex budget draft", status: "staged")]
    XCTAssertNil(ScreenTaskContext.select(keywords: candidates, query: "Alex budget draft", limit: 1).first?.taskID)
  }

  func testLegacyFallbackRejectsRevokedFrameBeforeNetworkOrQuotaWork() async throws {
    let authority = RuntimeOwnerAuthorizationAuthority()
    let stale = try XCTUnwrap(authority.capture(ownerID: "synthetic-user", expectedOwnerID: "synthetic-user"))
    let client = try GeminiClient(model: "gemini-2.5-flash", workload: .extraction)
    do {
      _ = try await client.sendImageToolLoop(contents: [], systemPrompt: "synthetic", tools: [], authorization: stale)
      XCTFail("Foreign/revoked frame authorization must not dispatch")
    } catch is CancellationError {}
  }

  func testDatesDoNotInventOrRetainInvalidPastDeadlines() {
    XCTAssertNil(ScreenTaskResponse.deadline("", today: "2026-10-02"))
    XCTAssertNil(ScreenTaskResponse.deadline("2026-09-01", today: "2026-10-02"))
    XCTAssertNil(ScreenTaskResponse.deadline("2026-10-99", today: "2026-10-02"))
    XCTAssertEqual(ScreenTaskResponse.deadline("2026-10-05", today: "2026-10-02"), "2026-10-05")
  }
}
