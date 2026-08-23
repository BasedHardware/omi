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

  func testProfileAndPlaybookOrderingUsesStableCanonicalTieBreakers() {
    let projection = KnowledgeLedgerPromptProjection(rows: [
      row(id: "fact-b", content: "B", slot: "home_city", curationWeight: 4, validAt: "2026-08-02"),
      row(id: "fact-a", content: "A", slot: "home_city", curationWeight: 4, validAt: "2026-08-02"),
      row(id: "fact-high", content: "High", slot: "work_city", curationWeight: 5, validAt: "2026-08-03"),
      row(id: "playbook-z", content: "Zeta workflow", kind: "document", curationWeight: 3),
      row(id: "playbook-a", content: "Alpha workflow", kind: "document", curationWeight: 3),
    ])

    let rendered = projection.render(userName: "David", marker: { "[\($0)]" })
    XCTAssertEqual(
      rendered,
      """
      Current profile for David:
      work_city: High [fact-high]
      home_city: A [fact-a]
      home_city: B [fact-b]

      Available playbooks (call read_playbook for the body; do not infer it from the title):
      playbook-a: Alpha workflow [playbook-a]
      playbook-z: Zeta workflow [playbook-z]
      """ + "\n")
    XCTAssertEqual(
      projection.citationSources.map(\.sourceID),
      ["fact-high", "fact-a", "fact-b", "playbook-a", "playbook-z"])
  }

  func testProfileAndPlaybookBudgetsAreIndependentAndBodiesStayOutOfPrompt() throws {
    let longFact = String(repeating: "f", count: 1_000)
    let longPlaybook = String(repeating: "p", count: 500)
    let projection = KnowledgeLedgerPromptProjection(rows: [
      row(id: "fact-one", content: longFact, slot: "one"),
      row(id: "fact-two", content: longFact, slot: "two"),
      row(id: "playbook-one", content: longPlaybook, kind: "document", body: "secret body"),
      row(id: "playbook-two", content: longPlaybook, kind: "document", body: "another secret body"),
    ])

    let rendered = try XCTUnwrap(projection.render(userName: "David"))
    let profile = try XCTUnwrap(rendered.components(separatedBy: "\n\n").first)
    let playbooks = try XCTUnwrap(rendered.components(separatedBy: "\n\n").last)
    XCTAssertLessThanOrEqual(profile.count, 2_400 + "Current profile for David:\n".count)
    XCTAssertLessThanOrEqual(
      playbooks.count,
      800 + "Available playbooks (call read_playbook for the body; do not infer it from the title):\n".count)
    XCTAssertFalse(rendered.contains("secret body"))
    XCTAssertFalse(rendered.contains("another secret body"))
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
    validAt: String? = nil,
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
    if let validAt { metadata["valid_at"] = validAt }
    if let status { metadata["status"] = status }
    if let supersededBy { metadata["superseded_by"] = supersededBy }
    return KnowledgeLedgerPromptProjection.Row(id: id, content: content, metadata: metadata)
  }
}
