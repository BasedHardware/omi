import XCTest

@testable import Omi_Computer

/// Regression: gauntlet owner-swap must never rewrite Firebase `auth_userId`.
/// Doing so makes `AuthService.getIdToken()` clear tokens (uid mismatch) and
/// leaves a ghost signed-in session after restore.
final class RuntimeOwnerIdentityTests: XCTestCase {
  private var defaults: UserDefaults!
  private let suiteName = "RuntimeOwnerIdentityTests.\(UUID().uuidString)"

  override func setUp() {
    super.setUp()
    defaults = UserDefaults(suiteName: suiteName)
  }

  override func tearDown() {
    defaults.removePersistentDomain(forName: suiteName)
    defaults = nil
    super.tearDown()
  }

  func testOverrideDoesNotRewriteAuthUserIdOrTokens() {
    defaults.set("real-owner-a", forKey: .authUserId)
    defaults.set("id-token-a", forKey: .authIdToken)
    defaults.set("refresh-token-a", forKey: .authRefreshToken)
    defaults.set("real-owner-a", forKey: .authTokenUserId)
    defaults.set(true, forKey: .authIsSignedIn)

    RuntimeOwnerIdentity.applyAutomationOwnerOverride("synthetic-owner-b", defaults: defaults)

    XCTAssertEqual(defaults.string(forKey: .authUserId), "real-owner-a")
    XCTAssertEqual(defaults.string(forKey: .authIdToken), "id-token-a")
    XCTAssertEqual(defaults.string(forKey: .authRefreshToken), "refresh-token-a")
    XCTAssertEqual(defaults.string(forKey: .authTokenUserId), "real-owner-a")
    XCTAssertTrue(defaults.bool(forKey: .authIsSignedIn))
    XCTAssertEqual(defaults.string(forKey: .automationOwnerOverride), "synthetic-owner-b")
    XCTAssertEqual(defaults.string(forKey: .automationOwnerABackup), "real-owner-a")
    XCTAssertEqual(
      RuntimeOwnerIdentity.currentOwnerId(defaults: defaults, allowAutomationOverride: true),
      "synthetic-owner-b"
    )
    XCTAssertEqual(
      RuntimeOwnerIdentity.currentOwnerId(defaults: defaults, allowAutomationOverride: false),
      "real-owner-a"
    )
  }

  func testClearOverrideRestoresKernelOwnerWithoutTouchingTokens() {
    defaults.set("real-owner-a", forKey: .authUserId)
    defaults.set("id-token-a", forKey: .authIdToken)
    defaults.set("refresh-token-a", forKey: .authRefreshToken)
    RuntimeOwnerIdentity.applyAutomationOwnerOverride("synthetic-owner-b", defaults: defaults)

    let result = RuntimeOwnerIdentity.clearAutomationOwnerOverride(defaults: defaults)

    XCTAssertTrue(result.restored)
    XCTAssertEqual(result.ownerId, "real-owner-a")
    XCTAssertEqual(defaults.string(forKey: .authUserId), "real-owner-a")
    XCTAssertEqual(defaults.string(forKey: .authIdToken), "id-token-a")
    XCTAssertEqual(defaults.string(forKey: .authRefreshToken), "refresh-token-a")
    XCTAssertNil(defaults.string(forKey: .automationOwnerOverride))
    XCTAssertNil(defaults.string(forKey: .automationOwnerABackup))
    XCTAssertEqual(
      RuntimeOwnerIdentity.currentOwnerId(defaults: defaults, allowAutomationOverride: true),
      "real-owner-a"
    )
  }

  func testClearHealsLegacySyntheticAuthUserId() {
    // Older builds wrote owner B into auth_userId and stashed owner A in backup.
    defaults.set("synthetic-owner-b", forKey: .authUserId)
    defaults.set("real-owner-a", forKey: .automationOwnerABackup)
    defaults.set("id-token-a", forKey: .authIdToken)

    let result = RuntimeOwnerIdentity.clearAutomationOwnerOverride(defaults: defaults)

    XCTAssertTrue(result.restored)
    XCTAssertEqual(result.ownerId, "real-owner-a")
    XCTAssertEqual(defaults.string(forKey: .authUserId), "real-owner-a")
    XCTAssertEqual(defaults.string(forKey: .authIdToken), "id-token-a")
    XCTAssertNil(defaults.string(forKey: .automationOwnerABackup))
  }

