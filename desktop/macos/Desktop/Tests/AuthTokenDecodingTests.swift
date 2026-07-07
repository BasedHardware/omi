import XCTest

@testable import Omi_Computer

final class AuthTokenDecodingTests: XCTestCase {
  func testDecodeJWTPayloadHandlesBase64URLWithoutPadding() throws {
    let jwt = makeJWT(payload: [
      "email": "person@example.com",
      "given_name": "Ada",
      "family_name": "Lovelace",
    ])

    let payload = try XCTUnwrap(AuthService.decodeJWTPayload(jwt))

    XCTAssertEqual(payload["email"] as? String, "person@example.com")
    XCTAssertEqual(payload["given_name"] as? String, "Ada")
    XCTAssertEqual(payload["family_name"] as? String, "Lovelace")
  }

  func testLocalUserIdPrefersUserIdThenFallsBackToSubject() {
    XCTAssertEqual(
      AuthService.localUserId(fromIDToken: makeJWT(payload: ["user_id": "firebase-user", "sub": "subject-user"])),
      "firebase-user"
    )
    XCTAssertEqual(
      AuthService.localUserId(fromIDToken: makeJWT(payload: ["sub": "subject-user"])),
      "subject-user"
    )
    XCTAssertNil(AuthService.localUserId(fromIDToken: "not-a-jwt"))
  }

  func testDecodeFirebaseTokenResultAcceptsStringAndIntegerExpiresIn() throws {
    let stringExpiryData = try firebaseTokenResponse(
      idToken: makeJWT(payload: ["sub": "fallback-user"]),
      expiresIn: "7200",
      localId: "explicit-user"
    )
    let stringExpiry = try AuthService.decodeFirebaseTokenResult(from: stringExpiryData)
    XCTAssertTrue(stringExpiry.idToken.hasSuffix("."))
    XCTAssertEqual(stringExpiry.refreshToken, "refresh-token")
    XCTAssertEqual(stringExpiry.expiresIn, 7200)
    XCTAssertEqual(stringExpiry.localId, "explicit-user")

    let integerExpiryData = try firebaseTokenResponse(
      idToken: makeJWT(payload: ["sub": "fallback-user"]),
      expiresIn: 1800,
      localId: "explicit-user"
    )
    let integerExpiry = try AuthService.decodeFirebaseTokenResult(from: integerExpiryData)
    XCTAssertEqual(integerExpiry.expiresIn, 1800)
  }

  func testDecodeFirebaseTokenResultFallsBackToJwtUserIdAndCanRequireIt() throws {
    let data = try firebaseTokenResponse(
      idToken: makeJWT(payload: ["user_id": "jwt-user"]),
      expiresIn: "3600",
      localId: nil
    )

    let token = try AuthService.decodeFirebaseTokenResult(from: data, requireLocalId: true)

    XCTAssertEqual(token.localId, "jwt-user")
  }

  func testDecodeFirebaseTokenResultRejectsMissingRequiredLocalId() throws {
    let data = try firebaseTokenResponse(
      idToken: makeJWT(payload: ["email": "person@example.com"]),
      expiresIn: "3600",
      localId: nil
    )

    XCTAssertThrowsError(try AuthService.decodeFirebaseTokenResult(from: data, requireLocalId: true)) { error in
      guard case AuthError.invalidResponse = error else {
        return XCTFail("expected invalidResponse, got \(error)")
      }
    }
  }

  private func firebaseTokenResponse(idToken: String, expiresIn: Any, localId: String?) throws -> Data {
    var json: [String: Any] = [
      "idToken": idToken,
      "refreshToken": "refresh-token",
      "expiresIn": expiresIn,
    ]
    if let localId {
      json["localId"] = localId
    }
    return try JSONSerialization.data(withJSONObject: json, options: [.sortedKeys])
  }

  private func makeJWT(payload: [String: Any]) -> String {
    let header = base64URL(["alg": "none", "typ": "JWT"])
    let payload = base64URL(payload)
    return "\(header).\(payload)."
  }

  private func base64URL(_ json: [String: Any]) -> String {
    let data = try! JSONSerialization.data(withJSONObject: json, options: [.sortedKeys])
    return data
      .base64EncodedString()
      .replacingOccurrences(of: "+", with: "-")
      .replacingOccurrences(of: "/", with: "_")
      .replacingOccurrences(of: "=", with: "")
  }
}
