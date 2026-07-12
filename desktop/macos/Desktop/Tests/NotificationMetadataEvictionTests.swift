import XCTest

@testable import Omi_Computer

/// Regression coverage for the notification-metadata FIFO cap.
///
/// `notificationMetadata` is only removed on user interaction (`didReceive`); a
/// functional banner the user never touches leaks its entry for the life of the
/// process. `evictOldestMetadata` bounds the growth by dropping the oldest ids once
/// the tracked order exceeds the cap. These tests pin that policy.
final class NotificationMetadataEvictionTests: XCTestCase {
    func testEvictsOldestBeyondCap() {
        var order: [String] = []
        var store: [String: Int] = [:]
        for i in 0..<250 {
            let id = "n\(i)"
            order.append(id)
            store[id] = i
        }
        NotificationService.evictOldestMetadata(order: &order, store: &store, max: 200)

        XCTAssertEqual(order.count, 200)
        XCTAssertEqual(store.count, 200)
        // Oldest 50 (n0...n49) evicted; newest retained.
        XCTAssertNil(store["n0"])
        XCTAssertNil(store["n49"])
        XCTAssertEqual(store["n50"], 50)
        XCTAssertEqual(store["n249"], 249)
        XCTAssertEqual(order.first, "n50")
        XCTAssertEqual(order.last, "n249")
    }

    func testNoEvictionUnderCap() {
        var order = ["a", "b", "c"]
        var store = ["a": 1, "b": 2, "c": 3]
        NotificationService.evictOldestMetadata(order: &order, store: &store, max: 200)
        XCTAssertEqual(order.count, 3)
        XCTAssertEqual(store.count, 3)
    }

    func testEvictsExactlyToCap() {
        var order: [String] = []
        var store: [String: Int] = [:]
        for i in 0..<10 {
            order.append("n\(i)")
            store["n\(i)"] = i
        }
        NotificationService.evictOldestMetadata(order: &order, store: &store, max: 3)
        XCTAssertEqual(order, ["n7", "n8", "n9"])
        XCTAssertEqual(Set(store.keys), Set(["n7", "n8", "n9"]))
    }
}
