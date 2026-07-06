import XCTest

@testable import Omi_Computer

@MainActor
final class AuthTokenStorageTests: XCTestCase {
  override func setUp() {
    super.setUp()
    clearAuthDefaults()
  }

  override func tearDown() {
    clearAuthDefaults()
    super.tearDown()
  }

  func testProductionTokenSaveFallsBackToUserDefaultsWhenKeychainWriteFails() async throws {
    let auth = AuthService()
    auth.tokenStorageHooks = AuthService.TokenStorageHooks(
      usesKeychainTokenStorage: { true },
      allowsUserDefaultsFallback: { true },
      readKeychainString: { _, _ in nil },
      writeKeychainString: { _, _, _ in false },
      deleteKeychainString: { _, _ in },
      recordsFallbackTelemetry: false
    )

    XCTAssertNoThrow(
      try auth.saveTokens(idToken: "id-token-stable", refreshToken: "refresh-token-stable", expiresIn: 3600, userId: "user-stable")
    )
    XCTAssertEqual(UserDefaults.standard.string(forKey: .authIdToken), "id-token-stable")
    XCTAssertEqual(UserDefaults.standard.string(forKey: .authRefreshToken), "refresh-token-stable")
    XCTAssertEqual(UserDefaults.standard.string(forKey: .authTokenUserId), "user-stable")

    let idToken = try await auth.getIdToken()
    XCTAssertEqual(idToken, "id-token-stable")
    XCTAssertEqual(UserDefaults.standard.string(forKey: .authUserId), "user-stable")
  }

  func testKeychainWriteFailureThrowsOnlyWhenFallbackDisabled() {
    let auth = AuthService()
    auth.tokenStorageHooks = AuthService.TokenStorageHooks(
      usesKeychainTokenStorage: { true },
      allowsUserDefaultsFallback: { false },
      readKeychainString: { _, _ in nil },
      writeKeychainString: { _, _, _ in false },
      deleteKeychainString: { _, _ in },
      recordsFallbackTelemetry: false
    )

    XCTAssertThrowsError(
      try auth.saveTokens(idToken: "id-token-stable", refreshToken: "refresh-token-stable", expiresIn: 3600, userId: "user-stable")
    ) { error in
      guard case AuthError.keychainTokenStorageUnavailable = error else {
        return XCTFail("expected keychainTokenStorageUnavailable, got \(error)")
      }
    }
    XCTAssertNil(UserDefaults.standard.string(forKey: .authIdToken))
    XCTAssertNil(UserDefaults.standard.string(forKey: .authRefreshToken))
    XCTAssertNil(UserDefaults.standard.string(forKey: .authTokenUserId))
  }

  func testUserDefaultsMigrationKeepsAuthContinuityWhenKeychainWriteFails() async throws {
    let auth = AuthService()
    auth.tokenStorageHooks = AuthService.TokenStorageHooks(
      usesKeychainTokenStorage: { true },
      allowsUserDefaultsFallback: { true },
      readKeychainString: { _, _ in nil },
      writeKeychainString: { _, _, _ in false },
      deleteKeychainString: { _, _ in },
      recordsFallbackTelemetry: false
    )

    UserDefaults.standard.set("existing-default-id-token", forKey: .authIdToken)
    UserDefaults.standard.set("existing-default-refresh-token", forKey: .authRefreshToken)
    UserDefaults.standard.set(Date().addingTimeInterval(3600).timeIntervalSince1970, forKey: .authTokenExpiry)
    UserDefaults.standard.set("existing-default-user", forKey: .authTokenUserId)

    let idToken = try await auth.getIdToken()

    XCTAssertEqual(idToken, "existing-default-id-token")
    XCTAssertEqual(UserDefaults.standard.string(forKey: .authIdToken), "existing-default-id-token")
    XCTAssertEqual(UserDefaults.standard.string(forKey: .authRefreshToken), "existing-default-refresh-token")
    XCTAssertEqual(UserDefaults.standard.string(forKey: .authTokenUserId), "existing-default-user")
    XCTAssertEqual(UserDefaults.standard.string(forKey: .authUserId), "existing-default-user")
  }

  func testKeychainSuccessClearsUserDefaultsFallbackTokensAndRetrievesFromKeychain() async throws {
    var keychainPayload: String?
    let auth = AuthService()
    auth.tokenStorageHooks = AuthService.TokenStorageHooks(
      usesKeychainTokenStorage: { true },
      allowsUserDefaultsFallback: { true },
      readKeychainString: { _, _ in keychainPayload },
      writeKeychainString: { value, _, _ in
        keychainPayload = value
        return true
      },
      deleteKeychainString: { _, _ in keychainPayload = nil },
      recordsFallbackTelemetry: false
    )

    UserDefaults.standard.set("old-default-id-token", forKey: .authIdToken)
    UserDefaults.standard.set("old-default-refresh-token", forKey: .authRefreshToken)
    UserDefaults.standard.set("old-default-user", forKey: .authTokenUserId)

    try auth.saveTokens(idToken: "id-token-keychain", refreshToken: "refresh-token-keychain", expiresIn: 3600, userId: "user-keychain")

    XCTAssertNotNil(keychainPayload)
    XCTAssertNil(UserDefaults.standard.string(forKey: .authIdToken))
    XCTAssertNil(UserDefaults.standard.string(forKey: .authRefreshToken))
    XCTAssertNil(UserDefaults.standard.string(forKey: .authTokenUserId))

    let idToken = try await auth.getIdToken()
    XCTAssertEqual(idToken, "id-token-keychain")
    XCTAssertEqual(UserDefaults.standard.string(forKey: .authUserId), "user-keychain")
  }

  private func clearAuthDefaults() {
    UserDefaults.standard.removeObject(forKey: .authIdToken)
    UserDefaults.standard.removeObject(forKey: .authRefreshToken)
    UserDefaults.standard.removeObject(forKey: .authTokenExpiry)
    UserDefaults.standard.removeObject(forKey: .authTokenUserId)
    UserDefaults.standard.removeObject(forKey: .authUserId)
  }
}
