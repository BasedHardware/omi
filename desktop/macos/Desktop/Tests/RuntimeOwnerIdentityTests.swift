import XCTest

@testable import Omi_Computer

private struct RuntimeOwnerTestDefaultsReference: @unchecked Sendable {
  let value: UserDefaults
}

private final class RuntimeOwnerChangeRecorder: @unchecked Sendable {
  private let lock = NSLock()
  private var notifications: [Notification] = []
  private var observedOwnerIDs: [String?] = []
  private var deliveryWasOnMainThread = true

  func record(_ notification: Notification, observedOwnerID: String?) {
    lock.withLock {
      notifications.append(notification)
      observedOwnerIDs.append(observedOwnerID)
      deliveryWasOnMainThread = deliveryWasOnMainThread && Thread.isMainThread
    }
  }

  func snapshot() -> (
    count: Int, deliveredOnMainThread: Bool, hasUserInfo: Bool, observedOwnerIDs: [String?]
  ) {
    lock.withLock {
      (
        notifications.count,
        deliveryWasOnMainThread,
        notifications.contains { $0.userInfo != nil },
        observedOwnerIDs
      )
    }
  }
}

private final class RuntimeOwnerTransitionOrderRecorder: @unchecked Sendable {
  private let lock = NSLock()
  private var events: [String] = []

  func append(_ event: String) { lock.withLock { events.append(event) } }
  func snapshot() -> [String] { lock.withLock { events } }
}

private actor RuntimeOwnerKernelRevokeGate {
  private let recorder: RuntimeOwnerTransitionOrderRecorder
  private var entered = false
  private var enteredWaiters: [CheckedContinuation<Void, Never>] = []
  private var releaseContinuation: CheckedContinuation<Void, Never>?
  private var observedPreviousOwner: String?
  private var observedCapability: RuntimeOwnerTransitionCleanupCapability?
  private var capabilityWasAuthorized = false

  init(recorder: RuntimeOwnerTransitionOrderRecorder) { self.recorder = recorder }

  func revoke(
    previousOwner: String,
    capability: RuntimeOwnerTransitionCleanupCapability
  ) async {
    observedPreviousOwner = previousOwner
    observedCapability = capability
    capabilityWasAuthorized = RuntimeOwnerIdentity.authorizesTransitionCleanup(
      capability,
      previousOwnerID: previousOwner)
    recorder.append("kernel_revoke_enter")
    entered = true
    enteredWaiters.forEach { $0.resume() }
    enteredWaiters.removeAll()
    await withCheckedContinuation { releaseContinuation = $0 }
    recorder.append("kernel_revoke_exit")
  }

  func waitUntilEntered() async {
    if entered { return }
    await withCheckedContinuation { enteredWaiters.append($0) }
  }

  func release() {
    releaseContinuation?.resume()
    releaseContinuation = nil
  }

  func observation() -> (
    previousOwner: String?,
    capability: RuntimeOwnerTransitionCleanupCapability?,
    wasAuthorized: Bool
  ) {
    (observedPreviousOwner, observedCapability, capabilityWasAuthorized)
  }
}

private actor RuntimeOwnerPhysicalEffectProbe {
  private let recorder: RuntimeOwnerTransitionOrderRecorder
  private var effectStarted = false
  private var effectStartWaiters: [CheckedContinuation<Void, Never>] = []
  private var drainStarted = false
  private var drainStartWaiters: [CheckedContinuation<Void, Never>] = []
  private var effectRelease: CheckedContinuation<Void, Never>?

  init(recorder: RuntimeOwnerTransitionOrderRecorder) { self.recorder = recorder }

  func runNonCooperativeEffect() async {
    recorder.append("effect_started")
    effectStarted = true
    effectStartWaiters.forEach { $0.resume() }
    effectStartWaiters.removeAll()
    await withCheckedContinuation { effectRelease = $0 }
    recorder.append(Task.isCancelled ? "effect_cancelled_and_finished" : "effect_finished")
  }

  func markDrainStarted() {
    recorder.append("drain_started")
    drainStarted = true
    drainStartWaiters.forEach { $0.resume() }
    drainStartWaiters.removeAll()
  }

  func waitUntilEffectStarted() async {
    if effectStarted { return }
    await withCheckedContinuation { effectStartWaiters.append($0) }
  }

  func waitUntilDrainStarted() async {
    if drainStarted { return }
    await withCheckedContinuation { drainStartWaiters.append($0) }
  }

  func releaseEffect() {
    effectRelease?.resume()
    effectRelease = nil
  }
}

