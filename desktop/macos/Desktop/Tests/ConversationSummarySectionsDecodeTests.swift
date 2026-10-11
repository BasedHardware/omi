import XCTest

@testable import Omi_Computer

/// The structured summary payload must survive the network/domain Codable boundary. SQLite cache
/// persistence is covered by `MeetingSummaryPersistenceTests` through `TranscriptionStorage`.
/// These run the real `JSONDecoder`/`JSONEncoder` over the real domain type, so they fail if the
/// field is dropped again in either direction.
final class ConversationSummarySectionsDecodeTests: XCTestCase {
  private func decodeStructured(_ json: String) throws -> Structured {
    try JSONDecoder().decode(Structured.self, from: Data(json.utf8))
  }

  func testSectionsSurviveTheWireDecode() throws {
    let structured = try decodeStructured(
      """
      {
        "title": "App Navigation Walkthrough",
        "overview": "A short compatibility paragraph.",
        "emoji": "🧠",
        "category": "other",
        "action_items": [],
        "events": [],
        "sections": [
          {
            "heading": "App Navigation Walkthrough",
            "body_markdown": "Walked the **Activity** tab end to end.",
            "source_segment_ids": ["seg-1", "seg-2"]
          },
          {
            "heading": "Follow-Up Request",
            "body_markdown": "- Fix the routing\\n- Restore the summary"
          }
        ]
      }
      """)

    XCTAssertEqual(structured.sections.count, 2, "the summary's headed blocks were dropped")
    XCTAssertEqual(structured.sections.first?.heading, "App Navigation Walkthrough")
    XCTAssertEqual(
      structured.sections.first?.bodyMarkdown, "Walked the **Activity** tab end to end.")
    XCTAssertEqual(structured.sections.first?.sourceSegmentIDs, ["seg-1", "seg-2"])
    // Absent `source_segment_ids` is routine on older captures and must not fail the decode.
    XCTAssertEqual(structured.sections.last?.sourceSegmentIDs, [])
  }

  /// A capture processed before the notes pipeline carries no `sections` at all. Its whole summary
  /// really is `overview`, so the field must decode to empty rather than throw — otherwise the
  /// entire conversation fails to decode and the row disappears.
  func testACaptureWithoutSectionsStillDecodes() throws {
    let structured = try decodeStructured(
      """
      {
        "title": "Older capture",
        "overview": "The whole summary, the old way.",
        "emoji": "🧠",
        "category": "other",
        "action_items": [],
        "events": []
      }
      """)

    XCTAssertEqual(structured.sections, [])
    XCTAssertEqual(structured.overview, "The whole summary, the old way.")
  }

  /// Domain Codable must retain sections for adapters that serialize structured data. The actual
  /// SQLite column and record round trip are tested through production storage separately.
  func testSectionsSurviveTheDomainCodableRoundTrip() throws {
    let original = Structured(
      title: "Title",
      overview: "Compatibility paragraph.",
      emoji: "🧠",
      category: "other",
      actionItems: [],
      events: [],
      sections: [
        SummarySection(
          heading: "Technical Friction",
          bodyMarkdown: "The pill opened the wrong page.",
          sourceSegmentIDs: ["seg-9"])
      ]
    )

    let restored = try JSONDecoder().decode(
      Structured.self, from: JSONEncoder().encode(original))

    XCTAssertEqual(restored.sections, original.sections)
  }
}
