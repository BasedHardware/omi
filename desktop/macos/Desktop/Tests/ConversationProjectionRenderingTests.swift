import XCTest

@testable import Omi_Computer

final class ConversationProjectionRenderingTests: XCTestCase {
  func testValidProjectionReplacesMinimumAndKeepsAttribution() throws {
    let conversation = try ProjectionRenderingFixture.decode()
    XCTAssertEqual(conversation.title, "On-device title")
    XCTAssertEqual(conversation.overview, "On-device overview")
    XCTAssertEqual(conversation.structured.emoji, "📌")
    XCTAssertEqual(conversation.structured.category, "work")
    XCTAssertEqual(conversation.structured.sections.first?.bodyMarkdown, "We agreed")
    XCTAssertEqual(conversation.structured.events.first?.title, "Review")
    XCTAssertEqual(conversation.structured.events.first?.duration, 30)
    XCTAssertEqual(conversation.localSummary?.modelId, "test-model")
    XCTAssertEqual(conversation.localSummary?.runtime, "test-runtime")
    XCTAssertEqual(conversation.localSummary?.deviceClass, "mac")
    XCTAssertEqual(conversation.localSummary?.generatedAt, "2026-09-18T00:00:00Z")
    XCTAssertEqual(conversation.localSummary?.transcriptVerified, true)
    XCTAssertEqual(conversation.localSummary?.schemaVersion, 1)
  }

  func testLegacyConversationWithoutProjectionKeepsCanonicalStructure() throws {
    let conversation = try ProjectionRenderingFixture.decode { $0.removeValue(forKey: "client_processing") }
    XCTAssertEqual(conversation.title, "I agree")
    XCTAssertEqual(conversation.overview, "")
    XCTAssertNil(conversation.localSummary)
  }

  func testFutureVersionWithIncompatibleBodyFallsBackWithoutLosingConversation() throws {
    let conversation = try ProjectionRenderingFixture.decode {
      $0["client_processing"] = ["schema_version": 2, "structure": "future shape"]
    }
    XCTAssertEqual(conversation.title, "I agree")
    XCTAssertNil(conversation.localSummary)
  }

  func testMalformedV1FallsBackWithoutLosingConversation() throws {
    let conversation = try ProjectionRenderingFixture.decode {
      $0["client_processing"] = ["schema_version": 1]
    }
    XCTAssertEqual(conversation.title, "I agree")
    XCTAssertNil(conversation.localSummary)
  }

  func testChangedTextOrAttributionRejectsStaleProjection() throws {
    for change in [["text": "Changed"], ["speaker": "Mallory"], ["person_id": "alice"], ["speaker_id": 7]]
      as [[String: Any]]
    {
      let conversation = try ProjectionRenderingFixture.decode {
        var segments = ProjectionRenderingFixture.objects($0, "transcript_segments")
        segments[0].merge(change) { _, new in new }
        $0["transcript_segments"] = segments
      }
      XCTAssertEqual(conversation.title, "I agree")
      XCTAssertNil(conversation.localSummary)
    }
  }

  func testExplicitEmptyAndNullTranscriptRejectNonemptyDigest() throws {
    for transcript: Any in [[], NSNull()] {
      let conversation = try ProjectionRenderingFixture.decode { $0["transcript_segments"] = transcript }
      XCTAssertNil(conversation.localSummary)
    }
  }

  func testListProjectionUsesServerBindingAndReportsUnverifiedTranscript() throws {
    let conversation = try ProjectionRenderingFixture.decode { $0.removeValue(forKey: "transcript_segments") }
    XCTAssertEqual(conversation.title, "On-device title")
    XCTAssertEqual(conversation.localSummary?.transcriptVerified, false)
    XCTAssertFalse(conversation.transcriptSegmentsIncluded)
  }

  func testProjectionWinsRegardlessOfStaleOrAbsentProcessingState() throws {
    for state: Any in ["local_pending", "none", NSNull()] {
      let conversation = try ProjectionRenderingFixture.decode { $0["processing_state"] = state }
      XCTAssertEqual(conversation.title, "On-device title")
    }
  }

  func testCloudEnrichmentOutranksRetainedProjectionAfterUpgrade() throws {
    for enrichment: [String: Any] in [
      ["overview": "Cloud summary"],
      ["sections": [["heading": "Cloud", "body_markdown": "Cloud section"]]],
      ["category": "work"],
      ["events": [["title": "Cloud event", "start": "2026-09-18T00:00:00Z"]]],
    ] {
      let conversation = try ProjectionRenderingFixture.decode {
        var structured = ProjectionRenderingFixture.object($0, "structured")
        structured["title"] = "Cloud title"
        structured.merge(enrichment) { _, new in new }
        $0["structured"] = structured
      }
      XCTAssertEqual(conversation.title, "Cloud title")
      XCTAssertNil(conversation.localSummary)
      XCTAssertTrue(conversation.structured.actionItems.isEmpty)
    }
  }

  func testActionMergePreservesCompletedAndReopenedCanonicalItems() throws {
    let conversation = try ProjectionRenderingFixture.decode {
      var structured = ProjectionRenderingFixture.object($0, "structured")
      structured["action_items"] = [
        ["description": "Send notes", "completed": true, "target_task_id": "task-1"],
        ["description": "Book room", "completed": false],
        ["description": "User added", "completed": false],
      ]
      $0["structured"] = structured
      var projection = ProjectionRenderingFixture.object($0, "client_processing")
      projection["action_items"] = [
        ["description": "Send notes", "completed": false],
        ["description": "Book room", "completed": true],
        ["description": "New item"], ["description": "New item", "completed": true],
      ]
      $0["client_processing"] = projection
    }
    XCTAssertEqual(
      conversation.structured.actionItems.map(\.description), ["Send notes", "Book room", "User added", "New item"])
    XCTAssertEqual(conversation.structured.actionItems.map(\.completed), [true, false, false, false])
    XCTAssertEqual(conversation.structured.actionItems[0].targetTaskID, "task-1")
    XCTAssertNil(conversation.structured.actionItems.last?.targetTaskID)
  }

