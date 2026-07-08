import Foundation

/// Resolves the owner id used by kernel / continuity surfaces.
///
/// Non-production automation may temporarily override the owner for isolation
/// tests without rewriting Firebase `auth_userId`. Writing a synthetic uid into
/// `auth_userId` makes `AuthService.getIdToken()` treat real tokens as stale and
/// call `clearTokens()`, leaving a ghost signed-in session.
enum RuntimeOwnerIdentity {
  /// Active kernel owner: automation override (non-prod) or real auth uid.
  ///
  /// - Parameter allowAutomationOverride: Defaults to `AppBuild.isNonProduction`.
  ///   Tests inject `true` so hermetic suites do not depend on the XCTest host
  ///   bundle id.
  static func currentOwnerId(
    defaults: UserDefaults = .standard,
    allowAutomationOverride: Bool = AppBuild.isNonProduction
  ) -> String? {
    if allowAutomationOverride,
      let override = defaults.string(forKey: .automationOwnerOverride)?
        .trimmingCharacters(in: .whitespacesAndNewlines),
      !override.isEmpty
    {
      return override
    }
    guard let value = defaults.string(forKey: .authUserId)?
      .trimmingCharacters(in: .whitespacesAndNewlines),
      !value.isEmpty
    else {
      return nil
    }
    return value
  }

  /// Apply a synthetic owner for automation without mutating Firebase credentials.
  @discardableResult
  static func applyAutomationOwnerOverride(
    _ ownerBId: String,
    defaults: UserDefaults = .standard
  ) -> String? {
    let trimmed = ownerBId.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return nil }
    let ownerA = defaults.string(forKey: .authUserId)?
      .trimmingCharacters(in: .whitespacesAndNewlines)
    defaults.set(trimmed, forKey: .automationOwnerOverride)
    // Preserve an existing backup (nested/re-entrant swap). Only seed when absent
    // so a second override cannot replace the real Firebase uid with owner B.
    let existingBackup = defaults.string(forKey: .automationOwnerABackup)?
      .trimmingCharacters(in: .whitespacesAndNewlines)
    if existingBackup == nil || existingBackup?.isEmpty == true,
      let ownerA, !ownerA.isEmpty, ownerA != trimmed
    {
      defaults.set(ownerA, forKey: .automationOwnerABackup)
    }
    return ownerA
  }

  /// Clear the automation override and heal a legacy synthetic auth_userId if needed.
  @discardableResult
  static func clearAutomationOwnerOverride(
    defaults: UserDefaults = .standard
  ) -> (restored: Bool, ownerId: String?) {
    let hadOverride = defaults.string(forKey: .automationOwnerOverride)?.isEmpty == false
    let backup = defaults.string(forKey: .automationOwnerABackup)?
      .trimmingCharacters(in: .whitespacesAndNewlines)
    defaults.removeObject(forKey: .automationOwnerOverride)

    if let backup, !backup.isEmpty {
      let currentAuthUserId = defaults.string(forKey: .authUserId)
      if currentAuthUserId != backup {
        // Heal legacy swap that overwrote auth_userId with a synthetic owner.
        defaults.set(backup, forKey: .authUserId)
      }
      defaults.removeObject(forKey: .automationOwnerABackup)
      return (true, backup)
    }

    if hadOverride {
      return (true, defaults.string(forKey: .authUserId))
    }
    return (false, nil)
  }
}
