import Foundation

@testable import Omi_Computer

private actor RewindStorageTestGate {
  static let shared = RewindStorageTestGate()

  private var isHeld = false
  private var waiters: [CheckedContinuation<Void, Never>] = []

  func acquire() async {
    if !isHeld {
      isHeld = true
      return
    }
    await withCheckedContinuation { continuation in
      waiters.append(continuation)
    }
  }

  func release() {
    guard !waiters.isEmpty else {
      isHeld = false
      return
    }
    waiters.removeFirst().resume()
  }
}

/// Shared setup/teardown for XCTest suites that touch Rewind storage singletons.
///
/// Mirrors the lifecycle used by `StagedTaskSyncIntegrityTests`: close the database,
/// invalidate cached storage actors, configure a throwaway user, initialize, and on
/// teardown close again before deleting the user directory.
enum RewindStorageTestIsolation {
  struct Fixture {
    let testUserId: String
    let userDir: URL
  }

  struct AuthSnapshot {
    let isSignedIn: Bool
    let userId: String?
  }

  static func setUp(userIdPrefix: String) async throws -> Fixture {
    await RewindStorageTestGate.shared.acquire()
    let testUserId = "\(userIdPrefix)-\(UUID().uuidString)"
    let userDir = userDirectory(for: testUserId)
    do {
      await RewindDatabase.shared.close()
      await invalidateAllStorageCaches()
      RewindDatabase.currentUserId = testUserId
      await RewindDatabase.shared.configure(userId: testUserId)
      try await RewindDatabase.shared.initialize()
      return Fixture(testUserId: testUserId, userDir: userDir)
    } catch {
      await RewindDatabase.shared.close()
      await invalidateAllStorageCaches()
      RewindDatabase.currentUserId = nil
      try? FileManager.default.removeItem(at: userDir)
      await RewindStorageTestGate.shared.release()
      throw error
    }
  }

  static func tearDown(userDir: URL?) async {
    guard let userDir else { return }
    await RewindDatabase.shared.close()
    await invalidateAllStorageCaches()
    RewindDatabase.currentUserId = nil
    try? FileManager.default.removeItem(at: userDir)
    await RewindStorageTestGate.shared.release()
  }

  @MainActor
  static func captureAuthSnapshot() -> AuthSnapshot {
    AuthSnapshot(
      isSignedIn: AuthState.shared.isSignedIn,
      userId: UserDefaults.standard.string(forKey: .authUserId)
    )
  }

  @MainActor
  static func signInForTests(userId: String) {
    AuthState.shared.update(isSignedIn: true)
    UserDefaults.standard.set(userId, forKey: .authUserId)
  }

  @MainActor
  static func restoreAuthSnapshot(_ snapshot: AuthSnapshot) {
    AuthState.shared.update(isSignedIn: snapshot.isSignedIn)
    if let userId = snapshot.userId {
      UserDefaults.standard.set(userId, forKey: .authUserId)
    } else {
      UserDefaults.standard.removeObject(forKey: .authUserId)
    }
  }

  static func invalidateAllStorageCaches() async {
    await MemoryStorage.shared.invalidateCache()
    await ActionItemStorage.shared.invalidateCache()
    await TranscriptionStorage.shared.invalidateCache()
    await StagedTaskStorage.shared.invalidateCache()
    await GoalStorage.shared.invalidateCache()
    await ProactiveStorage.shared.invalidateCache()
    await TaskChatMessageStorage.shared.invalidateCache()
  }

  static func userDirectory(for testUserId: String) -> URL {
    let appSupport = FileManager.default
      .urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
    return appSupport
      .appendingPathComponent("Omi", isDirectory: true)
      .appendingPathComponent("users", isDirectory: true)
      .appendingPathComponent(testUserId, isDirectory: true)
  }
}
