import Foundation
import XCTest

@testable import Omi_Computer

@MainActor
final class KernelJournalOwnerBoundAuthTests: XCTestCase {
  override func tearDown() async throws {
    let auth = AuthService.shared
    await auth.invalidateSession(reason: .manual)
    auth.tokenStorageHooks = .live
    auth.tokenRefreshHooks = .live
    UserDefaults.standard.removeObject(forKey: .authUserId)
  }

  func testTokenOwnerExtractionAcceptsFirebaseUserIDAndSubject() throws {
    XCTAssertEqual(
      AuthService.tokenOwnerId(from: token(payload: ["user_id": "owner-a", "sub": "fallback"])),
      "owner-a"
    )
    XCTAssertEqual(
      AuthService.tokenOwnerId(from: token(payload: ["sub": "owner-b"])),
      "owner-b"
    )
  }

  func testTokenOwnerExtractionFailsClosedForMalformedOrUnownedTokens() throws {
    XCTAssertNil(AuthService.tokenOwnerId(from: "not-a-jwt"))
    XCTAssertNil(AuthService.tokenOwnerId(from: token(payload: ["aud": "omi"])))
    XCTAssertNil(AuthService.tokenOwnerId(from: token(payload: ["sub": "  "])))
  }

  private func token(payload: [String: Any]) -> String {
    let data = try! JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
    let encoded = data.base64EncodedString()
      .replacingOccurrences(of: "+", with: "-")
      .replacingOccurrences(of: "/", with: "_")
      .replacingOccurrences(of: "=", with: "")
    return "e30.\(encoded).signature"
  }
}
