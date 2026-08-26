import Foundation

struct RewindCaptureOwnerSnapshot: Equatable, Sendable {
  let ownerID: String
  let generation: UInt64
  let authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?

  /// Prefer authenticated owner, then Rewind DB owner, then anonymous.
  /// `capture()` and `isCurrent()` must use the same order (#11572).
  static func resolvedOwnerID(
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? =
      RuntimeOwnerIdentity
      .captureAuthorizationSnapshot()
  ) -> String {
    authorizationSnapshot?.ownerID ?? RewindDatabase.currentUserId ?? "anonymous"
  }

  static func capture() -> RewindCaptureOwnerSnapshot? {
    let authorizationSnapshot = RuntimeOwnerIdentity.captureAuthorizationSnapshot()
    guard let generation = RewindCaptureOwnerGeneration.snapshot() else { return nil }
    return RewindCaptureOwnerSnapshot(
      ownerID: resolvedOwnerID(authorizationSnapshot: authorizationSnapshot),
      generation: generation,
      authorizationSnapshot: authorizationSnapshot)
  }

  func isCurrent() -> Bool {
    let currentOwnerID = Self.resolvedOwnerID()
    guard currentOwnerID == ownerID,
      RewindCaptureOwnerGeneration.isCurrent(generation)
    else { return false }
    return authorizationSnapshot.map(RuntimeOwnerIdentity.isAuthorizationCurrent) ?? true
  }
}

/// A synchronous session fence for local-only/anonymous capture, where an
/// authenticated authorization snapshot may not exist. It also closes the
/// same-uid sign-out/sign-in window by refusing admission during retargeting.
enum RewindCaptureOwnerGeneration {
  private final class State: @unchecked Sendable {
    let lock = NSLock()
    var generation: UInt64 = 0
    var transitionActive = false
  }

  private static let state = State()

  static func snapshot() -> UInt64? {
    state.lock.withLock { state.transitionActive ? nil : state.generation }
  }

  static func isCurrent(_ generation: UInt64) -> Bool {
    state.lock.withLock {
      !state.transitionActive && state.generation == generation
    }
  }

  static func beginTransition() {
    state.lock.withLock {
      state.generation &+= 1
      state.transitionActive = true
    }
  }

  static func endTransition() {
    state.lock.withLock { state.transitionActive = false }
  }
}

/// Owner/app admission token carried by a frame from capture into Rewind storage.
/// The generation changes synchronously when an app is excluded or re-included,
/// so an already queued frame cannot cross the persistence boundary afterward.
struct RewindCaptureExclusionSnapshot: Equatable, Sendable {
  let appName: String
  let generation: UInt64
  let ownerSnapshot: RewindCaptureOwnerSnapshot
}

struct RewindCaptureExcludedError: Error, Sendable {
  let relativePath: String?
  let snapshot: RewindCaptureExclusionSnapshot
}

/// Synchronous exclusion fence shared by the MainActor settings UI and the
/// RewindIndexer actor. Leases cover only encoder/DB critical sections (not OCR)
/// so changing privacy settings never waits on model/OCR work.
enum RewindCaptureExclusionGeneration {
  /// The state is guarded by `condition`; the unchecked marker is limited to
  /// this tiny synchronization wrapper so callers can use the fence from
  /// MainActor code and the RewindIndexer actor alike.
  private final class State: @unchecked Sendable {
    let condition = NSCondition()
    var generations: [String: UInt64] = [:]
    var excludedApps: Set<String> = []
    var inFlight: [String: Int] = [:]
  }

  private static let state = State()

  static func snapshot(appName: String) -> RewindCaptureExclusionSnapshot? {
    guard let ownerSnapshot = RewindCaptureOwnerSnapshot.capture() else { return nil }
    state.condition.lock()
    defer { state.condition.unlock() }
    guard !state.excludedApps.contains(appName) else { return nil }
    return RewindCaptureExclusionSnapshot(
      appName: appName,
      generation: state.generations[appName] ?? 0,
      ownerSnapshot: ownerSnapshot)
  }

  static func isOwnerCurrent(_ snapshot: RewindCaptureExclusionSnapshot) -> Bool {
    snapshot.ownerSnapshot.isCurrent()
  }