  func testNestedOverridePreservesOriginalBackup() {
    defaults.set("real-owner-a", forKey: .authUserId)
    RuntimeOwnerIdentity.applyAutomationOwnerOverride("synthetic-owner-b", defaults: defaults)
    RuntimeOwnerIdentity.applyAutomationOwnerOverride("synthetic-owner-c", defaults: defaults)

    XCTAssertEqual(defaults.string(forKey: .automationOwnerOverride), "synthetic-owner-c")
    XCTAssertEqual(defaults.string(forKey: .automationOwnerABackup), "real-owner-a")
    XCTAssertEqual(defaults.string(forKey: .authUserId), "real-owner-a")
  }

  func testClearDoesNotClobberAuthUserIdUpdatedDuringOverride() {
    defaults.set("real-owner-a", forKey: .authUserId)
    defaults.set("id-token-a", forKey: .authIdToken)
    RuntimeOwnerIdentity.applyAutomationOwnerOverride("synthetic-owner-b", defaults: defaults)
    // Mid-session sign-in updates the real auth uid while override is active.
    defaults.set("real-owner-c", forKey: .authUserId)
    defaults.set("id-token-c", forKey: .authIdToken)

    let result = RuntimeOwnerIdentity.clearAutomationOwnerOverride(defaults: defaults)

    XCTAssertTrue(result.restored)
    XCTAssertEqual(defaults.string(forKey: .authUserId), "real-owner-c")
    XCTAssertEqual(defaults.string(forKey: .authIdToken), "id-token-c")
    XCTAssertNil(defaults.string(forKey: .automationOwnerOverride))
    XCTAssertNil(defaults.string(forKey: .automationOwnerABackup))
  }

  func testClearHealsWhenAuthUserIdStillEqualsSyntheticOverride() {
    defaults.set("real-owner-a", forKey: .authUserId)
    RuntimeOwnerIdentity.applyAutomationOwnerOverride("synthetic-owner-b", defaults: defaults)
    // Legacy path also wrote the synthetic owner into auth_userId.
    defaults.set("synthetic-owner-b", forKey: .authUserId)

    let result = RuntimeOwnerIdentity.clearAutomationOwnerOverride(defaults: defaults)

    XCTAssertTrue(result.restored)
    XCTAssertEqual(result.ownerId, "real-owner-a")
    XCTAssertEqual(defaults.string(forKey: .authUserId), "real-owner-a")
  }

  func testSwapPathSourceNeverWritesAuthUserId() throws {
    let desktopDir = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
    let provider = try String(
      contentsOf: desktopDir.appendingPathComponent("Sources/Providers/ChatProvider.swift"),
      encoding: .utf8
    )
    let identity = try String(
      contentsOf: desktopDir.appendingPathComponent("Sources/Chat/RuntimeOwnerIdentity.swift"),
      encoding: .utf8
    )

    XCTAssertTrue(provider.contains("RuntimeOwnerIdentity.applyAutomationOwnerOverride"))
    XCTAssertTrue(provider.contains("RuntimeOwnerIdentity.clearAutomationOwnerOverride"))
    XCTAssertFalse(
      provider.contains("UserDefaults.standard.set(trimmedOwnerB, forKey:"),
      "swap must not write synthetic owner into auth defaults"
    )
    XCTAssertTrue(identity.contains("automationOwnerOverride"))
    XCTAssertFalse(
      identity.contains("defaults.set(trimmed, forKey: .authUserId)"),
      "override helper must never rewrite auth_userId"
    )

    let defaultsKey = try String(
      contentsOf: desktopDir.appendingPathComponent("Sources/DefaultsKey.swift"),
      encoding: .utf8
    )
    XCTAssertTrue(defaultsKey.contains("automationOwnerOverride = \"automation_owner_override\""))
    XCTAssertTrue(defaultsKey.contains("automationOwnerABackup = \"automation_swap_owner_a_backup\""))
  }
}
