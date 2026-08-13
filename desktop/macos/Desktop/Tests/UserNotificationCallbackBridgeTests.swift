@preconcurrency import UserNotifications
import XCTest

@testable import Omi_Computer

final class UserNotificationCallbackBridgeTests: XCTestCase {
  func testVisibleNotificationSurfaceRequiresGrantAndBannerStyle() {
    XCTAssertTrue(
      NotificationPermissionPolicy.hasVisibleAlertSurface(
        status: .authorized,
        alertStyle: .banner))
    XCTAssertTrue(
      NotificationPermissionPolicy.hasVisibleAlertSurface(
        status: .provisional,
        alertStyle: .alert))
    XCTAssertFalse(
      NotificationPermissionPolicy.hasVisibleAlertSurface(
        status: .denied,
        alertStyle: .banner))
    XCTAssertFalse(
      NotificationPermissionPolicy.hasVisibleAlertSurface(
        status: .authorized,
        alertStyle: .none))
  }

  @MainActor
  func testNotificationSettingsSyncJournalOnlyClearsMatchingRevision() throws {
    let suiteName = "UserNotificationCallbackBridgeTests.\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
    defer { defaults.removePersistentDomain(forName: suiteName) }

    let first = NotificationService.beginNotificationSettingsSync(defaults: defaults)
    let second = NotificationService.beginNotificationSettingsSync(defaults: defaults)
    XCTAssertTrue(NotificationService.hasPendingNotificationSettingsSync(defaults: defaults))

    NotificationService.completeNotificationSettingsSync(revision: first, defaults: defaults)
    XCTAssertTrue(
      NotificationService.hasPendingNotificationSettingsSync(defaults: defaults),
      "an older PATCH must not clear a newer unsynced mutation")

    NotificationService.completeNotificationSettingsSync(revision: second, defaults: defaults)
    XCTAssertFalse(NotificationService.hasPendingNotificationSettingsSync(defaults: defaults))
  }

  @MainActor
  func testNotificationSettingsAccessorsPreserveCompleteDesiredStateAcrossPartialMutations() throws {
    let suiteName = "UserNotificationCallbackBridgeTests.\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
    defer { defaults.removePersistentDomain(forName: suiteName) }

    defaults.set(false, forKey: NotificationService.masterEnabledDefaultsKey)
    defaults.set(5, forKey: NotificationService.frequencyDefaultsKey)

    XCTAssertFalse(NotificationService.areNotificationsEnabled(defaults: defaults))
    XCTAssertEqual(NotificationService.currentFrequencyLevel(defaults: defaults), 5)
  }

  @MainActor
  func testNotificationHydrationPreservesNewerOrPreviouslyPendingLocalState() {
    XCTAssertFalse(
      NotificationService.shouldPreserveLocalNotificationSettings(
        revisionAtLoadStart: 4,
        currentRevision: 4,
        pendingAtLoadStart: false,
        pendingNow: false))
    XCTAssertTrue(
      NotificationService.shouldPreserveLocalNotificationSettings(
        revisionAtLoadStart: 4,
        currentRevision: 5,
        pendingAtLoadStart: false,
        pendingNow: false),
      "a mutation racing the GET must win even if its PATCH already completed")
    XCTAssertTrue(
      NotificationService.shouldPreserveLocalNotificationSettings(
        revisionAtLoadStart: 4,
        currentRevision: 4,
        pendingAtLoadStart: true,
        pendingNow: false),
      "a retry that completed while GET was in flight must not let stale hydration win")
  }

  func testNotificationPermissionPolicyUsesPromptOnlyForUndeterminedStatus() {
    XCTAssertEqual(
      NotificationPermissionPolicy.enableAction(for: .notDetermined), .requestSystemPrompt)
    XCTAssertEqual(NotificationPermissionPolicy.enableAction(for: .denied), .openSystemSettings)
    XCTAssertEqual(NotificationPermissionPolicy.enableAction(for: .authorized), .refresh)
    XCTAssertEqual(NotificationPermissionPolicy.enableAction(for: .provisional), .refresh)
  }

  func testNotificationPermissionPolicyTreatsAllDeliverableStatusesAsGranted() {
    XCTAssertFalse(NotificationPermissionPolicy.isGranted(.notDetermined))
    XCTAssertFalse(NotificationPermissionPolicy.isGranted(.denied))
    XCTAssertTrue(NotificationPermissionPolicy.isGranted(.authorized))
    XCTAssertTrue(NotificationPermissionPolicy.isGranted(.provisional))
  }

  func testDefaultNotificationSettingsHandoffMovesOffMainCallbackToMainActorInRelease() async {
    let snapshot = UserNotificationSettingsSnapshot(
      authorizationStatus: .notDetermined,
      alertStyle: .none,
      soundSetting: .disabled,
      badgeSetting: .disabled
    )
    let result = await withCheckedContinuation { continuation in
      UserNotificationCallbackBridge.notificationSettings(
        query: { completion in
          DispatchQueue.global(qos: .userInitiated).async {
            completion(snapshot)
          }
        },
        handler: { deliveredSnapshot in
          continuation.resume(returning: (Thread.isMainThread, deliveredSnapshot.authorizationStatus))
        }
      )
    }

    XCTAssertTrue(result.0)
    XCTAssertEqual(result.1, .notDetermined)
  }

  func testSignedSmokeRequiresExplicitResultPath() {
    XCTAssertFalse(UserNotificationCallbackBridge.isSignedSmokeRequested(environment: [:]))
    XCTAssertFalse(
      UserNotificationCallbackBridge.isSignedSmokeRequested(
        environment: [UserNotificationCallbackBridge.signedSmokeResultPathEnvironmentKey: ""]))
    XCTAssertTrue(
      UserNotificationCallbackBridge.isSignedSmokeRequested(
        environment: [UserNotificationCallbackBridge.signedSmokeResultPathEnvironmentKey: "/tmp/proof"]))
    XCTAssertFalse(UserNotificationCallbackBridge.runSignedSmokeIfRequested(environment: [:]))
  }

  func testSelectorRegistrationCopiesPayloadAndHopsToMainActor() async {
    let notificationName = Notification.Name("com.omi.test.insight.\(UUID().uuidString)")
    let events = AsyncStream<(isMainThread: Bool, hours: String?, unsupported: String?)>.makeStream()
    let observer = ProactiveTestNotificationObserver(name: notificationName) { payload in
      events.continuation.yield(
        (
          Thread.isMainThread,
          payload["hours"],
          payload["unsupported"]
        ))
      events.continuation.finish()
    }
    let center = NotificationCenter.default
    observer.register(in: center)
    defer {
      observer.unregister(from: center)
    }

    DispatchQueue.global(qos: .userInitiated).async {
      NotificationCenter.default.post(
        name: notificationName,
        object: nil,
        userInfo: ["hours": "2.5", "unsupported": "must-not-cross-actor-boundary"]
      )
    }

    guard let result = await events.stream.first(where: { _ in true }) else {
      return XCTFail("expected selector-delivered notification")
    }

    XCTAssertTrue(result.isMainThread)
    XCTAssertEqual(result.hours, "2.5")
    XCTAssertNil(result.unsupported)
  }
}
