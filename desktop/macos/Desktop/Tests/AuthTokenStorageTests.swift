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

  /// Regression: the token Keychain store must NOT opt into the data-protection keychain.
  /// That requires a `keychain-access-groups` entitlement this non-sandboxed Developer ID
  /// app doesn't have, so on the signed/notarized build every SecItem write failed with
  /// errSecMissingEntitlement and sign-in broke with "Could not securely store sign-in
  /// tokens". This only ever failed on signed prod/beta builds and is invisible to the
  /// behavioral tests — hence a source-level guard.
  func testKeychainStoreDoesNotUseDataProtectionKeychain() throws {
    let source = try sourceFile("DesktopKeychainStore.swift")
    // Match an actual query assignment, not the explanatory comment that names the flag.
    XCTAssertFalse(
      source.contains("kSecUseDataProtectionKeychain as String")
        || source.contains("[kSecUseDataProtectionKeychain"),
      "DesktopKeychainStore must use the file-based login keychain (no keychain-access-groups "
        + "entitlement); the data-protection keychain breaks sign-in on signed builds.")
  }

  /// Regression: never show the login-keychain password dialog. Local Apple Development
  /// builds previously wrote the unscoped `firebase-rest-session` item; notarized Beta then
  /// prompted on every launch. Team+bundle scoped v2 service names + never querying the
  /// legacy unscoped item close that path (LAContext alone does not suppress file-based ACL sheets).
  func testKeychainStoreNeverPresentsAuthenticationUI() throws {
    let source = try sourceFile("DesktopKeychainStore.swift")
    XCTAssertTrue(
      source.contains("interactionNotAllowed = true"),
      "DesktopKeychainStore must set LAContext.interactionNotAllowed so SecItem prefers fail-closed")
    XCTAssertTrue(
      source.contains("kSecUseAuthenticationContext"),
      "DesktopKeychainStore must pass an LAContext via kSecUseAuthenticationContext")
    XCTAssertTrue(
      source.contains("scopedService"),
      "DesktopKeychainStore must scope service names so Dev and Developer ID items diverge")
    XCTAssertTrue(
      source.contains(".v2.team."),
      "Scoped service names must include a v2.team marker")
    XCTAssertTrue(
      source.contains(".bundle."),
      "Scoped service names must include bundle id so local contributor apps cannot poison each other")
    XCTAssertFalse(
      source.contains("legacyServices"),
      "DesktopKeychainStore must not offer a legacy-service migration path that SecItem-queries "
        + "the unscoped firebase-rest-session item (that query is what triggers the password dialog)")
  }

  func testAuthTokenServiceIsTeamScopedAndNeverTouchesLegacyItem() throws {
    let source = try sourceFile("AuthService.swift")
    XCTAssertTrue(
      source.contains("DesktopKeychainStore.scopedService(DesktopKeychainStore.legacyAuthTokenService)"),
      "AuthService must store tokens under the team+bundle scoped Keychain service")
    XCTAssertFalse(
      source.contains("private let authTokenKeychainService = \"com.omi.desktop.firebase-rest-session\""),
      "AuthService must not hardcode the unscoped firebase-rest-session service name")
    // Live hooks must not pass the unscoped legacy name into SecItem (read or delete).
    XCTAssertFalse(
      source.contains("legacyServices: [DesktopKeychainStore.legacyAuthTokenService]"),
      "AuthService must not migrate by reading the unscoped legacy Keychain item")
    XCTAssertFalse(
      source.contains("delete(\n                    service: DesktopKeychainStore.legacyAuthTokenService"),
      "AuthService must not delete the unscoped legacy Keychain item (can itself prompt)")
  }

  func testScopedServiceIncludesTeamAndBundle() {
    let prod = DesktopKeychainStore.scopedService(
      "com.omi.desktop.firebase-rest-session",
      teamID: "9536L8KLMP",
      bundleID: "com.omi.computer-macos"
    )
    XCTAssertEqual(
      prod,
      "com.omi.desktop.firebase-rest-session.v2.team.9536L8KLMP.bundle.com.omi.computer-macos")

    let sameTeamDifferentBundle = DesktopKeychainStore.scopedService(
      "com.omi.desktop.firebase-rest-session",
      teamID: "JVMXE5G542",
      bundleID: "com.omi.desktop-dev"
    )
    let named = DesktopKeychainStore.scopedService(
      "com.omi.desktop.firebase-rest-session",
      teamID: "JVMXE5G542",
      bundleID: "com.omi.omi-fix-rewind"
    )
    XCTAssertEqual(
      sameTeamDifferentBundle,
      "com.omi.desktop.firebase-rest-session.v2.team.JVMXE5G542.bundle.com.omi.desktop-dev")
    XCTAssertEqual(
      named,
      "com.omi.desktop.firebase-rest-session.v2.team.JVMXE5G542.bundle.com.omi.omi-fix-rewind")
    XCTAssertNotEqual(prod, sameTeamDifferentBundle)
    XCTAssertNotEqual(sameTeamDifferentBundle, named)
  }

  func testClientDeviceServiceNeverUsesSharedLegacyKeychain() throws {
    let source = try sourceFile("ClientDeviceService.swift")
    XCTAssertTrue(
      source.contains("DesktopKeychainStore.scopedService"),
      "ClientDeviceService must use a scoped Keychain service on production builds")
    XCTAssertTrue(
      source.contains("interactionNotAllowed = true"),
      "ClientDeviceService Keychain access must be silent")
    XCTAssertFalse(
      source.contains("private let keychainService = \"com.omi.client-device-id\""),
      "ClientDeviceService must not hardcode the shared legacy device-id Keychain service")
    // All non-production bundles must stay on UserDefaults (no Keychain prompt risk).
    XCTAssertTrue(
      source.contains("productionBundleIdentifier"),
      "ClientDeviceService must gate Keychain use to the production bundle only")
  }

  private func sourceFile(_ relativePath: String) throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources")
      .appendingPathComponent(relativePath)
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }

  private func clearAuthDefaults() {
    UserDefaults.standard.removeObject(forKey: .authIdToken)
    UserDefaults.standard.removeObject(forKey: .authRefreshToken)
    UserDefaults.standard.removeObject(forKey: .authTokenExpiry)
    UserDefaults.standard.removeObject(forKey: .authTokenUserId)
    UserDefaults.standard.removeObject(forKey: .authUserId)
  }
}
