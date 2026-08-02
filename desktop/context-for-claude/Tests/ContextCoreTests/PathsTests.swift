import Foundation
import XCTest
@testable import ContextCore

final class PathsTests: XCTestCase {
    func testOmiDatabaseUsesTheProvisionedOwner() throws {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("context-path-tests-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: root) }
        try FileManager.default.createDirectory(
            at: root.appendingPathComponent("Omi/users/user-a", isDirectory: true),
            withIntermediateDirectories: true)
        try FileManager.default.createDirectory(
            at: root.appendingPathComponent("Omi/users/user-b", isDirectory: true),
            withIntermediateDirectories: true)
        let expected = root.appendingPathComponent("Omi/users/user-b/omi.db")
        try Data().write(to: expected)

        XCTAssertEqual(
            ContextPaths.omiDatabaseURL(for: "user-b", applicationSupportDirectory: root), expected)
        XCTAssertNil(ContextPaths.omiDatabaseURL(for: "user-a/../user-b", applicationSupportDirectory: root))
    }
}
