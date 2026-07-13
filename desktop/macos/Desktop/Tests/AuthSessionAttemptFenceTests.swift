import XCTest
import OmiSupport

@testable import Omi_Computer

private actor AuthCommitLeaseGate {
  private var isHeld = false
  private var heldWaiters: [CheckedContinuation<Void, Never>] = []
  private var releaseContinuation: CheckedContinuation<Void, Never>?

  func hold() async {
    isHeld = true
    let waiters = heldWaiters
    heldWaiters.removeAll()
    waiters.forEach { $0.resume() }
    await withCheckedContinuation { continuation in
      releaseContinuation = continuation
    }
  }

  func waitUntilHeld() async {
    guard !isHeld else { return }
    await withCheckedContinuation { continuation in
      heldWaiters.append(continuation)
    }
  }

  func release() {
    releaseContinuation?.resume()
    releaseContinuation = nil
  }
}

private actor AuthRefreshResponseGate {
  private var reached = false
  private var reachedWaiters: [CheckedContinuation<Void, Never>] = []
  private var responseContinuation: CheckedContinuation<(Data, URLResponse), Never>?

  func waitForResponse() async -> (Data, URLResponse) {
    reached = true
    let waiters = reachedWaiters
    reachedWaiters.removeAll()
    waiters.forEach { $0.resume() }
    return await withCheckedContinuation { continuation in
      responseContinuation = continuation
    }
  }

  func waitUntilReached() async {
    guard !reached else { return }
    await withCheckedContinuation { continuation in
      reachedWaiters.append(continuation)
    }
  }

  func release(ownerID: String) {
    let data = Data(
      "{\"id_token\":\"refreshed-id\",\"refresh_token\":\"refreshed-refresh\",\"expires_in\":\"3600\",\"user_id\":\"\(ownerID)\"}"
        .utf8)
    let response = HTTPURLResponse(
      url: URL(string: "https://securetoken.googleapis.com/v1/token")!,
      statusCode: 200,
      httpVersion: nil,
      headerFields: nil)!
    responseContinuation?.resume(returning: (data, response))
    responseContinuation = nil
  }
}

@MainActor
final class AuthSessionAttemptFenceTests: XCTestCase {
  private var auth: AuthService!
  private var originalPhase: AuthSessionPhase = .signedOut
  private var createdOwnerIDs: [String] = []

  override func setUp() async throws {
    try await super.setUp()
    originalPhase = AuthState.shared.sessionPhase
    clearAuthDefaults()
    auth = AuthService()
    auth.tokenStorageHooks = AuthService.TokenStorageHooks(
      usesKeychainTokenStorage: { false },
      allowsUserDefaultsFallback: { true },
      readKeychainString: { _, _ in nil },
      writeKeychainString: { _, _, _ in true },
      deleteKeychainString: { _, _ in },
      recordsFallbackTelemetry: false)
    await RewindDatabase.shared.close()
  }

  override func tearDown() async throws {
    let cleanupAttempt = auth.beginSessionAttempt()
    _ = await auth.commitSignedOutSession(attempt: cleanupAttempt, phase: .signedOut)
    auth.tokenStorageHooks = .live
    auth.tokenRefreshHooks = .live
    auth = nil
    await RewindDatabase.shared.close()
    clearAuthDefaults()
    for ownerID in createdOwnerIDs {
      try? FileManager.default.removeItem(at: userDirectory(ownerID))
    }
    createdOwnerIDs = []
    AuthState.shared.transition(to: originalPhase)
    try await super.tearDown()
  }

  func testNewSignInTokensSurviveSupersededSignOutWaitingOnOwnerTransition() async throws {
    let ownerA = makeOwnerID("signout-a")
    let ownerB = makeOwnerID("signin-b")
    let seedAttempt = auth.beginSessionAttempt()
    let seededOwnerA = try await auth.commitSignedInSession(
      tokens: tokens(for: ownerA),
      email: "a@example.test",
      attempt: seedAttempt)
    XCTAssertTrue(seededOwnerA)

    let gate = AuthCommitLeaseGate()
    let leaseTask = Task {
      try await LocalMutationAuthorization.unrestricted.withCommitLease {
        await gate.hold()
      }
    }
    await gate.waitUntilHeld()

    let signOutAttempt = auth.beginSessionAttempt()
    let signOutTask = Task {
      await auth.commitSignedOutSession(attempt: signOutAttempt, phase: .signedOut)
    }
    await EffectiveOwnerTransitionFence.shared.waitUntilTransitionIsPending()

    let signInAttempt = auth.beginSessionAttempt()
    let signInTask = Task {
      try await auth.commitSignedInSession(
        tokens: tokens(for: ownerB),
        email: "b@example.test",
        attempt: signInAttempt)
    }

    await gate.release()
    try await leaseTask.value
    let staleSignOutCommitted = await signOutTask.value
    let ownerBCommitted = try await signInTask.value
    XCTAssertFalse(staleSignOutCommitted)
    XCTAssertTrue(ownerBCommitted)

    XCTAssertEqual(UserDefaults.standard.string(forKey: .authUserId), ownerB)
    XCTAssertEqual(UserDefaults.standard.string(forKey: .authTokenUserId), ownerB)
    XCTAssertEqual(UserDefaults.standard.string(forKey: .authIdToken), "id-\(ownerB)")
    XCTAssertEqual(AuthState.shared.sessionPhase, .authenticated)
  }

