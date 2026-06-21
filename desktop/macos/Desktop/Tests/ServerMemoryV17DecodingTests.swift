import Foundation
import XCTest
@testable import Omi_Computer

final class ServerMemoryV17DecodingTests: XCTestCase {
    private let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let value = try container.decode(String.self)
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

    func testConflictingIdAliasesFailClosed() {
        let json = """
        {
          "id": "mem-a",
          "memory_id": "mem-b",
          "content": "Conflicting ids",
          "category": "system",
          "tier": "long_term",
          "created_at": "2026-06-21T10:00:00Z",
          "updated_at": "2026-06-21T10:05:00Z"
        }
        """.data(using: .utf8)!

        XCTAssertThrowsError(try decoder.decode(ServerMemory.self, from: json))
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

}