  static func isCurrent(_ snapshot: RewindCaptureExclusionSnapshot) -> Bool {
    state.condition.lock()
    defer { state.condition.unlock() }
    return isOwnerCurrent(snapshot)
      && !state.excludedApps.contains(snapshot.appName)
      && state.generations[snapshot.appName, default: 0] == snapshot.generation
  }

  /// Begins a short encoder/DB lease. Returns false for stale or excluded work.
  static func begin(_ snapshot: RewindCaptureExclusionSnapshot) -> Bool {
    state.condition.lock()
    defer { state.condition.unlock() }
    guard isOwnerCurrent(snapshot),
      !state.excludedApps.contains(snapshot.appName),
      state.generations[snapshot.appName, default: 0] == snapshot.generation
    else { return false }
    state.inFlight[snapshot.appName, default: 0] += 1
    return true
  }

  static func end(_ snapshot: RewindCaptureExclusionSnapshot) {
    state.condition.lock()
    if let count = state.inFlight[snapshot.appName], count > 1 {
      state.inFlight[snapshot.appName] = count - 1
    } else {
      state.inFlight.removeValue(forKey: snapshot.appName)
    }
    state.condition.broadcast()
    state.condition.unlock()
  }

  /// Advances before purge work starts and waits only for a current encoder/DB
  /// lease. Any frame admitted before this call either finishes before exclusion
  /// returns (and is purged) or observes the new generation and is discarded.
  static func setExcluded(_ appName: String, excluded: Bool) {
    state.condition.lock()
    state.generations[appName, default: 0] &+= 1
    state.excludedApps =
      excluded ? state.excludedApps.union([appName]) : state.excludedApps.subtracting([appName])
    while (state.inFlight[appName] ?? 0) > 0 {
      state.condition.wait()
    }
    state.condition.unlock()
  }

  /// Seeds the in-memory state once during settings initialization.
  static func setInitialExcludedApps(_ apps: Set<String>) {
    state.condition.lock()
    state.excludedApps = apps
    state.condition.unlock()
  }
}

/// Retry journal for a stale frame whose video writer has already finalized by
/// the time exclusion rejects its database insert. The existing encoder
/// abandonment marker only covers an active writer; this small owner-scoped
/// journal keeps a finalized path retryable if deleting it fails transiently.
enum RewindExcludedVideoChunkCleanupJournal {
  private static let defaultsKey = "rewindPendingExcludedVideoChunkCleanups"

  private final class State: @unchecked Sendable {
    let lock = NSLock()
  }

  private static let state = State()

  static func enqueue(relativePath: String, ownerID: String) {
    let path = relativePath.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !path.isEmpty else { return }
    withLock {
      var pending = load()
      pending[ownerID, default: []].append(path)
      pending[ownerID] = Array(Set(pending[ownerID] ?? [])).sorted()
      save(pending)
    }
  }

  static func pending(ownerID: String) -> Set<String> {
    withLock { Set(load()[ownerID] ?? []) }
  }

  static func complete(relativePath: String, ownerID: String) {
    withLock {
      var pending = load()
      guard var ownerPending = pending[ownerID] else { return }
      ownerPending.removeAll { $0 == relativePath }
      if ownerPending.isEmpty {
        pending.removeValue(forKey: ownerID)
      } else {
        pending[ownerID] = ownerPending
      }
      save(pending)
    }
  }

  private static func withLock<T>(_ body: () -> T) -> T {
    state.lock.lock()
    defer { state.lock.unlock() }
    return body()
  }

  private static func load() -> [String: [String]] {
    guard let data = UserDefaults.standard.data(forKey: defaultsKey),
      let pending = try? JSONDecoder().decode([String: [String]].self, from: data)
    else { return [:] }
    return pending
  }

  private static func save(_ pending: [String: [String]]) {
    guard !pending.isEmpty,
      let data = try? JSONEncoder().encode(pending)
    else {
      UserDefaults.standard.removeObject(forKey: defaultsKey)
      return
    }
    UserDefaults.standard.set(data, forKey: defaultsKey)
  }
}
