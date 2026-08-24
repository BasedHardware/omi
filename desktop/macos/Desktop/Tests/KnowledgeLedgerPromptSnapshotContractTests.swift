import XCTest

@testable import Omi_Computer

final class KnowledgeLedgerPromptSnapshotContractTests: XCTestCase {
  func testEnabledEmptySnapshotIsAuthoritativeAndDoesNotRestoreLegacyPrompt() throws {
    let snapshot = try decode(
      #"{"schema_version":"knowledge_ledger.v1","mode":"enabled","reason":"migration_complete_zero_legacy","source_head_commit_id":"head","rows":[]}"#
    )
    let projection = KnowledgeLedgerPromptProjection(
      memories: snapshot.memories,
      hasAuthoritativeSnapshot: snapshot.authority == .enabled)

    XCTAssertEqual(snapshot.authority, .enabled)
    XCTAssertTrue(projection.isCompleteLedgerSnapshot)
    XCTAssertEqual(
      projection.render(userName: "David"),
      "Current profile for David:\n(no current slotted facts)\n")
  }

  func testCompatibilityKilledAndUnknownSnapshotsCannotClaimCompleteness() throws {
    for mode in ["compatibility", "killed", "disabled", "unknown"] {
      let snapshot = try decode(
        #"{"schema_version":"knowledge_ledger.v1","mode":"\#(mode)","reason":"fail_closed","source_head_commit_id":null,"rows":[]}"#
      )
      let projection = KnowledgeLedgerPromptProjection(
        memories: snapshot.memories,
        hasAuthoritativeSnapshot: snapshot.authority == .enabled)
      XCTAssertFalse(projection.isCompleteLedgerSnapshot, mode)
      XCTAssertNil(projection.render(userName: "David"), mode)
    }
  }

  func testFutureOrMixedRowsStillFailClosedEvenInEnabledEnvelope() throws {
    let snapshot = try decode(
      #"{"schema_version":"knowledge_ledger.v1","mode":"enabled","reason":"test","source_head_commit_id":"head","rows":[{"id":"future","uid":"u1","content":"not authority","category":"system","created_at":"2026-08-24T00:00:00Z","updated_at":"2026-08-24T00:00:00Z","ledger_schema_version":"knowledge_ledger.v2"}]}"#
    )
    let projection = KnowledgeLedgerPromptProjection(
      memories: snapshot.memories,
      hasAuthoritativeSnapshot: true)
    XCTAssertFalse(projection.isCompleteLedgerSnapshot)
    XCTAssertNil(projection.render(userName: "David"))
  }

  private func decode(_ json: String) throws -> APIClient.KnowledgeLedgerPromptSnapshot {
    try JSONDecoder().decode(
      APIClient.KnowledgeLedgerPromptSnapshot.self,
      from: Data(json.utf8))
  }
}