  func testReplacementCredentialsPublishAtomicallyWithTheirOwner() async throws {
    let ownerA = makeOwnerID("atomic-owner-a")
    let ownerB = makeOwnerID("atomic-owner-b")
    let seedAttempt = auth.beginSessionAttempt()
    let seededOwnerA = try await auth.commitSignedInSession(
      tokens: tokens(for: ownerA),
      email: "a@example.test",
      attempt: seedAttempt)
    XCTAssertTrue(seededOwnerA)

    let gate = AuthCommitLeaseGate()
    let leaseTask = Task {
      try await LocalMutationAuthorization.unrestricted.withCommitLease {
        await gate.hold()
      }
    }
    await gate.waitUntilHeld()

    let replacementAttempt = auth.beginSessionAttempt()
    let replacementTask = Task {
      try await auth.commitSignedInSession(
        tokens: tokens(for: ownerB),
        email: "b@example.test",
        attempt: replacementAttempt)
    }
    await EffectiveOwnerTransitionFence.shared.waitUntilTransitionIsPending()

    // While B is parked behind the owner fence, A remains a completely
    // consistent credential generation. Before the atomic commit contract,
    // B's token was already visible here with A's durable owner; this read then
    // deleted B's token as a mismatched stale credential.
    XCTAssertEqual(UserDefaults.standard.string(forKey: .authUserId), ownerA)
    XCTAssertEqual(UserDefaults.standard.string(forKey: .authTokenUserId), ownerA)
    let ownerAToken = try? await auth.getIdToken()
    XCTAssertEqual(ownerAToken, "id-\(ownerA)")

    await gate.release()
    try await leaseTask.value
    let ownerBCommitted = try await replacementTask.value
    XCTAssertTrue(ownerBCommitted)

    XCTAssertEqual(UserDefaults.standard.string(forKey: .authUserId), ownerB)
    XCTAssertEqual(UserDefaults.standard.string(forKey: .authTokenUserId), ownerB)
    XCTAssertEqual(UserDefaults.standard.string(forKey: .authIdToken), "id-\(ownerB)")
    let ownerBToken = try await auth.getIdToken()
    XCTAssertEqual(ownerBToken, "id-\(ownerB)")
  }

  func testStaleRestoreCannotRepublishAfterSignOutBegins() async throws {
    let ownerA = makeOwnerID("restore-a")
    let seedAttempt = auth.beginSessionAttempt()
    let seededOwnerA = try await auth.commitSignedInSession(
      tokens: tokens(for: ownerA),
      email: "a@example.test",
      attempt: seedAttempt)
    XCTAssertTrue(seededOwnerA)

    let gate = AuthCommitLeaseGate()
    let leaseTask = Task {
      try await LocalMutationAuthorization.unrestricted.withCommitLease {
        await gate.hold()
      }
    }
    await gate.waitUntilHeld()

    let restoreAttempt = auth.beginSessionAttempt()
    let restoreTask = Task {
      await auth.commitRestoredSession(
        userId: ownerA,
        email: "a@example.test",
        attempt: restoreAttempt)
    }
    await EffectiveOwnerTransitionFence.shared.waitUntilTransitionIsPending()

    let signOutAttempt = auth.beginSessionAttempt()
    let signOutTask = Task {
      await auth.commitSignedOutSession(attempt: signOutAttempt, phase: .signedOut)
    }

    await gate.release()
    try await leaseTask.value
    let staleRestoreCommitted = await restoreTask.value
    let signOutCommitted = await signOutTask.value
    XCTAssertFalse(staleRestoreCommitted)
    XCTAssertTrue(signOutCommitted)

    XCTAssertNil(UserDefaults.standard.string(forKey: .authUserId))
    XCTAssertNil(UserDefaults.standard.string(forKey: .authTokenUserId))
    XCTAssertNil(UserDefaults.standard.string(forKey: .authIdToken))
    XCTAssertEqual(AuthState.shared.sessionPhase, .signedOut)
  }

  func testStaleEnsureValidSessionCannotChangeNewerSignedOutPhase() async throws {
    let ownerA = makeOwnerID("validation-a")
    let seedAttempt = auth.beginSessionAttempt()
    let seeded = try await auth.commitSignedInSession(
      tokens: tokens(for: ownerA),
      email: "a@example.test",
      attempt: seedAttempt)
    XCTAssertTrue(seeded)

    let responseGate = AuthRefreshResponseGate()
    auth.tokenRefreshHooks = AuthService.TokenRefreshHooks(
      dataForRequest: { _ in
        await responseGate.waitForResponse()
      })
    setenv("FIREBASE_API_KEY", "test-key", 1)
    defer { unsetenv("FIREBASE_API_KEY") }

    let validationTask = Task {
      await AuthSessionCoordinator.shared.ensureValidSession(
        trigger: .appBecameActive,
        auth: auth)
    }
    await responseGate.waitUntilReached()

    let signOutAttempt = auth.beginSessionAttempt()
    let signedOut = await auth.commitSignedOutSession(
      attempt: signOutAttempt,
      phase: .signedOut)
    XCTAssertTrue(signedOut)
    await responseGate.release(ownerID: ownerA)

    let validationSucceeded = await validationTask.value
    XCTAssertFalse(validationSucceeded)
    XCTAssertEqual(AuthState.shared.sessionPhase, .signedOut)
    XCTAssertNil(UserDefaults.standard.string(forKey: .authUserId))
  }

  private func tokens(for ownerID: String) -> AuthService.FirebaseTokenResult {
    AuthService.FirebaseTokenResult(
      idToken: "id-\(ownerID)",
      refreshToken: "refresh-\(ownerID)",
      expiresIn: 3600,
      localId: ownerID)
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