/// Regression: gauntlet owner-swap must never rewrite Firebase `auth_userId`.
/// Doing so makes `AuthService.getIdToken()` clear tokens (uid mismatch) and
/// leaves a ghost signed-in session after restore.
final class RuntimeOwnerIdentityTests: XCTestCase {
  private var defaults: UserDefaults!
  private let suiteName = "RuntimeOwnerIdentityTests.\(UUID().uuidString)"

  func testAuthorizationAuthorityRejectsOutOfBandOwnerABA() throws {
    let authority = RuntimeOwnerAuthorizationAuthority()
    let original = try XCTUnwrap(
      authority.capture(ownerID: "owner-a", expectedOwnerID: "owner-a"))

    XCTAssertNil(authority.capture(ownerID: nil, expectedOwnerID: nil))
    XCTAssertNil(
      authority.capture(ownerID: "owner-a", expectedOwnerID: "owner-a"),
      "A -> nil -> A outside the transition boundary must not revive authority")
    XCTAssertFalse(authority.isCurrent(original, ownerID: "owner-a"))
  }

  func testAuthorizationAuthorityAcceptsLegitimateTransitionAndRejectsOldGeneration() throws {
    let authority = RuntimeOwnerAuthorizationAuthority()
    let ownerA = try XCTUnwrap(
      authority.capture(ownerID: "owner-a", expectedOwnerID: "owner-a"))

    authority.beginTransition()
    XCTAssertNil(authority.capture(ownerID: nil, expectedOwnerID: nil))
    authority.endTransition(ownerID: "owner-b")

    let ownerB = try XCTUnwrap(
      authority.capture(ownerID: "owner-b", expectedOwnerID: "owner-b"))
    XCTAssertFalse(authority.isCurrent(ownerA, ownerID: "owner-b"))
    XCTAssertTrue(authority.isCurrent(ownerB, ownerID: "owner-b"))
    XCTAssertNotEqual(ownerA, ownerB)
  }

  override func setUp() {
    super.setUp()
    defaults = UserDefaults(suiteName: suiteName)
  }

  override func tearDown() {
    defaults.removePersistentDomain(forName: suiteName)
    defaults = nil
    super.tearDown()
  }

  func testOverrideDoesNotRewriteAuthUserIdOrTokens() async {
    defaults.set("real-owner-a", forKey: .authUserId)
    defaults.set("id-token-a", forKey: .authIdToken)
    defaults.set("refresh-token-a", forKey: .authRefreshToken)
    defaults.set("real-owner-a", forKey: .authTokenUserId)
    defaults.set(true, forKey: .authIsSignedIn)

    await RuntimeOwnerIdentity.applyAutomationOwnerOverride("synthetic-owner-b", defaults: defaults)

    XCTAssertEqual(defaults.string(forKey: .authUserId), "real-owner-a")
    XCTAssertEqual(defaults.string(forKey: .authIdToken), "id-token-a")
    XCTAssertEqual(defaults.string(forKey: .authRefreshToken), "refresh-token-a")
    XCTAssertEqual(defaults.string(forKey: .authTokenUserId), "real-owner-a")
    XCTAssertTrue(defaults.bool(forKey: .authIsSignedIn))
    XCTAssertEqual(defaults.string(forKey: .automationOwnerOverride), "synthetic-owner-b")
    XCTAssertEqual(defaults.string(forKey: .automationOwnerABackup), "real-owner-a")
    XCTAssertEqual(
      RuntimeOwnerIdentity.currentOwnerId(defaults: defaults, allowAutomationOverride: true),
      "synthetic-owner-b"
    )
    XCTAssertEqual(
      RuntimeOwnerIdentity.currentOwnerId(defaults: defaults, allowAutomationOverride: false),
      "real-owner-a"
    )
  }

