import Foundation

@testable import Omi_Computer

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
    let testUserId = "\(userIdPrefix)-\(UUID().uuidString)"
    await RewindDatabase.shared.close()
    await invalidateAllStorageCaches()
    RewindDatabase.currentUserId = testUserId
    await RewindDatabase.shared.configure(userId: testUserId)
    try await RewindDatabase.shared.initialize()
    return Fixture(testUserId: testUserId, userDir: userDirectory(for: testUserId))
  }

  static func tearDown(userDir: URL?) async {
    await RewindDatabase.shared.close()
    await invalidateAllStorageCaches()
    RewindDatabase.currentUserId = nil
    if let userDir {
      try? FileManager.default.removeItem(at: userDir)
    }
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
