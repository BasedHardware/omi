import XCTest

@testable import Omi_Computer

/// S-13 — typed UserDefaults keys (BL-004, partial).
///
/// Guards the anti-typo foundation: the typed `DefaultsKey` accessors must read
/// and write the exact same underlying string keys the app has always used (so
/// migrated call sites see previously-persisted auth state), the key strings are
/// pinned against silent drift, and `AuthService` reads through the typed keys
/// rather than raw inline literals.
final class DefaultsKeyTests: XCTestCase {

  private var defaults: UserDefaults!
  private let suiteName = "DefaultsKeyTests.\(UUID().uuidString)"

  override func setUp() {
    super.setUp()
    defaults = UserDefaults(suiteName: suiteName)
  }

  override func tearDown() {
    defaults.removePersistentDomain(forName: suiteName)
    defaults = nil
    super.tearDown()
  }

  // MARK: Key-string stability

  /// The rawValue of each case is the on-disk key. Renaming any of these
  /// silently orphans previously-persisted auth state (the user gets logged
  /// out with no error). Pin them so such a change fails loudly in review.
  func testRawValuesMatchLegacyKeyStrings() {
    XCTAssertEqual(DefaultsKey.authIsSignedIn.rawValue, "auth_isSignedIn")
    XCTAssertEqual(DefaultsKey.authUserEmail.rawValue, "auth_userEmail")
    XCTAssertEqual(DefaultsKey.authUserId.rawValue, "auth_userId")
    XCTAssertEqual(DefaultsKey.authGivenName.rawValue, "auth_givenName")
    XCTAssertEqual(DefaultsKey.authFamilyName.rawValue, "auth_familyName")
    XCTAssertEqual(DefaultsKey.authIdToken.rawValue, "auth_idToken")
    XCTAssertEqual(DefaultsKey.authRefreshToken.rawValue, "auth_refreshToken")
    XCTAssertEqual(DefaultsKey.authTokenExpiry.rawValue, "auth_tokenExpiry")
    XCTAssertEqual(DefaultsKey.authTokenUserId.rawValue, "auth_tokenUserId")
    XCTAssertEqual(DefaultsKey.authIsImpersonating.rawValue, "auth_isImpersonating")
  }

  // MARK: Typed accessors round-trip through the same underlying key

  /// A value written with the typed setter must be readable with the raw
  /// `String` key (and vice versa) — i.e. the typed accessor is a pure alias for
  /// `forKey: key.rawValue`, so migrated code and any not-yet-migrated raw call
  /// site still agree on the same slot.
  func testTypedStringAccessorAliasesRawKey() {
    defaults.set("user-123", forKey: .authUserId)
    XCTAssertEqual(defaults.string(forKey: "auth_userId"), "user-123")
    XCTAssertEqual(defaults.string(forKey: .authUserId), "user-123")

    defaults.set("alt-456", forKey: "auth_userId")
    XCTAssertEqual(defaults.string(forKey: .authUserId), "alt-456")
  }

  func testTypedBoolAccessorAliasesRawKey() {
    XCTAssertFalse(defaults.bool(forKey: .authIsSignedIn))  // default
    defaults.set(true, forKey: .authIsSignedIn)
    XCTAssertTrue(defaults.bool(forKey: "auth_isSignedIn"))
    XCTAssertTrue(defaults.bool(forKey: .authIsSignedIn))
  }

  func testTypedNumericAccessorsAliasRawKey() {
    XCTAssertEqual(defaults.integer(forKey: .authTokenExpiry), 0)  // default
    defaults.set(1_700_000_000.5, forKey: .authTokenExpiry)
    XCTAssertEqual(defaults.double(forKey: .authTokenExpiry), 1_700_000_000.5, accuracy: 0.0001)
    XCTAssertEqual(defaults.double(forKey: "auth_tokenExpiry"), 1_700_000_000.5, accuracy: 0.0001)
  }

  func testRemoveObjectClearsTypedKey() {
    defaults.set("gone", forKey: .authIdToken)
    XCTAssertNotNil(defaults.string(forKey: .authIdToken))
    defaults.removeObject(forKey: .authIdToken)
    XCTAssertNil(defaults.string(forKey: .authIdToken))
    XCTAssertNil(defaults.string(forKey: "auth_idToken"))
  }

  // MARK: AuthService migration (regression guard)

  /// AuthService must read its auth keys through the typed enum, not through the
  /// old private `kAuth*` constants or raw inline literals.
  func testAuthServiceUsesTypedKeys() throws {
    let src = try source(relativePath: "Sources/AuthService.swift")

    XCTAssertTrue(
      src.contains("forKey: .authUserId"),
      "AuthService must read/write auth_userId through the typed DefaultsKey")
    XCTAssertFalse(
      src.contains("private let kAuthUserId"),
      "the duplicated private key constants must be gone (single source is DefaultsKey)")
    XCTAssertFalse(
      src.contains("forKey: \"auth_isImpersonating\""),
      "the raw impersonation literal must be migrated to .authIsImpersonating")
  }

  // MARK: Helper

  private func source(relativePath: String) throws -> String {
    let url = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent(relativePath)
    return try String(contentsOf: url, encoding: .utf8)
  }
}