  func testClearOverrideRestoresKernelOwnerWithoutTouchingTokens() async {
    defaults.set("real-owner-a", forKey: .authUserId)
    defaults.set("id-token-a", forKey: .authIdToken)
    defaults.set("refresh-token-a", forKey: .authRefreshToken)
    await RuntimeOwnerIdentity.applyAutomationOwnerOverride("synthetic-owner-b", defaults: defaults)

    let result = await RuntimeOwnerIdentity.clearAutomationOwnerOverride(defaults: defaults)

    XCTAssertTrue(result.restored)
    XCTAssertEqual(result.ownerId, "real-owner-a")
    XCTAssertEqual(defaults.string(forKey: .authUserId), "real-owner-a")
    XCTAssertEqual(defaults.string(forKey: .authIdToken), "id-token-a")
    XCTAssertEqual(defaults.string(forKey: .authRefreshToken), "refresh-token-a")
    XCTAssertNil(defaults.string(forKey: .automationOwnerOverride))
    XCTAssertNil(defaults.string(forKey: .automationOwnerABackup))
    XCTAssertEqual(
      RuntimeOwnerIdentity.currentOwnerId(defaults: defaults, allowAutomationOverride: true),
      "real-owner-a"
    )
  }

  func testClearHealsLegacySyntheticAuthUserId() async {
    // Older builds wrote owner B into auth_userId and stashed owner A in backup.
    defaults.set("synthetic-owner-b", forKey: .authUserId)
    defaults.set("real-owner-a", forKey: .automationOwnerABackup)
    defaults.set("id-token-a", forKey: .authIdToken)

    let result = await RuntimeOwnerIdentity.clearAutomationOwnerOverride(defaults: defaults)

    XCTAssertTrue(result.restored)
    XCTAssertEqual(result.ownerId, "real-owner-a")
    XCTAssertEqual(defaults.string(forKey: .authUserId), "real-owner-a")
    XCTAssertEqual(defaults.string(forKey: .authIdToken), "id-token-a")
    XCTAssertNil(defaults.string(forKey: .automationOwnerABackup))
  }

  func testNestedOverridePreservesOriginalBackup() async {
    defaults.set("real-owner-a", forKey: .authUserId)
    await RuntimeOwnerIdentity.applyAutomationOwnerOverride("synthetic-owner-b", defaults: defaults)
    await RuntimeOwnerIdentity.applyAutomationOwnerOverride("synthetic-owner-c", defaults: defaults)

    XCTAssertEqual(defaults.string(forKey: .automationOwnerOverride), "synthetic-owner-c")
    XCTAssertEqual(defaults.string(forKey: .automationOwnerABackup), "real-owner-a")
    XCTAssertEqual(defaults.string(forKey: .authUserId), "real-owner-a")
  }

  func testEffectiveOwnerTransitionPostsOneContentFreeMainThreadNotification() async {
    defaults.set("real-owner-a", forKey: .authUserId)
    let observedDefaults = RuntimeOwnerTestDefaultsReference(value: defaults)
    let recorder = RuntimeOwnerChangeRecorder()
    let token = NotificationCenter.default.addObserver(
      forName: .runtimeOwnerDidChange,
      object: nil,
      queue: nil
    ) { notification in
      recorder.record(
        notification,
        observedOwnerID: RuntimeOwnerIdentity.currentOwnerId(
          defaults: observedDefaults.value,
          allowAutomationOverride: true))
    }
    defer { NotificationCenter.default.removeObserver(token) }

    await RuntimeOwnerIdentity.applyAutomationOwnerOverride("synthetic-owner-b", defaults: defaults)
    // Reapplying the same effective owner is not a transition.
    await RuntimeOwnerIdentity.applyAutomationOwnerOverride("synthetic-owner-b", defaults: defaults)

    let snapshot = recorder.snapshot()
    XCTAssertEqual(snapshot.count, 1)
    XCTAssertTrue(snapshot.deliveredOnMainThread)
    XCTAssertFalse(snapshot.hasUserInfo)
    XCTAssertEqual(snapshot.observedOwnerIDs.count, 1)
    XCTAssertNil(
      snapshot.observedOwnerIDs[0],
      "neither owner may be authorized while synchronous owner projections are clearing")
    XCTAssertEqual(
      RuntimeOwnerIdentity.currentOwnerId(
        defaults: defaults,
        allowAutomationOverride: true),
      "synthetic-owner-b")
  }

