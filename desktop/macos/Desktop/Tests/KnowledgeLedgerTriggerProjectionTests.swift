import XCTest

@testable import Omi_Computer

final class KnowledgeLedgerTriggerProjectionTests: XCTestCase {
  func testServerMemoryProjectionPreservesSelectorsAndModelMetadata() throws {
    var metadata = canonicalMetadata()
    metadata.removeValue(forKey: "status")  // MemoryDB may omit this field.
    metadata["model_id"] = "trigger-model"
    metadata["model_version"] = "2026-08"
    metadata["threshold"] = "0.91"
    metadata["wakeup_budget_per_day"] = "2"
    let result = KnowledgeLedgerTriggerCompiler.project(memories: [serverMemory(id: "selectors", metadata: metadata)])

    XCTAssertEqual(result.quarantined, [])
    let entry = try XCTUnwrap(result.entries.first)
    XCTAssertEqual(entry.id, "selectors")
    XCTAssertEqual(entry.metadata.modelID, "trigger-model")
    XCTAssertEqual(entry.metadata.modelVersion, "2026-08")
    XCTAssertEqual(entry.metadata.threshold, 0.91)
    XCTAssertEqual(entry.metadata.wakeupBudgetPerDay, 2)
    XCTAssertEqual(entry.entities, ["project": ["omi", "omi app"]])
    XCTAssertEqual(entry.keywords, ["release"])
    XCTAssertEqual(entry.apps, ["slack"])
    XCTAssertEqual(entry.windows, ["#release"])
    XCTAssertEqual(entry.time?.weekdays, [0])
    XCTAssertEqual(entry.time?.start, 9 * 3_600)
    XCTAssertEqual(entry.time?.end, 10 * 3_600)
    XCTAssertEqual(entry.calendar?.eventKeywords, ["planning"])
    XCTAssertEqual(entry.calendar?.eventTypes, ["meeting"])
    XCTAssertEqual(entry.embedding?.prototypeID, "release-intent")
    XCTAssertEqual(entry.embedding?.prototypeRevision, "prototype-v1")
    XCTAssertEqual(entry.embedding?.modelID, "local-jit-embedding")
    XCTAssertEqual(entry.embedding?.modelVersion, "1")
    XCTAssertEqual(entry.embedding?.language, "en")
    XCTAssertEqual(entry.embedding?.minSimilarity, 0.82)
  }

  func testRecordProjectionOrdersNewestFirstAndDeduplicatesIndependentOfInputOrder() {
    let records = [
      record(id: "old", updatedAt: 100, keywords: ["old"]),
      record(id: "duplicate", updatedAt: 100, keywords: ["stale"]),
      record(id: "new-z", updatedAt: 300, keywords: ["z"]),
      record(id: "duplicate", updatedAt: 250, keywords: ["new"]),
      record(id: "new-a", updatedAt: 300, keywords: ["a"]),
    ]

    let first = KnowledgeLedgerTriggerCompiler.project(records: records)
    let second = KnowledgeLedgerTriggerCompiler.project(records: records.reversed())

    XCTAssertEqual(first, second)
    XCTAssertEqual(first.entries.map(\.id), ["new-a", "new-z", "duplicate", "old"])
    XCTAssertEqual(first.entries[2].keywords, ["new"])
    XCTAssertTrue(first.quarantined.isEmpty)
  }

