import Foundation

/// Auth pins this store only after saving credentials. A running transport
/// reads the same store before choosing a contract or request origin.
public protocol SoftwarePlaneStoring: Sendable {
  func softwarePlaneSnapshot() -> SoftwarePlaneSnapshot
  func storeSoftwarePlane(_ plane: SoftwarePlane)
  /// Readers must not observe the new credentials with the preceding plane.
  func commitSoftwarePlane(_ plane: SoftwarePlane, persistSession: () throws -> Void) throws
}

public struct SoftwarePlaneSnapshot: Sendable, Equatable {
  public let storedPlane: String?
  public let revision: String
  public init(storedPlane: String?, revision: String) {
    self.storedPlane = storedPlane
    self.revision = revision
  }
}

extension SoftwarePlaneStoring {
  public func storedSoftwarePlane() -> String? { softwarePlaneSnapshot().storedPlane }
}

public final class UserDefaultsSoftwarePlaneStore: SoftwarePlaneStoring, @unchecked Sendable {
  private let defaults: UserDefaults
  private let lock = NSLock()
  private var revision = UUID().uuidString
  private var observed: String?

  public init(defaults: UserDefaults = .standard) {
    self.defaults = defaults
    self.observed = defaults.string(forKey: SOFTWARE_PLANE_DEFAULTS_KEY)
  }

  public func softwarePlaneSnapshot() -> SoftwarePlaneSnapshot {
    lock.withLock {
      let selected = defaults.string(forKey: SOFTWARE_PLANE_DEFAULTS_KEY)
      if selected != observed {
        revision = UUID().uuidString
        observed = selected
      }
      return SoftwarePlaneSnapshot(storedPlane: selected, revision: revision)
    }
  }

  public func storeSoftwarePlane(_ plane: SoftwarePlane) {
    lock.withLock { storeLocked(plane) }
  }

  public func commitSoftwarePlane(_ plane: SoftwarePlane, persistSession: () throws -> Void) throws
  {
    lock.lock()
    // A failed secure write also retires readers holding an old snapshot.
    defer {
      revision = UUID().uuidString
      lock.unlock()
    }
    try persistSession()
    storeLocked(plane)
  }

  private func storeLocked(_ plane: SoftwarePlane) {
    defaults.set(plane.rawValue, forKey: SOFTWARE_PLANE_DEFAULTS_KEY)
    observed = plane.rawValue
    revision = UUID().uuidString
  }
}