  func testClearDoesNotClobberAuthUserIdUpdatedDuringOverride() async {
    defaults.set("real-owner-a", forKey: .authUserId)
    defaults.set("id-token-a", forKey: .authIdToken)
    await RuntimeOwnerIdentity.applyAutomationOwnerOverride("synthetic-owner-b", defaults: defaults)
    // Mid-session sign-in updates the real auth uid while override is active.
    defaults.set("real-owner-c", forKey: .authUserId)
    defaults.set("id-token-c", forKey: .authIdToken)

    let result = await RuntimeOwnerIdentity.clearAutomationOwnerOverride(defaults: defaults)

    XCTAssertTrue(result.restored)
    XCTAssertEqual(defaults.string(forKey: .authUserId), "real-owner-c")
    XCTAssertEqual(defaults.string(forKey: .authIdToken), "id-token-c")
    XCTAssertNil(defaults.string(forKey: .automationOwnerOverride))
    XCTAssertNil(defaults.string(forKey: .automationOwnerABackup))
  }

  func testClearHealsWhenAuthUserIdStillEqualsSyntheticOverride() async {
    defaults.set("real-owner-a", forKey: .authUserId)
    await RuntimeOwnerIdentity.applyAutomationOwnerOverride("synthetic-owner-b", defaults: defaults)
    // Legacy path also wrote the synthetic owner into auth_userId.
    defaults.set("synthetic-owner-b", forKey: .authUserId)

    let result = await RuntimeOwnerIdentity.clearAutomationOwnerOverride(defaults: defaults)

    XCTAssertTrue(result.restored)
    XCTAssertEqual(result.ownerId, "real-owner-a")
    XCTAssertEqual(defaults.string(forKey: .authUserId), "real-owner-a")
  }

  func testKernelRevocationCompletesBeforeReplacementOwnerBecomesVisible() async {
    defaults.set("owner-a", forKey: .authUserId)
    let defaultsReference = RuntimeOwnerTestDefaultsReference(value: defaults)
    let recorder = RuntimeOwnerTransitionOrderRecorder()
    let gate = RuntimeOwnerKernelRevokeGate(recorder: recorder)

    let transition = Task {
      await RuntimeOwnerIdentity.performEffectiveOwnerTransition(
        defaults: defaultsReference.value,
        allowAutomationOverride: true,
        plannedNextOwner: { _, _ in "owner-b" },
        quiesceVoice: { _, _ in recorder.append("voice_quiesced") },
        revokeKernelOwner: { previousOwner, capability in
          await gate.revoke(previousOwner: previousOwner, capability: capability)
        },
        retargetLocalStorage: { _, _ in recorder.append("storage_retargeted") },
        ownerDidChange: { recorder.append("owner_notified") }
      ) { defaults in
        recorder.append("defaults_mutated")
        defaults.set("owner-b", forKey: .automationOwnerOverride)
      }
    }

    await gate.waitUntilEntered()
    XCTAssertEqual(defaults.string(forKey: .authUserId), "owner-a")
    XCTAssertNil(defaults.string(forKey: .automationOwnerOverride))
    XCTAssertNil(
      RuntimeOwnerIdentity.currentOwnerId(
        defaults: defaults,
        allowAutomationOverride: true),
      "public owner authority must stay revoked while the kernel barrier is suspended")
    let observation = await gate.observation()
    XCTAssertEqual(observation.previousOwner, "owner-a")
    XCTAssertTrue(observation.wasAuthorized)
    XCTAssertEqual(recorder.snapshot(), ["voice_quiesced", "kernel_revoke_enter"])

    await gate.release()
    await transition.value

    XCTAssertEqual(
      RuntimeOwnerIdentity.currentOwnerId(
        defaults: defaults,
        allowAutomationOverride: true),
      "owner-b")
    XCTAssertEqual(
      recorder.snapshot(),
      [
        "voice_quiesced", "kernel_revoke_enter", "kernel_revoke_exit",
        "defaults_mutated", "storage_retargeted", "owner_notified",
      ])
    if let capability = observation.capability {
      XCTAssertFalse(
        RuntimeOwnerIdentity.authorizesTransitionCleanup(
          capability,
          previousOwnerID: "owner-a"),
        "cleanup capability must be revoked once owner B becomes visible")
    } else {
      XCTFail("kernel revoke did not receive a cleanup capability")
    }
  }

