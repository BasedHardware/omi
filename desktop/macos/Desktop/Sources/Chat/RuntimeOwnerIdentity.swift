import Foundation

private struct RuntimeOwnerDefaultsReference: @unchecked Sendable {
  let value: UserDefaults
}

/// Immutable authority captured by delayed owner-bound work. Owner identity
/// alone is insufficient because signing out and back into the same uid must
/// still revoke continuations from the previous authenticated session.
struct RuntimeOwnerAuthorizationSnapshot: Equatable, Sendable {
  let ownerID: String
  fileprivate let generation: UInt64
}

final class RuntimeOwnerAuthorizationAuthority: @unchecked Sendable {
  static let shared = RuntimeOwnerAuthorizationAuthority()

  private let lock = NSLock()
  private var generation: UInt64 = 0
  private var ownerID: String?
  private var revoked = false
  private var bootstrapped = false

  func beginTransition() {
    lock.withLock {
      generation &+= 1
      ownerID = nil
      revoked = true
    }
  }

  func endTransition(ownerID: String?) {
    let normalized = Self.normalize(ownerID)
    lock.withLock {
      self.ownerID = normalized
      revoked = false
      bootstrapped = true
    }
  }

  func capture(ownerID: String?, expectedOwnerID: String?) -> RuntimeOwnerAuthorizationSnapshot? {
    let normalized = Self.normalize(ownerID)
    let normalizedExpectedOwnerID = Self.normalize(expectedOwnerID)
    return lock.withLock {
      if !bootstrapped {
        guard let normalized, !revoked else { return nil }
        // Durable auth may predate construction of this in-memory authority.
        // This is the only path allowed to adopt an owner without a transition.
        self.ownerID = normalized
        bootstrapped = true
      } else if self.ownerID != normalized {
        revokeUnexpectedOwnerMismatch()
        return nil
      }
      guard let normalized, !revoked else { return nil }
      if expectedOwnerID != nil, normalizedExpectedOwnerID != normalized { return nil }
      return RuntimeOwnerAuthorizationSnapshot(ownerID: normalized, generation: generation)
    }
  }

  func isCurrent(
    _ snapshot: RuntimeOwnerAuthorizationSnapshot,
    ownerID: String?
  ) -> Bool {
    let normalized = Self.normalize(ownerID)
    return lock.withLock {
      guard bootstrapped else { return false }
      guard self.ownerID == normalized else {
        revokeUnexpectedOwnerMismatch()
        return false
      }
      return !revoked && normalized == snapshot.ownerID && generation == snapshot.generation
    }
  }

  /// Durable auth changed without crossing the exclusive transition boundary.
  /// Advance and revoke once, then stay fail-closed until a legitimate
  /// beginTransition/endTransition pair establishes the next generation.
  private func revokeUnexpectedOwnerMismatch() {
    if !revoked { generation &+= 1 }
    ownerID = nil
    revoked = true
  }

  private static func normalize(_ ownerID: String?) -> String? {
    guard let ownerID else { return nil }
    let normalized = ownerID.trimmingCharacters(in: .whitespacesAndNewlines)
    return normalized.isEmpty ? nil : normalized
  }
}

/// Unforgeable authority for the one cleanup phase that precedes an effective
/// owner mutation. It can terminalize work for exactly the captured previous
/// owner and exactly one transition generation; it cannot authorize new work.
struct RuntimeOwnerTransitionCleanupCapability: Equatable, Sendable {
  let previousOwnerID: String?
  fileprivate let generation: UInt64
  fileprivate let nonce: UUID

  fileprivate init(previousOwnerID: String?, generation: UInt64, nonce: UUID) {
    self.previousOwnerID = previousOwnerID
    self.generation = generation
    self.nonce = nonce
  }
}

private final class RuntimeOwnerTransitionCleanupAuthority: @unchecked Sendable {
  static let shared = RuntimeOwnerTransitionCleanupAuthority()

  private let lock = NSLock()
  private var generation: UInt64 = 0
  private var activeCapability: RuntimeOwnerTransitionCleanupCapability?

