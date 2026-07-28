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

  func testDecodesV17TierAndMemoryIdAlias() throws {
    let json = """
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
      """.data(using: .utf8)!

    let memory = try decoder.decode(ServerMemory.self, from: json)

    XCTAssertEqual(memory.id, "mem-short-1")
    XCTAssertEqual(memory.tier, .shortTerm)
    XCTAssertTrue(memory.tierIsExplicit)
    XCTAssertEqual(memory.category, .system)
    XCTAssertNotNil(memory.capturedAt)
    XCTAssertNotNil(memory.expiresAt)
  }

  func testDecodesMemoryTierAlias() throws {
    let json = """
      {
        "id": "mem-archive-1",
        "content": "Archived synthetic memory",
        "category": "manual",
        "memory_tier": "archive",
        "created_at": "2026-06-21T10:00:00Z",
        "updated_at": "2026-06-21T10:05:00Z"
      }
      """.data(using: .utf8)!

    let memory = try decoder.decode(ServerMemory.self, from: json)

    XCTAssertEqual(memory.id, "mem-archive-1")
    XCTAssertEqual(memory.tier, .archive)
    XCTAssertTrue(memory.tierIsExplicit)
    XCTAssertFalse(memory.tier.isDefaultAccessible)
  }

  func testMissingTierDefaultsLegacyMemoryToLongTerm() throws {
    let json = """
      {
        "id": "legacy-1",
        "content": "Legacy memory",
        "category": "interesting",
        "created_at": "2026-06-21T10:00:00Z",
        "updated_at": "2026-06-21T10:05:00Z"
      }
      """.data(using: .utf8)!

    let memory = try decoder.decode(ServerMemory.self, from: json)

    XCTAssertEqual(memory.tier, .longTerm)
    XCTAssertTrue(memory.tier.isDefaultAccessible)
    // Legacy records carry no tier from the backend, so the badge is suppressed.
    XCTAssertFalse(memory.tierIsExplicit)
  }

  func testUnknownPresentTierFailsClosed() {
    let json = """
      {
        "id": "mem-future",
        "content": "Future tier",
        "category": "system",
        "tier": "future_archive",
        "created_at": "2026-06-21T10:00:00Z",
        "updated_at": "2026-06-21T10:05:00Z"
      }
      """.data(using: .utf8)!

    XCTAssertThrowsError(try decoder.decode(ServerMemory.self, from: json))
  }

  func testConflictingTierAliasesFailClosed() {
    let json = """
      {
        "id": "mem-conflict",
        "content": "Conflicting tier",
        "category": "system",
        "tier": "long_term",
        "memory_tier": "archive",
        "created_at": "2026-06-21T10:00:00Z",
        "updated_at": "2026-06-21T10:05:00Z"
      }
      """.data(using: .utf8)!

    XCTAssertThrowsError(try decoder.decode(ServerMemory.self, from: json))
  }

  func testMatchingTierAliasesDecode() throws {
    let json = """
      {
        "id": "mem-match",
        "content": "Matching tier",
        "category": "system",
        "tier": "archive",
        "memory_tier": "archive",
        "created_at": "2026-06-21T10:00:00Z",
        "updated_at": "2026-06-21T10:05:00Z"
      }
      """.data(using: .utf8)!

    let memory = try decoder.decode(ServerMemory.self, from: json)
    XCTAssertEqual(memory.tier, .archive)
  }

  func testConflictingIdAliasesPreferIdNotFail() throws {
    // Legacy persisted rows carry memory_id = conversation_id (the pre-V17
    // backend behaviour), which differs from id. Such rows must NOT fail
    // decoding — a single throw would abort the entire memories array and
    // break the desktop memories load. Prefer id when present.
    let json = """
      {
        "id": "mem-a",
        "memory_id": "conv-legacy-1",
        "content": "Legacy memory_id alias",
        "category": "system",
        "tier": "long_term",
        "created_at": "2026-06-21T10:00:00Z",
        "updated_at": "2026-06-21T10:05:00Z"
      }
      """.data(using: .utf8)!

    let memory = try decoder.decode(ServerMemory.self, from: json)
    XCTAssertEqual(memory.id, "mem-a")
  }

  func testMatchingIdAliasesDecode() throws {
    let json = """
      {
        "id": "mem-a",
        "memory_id": "mem-a",
        "content": "Matching ids",
        "category": "system",
        "tier": "long_term",
        "created_at": "2026-06-21T10:00:00Z",
        "updated_at": "2026-06-21T10:05:00Z"
      }
      """.data(using: .utf8)!

    let memory = try decoder.decode(ServerMemory.self, from: json)
    XCTAssertEqual(memory.id, "mem-a")
  }

  func testDecodesLayerFieldWithoutTierAliases() throws {
    let json = """
      {
        "id": "mem-layer-1",
        "content": "Canonical short-term via layer field",
        "category": "interesting",
        "layer": "short_term",
        "created_at": "2026-06-21T10:00:00Z",
        "updated_at": "2026-06-21T10:05:00Z",
        "expires_at": "2026-06-28T10:00:00Z"
      }
      """.data(using: .utf8)!

    let memory = try decoder.decode(ServerMemory.self, from: json)

    XCTAssertEqual(memory.id, "mem-layer-1")
    XCTAssertEqual(memory.tier, .shortTerm)
    XCTAssertTrue(memory.tierIsExplicit)
  }

  func testLayerPreferredOverTierAlias() throws {
    let json = """
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
      """.data(using: .utf8)!

    let memory = try decoder.decode(ServerMemory.self, from: json)

    XCTAssertEqual(memory.tier, .shortTerm)
    XCTAssertTrue(memory.tierIsExplicit)
  }

  func testConflictingLayerAndTierAliasesFailClosed() {
    let json = """
      {
        "id": "mem-layer-conflict",
        "content": "Conflicting layer",
        "category": "system",
        "layer": "short_term",
        "memory_tier": "long_term",
        "created_at": "2026-06-21T10:00:00Z",
        "updated_at": "2026-06-21T10:05:00Z"
      }
      """.data(using: .utf8)!

    XCTAssertThrowsError(try decoder.decode(ServerMemory.self, from: json))
  }

  func testLayerOnlyLongTermSetsExplicitBadge() throws {
    let json = """
      {
        "id": "mem-layer-lt",
        "content": "Canonical long-term via layer field",
        "category": "manual",
        "layer": "long_term",
        "created_at": "2026-06-21T10:00:00Z",
        "updated_at": "2026-06-21T10:05:00Z"
      }
      """.data(using: .utf8)!

    let memory = try decoder.decode(ServerMemory.self, from: json)

    XCTAssertEqual(memory.tier, .longTerm)
    XCTAssertTrue(memory.tierIsExplicit)
  }

}
