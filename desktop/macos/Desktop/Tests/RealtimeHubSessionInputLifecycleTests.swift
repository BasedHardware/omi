import XCTest

@testable import Omi_Computer

@MainActor
final class RealtimeHubSessionInputLifecycleTests: XCTestCase {
  func testWarmGeminiBuffersAudioAndCommitUntilActivityWindowOpens() async {
    let delegate = RealtimeHubSessionDelegateSpy()
    let session = makeSession(provider: .gemini, delegate: delegate)
    session.markReadyForTesting()
    _ = await session.inputLifecycleSnapshot()

    session.sendAudio(Data([1, 2, 3, 4]))
    session.commitInputTurn()
    let deferred = await session.inputLifecycleSnapshot()

    XCTAssertTrue(deferred.isOpen)
    XCTAssertFalse(deferred.activityOpen)
    XCTAssertEqual(deferred.pendingAudioChunkCount, 1)
    XCTAssertTrue(deferred.pendingCommit)

    session.beginInputTurn()
    let committed = await session.inputLifecycleSnapshot()
    XCTAssertEqual(committed.pendingAudioChunkCount, 0)
    XCTAssertFalse(committed.pendingCommit)
    XCTAssertFalse(committed.activityOpen, "the deferred commit closes the newly opened activity")
  }

  func testColdGeminiKeepsAudioOrderedBetweenActivityStartAndCommit() async {
    let delegate = RealtimeHubSessionDelegateSpy()
    let session = makeSession(provider: .gemini, delegate: delegate)

    session.beginInputTurn()
    session.sendAudio(Data([5, 6]))
    session.commitInputTurn()
    let cold = await session.inputLifecycleSnapshot()
    XCTAssertFalse(cold.isOpen)
    XCTAssertTrue(cold.activityOpen)
    XCTAssertEqual(cold.pendingAudioChunkCount, 1)
    XCTAssertTrue(cold.pendingCommit)

    session.markReadyForTesting()
    let ready = await session.inputLifecycleSnapshot()
    XCTAssertTrue(ready.isOpen)
    XCTAssertEqual(ready.pendingAudioChunkCount, 0)
    XCTAssertFalse(ready.pendingCommit)
    XCTAssertFalse(ready.activityOpen)
  }

  func testAbandonClearsPreWindowAudioAndDeferredCommit() async {
    let delegate = RealtimeHubSessionDelegateSpy()
    let session = makeSession(provider: .gemini, delegate: delegate)
    session.markReadyForTesting()
    _ = await session.inputLifecycleSnapshot()
    session.sendAudio(Data([7, 8]))
    session.commitInputTurn()
    session.abandonInputTurn()

    let abandoned = await session.inputLifecycleSnapshot()
    XCTAssertEqual(abandoned.pendingAudioChunkCount, 0)
    XCTAssertFalse(abandoned.pendingCommit)
    XCTAssertFalse(abandoned.activityOpen)
  }

  func testAbandonClearsColdOpenAICommitBeforeNextTurnBecomesReady() async {
    let delegate = RealtimeHubSessionDelegateSpy()
    let session = makeSession(provider: .openai, delegate: delegate)
    session.sendAudio(Data([11, 12]))
    session.commitInputTurn()
    session.abandonInputTurn()

    let abandoned = await session.inputLifecycleSnapshot()
    XCTAssertEqual(abandoned.pendingAudioChunkCount, 0)
    XCTAssertFalse(abandoned.pendingCommit)

    session.sendAudio(Data([13, 14]))
    session.markReadyForTesting()
    let nextTurn = await session.inputLifecycleSnapshot()
    XCTAssertEqual(nextTurn.pendingAudioChunkCount, 0)
    XCTAssertFalse(nextTurn.pendingCommit, "the canceled turn must not commit next-turn audio")
  }