  func begin(previousOwnerID: String?) -> RuntimeOwnerTransitionCleanupCapability {
    lock.withLock {
      precondition(activeCapability == nil, "Effective-owner cleanup capability overlapped")
      generation &+= 1
      let capability = RuntimeOwnerTransitionCleanupCapability(
        previousOwnerID: previousOwnerID,
        generation: generation,
        nonce: UUID())
      activeCapability = capability
      return capability
    }
  }

  func end(_ capability: RuntimeOwnerTransitionCleanupCapability) {
    lock.withLock {
      guard activeCapability == capability else {
        assertionFailure("Effective-owner cleanup capability generation mismatched")
        return
      }
      activeCapability = nil
    }
  }

  func activeCapability(forPreviousOwnerID ownerID: String) -> RuntimeOwnerTransitionCleanupCapability? {
    lock.withLock {
      guard let activeCapability, activeCapability.previousOwnerID == ownerID else { return nil }
      return activeCapability
    }
  }

  func authorizes(
    _ capability: RuntimeOwnerTransitionCleanupCapability,
    previousOwnerID: String?
  ) -> Bool {
    lock.withLock {
      activeCapability == capability && capability.previousOwnerID == previousOwnerID
    }
  }
}

private final class RuntimeOwnerTransitionCleanupCapabilitySlot: @unchecked Sendable {
  private let lock = NSLock()
  private var capability: RuntimeOwnerTransitionCleanupCapability?

  func store(_ capability: RuntimeOwnerTransitionCleanupCapability) {
    lock.withLock { self.capability = capability }
  }

  func load() -> RuntimeOwnerTransitionCleanupCapability? {
    lock.withLock { capability }
  }

  func take() -> RuntimeOwnerTransitionCleanupCapability? {
    lock.withLock {
      defer { capability = nil }
      return capability
    }
  }
}

private final class EffectiveOwnerAuthorizationRevocation: @unchecked Sendable {
  static let shared = EffectiveOwnerAuthorizationRevocation()

  private let lock = NSLock()
  private var active = false

  func begin() { lock.withLock { active = true } }
  func end() { lock.withLock { active = false } }
  var isActive: Bool { lock.withLock { active } }
}

extension Notification.Name {
  /// Effective owner changed (sign-in, sign-out, account switch, or an
  /// automation override). Carries no owner id or other user content.
  static let runtimeOwnerDidChange = Notification.Name("com.omi.desktop.runtimeOwnerDidChange")
}

/// Resolves the owner id used by kernel / continuity surfaces.
///
/// Non-production automation may temporarily override the owner for isolation
/// tests without rewriting Firebase `auth_userId`. Writing a synthetic uid into
/// `auth_userId` makes `AuthService.getIdToken()` treat real tokens as stale and
/// call `clearTokens()`, leaving a ghost signed-in session.
enum RuntimeOwnerIdentity {
  static var effectiveOwnerTransitionInProgress: Bool {
    EffectiveOwnerAuthorizationRevocation.shared.isActive
  }

  /// Returns the cleanup-only capability for an already-running physical or
  /// kernel effect owned by `ownerID`. New work must never consult this seam.
  static func transitionCleanupCapability(
    forPreviousOwnerID ownerID: String
  ) -> RuntimeOwnerTransitionCleanupCapability? {
    RuntimeOwnerTransitionCleanupAuthority.shared.activeCapability(
      forPreviousOwnerID: ownerID)
  }

  static func authorizesTransitionCleanup(
    _ capability: RuntimeOwnerTransitionCleanupCapability,
    previousOwnerID: String?
  ) -> Bool {
    RuntimeOwnerTransitionCleanupAuthority.shared.authorizes(
      capability,
      previousOwnerID: previousOwnerID)
  }

