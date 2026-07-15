import Foundation

@testable import Omi_Computer

/// Keeps process-wide runtime-owner authorization aligned with the defaults a
/// test exposes. Raw defaults restoration is insufficient after any production
/// path has captured an authorization snapshot: the authority deliberately
/// fails closed on that out-of-band owner mismatch and remains revoked for the
/// next test in the xctest process.
@MainActor
final class RuntimeOwnerAuthorityTestFixture: @unchecked Sendable {
  private let defaults: UserDefaults
  private let originalAuthOwner: String?
  private let originalAutomationOverride: String?
  private let originalAutomationBackup: String?

  init(defaults: UserDefaults = .standard) {
    self.defaults = defaults
    originalAuthOwner = defaults.string(forKey: .authUserId)
    originalAutomationOverride = defaults.string(forKey: .automationOwnerOverride)
    originalAutomationBackup = defaults.string(forKey: .automationOwnerABackup)
  }

  func establish(authOwnerID: String?, automationOverrideID: String? = nil) async {
    await Self.establish(
      defaults: defaults,
      authOwnerID: authOwnerID,
      automationOverrideID: automationOverrideID,
      automationBackupID: nil)
  }

  func restore() async {
    await Self.establish(
      defaults: defaults,
      authOwnerID: originalAuthOwner,
      automationOverrideID: originalAutomationOverride,
      automationBackupID: originalAutomationBackup)
  }

  private static func establish(
    defaults: UserDefaults,
    authOwnerID: String?,
    automationOverrideID: String?,
    automationBackupID: String?
  ) async {
    let finalOwner = normalized(automationOverrideID) ?? normalized(authOwnerID)
    let bootstrapOwner = finalOwner == "runtime-owner-test-bootstrap-a"
      ? "runtime-owner-test-bootstrap-b"
      : "runtime-owner-test-bootstrap-a"
    await transition(
      defaults: defaults,
      authOwnerID: bootstrapOwner,
      automationOverrideID: nil,
      automationBackupID: nil)
    await transition(
      defaults: defaults,
      authOwnerID: authOwnerID,
      automationOverrideID: automationOverrideID,
      automationBackupID: automationBackupID)
  }

  private static func transition(
    defaults: UserDefaults,
    authOwnerID: String?,
    automationOverrideID: String?,
    automationBackupID: String?
  ) async {
    let nextOwner = normalized(automationOverrideID) ?? normalized(authOwnerID)
    await RuntimeOwnerIdentity.performEffectiveOwnerTransition(
      defaults: defaults,
      allowAutomationOverride: true,
      plannedNextOwner: { _, _ in nextOwner },
      quiesceVoice: { _, _ in },
      revokeKernelOwner: { _, _ in },
      retargetLocalStorage: { _, _ in },
      ownerDidChange: {}
    ) { defaults in
      set(authOwnerID, forKey: .authUserId, defaults: defaults)
      set(automationOverrideID, forKey: .automationOwnerOverride, defaults: defaults)
      set(automationBackupID, forKey: .automationOwnerABackup, defaults: defaults)
    }
  }

  nonisolated private static func set(
    _ value: String?,
    forKey key: DefaultsKey,
    defaults: UserDefaults
  ) {
    if let value {
      defaults.set(value, forKey: key)
    } else {
      defaults.removeObject(forKey: key)
    }
  }

  nonisolated private static func normalized(_ value: String?) -> String? {
    guard let value else { return nil }
    let normalized = value.trimmingCharacters(in: .whitespacesAndNewlines)
    return normalized.isEmpty ? nil : normalized
  }
}
