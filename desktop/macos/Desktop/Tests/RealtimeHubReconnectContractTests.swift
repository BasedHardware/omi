import XCTest

@testable import Omi_Computer

@MainActor
final class RealtimeHubReconnectContractTests: XCTestCase {
  private let reducer = VoiceTurnReducer()

  func testSessionCallbackAdmissionFencesSupersededSocketAndOwner() {
    XCTAssertTrue(
      RealtimeHubReconnectIdentityPolicy.admitsSessionCallback(
        isLiveSessionObject: true,
        sessionOwnerIsCurrent: true))
    XCTAssertFalse(
      RealtimeHubReconnectIdentityPolicy.admitsSessionCallback(
        isLiveSessionObject: false,
        sessionOwnerIsCurrent: true),
      "replaced session object callbacks must never enter the reducer")
    XCTAssertFalse(
      RealtimeHubReconnectIdentityPolicy.admitsSessionCallback(
        isLiveSessionObject: true,
        sessionOwnerIsCurrent: false),
      "authenticated owner change must fence the still-live socket")
  }

  func testReconnectedSessionIDFenceIgnoresLateOldSession() {
    let live = VoiceSessionID()
    let superseded = VoiceSessionID()
    XCTAssertTrue(
      RealtimeHubReconnectIdentityPolicy.admitsReconnectedSessionID(
        callbackSessionID: live,
        liveSessionID: live))
    XCTAssertFalse(
      RealtimeHubReconnectIdentityPolicy.admitsReconnectedSessionID(
        callbackSessionID: superseded,
        liveSessionID: live))
  }

  func testSuccessfulReconnectCompletesOnceAndFencesLateOldSession() {
    let turnID = VoiceTurnID()
    let oldSessionID = VoiceSessionID()
    let newSessionID = VoiceSessionID()
    let responseID = VoiceResponseID("reconnect-success")
    var model = reduce(.idle, .start(turnID: turnID, ownerID: nil, intent: .hold)).model
    model = reduce(model, .selectRoute(turnID: turnID, route: .hub(sessionID: oldSessionID))).model
    model = reduce(model, .finalize(turnID: turnID)).model
    model = reduce(
      model,
      .hubCommitAccepted(turnID: turnID, sessionID: oldSessionID, responseID: responseID)
    ).model
    let reservation = reserveIdentity(model, turnID: turnID)
    model = reservation.model

    model = reduce(
      model,
      .providerReconnectStarted(
        turnID: turnID,
        identity: reservation.identity,
        previousSessionID: oldSessionID)).model
    XCTAssertEqual(
      model.turn?.providerConnection,
      .reconnecting(identity: reservation.identity, previousSessionID: oldSessionID))

    XCTAssertFalse(
      RealtimeHubReconnectIdentityPolicy.admitsReconnectedSessionID(
        callbackSessionID: oldSessionID,
        liveSessionID: newSessionID),
      "production boundary must fence the superseded session before reducer admission")

    model = reduce(
      model,
      .providerReconnected(
        turnID: turnID,
        identity: reservation.identity,
        sessionID: newSessionID)).model
    XCTAssertEqual(model.turn?.providerConnection, .ready)
    XCTAssertEqual(model.turn?.sessionID, newSessionID)

    let lateOld = reduce(
      model,
      .providerReconnected(
        turnID: turnID,
        identity: reservation.identity,
        sessionID: oldSessionID))
    XCTAssertEqual(lateOld.model.staleEventCount, 1)
    XCTAssertEqual(lateOld.model.turn?.sessionID, newSessionID)
    XCTAssertEqual(lateOld.model.turn?.providerConnection, .ready)
    XCTAssertNotEqual(lateOld.model.turn?.phase, .terminal(.providerFailed))
  }

  func testFailedReconnectDeadlineTerminatesOnceWithoutSleep() {
    let turnID = VoiceTurnID()
    let sessionID = VoiceSessionID()
    let responseID = VoiceResponseID("reconnect-deadline")
    var model = reduce(.idle, .start(turnID: turnID, ownerID: nil, intent: .hold)).model
    model = reduce(model, .selectRoute(turnID: turnID, route: .hub(sessionID: sessionID))).model
    model = reduce(model, .finalize(turnID: turnID)).model
    model = reduce(
      model,
      .hubCommitAccepted(turnID: turnID, sessionID: sessionID, responseID: responseID)
    ).model
    let reservation = reserveIdentity(model, turnID: turnID)
    model = reduce(
      reservation.model,
      .providerReconnectStarted(
        turnID: turnID,
        identity: reservation.identity,
        previousSessionID: sessionID)).model

    let timedOut = reduce(
      model,
      .deadlineFired(turnID: turnID, deadline: .providerReconnect))
    XCTAssertEqual(timedOut.model.turn?.phase, .terminal(.providerFailed))
    XCTAssertEqual(
      timedOut.effects.filter { effect in
        if case .terminal = effect { return true }
        return false
      }.count,
      1)

    let lateSuccess = reduce(
      timedOut.model,
      .providerReconnected(
        turnID: turnID,
        identity: reservation.identity,
        sessionID: VoiceSessionID()))
    XCTAssertEqual(lateSuccess.model.turn?.phase, .terminal(.providerFailed))
    XCTAssertEqual(
      lateSuccess.effects.filter { effect in
        if case .terminal = effect { return true }
        return false
      }.count,
      0,
      "late reconnect success after deadline must not emit a second terminal")
  }

  func testHubWiresSessionCallbackAdmissionThroughReconnectIdentityPolicy() throws {
    let hubURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/FloatingControlBar/RealtimeHubController.swift")
    let policiesURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/FloatingControlBar/RealtimeHubSessionPolicies.swift")
    let hubSource = try String(contentsOf: hubURL, encoding: .utf8)
    let policiesSource = try String(contentsOf: policiesURL, encoding: .utf8)
    XCTAssertTrue(hubSource.contains("RealtimeHubReconnectIdentityPolicy.admitsSessionCallback("))
    XCTAssertTrue(policiesSource.contains("admitsReconnectedSessionID("))
  }

  private func reduce(_ model: VoiceTurnModel, _ event: VoiceTurnEvent) -> VoiceTurnReduction {
    reducer.reduce(model, event)
  }

  private func reserveIdentity(
    _ model: VoiceTurnModel,
    turnID: VoiceTurnID
  ) -> (model: VoiceTurnModel, identity: VoiceEffectIdentity) {
    let effectID = model.turn?.nextEffectID ?? 0
    let reserved = reduce(model, .effectIdentityReserved(turnID: turnID)).model
    return (reserved, VoiceEffectIdentity(turnID: turnID, effectID: effectID))
  }
}