  /// Central production boundary for every mutation that can change the
  /// effective runtime owner. The notification is delivered on MainActor while
  /// the exclusive transition reservation is still held, so owner-derived
  /// caches purge before work for the new owner can acquire a commit lease.
  static func performEffectiveOwnerTransition<T: Sendable>(
    defaults: UserDefaults = .standard,
    allowAutomationOverride: Bool = AppBuild.isNonProduction,
    plannedNextOwner:
      @escaping @Sendable (
        _ defaults: UserDefaults, _ previousOwner: String?
      ) -> String?,
    quiesceVoice:
      @escaping @Sendable (
        _ previousOwner: String?, _ cleanupCapability: RuntimeOwnerTransitionCleanupCapability
      ) async -> Void = { previousOwner, cleanupCapability in
        await PushToTalkManager.shared.quiesceForEffectiveOwnerTransition(
          previousOwnerID: previousOwner,
          cleanupCapability: cleanupCapability)
      },
    revokeKernelOwner: (
      @Sendable (
        _ previousOwner: String, _ cleanupCapability: RuntimeOwnerTransitionCleanupCapability
      ) async -> Void
    )? = nil,
    retargetLocalStorage:
      @escaping @Sendable (
        _ previousOwner: String?, _ nextOwner: String?
      ) async -> Void = { previousOwner, nextOwner in
        await RuntimeOwnerIdentity.retargetOwnerBoundLocalStorage(
          previousOwner: previousOwner,
          nextOwner: nextOwner)
      },
    ownerDidChange: @escaping @Sendable () async -> Void = {
      await MainActor.run {
        NotificationCenter.default.post(name: .runtimeOwnerDidChange, object: nil)
      }
    },
    _ transition: @escaping @Sendable (UserDefaults) async throws -> T
  ) async rethrows -> T {
    let defaultsReference = RuntimeOwnerDefaultsReference(value: defaults)
    let cleanupCapabilitySlot = RuntimeOwnerTransitionCleanupCapabilitySlot()
    return try await EffectiveOwnerTransitionFence.shared.performEffectiveOwnerTransition(
      currentOwner: {
        persistedOwnerId(
          defaults: defaultsReference.value,
          allowAutomationOverride: allowAutomationOverride)
      },
      plannedNextOwner: { previousOwner in
        plannedNextOwner(defaultsReference.value, previousOwner)
      },
      beginAuthorizationRevocation: { previousOwner in
        // Issue the exact previous-owner cleanup capability before public owner
        // resolution is revoked. Existing terminalization tasks can capture it
        // without ever regaining general owner authority.
        cleanupCapabilitySlot.store(
          RuntimeOwnerTransitionCleanupAuthority.shared.begin(
            previousOwnerID: previousOwner))
        RuntimeOwnerAuthorizationAuthority.shared.beginTransition()
        EffectiveOwnerAuthorizationRevocation.shared.begin()
      },
      endAuthorizationRevocation: {
        if let cleanupCapability = cleanupCapabilitySlot.take() {
          RuntimeOwnerTransitionCleanupAuthority.shared.end(cleanupCapability)
        } else {
          assertionFailure("Effective-owner cleanup capability was not installed")
        }
        RuntimeOwnerAuthorizationAuthority.shared.endTransition(
          ownerID: persistedOwnerId(
            defaults: defaultsReference.value,
            allowAutomationOverride: allowAutomationOverride))
        EffectiveOwnerAuthorizationRevocation.shared.end()
      },
      quiescePreviousOwner: { previousOwner, _ in
        guard let cleanupCapability = cleanupCapabilitySlot.load(),
          RuntimeOwnerTransitionCleanupAuthority.shared.authorizes(
            cleanupCapability,
            previousOwnerID: previousOwner)
        else {
          assertionFailure("Effective-owner cleanup capability was revoked before quiescence")
          return
        }
        await quiesceVoice(previousOwner, cleanupCapability)
        guard let previousOwner else { return }
        if let revokeKernelOwner {
          await revokeKernelOwner(previousOwner, cleanupCapability)
        } else if defaultsReference.value === UserDefaults.standard {
          await AgentRuntimeProcess.shared.revokeOwnerRuntime(
            previousOwnerID: previousOwner,
            cleanupCapability: cleanupCapability)
        }
      },
      transition: {
        try await transition(defaultsReference.value)
      },
      retargetLocalStorage: retargetLocalStorage,
      ownerDidChange: ownerDidChange)
  }

  /// Capture the current owner plus the authenticated-session generation.
  /// Returns nil during a transition or when the expected owner is stale.
  nonisolated static func captureAuthorizationSnapshot(
    expectedOwnerID: String? = nil
  ) -> RuntimeOwnerAuthorizationSnapshot? {
    RuntimeOwnerAuthorizationAuthority.shared.capture(
      ownerID: currentOwnerId(),
      expectedOwnerID: expectedOwnerID)
  }