  func testReconciliationPreservesProjectionAndPendingTitleOverlay() throws {
    let conversation = try ProjectionRenderingFixture.decode()
    var pending = ConversationPendingMutation()
    pending.setTitle("User title")
    let result = ConversationReconciliationPolicy.mergeList(
      server: [conversation], current: [], pendingMutations: [conversation.id: pending])
    XCTAssertEqual(result.conversations.first?.title, "User title")
    XCTAssertEqual(result.conversations.first?.overview, conversation.overview)
    XCTAssertEqual(result.conversations.first?.localSummary, conversation.localSummary)
  }

  func testListReconciliationDoesNotAttachAnOlderTranscriptToNewProjection() throws {
    let current = try ProjectionRenderingFixture.decode()
    let server = try ProjectionRenderingFixture.decode {
      $0.removeValue(forKey: "transcript_segments")
      var projection = ProjectionRenderingFixture.object($0, "client_processing")
      projection["transcript_sha256"] = String(repeating: "a", count: 64)
      $0["client_processing"] = projection
    }
    let retained = ConversationReconciliationPolicy.retainingLoadedTranscript(server: server, current: current)
    XCTAssertEqual(retained.title, "On-device title")
    XCTAssertFalse(retained.transcriptSegmentsIncluded)
    XCTAssertTrue(retained.transcriptSegments.isEmpty)
    let same = try ProjectionRenderingFixture.decode { $0.removeValue(forKey: "transcript_segments") }
    let matched = ConversationReconciliationPolicy.retainingLoadedTranscript(server: same, current: current)
    XCTAssertEqual(matched.transcriptSegments.map(\.text), current.transcriptSegments.map(\.text))
    let repeated = ConversationReconciliationPolicy.retainingLoadedTranscript(server: same, current: matched)
    XCTAssertEqual(repeated.transcriptSegments.map(\.text), current.transcriptSegments.map(\.text))
  }

  func testDomainCodableRoundTripKeepsSelectedSummaryAndProvenance() throws {
    let original = try ProjectionRenderingFixture.decode()
    let encoder = JSONEncoder()
    encoder.dateEncodingStrategy = .iso8601
    let decoder = JSONDecoder()
    decoder.dateDecodingStrategy = .iso8601
    let restored = try decoder.decode(ServerConversation.self, from: encoder.encode(original))
    XCTAssertEqual(restored.structured, original.structured)
    XCTAssertEqual(restored.localSummary, original.localSummary)
  }
}

/// Python v5 known-answer digest, shared with TranscriptHashTests; never computed by the code under test.
enum ProjectionRenderingFixture {
  /// Read a nested fixture object without a force cast, which SwiftLint bans.
  ///
  /// A silent `?? [:]` would be worse than the force cast it replaces: a
  /// mistyped key would mutate nothing, the fixture would decode unchanged,
  /// and the assertion would pass for the wrong reason. A miss is a test
  /// failure, reported at the caller.
  static func object(
    _ json: [String: Any], _ key: String, file: StaticString = #filePath, line: UInt = #line
  ) -> [String: Any] {
    guard let value = json[key] as? [String: Any] else {
      XCTFail("fixture key '\(key)' is not an object", file: file, line: line)
      return [:]
    }
    return value
  }

  static func objects(
    _ json: [String: Any], _ key: String, file: StaticString = #filePath, line: UInt = #line
  ) -> [[String: Any]] {
    guard let value = json[key] as? [[String: Any]] else {
      XCTFail("fixture key '\(key)' is not an array of objects", file: file, line: line)
      return []
    }
    return value
  }

  static func decode(_ mutate: (inout [String: Any]) -> Void = { _ in }) throws -> ServerConversation {
    var json: [String: Any] = [
      "id": "projection-test", "created_at": "2026-09-18T00:00:00Z", "updated_at": "2026-09-18T00:01:00Z",
      "status": "completed", "processing_state": "local_pending",
      "structured": ["title": "I agree", "overview": "", "category": "other", "emoji": "🧠"],
      "transcript_segments": [
        ["text": "I agree", "speaker": "Alice", "speaker_id": 0, "is_user": false, "start": 0, "end": 1],
        ["text": "I refuse", "speaker": "Bob", "speaker_id": 0, "is_user": false, "start": 1, "end": 2],
      ],
      "client_processing": [
        "schema_version": 1,
        "transcript_sha256": "6698e08ad93c92100b75e3ab279d15bfa3a70288b1693377841759a26e588d40",
        "structure": [
          "title": "On-device title", "overview": "On-device overview", "emoji": "📌", "category": "work",
          "sections": [["heading": "Decisions", "body_markdown": "We agreed"]],
          "events": [["title": "Review", "start": "2026-09-19T00:00:00Z", "duration": 30]],
        ],
        "action_items": [["description": "Send notes", "completed": false]],
        "provenance": [
          "model_id": "test-model", "runtime": "test-runtime", "device_class": "mac",
          "generated_at": "2026-09-18T00:00:00Z",
        ],
      ],
    ]
    mutate(&json)
    let decoder = JSONDecoder()
    decoder.dateDecodingStrategy = .iso8601
    return try decoder.decode(ServerConversation.self, from: JSONSerialization.data(withJSONObject: json))
  }
}