  func testDeletedRejectedClosedFutureMalformedRowsAreQuarantinedWithTypedFailures() {
    var futureMetadata = canonicalMetadata()
    futureMetadata[MemoryLedgerMetadata.schemaVersionKey] = "knowledge_ledger.v2"

    var malformed = record(id: "malformed", updatedAt: 200, keywords: ["bad"])
    malformed.ledgerMetadataJson =
      "{\"ledger_schema_version\":\"knowledge_ledger.v1\",\"kind\":\"trigger\",\"subject_scope\":\"primary_user\",\"intent_backed\":\"true\",\"trigger_condition_json\":\"{not-json\"}"

    var deleted = record(id: "deleted", updatedAt: 300, keywords: ["deleted"])
    deleted.deleted = true
    var rejected = record(id: "rejected", updatedAt: 299, keywords: ["rejected"])
    rejected.userReview = false

    let rows = [
      record(id: "active", updatedAt: 500, keywords: ["active"]),
      deleted,
      rejected,
      record(id: "closed", updatedAt: 298, keywords: ["closed"], status: "superseded"),
      MemoryRecord.from(serverMemory(id: "future", updatedAt: 297, metadata: futureMetadata)),
      malformed,
    ]

    let result = KnowledgeLedgerTriggerCompiler.project(records: rows)
    XCTAssertEqual(result.entries.map(\.id), ["active"])
    XCTAssertEqual(
      result.quarantined,
      [
        .init(id: "deleted", failure: .deletedRow),
        .init(id: "rejected", failure: .rejectedRow),
        .init(id: "closed", failure: .closedRow),
        .init(id: "future", failure: .unsupportedSchema("knowledge_ledger.v2")),
        .init(id: "malformed", failure: .malformed("trigger condition is missing, malformed, or oversized")),
      ])
  }

  func testMissingBackendIDIsQuarantinedWithoutCreatingLocalWatchlistIdentity() {
    let memory = serverMemory(id: "local-only", metadata: canonicalMetadata())
    var local = MemoryRecord.from(memory)
    local.backendId = nil

    let result = KnowledgeLedgerTriggerCompiler.project(records: [local])
    XCTAssertTrue(result.entries.isEmpty)
    XCTAssertEqual(result.quarantined, [.init(id: "", failure: .missingBackendID)])
  }

  private func canonicalMetadata() -> [String: String] {
    [
      MemoryLedgerMetadata.schemaVersionKey: KnowledgeLedgerTriggerRow.schemaVersion,
      "kind": "trigger",
      "subject_scope": "primary_user",
      "intent_backed": "true",
      "trigger_condition_json":
        "{\"apps\":[\"Slack\"],\"calendar\":{\"event_keywords\":[\"planning\"],\"event_types\":[\"meeting\"]},\"embedding\":{\"language\":\"en\",\"min_similarity\":0.82,\"model_id\":\"local-jit-embedding\",\"model_version\":\"1\",\"prototype_id\":\"release-intent\",\"prototype_revision\":\"prototype-v1\"},\"entity_aliases\":{\"project\":[\"Omi\",\"Omi App\"]},\"keywords\":[\"release\"],\"match_mode\":\"all\",\"schema_version\":\"jit_trigger.v1\",\"time\":{\"end\":\"10:00\",\"start\":\"09:00\",\"timezone\":\"UTC\",\"weekdays\":[0]},\"windows\":[\"#release\"]}",
    ]
  }

  private func record(
    id: String,
    updatedAt: TimeInterval,
    keywords: [String],
    status: String? = "active"
  ) -> MemoryRecord {
    var metadata = canonicalMetadata()
    let condition = "{\"keywords\":[\"\(keywords[0])\"],\"schema_version\":\"jit_trigger.v1\"}"
    metadata[MemoryLedgerMetadata.triggerConditionJSONKey] = condition
    if let status { metadata["status"] = status }
    return MemoryRecord.from(
      serverMemory(
        id: id,
        updatedAt: updatedAt,
        metadata: metadata
      ))
  }

  private func serverMemory(
    id: String,
    updatedAt: TimeInterval = 2,
    metadata: [String: String],
    userReview: Bool? = nil
  ) -> ServerMemory {
    ServerMemory(
      id: id,
      content: "Trigger \(id)",
      category: .workflow,
      tier: .longTerm,
      tierIsExplicit: true,
      createdAt: Date(timeIntervalSince1970: 1),
      updatedAt: Date(timeIntervalSince1970: updatedAt),
      conversationId: nil,
      reviewed: false,
      userReview: userReview,
      visibility: "private",
      manuallyAdded: false,
      scoring: nil,
      source: "desktop",
      confidence: nil,
      sourceApp: nil,
      contextSummary: nil,
      isRead: false,
      isDismissed: false,
      tags: [],
      reasoning: nil,
      currentActivity: nil,
      inputDeviceName: nil,
      windowTitle: nil,
      headline: nil,
      ledgerMetadata: metadata
    )
  }
}