  /// Revalidate immediately before every delayed mutation and after every await
  /// that precedes UI/default/notification publication.
  nonisolated static func isAuthorizationCurrent(
    _ snapshot: RuntimeOwnerAuthorizationSnapshot
  ) -> Bool {
    RuntimeOwnerAuthorizationAuthority.shared.isCurrent(
      snapshot,
      ownerID: currentOwnerId())
  }

  private static func retargetOwnerBoundLocalStorage(
    previousOwner: String?,
    nextOwner: String?
  ) async {
    guard previousOwner != nextOwner else {
      await RewindDatabase.shared.retargetEffectiveOwner(to: nextOwner)
      return
    }
    // These actors retain pools, directories, encoders, or owner-derived
    // values. Purge them while the transition reservation is still held so
    // automation swaps and every auth path share the same hard boundary.
    await AgentSyncService.shared.stop(flushPendingChanges: false)
    // Wait for an active file scan to leave its actor before closing the pool
    // it captured. New-owner mutations remain parked by the fence.
    await FileIndexerService.shared.invalidateCache()
    await RewindIndexer.shared.reset()
    await RewindStorage.shared.reset()
    await RewindDatabase.shared.retargetEffectiveOwner(to: nextOwner)
    await TranscriptionStorage.shared.invalidateCache()
    await MemoryStorage.shared.invalidateCache()
    await ActionItemStorage.shared.invalidateCache()
    await ProactiveStorage.shared.invalidateCache()
    await NoteStorage.shared.invalidateCache()
    await AIUserProfileService.shared.invalidateCache()
    await StagedTaskStorage.shared.invalidateCache()
    await GoalStorage.shared.invalidateCache()
    await TaskChatMessageStorage.shared.invalidateCache()
    await KnowledgeGraphStorage.shared.invalidateCache()
    await MainActor.run {
      FloatingBarUsageLimiter.shared.reset()
    }
  }

  /// Active kernel owner: automation override (non-prod) or real auth uid.
  /// Returns nil during the exclusive A→B transition so neither account can
  /// authorize work before physical resources and owner projections are clear.
  ///
  /// - Parameter allowAutomationOverride: Defaults to `AppBuild.isNonProduction`.
  ///   Tests inject `true` so hermetic suites do not depend on the XCTest host
  ///   bundle id.
  static func currentOwnerId(
    defaults: UserDefaults = .standard,
    allowAutomationOverride: Bool = AppBuild.isNonProduction
  ) -> String? {
    guard !effectiveOwnerTransitionInProgress else { return nil }
    return persistedOwnerId(
      defaults: defaults,
      allowAutomationOverride: allowAutomationOverride)
  }

  private static func persistedOwnerId(
    defaults: UserDefaults,
    allowAutomationOverride: Bool
  ) -> String? {
    if allowAutomationOverride,
      let override = defaults.string(forKey: .automationOwnerOverride)?
        .trimmingCharacters(in: .whitespacesAndNewlines),
      !override.isEmpty
    {
      return override
    }
    guard
      let value = defaults.string(forKey: .authUserId)?
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
  ) async -> String? {
    let trimmed = ownerBId.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return nil }
    return await performEffectiveOwnerTransition(
      defaults: defaults,
      allowAutomationOverride: true,
      plannedNextOwner: { _, _ in trimmed }
    ) { defaults in
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
  }

