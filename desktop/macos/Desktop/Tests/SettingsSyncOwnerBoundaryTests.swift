import XCTest

@testable import Omi_Computer

private final class SettingsTestSession: @unchecked Sendable {
  let authority = RuntimeOwnerAuthorizationAuthority()
  private let lock = NSLock()
  private var owner: String?

  init(owner: String) {
    self.owner = owner
    authority.endTransition(ownerID: owner)
  }

  func transition(to owner: String?) {
    authority.beginTransition()
    lock.withLock { self.owner = owner }
    authority.endTransition(ownerID: owner)
  }

  func capture() -> RuntimeOwnerAuthorizationSnapshot? {
    authority.capture(ownerID: lock.withLock { owner }, expectedOwnerID: nil)
  }

  func isCurrent(_ snapshot: RuntimeOwnerAuthorizationSnapshot) -> Bool {
    authority.isCurrent(snapshot, ownerID: lock.withLock { owner })
  }
}

private actor SettingsBoundaryRemote: AssistantSettingsRemote {
  let pauseRead: Bool
  let pauseFirstWrite: Bool
  private var readStarted = false
  private var startedWaiters: [CheckedContinuation<Void, Never>] = []
  private var readContinuation: CheckedContinuation<AssistantSettingsResponse, Never>?
  private(set) var writes: [RuntimeOwnerAuthorizationSnapshot] = []
  private(set) var appliedValues: [Int] = []
  private var writeContinuation: CheckedContinuation<Void, Never>?
  private var writeStartedWaiters: [CheckedContinuation<Void, Never>] = []

  init(pauseRead: Bool = false, pauseFirstWrite: Bool = false) {
    self.pauseRead = pauseRead
    self.pauseFirstWrite = pauseFirstWrite
  }

  func get(authorization: RuntimeOwnerAuthorizationSnapshot) async throws -> AssistantSettingsResponse {
    if !pauseRead { return AssistantSettingsResponse(shared: SharedAssistantSettingsResponse(cooldownInterval: 42)) }
    return await withCheckedContinuation { continuation in
      readContinuation = continuation
      readStarted = true
      startedWaiters.forEach { $0.resume() }
      startedWaiters.removeAll()
    }
  }

  func waitForRead() async {
    if readStarted { return }
    await withCheckedContinuation { startedWaiters.append($0) }
  }

  func finishRead() {
    readContinuation?.resume(returning: AssistantSettingsResponse())
    readContinuation = nil
  }

  func update(_ settings: AssistantSettingsResponse, authorization: RuntimeOwnerAuthorizationSnapshot) async throws
    -> AssistantSettingsResponse
  {
    writes.append(authorization)
    if pauseFirstWrite, writes.count == 1 {
      await withCheckedContinuation { continuation in
        writeContinuation = continuation
        writeStartedWaiters.forEach { $0.resume() }
        writeStartedWaiters.removeAll()
      }
    }
    if let value = settings.shared?.cooldownInterval { appliedValues.append(value) }
    return settings
  }

  func waitForFirstWrite() async {
    if writeContinuation != nil { return }
    await withCheckedContinuation { writeStartedWaiters.append($0) }
  }

  func finishFirstWrite() {
    writeContinuation?.resume()
    writeContinuation = nil
  }
}

@MainActor
final class SettingsSyncOwnerBoundaryTests: XCTestCase {
  func testCurrentPullAppliesSettingsAndRefreshesVoice() async {
    let session = SettingsTestSession(owner: "a")
    var applied = 0
    var voiceRefreshes = 0
    let manager = SettingsSyncManager(
      remote: SettingsBoundaryRemote(), captureAuthorization: { session.capture() },
      isCurrent: { session.isCurrent($0) }, applySettings: { _ in applied += 1 },
      refreshVoice: { voiceRefreshes += 1 })

    await manager.syncFromServer()

    XCTAssertEqual(applied, 1)
    XCTAssertEqual(voiceRefreshes, 1)
  }

  func testPullCannotPublishAcrossDifferentOwner() async {
    await assertPullRevoked(nextOwner: "b")
  }

  func testPullCannotPublishAfterSameOwnerReauthentication() async {
    await assertPullRevoked(nextOwner: "a")
  }

