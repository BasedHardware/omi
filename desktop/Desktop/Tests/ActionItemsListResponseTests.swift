import XCTest
@testable import Omi_Computer

/// Tests for ActionItemsListResponse decoder.
/// Ensures the shared response type decodes both /v1/action-items ("action_items")
/// and /v1/staged-tasks ("items") payloads correctly.
final class ActionItemsListResponseTests: XCTestCase {

    // MARK: - Helpers

    /// Builds a JSONDecoder matching APIClient.makeDecoder() date handling.
    private func makeDecoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let dateString = try container.decode(String.self)
            let isoWithFractional = ISO8601DateFormatter()
            isoWithFractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            if let date = isoWithFractional.date(from: dateString) { return date }
            let iso = ISO8601DateFormatter()
            if let date = iso.date(from: dateString) { return date }
            throw DecodingError.dataCorruptedError(in: container, debugDescription: "Invalid date: \(dateString)")
        }
        return decoder
    }

    /// Minimal task JSON for embedding in response payloads.
    private let taskJSON = """
        {"id":"t-1","description":"Test task","completed":false,"created_at":"2026-04-07T14:00:00Z"}
    """

    // MARK: - action_items key (/v1/action-items shape)

    func testDecodeWithActionItemsKey() throws {
        let json = """
        {"action_items":[\(taskJSON)],"has_more":false}
        """
        let resp = try makeDecoder().decode(ActionItemsListResponse.self, from: json.data(using: .utf8)!)
        XCTAssertEqual(resp.items.count, 1)
        XCTAssertEqual(resp.items[0].id, "t-1")
        XCTAssertFalse(resp.hasMore)
    }

    // MARK: - items key (/v1/staged-tasks shape)

    func testDecodeWithItemsKey() throws {
        let json = """
        {"items":[\(taskJSON)],"has_more":true}
        """
        let resp = try makeDecoder().decode(ActionItemsListResponse.self, from: json.data(using: .utf8)!)
        XCTAssertEqual(resp.items.count, 1)
        XCTAssertEqual(resp.items[0].id, "t-1")
        XCTAssertTrue(resp.hasMore)
    }

    // MARK: - Both keys present (action_items wins)

    func testDecodeWithBothKeysPreferActionItems() throws {
        let otherTask = """
        {"id":"t-2","description":"Other","completed":true,"created_at":"2026-04-07T15:00:00Z"}
        """
        let json = """
        {"action_items":[\(taskJSON)],"items":[\(otherTask)],"has_more":false}
        """
        let resp = try makeDecoder().decode(ActionItemsListResponse.self, from: json.data(using: .utf8)!)
        XCTAssertEqual(resp.items.count, 1)
        XCTAssertEqual(resp.items[0].id, "t-1", "action_items key should take precedence over items")
    }

    // MARK: - Neither key present (decode failure)

    func testDecodeFailsWithNeitherKey() {
        let json = """
        {"has_more":false}
        """
        XCTAssertThrowsError(
            try makeDecoder().decode(ActionItemsListResponse.self, from: json.data(using: .utf8)!)
        )
    }

    // MARK: - Missing has_more (decode failure)

    func testDecodeFailsWithoutHasMore() {
        let json = """
        {"action_items":[\(taskJSON)]}
        """
        XCTAssertThrowsError(
            try makeDecoder().decode(ActionItemsListResponse.self, from: json.data(using: .utf8)!)
        )
    }

    // MARK: - Empty arrays

    func testDecodeEmptyActionItems() throws {
        let json = """
        {"action_items":[],"has_more":false}
        """
        let resp = try makeDecoder().decode(ActionItemsListResponse.self, from: json.data(using: .utf8)!)
        XCTAssertTrue(resp.items.isEmpty)
        XCTAssertFalse(resp.hasMore)
    }

    func testDecodeEmptyItems() throws {
        let json = """
        {"items":[],"has_more":false}
        """
        let resp = try makeDecoder().decode(ActionItemsListResponse.self, from: json.data(using: .utf8)!)
        XCTAssertTrue(resp.items.isEmpty)
    }
}
