import XCTest

@testable import Omi_Computer

final class ClientProcessingContractTests: XCTestCase {
  func testSchemaVersionMatchesBackendLiteralOne() {
    XCTAssertEqual(ClientProcessingContract.schemaVersion, 1)
  }

  func testGeneratedTypesRoundTripThePydanticRequiredKeys() throws {
    let projection = try decodeGolden()
    let data = try ClientProcessingContract.encode(projection)
    let object = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])

    XCTAssertEqual(object["schema_version"] as? Int, 1)
    XCTAssertEqual(object["transcript_sha256"] as? String, emptyDigest)
    XCTAssertNotNil(object["structure"] as? [String: Any])
    XCTAssertNotNil(object["action_items"] as? [Any])
    XCTAssertNotNil(object["provenance"] as? [String: Any])

    let provenance = try XCTUnwrap(object["provenance"] as? [String: Any])
    XCTAssertEqual(provenance["runtime"] as? String, "local")
    XCTAssertEqual(provenance["device_class"] as? String, "macos")
    XCTAssertEqual(provenance["generated_at"] as? String, "2024-01-01T20:14:00Z")

    let decoded = try ClientProcessingContract.decode(data)
    XCTAssertEqual(decoded.schemaVersion, 1)
    XCTAssertEqual(decoded.structure.title, "Standup")
    XCTAssertEqual(decoded.actionItems?.first?.description_, "Open the S11 PR")
  }

  func testOverCapTitleIsClippedBeforePersist() {
    let long = String(repeating: "a", count: 200)
    XCTAssertEqual(ClientProcessingContract.clip(long, max: 120, empty: "x").count, 120)
  }

  func testAssembleStampsSchemaVersionAndHash() throws {
    let draft = LocalSummaryDraft(
      title: "Ship S10",
      overview: "Chunk then reduce.",
      actionItems: [LocalActionItemDraft(description: "Open S11")]
    )
    let projection = ClientProcessingContract.assemble(
      draft: draft,
      transcriptSha256: emptyDigest,
      provenance: OmiAPI.ProjectionProvenance(
        deviceClass: "macos",
        generatedAt: "2024-01-01T20:14:00Z",
        modelId: "local-server",
        runtime: "local"
      ),
      fallbackTitle: "Recording"
    )
    XCTAssertEqual(projection.schemaVersion, 1)
    XCTAssertEqual(projection.transcriptSha256, emptyDigest)
    XCTAssertEqual(projection.structure.title, "Ship S10")
    XCTAssertEqual(projection.provenance.runtime, "local")
    XCTAssertEqual(projection.transcriptSha256.count, 64)
  }

  func testNumericDatetimeIsNotEmittedForProvenance() {
    let stamped = ClientProcessingContract.iso8601(Date(timeIntervalSince1970: 1_704_140_040))
    XCTAssertEqual(stamped, "2024-01-01T20:14:00Z")
    XCTAssertFalse(stamped.contains("1704140040"))
  }

  private var emptyDigest: String {
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
  }

  private func decodeGolden() throws -> OmiAPI.ClientProcessing {
    let json = """
      {
        "schema_version": 1,
        "transcript_sha256": "\(emptyDigest)",
        "structure": {
          "title": "Standup",
          "overview": "Shipped the summarizer.",
          "emoji": "🧠",
          "category": "other",
          "sections": [{"heading": "Notes", "body_markdown": "Shipped."}],
          "events": []
        },
        "action_items": [{"description": "Open the S11 PR", "completed": false}],
        "provenance": {
          "model_id": "local",
          "runtime": "local",
          "device_class": "macos",
          "generated_at": "2024-01-01T20:14:00Z"
        }
      }
      """
    return try ClientProcessingContract.decode(Data(json.utf8))
  }
}