  private func assertPullRevoked(nextOwner: String) async {
    let session = SettingsTestSession(owner: "a")
    let remote = SettingsBoundaryRemote(pauseRead: true)
    var publications = 0
    let manager = SettingsSyncManager(
      remote: remote, captureAuthorization: { session.capture() },
      isCurrent: { session.isCurrent($0) }, applySettings: { _ in publications += 1 },
      refreshVoice: { publications += 1 })
    let pull = Task { await manager.syncFromServer() }
    await remote.waitForRead()
    session.transition(to: nextOwner)
    await remote.finishRead()
    await pull.value

    XCTAssertEqual(publications, 0, "A revoked session must not hydrate defaults or begin voice refresh")
  }

  func testQueuedPartialWriteIsRevokedAfterSameOwnerReauthentication() async {
    let session = SettingsTestSession(owner: "a")
    let remote = SettingsBoundaryRemote()
    let manager = SettingsSyncManager(
      remote: remote, captureAuthorization: { session.capture() }, isCurrent: { session.isCurrent($0) })

    let pending = manager.pushPartialUpdate(AssistantSettingsResponse())
    session.transition(to: "a")
    await pending.value

    let writes = await remote.writes
    XCTAssertTrue(writes.isEmpty)
  }

  func testQueuedPartialWriteCannotCrossSignOutOrDifferentOwner() async {
    for nextOwner: String? in [nil, "b"] {
      let session = SettingsTestSession(owner: "a")
      let remote = SettingsBoundaryRemote()
      let manager = SettingsSyncManager(
        remote: remote, captureAuthorization: { session.capture() }, isCurrent: { session.isCurrent($0) })
      let pending = manager.pushPartialUpdate(AssistantSettingsResponse())
      session.transition(to: nextOwner)
      await pending.value
      let writes = await remote.writes
      XCTAssertTrue(writes.isEmpty)
    }
  }

  func testFullAndPartialWritesCarryTheOriginalSessionSnapshot() async throws {
    let session = SettingsTestSession(owner: "a")
    let original = try XCTUnwrap(session.capture())
    let remote = SettingsBoundaryRemote()
    let manager = SettingsSyncManager(
      remote: remote, captureAuthorization: { session.capture() }, isCurrent: { session.isCurrent($0) },
      localSettings: { AssistantSettingsResponse() })

    await manager.syncToServer()
    await manager.pushPartialUpdate(AssistantSettingsResponse()).value

    let writes = await remote.writes
    XCTAssertEqual(writes, [original, original])
  }

  func testPullPredatingALocalWriteDoesNotOverwriteNewerIntent() async {
    let session = SettingsTestSession(owner: "a")
    let remote = SettingsBoundaryRemote(pauseRead: true)
    var publications = 0
    let manager = SettingsSyncManager(
      remote: remote, captureAuthorization: { session.capture() }, isCurrent: { session.isCurrent($0) },
      applySettings: { _ in publications += 1 }, refreshVoice: {})
    let pull = Task { await manager.syncFromServer() }
    await remote.waitForRead()
    await manager.pushPartialUpdate(AssistantSettingsResponse()).value
    await remote.finishRead()
    await pull.value
    XCTAssertEqual(publications, 0)
  }

  func testSlowFirstWriteCannotOverwriteLaterUserEdits() async {
    let session = SettingsTestSession(owner: "a")
    let remote = SettingsBoundaryRemote(pauseFirstWrite: true)
    let manager = SettingsSyncManager(
      remote: remote, captureAuthorization: { session.capture() }, isCurrent: { session.isCurrent($0) })
    let first = manager.pushPartialUpdate(
      AssistantSettingsResponse(shared: SharedAssistantSettingsResponse(cooldownInterval: 1)))
    await remote.waitForFirstWrite()
    let pending = (2...20).map { value in
      manager.pushPartialUpdate(
        AssistantSettingsResponse(shared: SharedAssistantSettingsResponse(cooldownInterval: value)))
    }
    await remote.finishFirstWrite()
    await first.value
    for operation in pending { await operation.value }
    let values = await remote.appliedValues
    XCTAssertEqual(values, Array(1...20))
  }

  func testNewSessionWriteDoesNotWaitForPreviousOwnerNetwork() async {
    let session = SettingsTestSession(owner: "a")
    let remote = SettingsBoundaryRemote(pauseFirstWrite: true)
    let manager = SettingsSyncManager(
      remote: remote, captureAuthorization: { session.capture() }, isCurrent: { session.isCurrent($0) })
    let old = manager.pushPartialUpdate(AssistantSettingsResponse())
    await remote.waitForFirstWrite()
    session.transition(to: "b")
    await manager.pushPartialUpdate(AssistantSettingsResponse()).value
    let writes = await remote.writes
    XCTAssertEqual(writes.map(\.ownerID), ["a", "b"])
    await remote.finishFirstWrite()
    await old.value
  }
}
