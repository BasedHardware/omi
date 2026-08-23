import XCTest

@testable import Omi_Computer

final class KnowledgeLedgerPromptProjectionTests: XCTestCase {
  func testCurrentProfileAndPlaybookHandlesAreBoundedAndDeterministic() {
    let projection = KnowledgeLedgerPromptProjection(rows: [
      row(
        id: "playbook-1",
        content: "Release the macOS beta",
        kind: "document",
        body: "private full workflow body"
      ),
      row(id: "city", content: "Brooklyn", slot: "home_city", curationWeight: 5),
      row(id: "older-city", content: "Boston", slot: "home_city", curationWeight: 4, status: "superseded"),
      row(id: "third-party", content: "Queens", subjectScope: "third_party", slot: "home_city"),
      row(id: "episodic", content: "Went to a concert", kind: "fact"),
    ])

    let rendered = projection.render(userName: "David")

    let expected = """
      Current profile for David:
      home_city: Brooklyn

      Available playbooks (call read_playbook for the body; do not infer it from the title):
      playbook-1: Release the macOS beta
      """ + "\n"
    XCTAssertEqual(rendered, expected)
    XCTAssertFalse(rendered?.contains("Boston") == true)
    XCTAssertFalse(rendered?.contains("Queens") == true)
    XCTAssertFalse(rendered?.contains("Went to a concert") == true)
    XCTAssertFalse(rendered?.contains("private full workflow body") == true)
  }

  func testLegacyAndUnknownRowsFailClosedWithoutPromptInjection() {
    let projection = KnowledgeLedgerPromptProjection(rows: [
      row(id: "legacy", content: "Legacy wholesale memory", schemaVersion: nil),
      row(id: "future", content: "Future row", schemaVersion: "knowledge_ledger.v2"),
    ])

    XCTAssertNil(projection.render(userName: "David"))
    XCTAssertTrue(projection.citationSources.isEmpty)
  }

  func testOneLedgerRowCannotHideLegacySnapshot() {
    let projection = KnowledgeLedgerPromptProjection(rows: [
      row(id: "ledger", content: "Brooklyn", slot: "home_city"),
      row(id: "legacy", content: "Historical released memory", schemaVersion: nil),
    ])

    XCTAssertFalse(projection.isCompleteLedgerSnapshot)
    XCTAssertNil(projection.render(userName: "David"))
    XCTAssertTrue(projection.citationSources.isEmpty)
  }

  func testSupersededAndUnslottedFactsCannotBecomeCitations() {
    let projection = KnowledgeLedgerPromptProjection(rows: [
      row(id: "active", content: "Brooklyn", slot: "home_city"),
      row(id: "superseded", content: "Boston", slot: "home_city", supersededBy: "active"),
      row(id: "unslotted", content: "Private observation", kind: "fact"),
    ])

    XCTAssertEqual(projection.citationSources.map(\.sourceID), ["active"])
  }

  private func row(
    id: String,
    content: String,
    schemaVersion: String? = KnowledgeLedgerPromptProjection.schemaVersion,
    kind: String = "fact",
    subjectScope: String = "primary_user",
    slot: String? = nil,
    body: String? = nil,
    intentBacked: Bool = true,
    curationWeight: Int = 0,
    status: String? = "active",
    supersededBy: String? = nil
  ) -> KnowledgeLedgerPromptProjection.Row {
    var metadata: [String: String] = [
      "kind": kind,
      "subject_scope": subjectScope,
      "intent_backed": intentBacked ? "true" : "false",
      "curation_weight": String(curationWeight),
    ]
    if let schemaVersion { metadata["ledger_schema_version"] = schemaVersion }
    if let slot { metadata["slot"] = slot }
    if let body { metadata["body"] = body }
    if let status { metadata["status"] = status }
    if let supersededBy { metadata["superseded_by"] = supersededBy }
    return KnowledgeLedgerPromptProjection.Row(id: id, content: content, metadata: metadata)
  }
}
