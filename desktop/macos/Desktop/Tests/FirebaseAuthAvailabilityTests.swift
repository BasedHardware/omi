import OmiSupport
import XCTest

@testable import Omi_Computer

@MainActor
final class FirebaseAuthAvailabilityTests: XCTestCase {
  private var auth = AuthService()
  private var originalPhase: AuthSessionPhase = .signedOut
  private var createdOwnerIDs: [String] = []

  override func setUp() async throws {
    originalPhase = AuthState.shared.sessionPhase
    clearAuthDefaults()
    auth = AuthService()
    auth.firebaseAuthAvailability = FirebaseAuthAvailability(configuredAuth: { nil })
    auth.tokenStorageHooks = AuthService.TokenStorageHooks(
      usesKeychainTokenStorage: { false },
      allowsUserDefaultsFallback: { true },
      readKeychainString: { _, _ in nil },
      writeKeychainString: { _, _, _ in true },
      deleteKeychainString: { _, _ in },
      recordsFallbackTelemetry: false
    )
    await RewindDatabase.shared.close()
  }

  override func tearDown() async throws {
    let cleanupAttempt = auth.beginSessionAttempt()
    _ = await auth.commitSignedOutSession(attempt: cleanupAttempt, phase: .signedOut)
    auth.firebaseAuthAvailability = .live
    auth.tokenStorageHooks = .live
    await RewindDatabase.shared.close()
    clearAuthDefaults()
    for ownerID in createdOwnerIDs {
      try? FileManager.default.removeItem(at: userDirectory(ownerID))
    }
    createdOwnerIDs = []
    AuthState.shared.transition(to: originalPhase)
  }

  func testUnavailableFirebaseConfiguresRESTBackedAuth() async {
    await auth.configure()

    XCTAssertEqual(AuthState.shared.sessionPhase, .signedOut)
  }

  func testUnavailableFirebaseKeepsRESTBackedSignInAndSignOutUsable() async throws {
    let ownerID = makeOwnerID("firebase-unavailable")
    let signInAttempt = auth.beginSessionAttempt()

    let committed = try await auth.commitSignedInSession(
      tokens: .init(
        idToken: "id-\(ownerID)",
        refreshToken: "refresh-\(ownerID)",
        expiresIn: 3600,
        localId: ownerID),
      email: "firebase-unavailable@example.test",
      attempt: signInAttempt)

    XCTAssertTrue(committed)
    let restoredToken = try await auth.getIdToken()
    XCTAssertEqual(restoredToken, "id-\(ownerID)")
    XCTAssertEqual(AuthState.shared.sessionPhase, .authenticated)

    try await auth.signOut()

    XCTAssertEqual(AuthState.shared.sessionPhase, .signedOut)
    XCTAssertNil(UserDefaults.standard.string(forKey: .authUserId))
    XCTAssertNil(UserDefaults.standard.string(forKey: .authIdToken))
    XCTAssertNil(UserDefaults.standard.string(forKey: .authRefreshToken))
  }

  func testUnavailableFirebaseNativeApplePathUsesRESTFallback() async throws {
    var restFallbackCalled = false
    let result = try await FirebaseAuthAvailability.signInWithNativeApple(
      auth: nil,
      identityToken: "identity-token",
      nonce: "nonce",
      isSessionCurrent: { true },
      discardStaleFirebaseUser: { _ in XCTFail("unconfigured SDK must not produce a stale Firebase user") },
      restFallback: {
        restFallbackCalled = true
        return .init(
          idToken: "rest-id-token", refreshToken: "rest-refresh-token", expiresIn: 3600, localId: "rest-user")
      }
    )

    XCTAssertTrue(restFallbackCalled)
    XCTAssertEqual(result.tokens.localId, "rest-user")
    XCTAssertEqual(result.fallbackReason, "config_incomplete")
  }

  private func makeOwnerID(_ prefix: String) -> String {
    let ownerID = "\(prefix)-\(UUID().uuidString)"
    createdOwnerIDs.append(ownerID)
    return ownerID
  }

  private func userDirectory(_ ownerID: String) -> URL {
    DesktopLocalProfile.applicationSupportURL()
      .appendingPathComponent("users", isDirectory: true)
      .appendingPathComponent(ownerID, isDirectory: true)
  }

  private func clearAuthDefaults() {
    for key in [
      DefaultsKey.authIsSignedIn,
      .authUserEmail,
      .authUserId,
      .authIdToken,
      .authRefreshToken,
      .authTokenExpiry,
      .authTokenUserId,
      .automationOwnerOverride,
      .automationOwnerABackup,
    ] {
      UserDefaults.standard.removeObject(forKey: key)
    }
  }
}
