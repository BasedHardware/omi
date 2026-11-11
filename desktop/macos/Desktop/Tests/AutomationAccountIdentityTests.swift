import Foundation
import XCTest

@testable import Omi_Computer

/// The bridge must be able to answer *which* account a bundle is signed into.
///
/// `isSignedIn` alone cannot, and a named bundle's identity is not stable across
/// rebuilds: `run.sh` reseeds auth from a source bundle, so reinstalling a QA
/// bundle can silently swap the account. On 2026-09-18 that turned a free-tier
/// verification into a managed-path run against a different account, and every
/// downstream signal still looked plausible.
final class AutomationAccountIdentityTests: XCTestCase {
  private func scratchDefaults() throws -> UserDefaults {
    try XCTUnwrap(UserDefaults(suiteName: UUID().uuidString))
  }

  func testReportsTheStoredUserID() throws {
    let defaults = try scratchDefaults()
    defaults.set("gTVXbJh4JePPxsB3hlFQsX8OHhq2", forKey: DefaultsKey.authUserId)
    XCTAssertEqual(
      AuthState.automationAccountUserID(defaults: defaults, isNonProduction: true),
      "gTVXbJh4JePPxsB3hlFQsX8OHhq2"
    )
  }

  func testMissingAndBlankAreBothNil() throws {
    let empty = try scratchDefaults()
    XCTAssertNil(AuthState.automationAccountUserID(defaults: empty, isNonProduction: true))

    let blank = try scratchDefaults()
    blank.set("   ", forKey: DefaultsKey.authUserId)
    XCTAssertNil(
      AuthState.automationAccountUserID(defaults: blank, isNonProduction: true),
      "a whitespace-only value is 'unknown', not an account id"
    )
  }

  /// Read from the persisted default rather than from Firebase, so identity is
  /// answerable during `.restoring`. A harness that checks right after launch
  /// must not be told `nil` merely because the credential is still validating —
  /// that reintroduces the same ambiguity this exists to remove.
  func testAnswersBeforeTheCredentialHasValidated() throws {
    let defaults = try scratchDefaults()
    defaults.set("some-uid", forKey: DefaultsKey.authUserId)
    defaults.set(false, forKey: DefaultsKey.authIsSignedIn)
    XCTAssertEqual(AuthState.automationAccountUserID(defaults: defaults, isNonProduction: true), "some-uid")
  }

  /// The account id is a non-production affordance. A production build must not
  /// report it even if the default is present, so the guard is exercised rather
  /// than assumed.
  func testProductionBuildsReportNothing() throws {
    let defaults = try scratchDefaults()
    defaults.set("some-uid", forKey: DefaultsKey.authUserId)
    XCTAssertNil(AuthState.automationAccountUserID(defaults: defaults, isNonProduction: false))
  }
}