  /// Installs an automation owner only if the owner is still absent after this
  /// request has acquired the serialized effective-owner transition fence.
  /// A preflight outside that fence could otherwise overwrite a real owner
  /// that signed in while a reset was queued.
  static func applyAutomationOwnerOverrideIfMissing(
    _ ownerID: String,
    defaults: UserDefaults = .standard
  ) async -> Bool {
    let trimmed = ownerID.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return false }
    return await performEffectiveOwnerTransition(
      defaults: defaults,
      allowAutomationOverride: true,
      plannedNextOwner: { _, previousOwner in previousOwner ?? trimmed }
    ) { defaults in
      guard persistedOwnerId(defaults: defaults, allowAutomationOverride: true) == nil else {
        return false
      }
      defaults.set(trimmed, forKey: .automationOwnerOverride)
      return true
    }
  }

  /// Temporarily establishes a non-production owner only when no effective
  /// owner exists. Harness reset operations still execute through the normal
  /// owner-scoped kernel boundary; they do not bypass it because a faulted
  /// auth endpoint left the bundle in auth recovery.
  static func withAutomationOwnerIfMissing<Result: Sendable>(
    _ ownerID: String,
    defaults: UserDefaults = .standard,
    operation: @MainActor () async throws -> Result
  ) async rethrows -> Result {
    let normalizedOwnerID = ownerID.trimmingCharacters(in: .whitespacesAndNewlines)
    precondition(!normalizedOwnerID.isEmpty, "automation owner must not be empty")
    let installedTemporaryOwner = await applyAutomationOwnerOverrideIfMissing(
      normalizedOwnerID,
      defaults: defaults)

    do {
      let result = try await operation()
      if installedTemporaryOwner {
        _ = await clearAutomationOwnerOverride(defaults: defaults)
      }
      return result
    } catch {
      if installedTemporaryOwner {
        _ = await clearAutomationOwnerOverride(defaults: defaults)
      }
      throw error
    }
  }

  /// Clear the automation override and heal a legacy synthetic auth_userId if needed.
  @discardableResult
  static func clearAutomationOwnerOverride(
    defaults: UserDefaults = .standard
  ) async -> (restored: Bool, ownerId: String?) {
    await performEffectiveOwnerTransition(
      defaults: defaults,
      allowAutomationOverride: true,
      plannedNextOwner: { defaults, previousOwner in
        plannedOwnerAfterClearingAutomationOverride(
          defaults: defaults,
          previousOwner: previousOwner)
      }
    ) { defaults in
      let override = defaults.string(forKey: .automationOwnerOverride)?
        .trimmingCharacters(in: .whitespacesAndNewlines)
      let hadOverride = !(override?.isEmpty ?? true)
      let backup = defaults.string(forKey: .automationOwnerABackup)?
        .trimmingCharacters(in: .whitespacesAndNewlines)
      defaults.removeObject(forKey: .automationOwnerOverride)

      if let backup, !backup.isEmpty {
        let currentAuthUserId = defaults.string(forKey: .authUserId)?
          .trimmingCharacters(in: .whitespacesAndNewlines)
        // Only rewrite auth_userId when it still looks like a synthetic overwrite
        // (empty, equals the override we cleared, or legacy backup-only heal).
        // Never clobber a legitimately updated auth uid from a mid-session sign-in.
        let shouldHealAuthUserId =
          currentAuthUserId == nil
          || currentAuthUserId?.isEmpty == true
          || (hadOverride && currentAuthUserId == override)
          || (!hadOverride && currentAuthUserId != backup)
        if shouldHealAuthUserId {
          defaults.set(backup, forKey: .authUserId)
        }
        defaults.removeObject(forKey: .automationOwnerABackup)
        return (true, defaults.string(forKey: .authUserId) ?? backup)
      }

      if hadOverride {
        return (true, defaults.string(forKey: .authUserId))
      }
      return (false, nil)
    }
  }

  private static func plannedOwnerAfterClearingAutomationOverride(
    defaults: UserDefaults,
    previousOwner: String?
  ) -> String? {
    let override = defaults.string(forKey: .automationOwnerOverride)?
      .trimmingCharacters(in: .whitespacesAndNewlines)
    let hadOverride = !(override?.isEmpty ?? true)
    let backup = defaults.string(forKey: .automationOwnerABackup)?
      .trimmingCharacters(in: .whitespacesAndNewlines)
    let currentAuthUserId = defaults.string(forKey: .authUserId)?
      .trimmingCharacters(in: .whitespacesAndNewlines)

    if let backup, !backup.isEmpty {
      let shouldHealAuthUserId =
        currentAuthUserId == nil
        || currentAuthUserId?.isEmpty == true
        || (hadOverride && currentAuthUserId == override)
        || (!hadOverride && currentAuthUserId != backup)
      return shouldHealAuthUserId ? backup : currentAuthUserId
    }
    return hadOverride ? currentAuthUserId : previousOwner
  }
}
