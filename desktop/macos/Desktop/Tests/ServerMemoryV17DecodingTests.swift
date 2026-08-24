import Foundation
import XCTest

@testable import Omi_Computer

final class ServerMemoryV17DecodingTests: XCTestCase {
  private let decoder: JSONDecoder = {
    let decoder = JSONDecoder()
    decoder.dateDecodingStrategy = .custom { decoder in
      let container = try decoder.singleValueContainer()
      let value = try container.decode(String.self)
      let formatter = ISO8601DateFormatter()
      formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
      if let date = formatter.date(from: value) {
        return date
      }
      let fallback = ISO8601DateFormatter()
      if let date = fallback.date(from: value) {
        return date
      }
      throw DecodingError.dataCorruptedError(in: container, debugDescription: "Invalid ISO8601 date: \(value)")
    }
    return decoder
  }()

  func testSharedJITRuntimeMatrixKeepsMixedVersionTextAndOnlyV1Authority() throws {
    let testFile = URL(fileURLWithPath: #filePath)
    let repositoryRoot =
      testFile
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .deletingLastPathComponent()
    let fixtureURL =
      repositoryRoot
      .appendingPathComponent("contracts/parity/jit_runtime_contract_matrix.json")
    let fixture = try JSONSerialization.jsonObject(with: Data(contentsOf: fixtureURL)) as? [String: Any]
    let rows = try XCTUnwrap(fixture?["memory_rows"] as? [[String: Any]])
    let chatRecords = try XCTUnwrap(fixture?["chat_records"] as? [String: [String: Any]])
    let expected = try XCTUnwrap(fixture?["expected"] as? [String: Any])
    let data = try JSONSerialization.data(withJSONObject: rows)
    let memories = try decoder.decode([ServerMemory].self, from: data)

    XCTAssertEqual(memories.map(\.id), expected["memory_ids"] as? [String])
    XCTAssertEqual(
      Dictionary(uniqueKeysWithValues: memories.map { ($0.id, $0.content) }),
      expected["readable_text_by_id"] as? [String: String]
    )
    XCTAssertEqual(
      memories.filter { MemoryLedgerMetadata.isSupportedVersion($0.ledgerMetadata) }.map(\.id),
      expected["authoritative_ledger_ids"] as? [String]
    )

    let chatMessages = try chatRecords.values.map { record in
      try decoder.decode(ChatMessageDB.self, from: JSONSerialization.data(withJSONObject: record))
    }
    XCTAssertEqual(
      Dictionary(uniqueKeysWithValues: chatMessages.map { ($0.id, $0.text) }),
      expected["readable_chat_text_by_id"] as? [String: String]
    )
    let futureMessage = try XCTUnwrap(chatMessages.first { $0.id == "future-message" })
    XCTAssertNil(futureMessage.metadata)
    XCTAssertNil(futureMessage.contentBlocksJSON)
  }

  func testDecodesV17TierAndMemoryIdAlias() throws {
    let json = Data(
      """
      {
        "memory_id": "mem-short-1",
        "content": "Short-term synthetic memory",
        "category": "system",
        "tier": "short_term",
        "created_at": "2026-06-21T10:00:00Z",
        "updated_at": "2026-06-21T10:05:00Z",
        "captured_at": "2026-06-21T09:59:00Z",
        "expires_at": "2026-06-28T10:00:00Z"
      }
      """.utf8)

    let memory = try decoder.decode(ServerMemory.self, from: json)

    XCTAssertEqual(memory.id, "mem-short-1")
    XCTAssertEqual(memory.tier, .shortTerm)
    XCTAssertTrue(memory.tierIsExplicit)
    XCTAssertEqual(memory.category, .system)
    XCTAssertNotNil(memory.capturedAt)
    XCTAssertNotNil(memory.expiresAt)
  }

  func testDecodesMemoryTierAlias() throws {
    let json = Data(
      """
      {
        "id": "mem-archive-1",
        "content": "Archived synthetic memory",
        "category": "manual",
        "memory_tier": "archive",
        "created_at": "2026-06-21T10:00:00Z",
        "updated_at": "2026-06-21T10:05:00Z"
      }
      """.utf8)

    let memory = try decoder.decode(ServerMemory.self, from: json)

    XCTAssertEqual(memory.id, "mem-archive-1")
    XCTAssertEqual(memory.tier, .archive)
    XCTAssertTrue(memory.tierIsExplicit)
    XCTAssertFalse(memory.tier.isDefaultAccessible)
  }

  func testMissingTierDefaultsLegacyMemoryToLongTerm() throws {
    let json = Data(
      """
      {
        "id": "legacy-1",
        "content": "Legacy memory",
        "category": "interesting",
        "created_at": "2026-06-21T10:00:00Z",
        "updated_at": "2026-06-21T10:05:00Z"
      }
      """.utf8)

    let memory = try decoder.decode(ServerMemory.self, from: json)

    XCTAssertEqual(memory.tier, .longTerm)
    XCTAssertTrue(memory.tier.isDefaultAccessible)
    // Legacy records carry no tier from the backend, so the badge is suppressed.
    XCTAssertFalse(memory.tierIsExplicit)
  }

  func testUnknownPresentTierFailsClosed() {
    let json = Data(
      """
      {
        "id": "mem-future",
        "content": "Future tier",
        "category": "system",
        "tier": "future_archive",
        "created_at": "2026-06-21T10:00:00Z",
        "updated_at": "2026-06-21T10:05:00Z"
      }
      """.utf8)

    XCTAssertThrowsError(try decoder.decode(ServerMemory.self, from: json))
  }

  func testConflictingTierAliasesFailClosed() {
    let json = Data(
      """
      {
        "id": "mem-conflict",
        "content": "Conflicting tier",
        "category": "system",
        "tier": "long_term",
        "memory_tier": "archive",
        "created_at": "2026-06-21T10:00:00Z",
        "updated_at": "2026-06-21T10:05:00Z"
      }
      """.utf8)

    XCTAssertThrowsError(try decoder.decode(ServerMemory.self, from: json))
  }

  func testMatchingTierAliasesDecode() throws {
    let json = Data(
      """
      {
        "id": "mem-match",
        "content": "Matching tier",
        "category": "system",
        "tier": "archive",
        "memory_tier": "archive",
        "created_at": "2026-06-21T10:00:00Z",
        "updated_at": "2026-06-21T10:05:00Z"
      }
      """.utf8)

    let memory = try decoder.decode(ServerMemory.self, from: json)
    XCTAssertEqual(memory.tier, .archive)
  }

  func testConflictingIdAliasesPreferIdNotFail() throws {
    // Legacy persisted rows carry memory_id = conversation_id (the pre-V17
    // backend behaviour), which differs from id. Such rows must NOT fail
    // decoding — a single throw would abort the entire memories array and
    // break the desktop memories load. Prefer id when present.
    let json = Data(
      """
      {
        "id": "mem-a",
        "memory_id": "conv-legacy-1",
        "content": "Legacy memory_id alias",
        "category": "system",
        "tier": "long_term",
        "created_at": "2026-06-21T10:00:00Z",
        "updated_at": "2026-06-21T10:05:00Z"
      }
      """.utf8)

    let memory = try decoder.decode(ServerMemory.self, from: json)
    XCTAssertEqual(memory.id, "mem-a")
  }

  func testMatchingIdAliasesDecode() throws {
    let json = Data(
      """
      {
        "id": "mem-a",
        "memory_id": "mem-a",
        "content": "Matching ids",
        "category": "system",
        "tier": "long_term",
        "created_at": "2026-06-21T10:00:00Z",
        "updated_at": "2026-06-21T10:05:00Z"
      }
      """.utf8)

    let memory = try decoder.decode(ServerMemory.self, from: json)
    XCTAssertEqual(memory.id, "mem-a")
  }

  func testDecodesLayerFieldWithoutTierAliases() throws {
    let json = Data(
      """
      {
        "id": "mem-layer-1",
        "content": "Canonical short-term via layer field",
        "category": "interesting",
        "layer": "short_term",
        "created_at": "2026-06-21T10:00:00Z",
        "updated_at": "2026-06-21T10:05:00Z",
        "expires_at": "2026-06-28T10:00:00Z"
      }
      """.utf8)

    let memory = try decoder.decode(ServerMemory.self, from: json)

    XCTAssertEqual(memory.id, "mem-layer-1")
    XCTAssertEqual(memory.tier, .shortTerm)
    XCTAssertTrue(memory.tierIsExplicit)
  }

  func testLayerPreferredOverTierAlias() throws {
    let json = Data(
      """
      {
        "id": "mem-layer-priority",
        "content": "Layer wins when all aliases agree on short_term",
        "category": "system",
        "layer": "short_term",
        "tier": "short_term",
        "memory_tier": "short_term",
        "created_at": "2026-06-21T10:00:00Z",
        "updated_at": "2026-06-21T10:05:00Z"
      }
      """.utf8)

    let memory = try decoder.decode(ServerMemory.self, from: json)

    XCTAssertEqual(memory.tier, .shortTerm)
    XCTAssertTrue(memory.tierIsExplicit)
  }

  func testConflictingLayerAndTierAliasesFailClosed() {
    let json = Data(
      """
      {
        "id": "mem-layer-conflict",
        "content": "Conflicting layer",
        "category": "system",
        "layer": "short_term",
        "memory_tier": "long_term",
        "created_at": "2026-06-21T10:00:00Z",
        "updated_at": "2026-06-21T10:05:00Z"
      }
      """.utf8)

    XCTAssertThrowsError(try decoder.decode(ServerMemory.self, from: json))
  }

  func testLayerOnlyLongTermSetsExplicitBadge() throws {
    let json = Data(
      """
      {
        "id": "mem-layer-lt",
        "content": "Canonical long-term via layer field",
        "category": "manual",
        "layer": "long_term",
        "created_at": "2026-06-21T10:00:00Z",
        "updated_at": "2026-06-21T10:05:00Z"
      }
      """.utf8)

    let memory = try decoder.decode(ServerMemory.self, from: json)

    XCTAssertEqual(memory.tier, .longTerm)
    XCTAssertTrue(memory.tierIsExplicit)
  }

  func testDecodesBoundedLedgerPayloadsIntoCanonicalMirrorMetadata() throws {
    let json = Data(
      """
      {
        "id": "mem-ledger-trigger",
        "uid": "mem-ledger-trigger",
        "content": "When release work is active",
        "category": "workflow",
        "created_at": "2026-06-21T10:00:00Z",
        "updated_at": "2026-06-21T10:05:00Z",
        "ledger_schema_version": "knowledge_ledger.v1",
        "kind": "trigger",
        "subject_scope": "primary_user",
        "subject_entity_id": "user",
        "intent_backed": true,
        "curation_weight": 4,
        "status": "active",
        "valid_at": "2026-06-21T10:00:00Z",
        "write_reason": "standing_trigger",
        "object_entity_ids": ["project-release"],
        "qualifiers": {"source": "user"},
        "arguments": {"owner": "user"},
        "trigger_condition": {
          "schema_version": "jit_trigger.v1",
          "keywords": ["release"],
          "entity_aliases": {"release_owner": ["David", "dave"]}
        }
      }
      """.utf8)

    let memory = try decoder.decode(ServerMemory.self, from: json)

    XCTAssertEqual(memory.ledgerMetadata["ledger_schema_version"], "knowledge_ledger.v1")
    XCTAssertEqual(memory.ledgerMetadata["kind"], "trigger")
    XCTAssertEqual(memory.ledgerMetadata["subject_scope"], "primary_user")
    XCTAssertEqual(memory.ledgerMetadata["subject_entity_id"], "user")
    XCTAssertEqual(memory.ledgerMetadata["write_reason"], "standing_trigger")
    XCTAssertEqual(memory.ledgerMetadata["object_entity_ids_json"], "[\"project-release\"]")
    XCTAssertEqual(memory.ledgerMetadata["qualifiers_json"], "{\"source\":\"user\"}")
    XCTAssertEqual(memory.ledgerMetadata["arguments_json"], "{\"owner\":\"user\"}")
    XCTAssertEqual(
      memory.ledgerMetadata["trigger_condition_json"],
      "{\"entity_aliases\":{\"release_owner\":[\"David\",\"dave\"]},\"keywords\":[\"release\"],\"schema_version\":\"jit_trigger.v1\"}"
    )
  }

  func testDecodesGeneratedV3EvidenceIntoBoundedMirror() throws {
    let json = Data(
      """
      {
        "id": "mem-evidence",
        "content": "Evidence remains readable",
        "category": "workflow",
        "created_at": "2026-06-21T10:00:00Z",
        "updated_at": "2026-06-21T10:05:00Z",
        "evidence": [
          {
            "evidence_id": "ev-1",
            "independence_group": "conversation-1",
            "source_type": "conversation",
            "source_signal": "transcript",
            "client_device_id": "desktop-1",
            "artifact_ref": {"conversation_id": "conv-1"},
            "capture_confidence": 0.91
          }
        ]
      }
      """.utf8)

    let memory = try decoder.decode(ServerMemory.self, from: json)

    XCTAssertEqual(memory.content, "Evidence remains readable")
    XCTAssertTrue(memory.evidenceIsExplicit)
    let evidence = try XCTUnwrap(memory.evidence.first)
    XCTAssertEqual(evidence.evidenceId, "ev-1")
    XCTAssertEqual(evidence.independenceGroup, "conversation-1")
    XCTAssertEqual(evidence.sourceType, "conversation")
    XCTAssertEqual(evidence.captureConfidence, 0.91)
    XCTAssertLessThanOrEqual(
      try XCTUnwrap(MemoryLedgerEvidence.canonicalJSONString(memory.evidence)).utf8.count,
      MemoryLedgerEvidence.maxEvidenceJSONBytes
    )
  }

  func testMalformedEvidenceFailsClosedWithoutRejectingMemoryText() throws {
    let json = Data(
      """
      {
        "id": "mem-malformed-evidence",
        "content": "Keep this memory text",
        "category": "workflow",
        "created_at": "2026-06-21T10:00:00Z",
        "updated_at": "2026-06-21T10:05:00Z",
        "evidence": [{"evidence_id": "ev-missing-group"}]
      }
      """.utf8)

    let memory = try decoder.decode(ServerMemory.self, from: json)

    XCTAssertEqual(memory.content, "Keep this memory text")
    XCTAssertTrue(memory.evidenceIsExplicit)
    XCTAssertTrue(memory.evidence.isEmpty)
  }

  func testFutureShapedEvidenceFailsClosedWithoutRejectingMemoryText() throws {
    let json = Data(
      """
      {
        "id": "mem-future-evidence",
        "content": "Future evidence must not block reads",
        "category": "workflow",
        "created_at": "2026-06-21T10:00:00Z",
        "updated_at": "2026-06-21T10:05:00Z",
        "evidence": {"schema_version": "evidence.v4"}
      }
      """.utf8)

    let memory = try decoder.decode(ServerMemory.self, from: json)

    XCTAssertEqual(memory.content, "Future evidence must not block reads")
    XCTAssertTrue(memory.evidenceIsExplicit)
    XCTAssertTrue(memory.evidence.isEmpty)
  }

  func testOversizedAndTooManyEvidenceEntriesFailClosed() throws {
    let oversizedArtifact = String(
      repeating: "x", count: MemoryLedgerEvidence.maxEvidenceJSONBytes)
    let oversizedObject: [String: Any] = [
      "id": "mem-oversized-evidence",
      "content": "Oversized evidence must not block reads",
      "category": "workflow",
      "created_at": "2026-06-21T10:00:00Z",
      "updated_at": "2026-06-21T10:05:00Z",
      "evidence": [
        [
          "evidence_id": "ev-oversized",
          "independence_group": "group",
          "artifact_ref": ["payload": oversizedArtifact],
        ]
      ],
    ]
    let oversizedData = try JSONSerialization.data(withJSONObject: oversizedObject)
    let oversized = try decoder.decode(ServerMemory.self, from: oversizedData)
    XCTAssertEqual(oversized.content, "Oversized evidence must not block reads")
    XCTAssertTrue(oversized.evidence.isEmpty)

    let tooManyEntries = (0...MemoryLedgerEvidence.maxEvidenceEntries).map { index in
      ["evidence_id": "ev-\(index)", "independence_group": "group"]
    }
    let tooManyObject: [String: Any] = [
      "id": "mem-too-many-evidence",
      "content": "Too many evidence rows must not block reads",
      "category": "workflow",
      "created_at": "2026-06-21T10:00:00Z",
      "updated_at": "2026-06-21T10:05:00Z",
      "evidence": tooManyEntries,
    ]
    let tooManyData = try JSONSerialization.data(withJSONObject: tooManyObject)
    let tooMany = try decoder.decode(ServerMemory.self, from: tooManyData)
    XCTAssertEqual(tooMany.content, "Too many evidence rows must not block reads")
    XCTAssertTrue(tooMany.evidence.isEmpty)
  }

}
