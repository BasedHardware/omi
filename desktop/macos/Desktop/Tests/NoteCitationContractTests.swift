import Foundation
import XCTest

@testable import Omi_Computer

final class NoteCitationContractTests: XCTestCase {
  func testThousandsOfProtectedUnitsRestoreExactlyIncludingCodeNestedInALink() {
    // Keys used to grow with the unit count and restore once per unit: quadratic.
    let many = (0..<3000).map { "`c\($0)` [s01234]" }.joined(separator: " ")
    let kept = (0..<3000).map { "`c\($0)`" }.joined(separator: " ")
    XCTAssertEqual(NoteCitationContract.repair(many, valid: ["s01234"]).text, kept)
    let nested = NoteCitationContract.repair("See [`x`](https://e.com) [s01234].", valid: ["s01234"])
    XCTAssertEqual(nested.text, "See [`x`](https://e.com).")
    XCTAssertEqual(nested.sourceIDs, ["s01234"])
  }

  func testHandAuthoredCrossClientContract() throws {
    // Read the single tracked contract directly, never a generated fixture copy.
    let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
      .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
    let contract = try JSONDecoder().decode(
      Contract.self,
      from: Data(
        contentsOf:
          root.appendingPathComponent("contracts/note_citation_contract.json")))
    XCTAssertFalse(contract.cases.isEmpty)
    print("Cross-client note citation contract: \(contract.cases.count) vectors")
    for item in contract.cases {
      let knownIDs = item.known_ids ?? contract.known_ids
      let result = NoteCitationContract.repair(item.input, valid: Set(knownIDs))
      XCTAssertEqual(result.text, item.output, item.name)
      XCTAssertEqual(result.sourceIDs, item.source_ids, item.name)
      XCTAssertEqual(NoteCitationContract.repair(result.text, valid: Set(knownIDs)).text, item.output, item.name)
      let segments = knownIDs.map {
        TranscriptSegment(
          id: $0, backendId: nil, text: "Evidence", speaker: nil, isUser: false,
          personId: nil, start: 0, end: 1)
      }
      let section = SummarySection(heading: item.input, bodyMarkdown: item.input, sourceSegmentIDs: [])
      let presented = ConversationSummarySelection.presentableSection(section, segments: segments)
      XCTAssertEqual(presented.heading, item.output, item.name)
      XCTAssertEqual(presented.bodyMarkdown, item.output, item.name)
      XCTAssertEqual(presented.sourceSegmentIDs, item.source_ids, item.name)
      XCTAssertEqual(section.bodyMarkdown, item.input, "Read-time repair must not mutate the stored note")
    }
  }

  private struct Contract: Decodable {
    let known_ids: [String]
    let cases: [Case]
  }
  private struct Case: Decodable {
    let name: String
    let input: String
    let output: String
    let source_ids: [String]
    let known_ids: [String]?
  }
}
