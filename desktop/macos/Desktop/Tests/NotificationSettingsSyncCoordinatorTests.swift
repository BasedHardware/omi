import XCTest

@testable import Omi_Computer

private final class SleepLog: @unchecked Sendable {
  var values: [UInt64] = []
}

private struct FakeNotificationSettingsError: Error {}

private final class FakeNotificationSettingsRemote: NotificationSettingsRemote, @unchecked Sendable {
  var getResult: Result<NotificationSettingsResponse, Error> = .success(
    NotificationSettingsResponse(enabled: false, frequency: 0))
  var updateResults: [Result<NotificationSettingsResponse, Error>] = []
  var getCount = 0
  var updates: [(enabled: Bool?, frequency: Int?)] = []
  var beforeGet: (() async -> Void)?

  func get() async throws -> NotificationSettingsResponse {
    getCount += 1
    if let beforeGet {
      await beforeGet()
    }
    return try getResult.get()
  }

  func update(enabled: Bool?, frequency: Int?) async throws -> NotificationSettingsResponse {
    updates.append((enabled, frequency))
    if updateResults.isEmpty {
      return NotificationSettingsResponse(enabled: enabled ?? true, frequency: frequency ?? 0)
    }
    return try updateResults.removeFirst().get()
  }
}

@MainActor
private struct Fixture {
  let suiteName: String
  let defaults: UserDefaults
  let remote: FakeNotificationSettingsRemote
  let coordinator: NotificationSettingsSyncCoordinator
  let sleepLog: SleepLog
  var sleeps: [UInt64] { sleepLog.values }

  func tearDown() {
    coordinator.cancel()
    defaults.removePersistentDomain(forName: suiteName)
  }
}

@MainActor
final class NotificationSettingsSyncCoordinatorTests: XCTestCase {
  private func makeFixture() throws -> Fixture {
    let suiteName = "NotificationSettingsSyncCoordinatorTests.\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
    let remote = FakeNotificationSettingsRemote()
    let sleepLog = SleepLog()
    let coordinator = NotificationSettingsSyncCoordinator(
      remote: remote,
      defaults: defaults,
      sleeper: { [sleepLog] nanoseconds in
        sleepLog.values.append(nanoseconds)
      },
      isSignedIn: { true })
    return Fixture(
      suiteName: suiteName,
      defaults: defaults,
      remote: remote,
      coordinator: coordinator,
      sleepLog: sleepLog)
  }

  func testBackoffDelayIsBounded() {
    XCTAssertEqual(NotificationSettingsSyncBackoff.delayNanoseconds(attempt: 0), 1_000_000_000)
    XCTAssertEqual(NotificationSettingsSyncBackoff.delayNanoseconds(attempt: 1), 2_000_000_000)
    XCTAssertEqual(
      NotificationSettingsSyncBackoff.delayNanoseconds(attempt: 10),
      NotificationSettingsSyncBackoff.maxNanoseconds)
    XCTAssertEqual(
      NotificationSettingsSyncBackoff.delayNanoseconds(attempt: 100),
      NotificationSettingsSyncBackoff.maxNanoseconds)
  }

  func testFailedPatchIsRetriedUntilServerConfirmsWithoutReopeningSettings() async throws {
    let fixture = try makeFixture()
    defer { fixture.tearDown() }
    fixture.defaults.set(true, forKey: NotificationService.masterEnabledDefaultsKey)
    fixture.defaults.set(3, forKey: NotificationService.frequencyDefaultsKey)
    fixture.remote.updateResults = [
      .failure(FakeNotificationSettingsError()),
      .success(NotificationSettingsResponse(enabled: true, frequency: 3)),
    ]

    let revision = NotificationService.beginNotificationSettingsSync(defaults: fixture.defaults)
    fixture.coordinator.enqueue(enabled: true, frequency: 3, revision: revision)
    await fixture.coordinator.waitUntilIdleForTesting()

    XCTAssertEqual(fixture.remote.updates.count, 2)
    XCTAssertEqual(fixture.remote.updates[0].enabled, true)
    XCTAssertEqual(fixture.remote.updates[0].frequency, 3)
    XCTAssertEqual(fixture.remote.updates[1].enabled, true)
    XCTAssertEqual(fixture.remote.updates[1].frequency, 3)
    XCTAssertFalse(
      NotificationService.hasPendingNotificationSettingsSync(defaults: fixture.defaults),
      "a successful retry must clear the pending journal")
    XCTAssertEqual(fixture.sleeps.first, NotificationSettingsSyncBackoff.delayNanoseconds(attempt: 0))
    XCTAssertTrue(NotificationService.areNotificationsEnabled(defaults: fixture.defaults))
    XCTAssertEqual(NotificationService.currentFrequencyLevel(defaults: fixture.defaults), 3)
  }

  func testRetryWithoutLocallyWrittenMasterKeySendsNilEnabled() async throws {
    let fixture = try makeFixture()
    defer { fixture.tearDown() }
    // First launch: only the frequency migration is pending and the master key
    // was never written locally. The retry must not push the absent-key default
    // of `true` over a toggle another client may have set server-side.
    fixture.defaults.set(3, forKey: NotificationService.frequencyDefaultsKey)
    fixture.remote.updateResults = [
      .failure(FakeNotificationSettingsError()),
      .success(NotificationSettingsResponse(enabled: false, frequency: 3)),
    ]

    let revision = NotificationService.beginNotificationSettingsSync(defaults: fixture.defaults)
    fixture.coordinator.enqueue(enabled: nil, frequency: 3, revision: revision)
    await fixture.coordinator.waitUntilIdleForTesting()

    XCTAssertEqual(fixture.remote.updates.count, 2)
    XCTAssertNil(fixture.remote.updates[0].enabled)
    XCTAssertNil(
      fixture.remote.updates[1].enabled,
      "a retry must not invent a master-toggle value the user never chose")
    XCTAssertEqual(fixture.remote.updates[1].frequency, 3)
    XCTAssertFalse(NotificationService.hasPendingNotificationSettingsSync(defaults: fixture.defaults))
  }

