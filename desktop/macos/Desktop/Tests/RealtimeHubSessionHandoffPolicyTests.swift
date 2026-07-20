import VoiceTurnDomain
import XCTest

@testable import Omi_Computer

final class RealtimeHubSessionHandoffPolicyTests: XCTestCase {
  func testProviderLogTagDoesNotGuessOpenAIWhileSessionIsUnbound() {
    XCTAssertEqual(RealtimeHubProviderLogTag.current(nil), "unbound")
    XCTAssertEqual(RealtimeHubProviderLogTag.current(.gemini), "gemini")
    XCTAssertEqual(RealtimeHubProviderLogTag.current(.openai), "openai")
  }

  func testAuthenticatedSocketWithStaleContextCapturesAndBuffersInsteadOfEnteringDirectly() {
    XCTAssertEqual(
      RealtimePTTAdmissionPolicy.decide(
        requirementIsResolved: true,
        transportIsReady: true,
        bindingMatchesRequirement: false),
      .captureAndBuffer)
  }

  func testOnlyExactAuthenticatedBindingAdmitsPTTImmediately() {
    XCTAssertEqual(
      RealtimePTTAdmissionPolicy.decide(
        requirementIsResolved: true,
        transportIsReady: true,
        bindingMatchesRequirement: true),
      .immediate)
  }

  func testMatchingBindingNeverStartsMaintenanceHandoff() {
    XCTAssertEqual(
      RealtimeHubSessionHandoffPolicy.decide(
        bindingMatchesRequirement: true,
        canReplaceIdleSession: true,
        hasBufferedTurn: false),
      .keepActive)
  }

  func testGeminiPostTurnRefreshUsesOnlyItsPersistenceFencedBoundary() {
    XCTAssertFalse(
      RealtimePersistedVoiceContextRefreshPolicy.shouldHandoffImmediately(provider: .gemini))
    XCTAssertTrue(
      RealtimePersistedVoiceContextRefreshPolicy.shouldHandoffImmediately(provider: .openai))
    XCTAssertTrue(
      RealtimePersistedVoiceContextRefreshPolicy.shouldHandoffImmediately(provider: nil))
  }

  func testStreamingContextUpdateDebouncesIdleSessionHandoff() {
    XCTAssertEqual(
      RealtimeVoiceContextRefreshPolicy.handoffDecision(
        currentSnapshotIdentity: "newer", sessionSnapshotIdentity: "older", hasBufferedTurn: false),
      .debounceIdleHandoff)
    XCTAssertEqual(
      RealtimeVoiceContextRefreshPolicy.handoffDecision(
        currentSnapshotIdentity: "same", sessionSnapshotIdentity: "same", hasBufferedTurn: false),
      .keepCurrentSession)
  }

  func testCapturedPTTBypassesIdleContextDebounce() {
    XCTAssertEqual(
      RealtimeVoiceContextRefreshPolicy.handoffDecision(
        currentSnapshotIdentity: "newer", sessionSnapshotIdentity: "older", hasBufferedTurn: true),
      .replacePreservingBufferedTurn)
  }

  func testWarmSessionWaitsForOwnerBoundVoiceContext() {
    XCTAssertFalse(RealtimeWarmSessionStartPolicy.canStart(requirementIsResolved: false))
    XCTAssertTrue(RealtimeWarmSessionStartPolicy.canStart(requirementIsResolved: true))
  }

  func testIdleMaintenanceDefersWhileAnotherLogicalTurnOwnsTheSession() {
    XCTAssertEqual(
      RealtimeHubSessionHandoffPolicy.decide(
        bindingMatchesRequirement: false,
        canReplaceIdleSession: false,
        hasBufferedTurn: false),
      .deferUntilIdle)
  }

  func testCapturedTurnGetsOneTransparentRebindThenFallsBack() {
    XCTAssertEqual(
      RealtimeHubSessionHandoffPolicy.decide(
        bindingMatchesRequirement: false,
        canReplaceIdleSession: false,
        hasBufferedTurn: true,
        rebindAttempts: 0),
      .replacePreservingBufferedTurn)
    XCTAssertEqual(
      RealtimeHubSessionHandoffPolicy.decide(
        bindingMatchesRequirement: false,
        canReplaceIdleSession: false,
        hasBufferedTurn: true,
        rebindAttempts: RealtimeReconnectAudioBuffer.maximumRebindAttempts + 1),
      .fallbackToTranscription)
  }

  func testReconnectBufferRefusesASecondRebindAttempt() {
    let turnID = VoiceTurnID()
    var buffer = RealtimeReconnectAudioBuffer(
      turnID: turnID,
      responseID: VoiceResponseID("rebind-response"),
      identity: VoiceEffectIdentity(turnID: turnID, effectID: 1),
      interrupting: false)

    XCTAssertTrue(buffer.beginRebindAttempt())
    XCTAssertEqual(buffer.rebindAttempts, 1)
    XCTAssertFalse(buffer.beginRebindAttempt())
    XCTAssertEqual(buffer.rebindAttempts, 1)
  }

  func testBufferedTurnCanAdoptTheNewestRequirementBeforePhysicalReplay() {
    let turnID = VoiceTurnID()
    var buffer = RealtimeReconnectAudioBuffer(
      turnID: turnID,
      responseID: VoiceResponseID("requirement-response"),
      identity: VoiceEffectIdentity(turnID: turnID, effectID: 1),
      interrupting: false)

    XCTAssertTrue(buffer.bindRequiredContextFreshnessIdentity("cached-requirement"))
    XCTAssertTrue(buffer.replaceRequiredContextFreshnessIdentity("fresh-requirement"))
    XCTAssertEqual(buffer.requiredContextFreshnessIdentity, "fresh-requirement")
  }
}
