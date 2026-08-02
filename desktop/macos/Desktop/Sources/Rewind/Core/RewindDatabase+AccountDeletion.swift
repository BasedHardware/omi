import Foundation
import OmiSupport

extension RewindDatabase {
  /// Apply the local-data half of the account-deletion acceptance boundary.
  ///
  /// Ordinary sign-out and requests that fail before the backend accepts a
  /// durable deletion intent pass `accepted == false` and preserve every file.
  /// Once accepted, the current owner directory is removed before credentials
  /// are cleared. The legacy shared Rewind artifacts are also removed for the
  /// non-isolated production profile so they cannot migrate into a later UID.
  func applyAcceptedAccountDeletionLocalDataPolicy(
    ownerID: String?,
    accepted: Bool,
    profileRoot: URL? = nil,
    legacyRoot: URL? = nil,
    includeLegacyStorage: Bool? = nil
  ) throws {
    guard accepted, let ownerID, !ownerID.isEmpty else { return }
    guard ownerID != ".", ownerID != "..", !ownerID.contains("/") else {
      throw RewindError.storageError("Invalid account owner for local-data deletion")
    }

    close()

    let fileManager = FileManager.default
    let resolvedProfileRoot = profileRoot ?? DesktopLocalProfile.applicationSupportURL()
    let ownerDirectory =
      resolvedProfileRoot
      .appendingPathComponent("users", isDirectory: true)
      .appendingPathComponent(ownerID, isDirectory: true)
    if fileManager.fileExists(atPath: ownerDirectory.path) {
      try fileManager.removeItem(at: ownerDirectory)
    }

    let shouldDeleteLegacy =
      includeLegacyStorage
      ?? Self.shouldMigrateLegacyStorage(isolatedStorage: DesktopLocalProfile.usesIsolatedStorage)
    guard shouldDeleteLegacy else { return }

    let resolvedLegacyRoot: URL
    if let legacyRoot {
      resolvedLegacyRoot = legacyRoot
    } else {
      guard
        let appSupport = fileManager.urls(
          for: .applicationSupportDirectory,
          in: .userDomainMask
        ).first
      else {
        throw RewindError.storageError("Application Support is unavailable for local-data deletion")
      }
      resolvedLegacyRoot = appSupport.appendingPathComponent("Omi", isDirectory: true)
    }
    for artifact in [
      "omi.db", "omi.db-wal", "omi.db-shm", ".omi_running",
      "Screenshots", "Videos", "backups",
    ] {
      let target = resolvedLegacyRoot.appendingPathComponent(artifact)
      if fileManager.fileExists(atPath: target.path) {
        try fileManager.removeItem(at: target)
      }
    }
    log("RewindDatabase: Removed accepted account-deletion local data")
  }
}