  func testReplacementOwnerWaitsForNonCooperativePhysicalEffectToDrain() async {
    defaults.set("owner-a", forKey: .authUserId)
    let defaultsReference = RuntimeOwnerTestDefaultsReference(value: defaults)
    let recorder = RuntimeOwnerTransitionOrderRecorder()
    let probe = RuntimeOwnerPhysicalEffectProbe(recorder: recorder)
    let physicalEffect = Task { await probe.runNonCooperativeEffect() }
    await probe.waitUntilEffectStarted()

    let transition = Task {
      await RuntimeOwnerIdentity.performEffectiveOwnerTransition(
        defaults: defaultsReference.value,
        allowAutomationOverride: true,
        plannedNextOwner: { _, _ in "owner-b" },
        quiesceVoice: { _, _ in recorder.append("voice_quiesced") },
        revokeKernelOwner: { _, _ in
          await probe.markDrainStarted()
          await AgentRuntimeProcess.cancelAndAwaitPhysicalExecutionTasks([physicalEffect])
          recorder.append("drain_finished")
        },
        retargetLocalStorage: { _, _ in recorder.append("storage_retargeted") },
        ownerDidChange: { recorder.append("owner_notified") }
      ) { defaults in
        recorder.append("defaults_mutated")
        defaults.set("owner-b", forKey: .automationOwnerOverride)
      }
    }

    await probe.waitUntilDrainStarted()
    XCTAssertEqual(defaults.string(forKey: .authUserId), "owner-a")
    XCTAssertNil(defaults.string(forKey: .automationOwnerOverride))
    XCTAssertNil(
      RuntimeOwnerIdentity.currentOwnerId(
        defaults: defaults,
        allowAutomationOverride: true))
    XCTAssertEqual(
      recorder.snapshot(),
      ["effect_started", "voice_quiesced", "drain_started"])

    // `markDrainStarted()` crosses an actor boundary immediately before the
    // drain helper requests cancellation. Wait for that request explicitly so
    // releasing the non-cooperative effect cannot race ahead of `cancel()`.
    for _ in 0..<10_000 where !physicalEffect.isCancelled {
      await Task.yield()
    }
    XCTAssertTrue(physicalEffect.isCancelled)

    await probe.releaseEffect()
    await transition.value

    XCTAssertEqual(
      RuntimeOwnerIdentity.currentOwnerId(
        defaults: defaults,
        allowAutomationOverride: true), "owner-b")
    XCTAssertEqual(
      recorder.snapshot(),
      [
        "effect_started", "voice_quiesced", "drain_started",
        "effect_cancelled_and_finished", "drain_finished", "defaults_mutated",
        "storage_retargeted", "owner_notified",
      ])
  }

  func testSwapPathSourceNeverWritesAuthUserId() throws {
    let desktopDir = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
    let provider = try String(
      contentsOf: desktopDir.appendingPathComponent("Sources/Providers/ChatProvider.swift"),
      encoding: .utf8
    )
    let identity = try String(
      contentsOf: desktopDir.appendingPathComponent("Sources/Chat/RuntimeOwnerIdentity.swift"),
      encoding: .utf8
    )

    XCTAssertTrue(provider.contains("RuntimeOwnerIdentity.applyAutomationOwnerOverride"))
    XCTAssertTrue(provider.contains("RuntimeOwnerIdentity.clearAutomationOwnerOverride"))
    XCTAssertFalse(
      provider.contains("UserDefaults.standard.set(trimmedOwnerB, forKey:"),
      "swap must not write synthetic owner into auth defaults"
    )
    XCTAssertTrue(identity.contains("automationOwnerOverride"))
    XCTAssertFalse(
      identity.contains("defaults.set(trimmed, forKey: .authUserId)"),
      "override helper must never rewrite auth_userId"
    )

    let defaultsKey = try String(
      contentsOf: desktopDir.appendingPathComponent("Sources/DefaultsKey.swift"),
      encoding: .utf8
    )
    XCTAssertTrue(defaultsKey.contains("automationOwnerOverride = \"automation_owner_override\""))
    XCTAssertTrue(
      defaultsKey.contains("automationOwnerABackup = \"automation_swap_owner_a_backup\""))
  }
}