  func testHydrationAppliesServerValuesWhenNoLocalChangeIsPending() async throws {
    let fixture = try makeFixture()
    defer { fixture.tearDown() }
    fixture.defaults.set(true, forKey: NotificationService.masterEnabledDefaultsKey)
    fixture.defaults.set(5, forKey: NotificationService.frequencyDefaultsKey)
    fixture.remote.getResult = .success(NotificationSettingsResponse(enabled: false, frequency: 2))

    await fixture.coordinator.reconcile()

    XCTAssertTrue(fixture.remote.updates.isEmpty, "idle hydration must not PATCH")
    XCTAssertFalse(NotificationService.areNotificationsEnabled(defaults: fixture.defaults))
    XCTAssertEqual(NotificationService.currentFrequencyLevel(defaults: fixture.defaults), 2)
  }

  func testPendingLocalChangeIsPreservedAndPatchedInsteadOfHydrated() async throws {
    let fixture = try makeFixture()
    defer { fixture.tearDown() }
    fixture.defaults.set(true, forKey: NotificationService.masterEnabledDefaultsKey)
    fixture.defaults.set(5, forKey: NotificationService.frequencyDefaultsKey)
    _ = NotificationService.beginNotificationSettingsSync(defaults: fixture.defaults)
    fixture.remote.getResult = .success(NotificationSettingsResponse(enabled: false, frequency: 0))
    fixture.remote.updateResults = [
      .success(NotificationSettingsResponse(enabled: true, frequency: 5))
    ]

    await fixture.coordinator.reconcile()
    await fixture.coordinator.waitUntilIdleForTesting()

    XCTAssertTrue(
      NotificationService.areNotificationsEnabled(defaults: fixture.defaults),
      "local remains authoritative while a PATCH is pending")
    XCTAssertEqual(NotificationService.currentFrequencyLevel(defaults: fixture.defaults), 5)
    XCTAssertEqual(fixture.remote.updates.count, 1)
    XCTAssertEqual(fixture.remote.updates[0].enabled, true)
    XCTAssertEqual(fixture.remote.updates[0].frequency, 5)
    XCTAssertFalse(NotificationService.hasPendingNotificationSettingsSync(defaults: fixture.defaults))
  }

  func testRevisionRaceDuringGetPreservesLocalAndDoesNotHydrate() async throws {
    let fixture = try makeFixture()
    defer { fixture.tearDown() }
    let defaults = fixture.defaults
    defaults.set(true, forKey: NotificationService.masterEnabledDefaultsKey)
    defaults.set(4, forKey: NotificationService.frequencyDefaultsKey)
    fixture.remote.getResult = .success(NotificationSettingsResponse(enabled: false, frequency: 0))
    fixture.remote.beforeGet = {
      _ = NotificationService.beginNotificationSettingsSync(defaults: defaults)
      defaults.set(true, forKey: NotificationService.masterEnabledDefaultsKey)
      defaults.set(4, forKey: NotificationService.frequencyDefaultsKey)
    }

    await fixture.coordinator.reconcile()
    await fixture.coordinator.waitUntilIdleForTesting()

    XCTAssertTrue(NotificationService.areNotificationsEnabled(defaults: defaults))
    XCTAssertEqual(NotificationService.currentFrequencyLevel(defaults: defaults), 4)
    XCTAssertFalse(
      defaults.bool(forKey: NotificationService.masterEnabledDefaultsKey) == false,
      "a GET that raced a local mutation must not hydrate the stale server pair")
  }

  func testDeliveryGateStillReadsOnlyLocalDefaults() throws {
    let fixture = try makeFixture()
    defer { fixture.tearDown() }
    fixture.defaults.set(true, forKey: NotificationService.masterEnabledDefaultsKey)
    fixture.remote.getResult = .success(NotificationSettingsResponse(enabled: false, frequency: 0))
    XCTAssertTrue(NotificationService.areNotificationsEnabled(defaults: fixture.defaults))
    XCTAssertEqual(fixture.remote.getCount, 0)
    XCTAssertTrue(fixture.remote.updates.isEmpty)
  }

  func testStartReconcilesWhenSignedIn() async throws {
    let fixture = try makeFixture()
    defer { fixture.tearDown() }
    fixture.remote.getResult = .success(NotificationSettingsResponse(enabled: false, frequency: 2))
    fixture.coordinator.start()
    await fixture.coordinator.waitUntilIdleForTesting()
    XCTAssertEqual(fixture.remote.getCount, 1)
    XCTAssertFalse(NotificationService.areNotificationsEnabled(defaults: fixture.defaults))
    XCTAssertEqual(NotificationService.currentFrequencyLevel(defaults: fixture.defaults), 2)

    fixture.remote.getResult = .success(NotificationSettingsResponse(enabled: true, frequency: 4))
    NotificationCenter.default.post(name: .sessionDidAuthenticate, object: nil)
    await Task { @MainActor in }.value
    await fixture.coordinator.waitUntilIdleForTesting()
    XCTAssertEqual(fixture.remote.getCount, 2)
    XCTAssertTrue(NotificationService.areNotificationsEnabled(defaults: fixture.defaults))
    XCTAssertEqual(NotificationService.currentFrequencyLevel(defaults: fixture.defaults), 4)
  }
}