  func testAbandonClearsColdGeminiVideoFrame() async {
    let delegate = RealtimeHubSessionDelegateSpy()
    let session = makeSession(provider: .gemini, delegate: delegate)
    session.sendVideoFrame(Data([1, 2, 3]), mime: "image/jpeg")
    var buffered = await session.inputLifecycleSnapshot()
    XCTAssertEqual(buffered.pendingVideoFrameCount, 1)

    session.abandonInputTurn()
    buffered = await session.inputLifecycleSnapshot()
    XCTAssertEqual(buffered.pendingVideoFrameCount, 0)
  }

  func testOpenAIOnlyNeedsTransportReadiness() async {
    let delegate = RealtimeHubSessionDelegateSpy()
    let session = makeSession(provider: .openai, delegate: delegate)
    session.markReadyForTesting()
    _ = await session.inputLifecycleSnapshot()
    session.sendAudio(Data([9, 10]))
    session.commitInputTurn()

    let committed = await session.inputLifecycleSnapshot()
    XCTAssertTrue(committed.isOpen)
    XCTAssertEqual(committed.pendingAudioChunkCount, 0)
    XCTAssertFalse(committed.pendingCommit)
  }

  func testOpenAICancelReclaimsActiveResponseIdentity() async {
    let delegate = RealtimeHubSessionDelegateSpy()
    let session = makeSession(provider: .openai, delegate: delegate)
    session.markReadyForTesting()
    _ = await session.inputLifecycleSnapshot()
    let identity = RealtimeHubEventIdentity(
      turnID: VoiceTurnID(), responseID: VoiceResponseID("voice-response"))
    await session.seedOpenAIIdentityMapsForTesting(
      identity: identity,
      responseID: "provider-response",
      inputItemID: "input-item")

    session.cancelActiveResponse()
    let canceled = await session.inputLifecycleSnapshot()

    XCTAssertEqual(canceled.responseIdentityCount, 0)
    XCTAssertEqual(canceled.inputIdentityCount, 1)
  }

  func testOpenAICompletedTranscriptReclaimsInputIdentity() async {
    let delegate = RealtimeHubSessionDelegateSpy()
    let session = makeSession(provider: .openai, delegate: delegate)
    let identity = RealtimeHubEventIdentity(
      turnID: VoiceTurnID(), responseID: VoiceResponseID("voice-response"))
    await session.seedOpenAIIdentityMapsForTesting(
      identity: identity,
      responseID: "provider-response",
      inputItemID: "input-item")

    await session.receiveOpenAIEventForTesting([
      "type": "conversation.item.input_audio_transcription.completed",
      "item_id": "input-item",
      "transcript": "fixture",
    ])
    let completed = await session.inputLifecycleSnapshot()

    XCTAssertEqual(completed.inputIdentityCount, 0)
  }

  private func makeSession(
    provider: RealtimeHubProvider,
    delegate: RealtimeHubSessionDelegate
  ) -> RealtimeHubSession {
    RealtimeHubSession(
      provider: provider,
      auth: .byokKey("fixture"),
      instructions: "fixture",
      delegate: delegate)
  }
}

@MainActor
private final class RealtimeHubSessionDelegateSpy: RealtimeHubSessionDelegate {
  func hubDidConnect(source: RealtimeHubSession) {}
  func hubDidReceiveInputTranscript(
    _ text: String, isFinal: Bool, identity: RealtimeHubEventIdentity?, source: RealtimeHubSession
  ) {}
  func hubDidReceiveAudio(
    _ pcm24k: Data, identity: RealtimeHubEventIdentity?, source: RealtimeHubSession
  ) {}
  func hubDidEmitText(
    _ text: String, isFinal: Bool, identity: RealtimeHubEventIdentity?, source: RealtimeHubSession
  ) {}
  func hubDidRequestTool(
    name: String,
    callId: String,
    argumentsJSON: String,
    identity: RealtimeHubEventIdentity?,
    source: RealtimeHubSession
  ) {}
  func hubDidFinishTurn(identity: RealtimeHubEventIdentity?, source: RealtimeHubSession) {}
  func hubDidError(_ message: String, source: RealtimeHubSession) {}
}
