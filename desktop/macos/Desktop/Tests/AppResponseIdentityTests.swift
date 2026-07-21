import XCTest

@testable import Omi_Computer

/// Regression coverage for `AppResponse` Identifiable stability.
///
/// `id` used to be `appId ?? UUID().uuidString` — a computed property that
/// minted a fresh UUID on every read whenever `app_id` was null (legacy
/// summary results still carry it as null). SwiftUI reads `.id` on every diff,
/// so a nil-appId row got a brand-new identity each pass: rows were torn down
/// and recreated, per-row @State was lost, and transitions flashed. `id` is now
/// a stored property assigned once at decode time.
final class AppResponseIdentityTests: XCTestCase {
  func testNilAppIdKeepsStableIdentityAcrossReads() throws {
    let json = Data(#"{"app_id": null, "content": "summary"}"#.utf8)
    let response = try JSONDecoder().decode(AppResponse.self, from: json)
    XCTAssertNil(response.appId)
    XCTAssertEqual(response.id, response.id, "id must be stable across reads, not re-minted")
  }

  func testTwoNilAppIdRowsHaveDistinctIdentities() throws {
    let json = Data(#"[{"app_id": null, "content": "a"}, {"app_id": null, "content": "b"}]"#.utf8)
    let rows = try JSONDecoder().decode([AppResponse].self, from: json)
    XCTAssertEqual(rows.count, 2)
    XCTAssertNotEqual(rows[0].id, rows[1].id, "distinct rows must not collide on identity")
  }

  func testNonNilAppIdIsUsedAsIdentity() throws {
    let json = Data(#"{"app_id": "assistant", "content": "hi"}"#.utf8)
    let response = try JSONDecoder().decode(AppResponse.self, from: json)
    XCTAssertEqual(response.id, "assistant")
  }
}
