import Foundation
import VoiceTurnDomain
import XCTest

@testable import Omi_Computer

#if DEBUG
  // omi-release-compile: this suite drives DEBUG-only test seams; the release-mode
  // notification regression step must compile the bundle without them.

  @MainActor
  final class RealtimeHubSessionInputLifecycleTests: XCTestCase {
    func testTerminalReceiveFailureClosesOldGeminiTransportBeforeUsableReplacement() async {
      let tracker = RealtimeTransportTracker()
      let firstDelegate = RealtimeHubSessionDelegateSpy()
      let firstConnected = expectation(description: "first session connected")
      let firstFailed = expectation(description: "first session failed")
      var firstTransport: ControllableRealtimeRawWebSocket?
      firstDelegate.onConnect = { firstConnected.fulfill() }
      firstDelegate.onError = { failure in
        XCTAssertEqual(failure.kind, .localAddressUnavailable)
        XCTAssertTrue(firstTransport?.closeRequested == true)
        firstFailed.fulfill()
      }
      let first = makeSession(
        provider: .gemini,
        delegate: firstDelegate,
        rawWebSocketFactory: { _, queue in
          let transport = ControllableRealtimeRawWebSocket(queue: queue, tracker: tracker)
          firstTransport = transport
          return transport
        })
      first.start()
      await fulfillment(of: [firstConnected], timeout: 1)

      firstTransport?.fail(
        NSError(
          domain: NSPOSIXErrorDomain,
          code: Int(POSIXErrorCode.EADDRNOTAVAIL.rawValue)))
      await fulfillment(of: [firstFailed], timeout: 1)
      let oldTransportDrained = expectation(description: "old transport drained")
      Task {
        await first.stopAndWait()
        oldTransportDrained.fulfill()
      }
      await Task.yield()
      XCTAssertEqual(tracker.liveCount, 1, "cancel request alone is not terminal acknowledgement")
      firstTransport?.acknowledgeClose()
      await fulfillment(of: [oldTransportDrained], timeout: 1)
      XCTAssertEqual(tracker.liveCount, 0)

      let replacementDelegate = RealtimeHubSessionDelegateSpy()
      let replacementConnected = expectation(description: "replacement connected")
      replacementDelegate.onConnect = { replacementConnected.fulfill() }
      var replacementTransport: ControllableRealtimeRawWebSocket?
      let replacement = makeSession(
        provider: .gemini,
        delegate: replacementDelegate,
        rawWebSocketFactory: { _, queue in
          let transport = ControllableRealtimeRawWebSocket(queue: queue, tracker: tracker)
          replacementTransport = transport
          return transport
        })
      replacement.start()
      await fulfillment(of: [replacementConnected], timeout: 1)

      let acceptedInput = expectation(description: "replacement accepted input")
      replacementTransport?.onInputAccepted = { acceptedInput.fulfill() }
      replacement.beginInputTurn()
      replacement.sendAudio(Data([1, 2, 3, 4]))
      replacement.commitInputTurn()
      await fulfillment(of: [acceptedInput], timeout: 1)

      XCTAssertEqual(tracker.maximumLiveCount, 1)
      let replacementDrained = expectation(description: "replacement drained")
      Task {
        await replacement.stopAndWait()
        replacementDrained.fulfill()
      }
      await Task.yield()
      replacementTransport?.acknowledgeClose()
      await fulfillment(of: [replacementDrained], timeout: 1)
      XCTAssertEqual(tracker.liveCount, 0)
    }

    func testLocalProfileTransportAuthorityIsExactSessionAndOwnerScoped() throws {
      let sourceA = NSObject()
      let sourceB = NSObject()
      let ownerAuthority = RuntimeOwnerAuthorizationAuthority()
      let ownerSnapshot = try XCTUnwrap(
        ownerAuthority.capture(ownerID: "owner-a", expectedOwnerID: "owner-a"))
      let authority = RealtimeLocalProfileTransportAuthority(
        sourceID: ObjectIdentifier(sourceA),
        ownerScope: .authenticated("owner-a"),
        authorizationSnapshot: ownerSnapshot)

      XCTAssertTrue(
        authority.accepts(
          sourceID: ObjectIdentifier(sourceA),
          currentOwnerID: "owner-a",
          localProfileEnabled: true,
          authorizationIsCurrent: true))
      XCTAssertFalse(
        authority.accepts(
          sourceID: ObjectIdentifier(sourceB),
          currentOwnerID: "owner-a",
          localProfileEnabled: true,
          authorizationIsCurrent: true),
        "a replacement socket must not inherit the offline provider-warm bypass")
      XCTAssertFalse(
        authority.accepts(
          sourceID: ObjectIdentifier(sourceA),
          currentOwnerID: "owner-b",
          localProfileEnabled: true,
          authorizationIsCurrent: true),
        "an owner transition must revoke the hermetic transport")
      XCTAssertFalse(
        authority.accepts(
          sourceID: ObjectIdentifier(sourceA),
          currentOwnerID: "owner-a",
          localProfileEnabled: false,
          authorizationIsCurrent: true),
        "the capability must not exist outside the local profile")
      XCTAssertFalse(
        authority.accepts(
          sourceID: ObjectIdentifier(sourceA),
          currentOwnerID: "owner-a",
          localProfileEnabled: true,
          authorizationIsCurrent: false),
        "same-UID ABA must not revive a transport from an older authorization generation")
    }

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

    func testWarmGeminiFlushesBufferedScreenFrameWhenTheActivityWindowOpens() async {
      // The PTT-down frame usually finishes encoding before activityStart. It must ride this
      // turn (flushed at activityStart), not wait for a reconnect that never comes.
      let delegate = RealtimeHubSessionDelegateSpy()
      let session = makeSession(provider: .gemini, delegate: delegate)
      session.markReadyForTesting()
      _ = await session.inputLifecycleSnapshot()

      session.sendVideoFrame(Data([9, 9]), mime: "image/jpeg")
      let buffered = await session.inputLifecycleSnapshot()
      XCTAssertEqual(buffered.pendingVideoFrameCount, 1, "no activity window yet: frame waits")

      session.beginInputTurn()
      let opened = await session.inputLifecycleSnapshot()
      XCTAssertTrue(opened.activityOpen)
      XCTAssertEqual(opened.pendingVideoFrameCount, 0, "activityStart flushes the frame into the turn")
    }

    func testGeminiCommitDropsAFrameThatMissedItsTurnWindow() async {
      // A frame encoded after activityEnd belongs to a finished turn. It must never be
      // carried into the next turn as a stale screen.
      let delegate = RealtimeHubSessionDelegateSpy()
      let session = makeSession(provider: .gemini, delegate: delegate)
      session.markReadyForTesting()
      session.beginInputTurn()
      session.commitInputTurn()
      _ = await session.inputLifecycleSnapshot()

      let finishedTurn = VoiceTurnID()
      session.sendVideoFrame(Data([7]), mime: "image/jpeg", turnID: finishedTurn)
      let late = await session.inputLifecycleSnapshot()
      XCTAssertEqual(late.pendingVideoFrameCount, 1)

      session.beginInputTurn(turnID: VoiceTurnID(), responseID: VoiceResponseID("next"))
      let next = await session.inputLifecycleSnapshot()
      XCTAssertTrue(next.activityOpen)
      XCTAssertEqual(next.pendingVideoFrameCount, 0, "a frame from a finished turn is dropped, not sent")
      XCTAssertFalse(
        session.sentVideoFramesForTesting.contains(Data([7]).base64EncodedString()),
        "the earlier turn's screen never reaches the new turn")
    }

    func testGeminiScreenshotToolResultCarriesPixelsInsideTheMatchingFunctionResponse() throws {
      let descriptor = RealtimeScreenEvidenceDescriptor(
        evidenceID: "evidence-1",
        turnID: VoiceTurnID(try XCTUnwrap(UUID(uuidString: "00000000-0000-0000-0000-000000000001"))),
        capturedAt: Date(timeIntervalSince1970: 1),
        target: .frontmostDisplay,
        frontmostApp: "Codex",
        frontmostBundleID: "com.openai.codex",
        windowID: 1,
        displayID: 1,
        imageByteCount: 3,
        imageDigest: "digest"
      )
      let wire = RealtimeHubSession.geminiToolResponse(
        callId: "call-1",
        name: "screenshot",
        output: "Live screenshot captured just now.",
        screenEvidence: RealtimeScreenEvidenceAttachment(descriptor: descriptor, jpeg: Data([1, 2, 3])))
      let toolResponse = wire["toolResponse"] as? [String: Any]
      let responses = toolResponse?["functionResponses"] as? [[String: Any]]
      let response = try? XCTUnwrap(responses?.first)
      let body = response?["response"] as? [String: Any]
      let imageReference = body?["image"] as? [String: String]
      let evidenceID = body?["evidence_id"] as? String
      let parts = response?["parts"] as? [[String: Any]]
      let inlineData = parts?.first?["inlineData"] as? [String: String]

      XCTAssertEqual(response?["id"] as? String, "call-1")
      XCTAssertEqual(response?["name"] as? String, "screenshot")
      XCTAssertEqual(imageReference?["$ref"], "live-screenshot.jpg")
      XCTAssertEqual(evidenceID, "evidence-1")
      XCTAssertEqual(inlineData?["mimeType"], "image/jpeg")
      XCTAssertEqual(inlineData?["data"], "AQID")
      XCTAssertEqual(inlineData?["displayName"], "live-screenshot.jpg")
    }

    func testGeminiThinkDeeperToolResultPinsTheCanonicalSpokenAnswer() throws {
      let output = #"{"ok":true,"text":"About six weeks.","toolResultEnvelope":{"version":1}}"#
      let wire = RealtimeHubSession.geminiToolResponse(
        callId: "call-1",
        name: HubTool.thinkDeeper.rawValue,
        output: output,
        screenEvidence: nil)
      let toolResponse = try XCTUnwrap(wire["toolResponse"] as? [String: Any])
      let responses = try XCTUnwrap(toolResponse["functionResponses"] as? [[String: Any]])
      let body = try XCTUnwrap(responses.first?["response"] as? [String: Any])

      XCTAssertEqual(body["result"] as? String, output)
      XCTAssertEqual(body["spoken_answer"] as? String, "About six weeks.")
      XCTAssertTrue((body["delivery_instruction"] as? String ?? "").contains("Do not add"))
      XCTAssertTrue((body["delivery_instruction"] as? String ?? "").contains("earlier topic"))
    }

    func testGeminiPostToolContinuationOpensASeparateInternalActivityTurn() {
      let wires = RealtimeHubSession.geminiPostToolContinuationWires()

      XCTAssertEqual(wires.count, 3)
      XCTAssertNotNil((wires[0]["realtimeInput"] as? [String: Any])?["activityStart"])
      XCTAssertEqual(
        (wires[1]["realtimeInput"] as? [String: String])?["text"],
        RealtimeHubSession.geminiPostToolContinuationInstruction)
      XCTAssertNotNil((wires[2]["realtimeInput"] as? [String: Any])?["activityEnd"])
      XCTAssertFalse(
        RealtimeHubSession.geminiPostToolContinuationInstruction.localizedCaseInsensitiveContains("screenshot"),
        "the continuation must work for every synchronous Gemini tool, not only visual evidence")
    }

    func testOpenAIPostToolContinuationCreatesExactlyOneToolDisabledAudioResponse() async {
      let delegate = RealtimeHubSessionDelegateSpy()
      let session = makeSession(provider: .openai, delegate: delegate)
      let identity = RealtimeHubEventIdentity(turnID: VoiceTurnID(), responseID: VoiceResponseID("voice-response"))
      session.markReadyForTesting()
      _ = await session.inputLifecycleSnapshot()
      session.beginInputTurn(turnID: identity.turnID, responseID: identity.responseID)
      _ = await session.inputLifecycleSnapshot()

      let first = await resumePostToolCycle(session, identity: identity)
      let second = await resumePostToolCycle(session, identity: identity)
      let snapshot = await session.inputLifecycleSnapshot()

      XCTAssertEqual(first, .started)
      XCTAssertEqual(second, .alreadyInFlight, "a tool-only cycle gets one bounded continuation, never a retry loop")
      XCTAssertEqual(snapshot.testingResponseCreateCount, 1)
      XCTAssertEqual(snapshot.testingLastResponseToolChoice, "none")
      XCTAssertEqual(snapshot.testingLastResponseInstruction, RealtimeHubSession.openAIPostToolContinuationInstruction)
      XCTAssertFalse(
        RealtimeHubSession.openAIPostToolContinuationInstruction.localizedCaseInsensitiveContains("screenshot"),
        "the continuation must work for every OpenAI tool, not only visual evidence")
    }

    func testPostToolContinuationClassifiesUnavailableAndStaleSessionsWithoutGuessing() async {
      let delegate = RealtimeHubSessionDelegateSpy()
      let unavailable = makeSession(provider: .openai, delegate: delegate)
      let identity = RealtimeHubEventIdentity(turnID: VoiceTurnID(), responseID: VoiceResponseID("voice-response"))
      unavailable.beginInputTurn(turnID: identity.turnID, responseID: identity.responseID)
      _ = await unavailable.inputLifecycleSnapshot()
      let unavailableResult = await resumePostToolCycle(unavailable, identity: identity)
      XCTAssertEqual(
        unavailableResult,
        .transportUnavailable)

      let active = makeSession(provider: .openai, delegate: delegate)
      active.markReadyForTesting()
      _ = await active.inputLifecycleSnapshot()
      active.beginInputTurn(turnID: identity.turnID, responseID: identity.responseID)
      _ = await active.inputLifecycleSnapshot()
      let staleResult = await resumePostToolCycle(
        active,
        identity: RealtimeHubEventIdentity(turnID: VoiceTurnID(), responseID: VoiceResponseID("replacement")))
      XCTAssertEqual(
        staleResult,
        .stale)
    }

    func testScreenToolWireFailureTerminatesInsteadOfLeavingAReceiptPending() async {
      let delegate = RealtimeHubSessionDelegateSpy()
      let session = makeSession(provider: .openai, delegate: delegate)
      let attachment = RealtimeScreenEvidenceAttachment(
        descriptor: RealtimeScreenEvidenceDescriptor(
          evidenceID: "evidence-no-transport",
          turnID: VoiceTurnID(),
          capturedAt: Date(),
          target: .frontmostDisplay,
          frontmostApp: "Codex",
          frontmostBundleID: "com.openai.codex",
          windowID: 1,
          displayID: 1,
          imageByteCount: 3,
          imageDigest: "digest"),
        jpeg: Data([1, 2, 3]))
      var wireEnqueued: Bool?

      session.sendToolResult(
        callId: "screenshot-call",
        name: HubTool.screenshot.rawValue,
        output: "Live screenshot captured just now.",
        screenEvidence: attachment,
        onWireEnqueued: { result in
          Task { @MainActor in wireEnqueued = result }
        })

      _ = await session.inputLifecycleSnapshot()
      for _ in 0..<100 where wireEnqueued == nil || delegate.errors.isEmpty {
        await Task.yield()
      }
      XCTAssertEqual(wireEnqueued, false)
      XCTAssertEqual(delegate.errors, ["Realtime transport is not connected."])
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

    func testBackgroundAgentContextDoesNotBufferBeforeTransportIsReady() async {
      // Exactly-once contract: a completion must never be marked delivered while
      // it is only sitting in an in-memory buffer that stop()/close() would drop.
      // sendBackgroundAgentContext must therefore refuse (return false) instead of
      // buffering when the session cannot deliver right now.
      let delegate = RealtimeHubSessionDelegateSpy()
      let session = makeSession(provider: .openai, delegate: delegate)

      let acceptedBeforeReady = await session.sendBackgroundAgentContext("agent finished")
      let coldSnapshot = await session.inputLifecycleSnapshot()
      XCTAssertEqual(acceptedBeforeReady, .retry, "a closed socket must not accept background context")
      XCTAssertEqual(coldSnapshot.pendingTextInputCount, 0, "background context must not be buffered")

      session.markReadyForTesting()
      let acceptedWhenReady = await session.sendBackgroundAgentContext("agent finished")
      let readySnapshot = await session.inputLifecycleSnapshot()
      XCTAssertEqual(acceptedWhenReady, .delivered, "an open OpenAI session accepts background context immediately")
      XCTAssertEqual(readySnapshot.pendingTextInputCount, 0, "an accepted send leaves nothing buffered")
      XCTAssertEqual(
        readySnapshot.testingLastConversationItemRole, "system",
        "background context must never impersonate a user utterance")
    }

    func testTrustedTurnInstructionRefusesWhenTheSessionCannotAcceptContext() async {
      let delegate = RealtimeHubSessionDelegateSpy()
      let session = makeSession(provider: .openai, delegate: delegate)

      let refusedWhileCold = await session.sendTrustedTurnInstruction("TURN INSTRUCTION")
      XCTAssertFalse(refusedWhileCold, "a closed socket must refuse a trusted turn instruction")

      session.markReadyForTesting()
      let acceptedWhenReady = await session.sendTrustedTurnInstruction("TURN INSTRUCTION")
      XCTAssertTrue(acceptedWhenReady, "an open OpenAI session accepts a trusted turn instruction")
    }

    func testGeminiTrustedTurnInstructionRefusesWithoutAnActivityWindow() async {
      let delegate = RealtimeHubSessionDelegateSpy()
      let session = makeSession(provider: .gemini, delegate: delegate)
      session.markReadyForTesting()

      let accepted = await session.sendTrustedTurnInstruction("TURN INSTRUCTION")
      XCTAssertFalse(accepted, "Gemini must refuse a trusted instruction with no activity window")
    }

    func testTrustedTurnInstructionUsesOpenAIResponseCreateInstructions() async {
      let delegate = RealtimeHubSessionDelegateSpy()
      let session = makeSession(provider: .openai, delegate: delegate)
      session.markReadyForTesting()
      _ = await session.inputLifecycleSnapshot()

      let accepted = await session.sendTrustedTurnInstruction("TURN INSTRUCTION")
      XCTAssertTrue(accepted, "an open OpenAI session accepts a trusted instruction by parking it")
      let parked = await session.inputLifecycleSnapshot()
      XCTAssertNil(
        parked.testingLastResponseInstruction,
        "parking must not send response.create yet")
      XCTAssertNil(
        parked.testingLastConversationItemRole,
        "a trusted instruction must not be a durable conversation item")

      session.commitInputTurn()
      let committed = await session.inputLifecycleSnapshot()
      XCTAssertEqual(committed.testingResponseCreateCount, 1)
      XCTAssertEqual(committed.testingLastResponseInstruction, "TURN INSTRUCTION")
      XCTAssertNil(
        committed.testingLastConversationItemRole,
        "response.create instructions must not create a system conversation item")
    }

    func testGeminiFlushesAParkedTrustedInstructionBeforeAPendingCommitClosesTheWindow() async {
      let delegate = RealtimeHubSessionDelegateSpy()
      let session = makeSession(provider: .gemini, delegate: delegate)
      session.markReadyForTesting()
      _ = await session.inputLifecycleSnapshot()

      let refusedWhileIdle = await session.sendTrustedTurnInstruction("TURN INSTRUCTION")
      XCTAssertFalse(refusedWhileIdle)

      session.commitInputTurn()
      session.beginInputTurn()
      let committed = await session.inputLifecycleSnapshot()
      XCTAssertEqual(
        committed.testingLastRealtimeInputText, "TURN INSTRUCTION",
        "the parked instruction must land inside the activity window before activityEnd")
      XCTAssertFalse(committed.activityOpen)
      XCTAssertFalse(committed.pendingCommit)

      let replay = await session.sendTrustedTurnInstruction("TURN INSTRUCTION")
      XCTAssertTrue(replay, "a flushed instruction is confirmed on retry without a second send")
    }

    func testGeminiBackgroundAgentContextIsUnsupportedWithoutWritingUserInput() async {
      // Gemini can only accept text inside an open activity window; without one,
      // sendTextInput would buffer. Background context must instead refuse so the
      // caller keeps its checkpoint unadvanced and retries when a window opens.
      let delegate = RealtimeHubSessionDelegateSpy()
      let session = makeSession(provider: .gemini, delegate: delegate)
      session.markReadyForTesting()

      let accepted = await session.sendBackgroundAgentContext("agent finished")
      let snapshot = await session.inputLifecycleSnapshot()

      XCTAssertFalse(snapshot.activityOpen)
      XCTAssertEqual(accepted, .unsupported, "Gemini has no safe mid-session system-context channel")
      XCTAssertEqual(snapshot.pendingTextInputCount, 0, "refused background context must not be buffered")
      XCTAssertNil(
        snapshot.testingLastRealtimeInputText, "background text must never enter Gemini's user activity stream")
    }

    func testOpenAITransportCloseImmediatelyMakesSessionNonSendableBeforeControllerTeardown() async {
      let delegate = RealtimeHubSessionDelegateSpy()
      let session = makeSession(provider: .openai, delegate: delegate)
      session.markReadyForTesting()
      _ = await session.inputLifecycleSnapshot()
      let transport = URLSession.shared.webSocketTask(with: URL(string: "wss://example.com")!)

      session.urlSession(URLSession.shared, webSocketTask: transport, didCloseWith: .normalClosure, reason: nil)

      let closed = await session.inputLifecycleSnapshot()
      XCTAssertFalse(
        closed.isOpen, "a closed transport must become non-sendable before its controller handles the error")
    }

    func testTerminalOpenAISessionDoesNotResurrectFromLateReadiness() async {
      let delegate = RealtimeHubSessionDelegateSpy()
      let session = makeSession(provider: .openai, delegate: delegate)
      let transport = URLSession.shared.webSocketTask(with: URL(string: "wss://example.com")!)

      session.sendAudio(Data([1, 2, 3, 4]))
      session.commitInputTurn()
      let buffered = await session.inputLifecycleSnapshot()
      XCTAssertEqual(buffered.pendingAudioChunkCount, 1)
      XCTAssertTrue(buffered.pendingCommit)

      session.urlSession(URLSession.shared, webSocketTask: transport, didCloseWith: .normalClosure, reason: nil)
      _ = await session.inputLifecycleSnapshot()
      await session.receiveOpenAIEventForTesting(["type": "session.updated"])
      await Task.yield()

      let afterLateReadiness = await session.inputLifecycleSnapshot()
      XCTAssertFalse(afterLateReadiness.isOpen)
      XCTAssertEqual(afterLateReadiness.pendingAudioChunkCount, 1, "a terminal session must not flush buffered audio")
      XCTAssertTrue(afterLateReadiness.pendingCommit, "a terminal session must not commit buffered input")
      XCTAssertEqual(delegate.connectCount, 0, "a terminal session must not report a late connection")
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

    func testGeminiBackgroundAgentContextRemainsUnsupportedWhenInputWindowOpens() async {
      let delegate = RealtimeHubSessionDelegateSpy()
      let session = makeSession(provider: .gemini, delegate: delegate)
      session.markReadyForTesting()

      // Warm but idle (no activity window): must REFUSE — return false, never
      // buffer-and-report-success. A buffered completion is dropped by
      // stopOnQueue/abandonInputTurn, so reporting success would advance the
      // exactly-once checkpoint on a completion that is then lost.
      let refusedWhileIdle = await session.sendBackgroundAgentContext("agent finished")
      XCTAssertEqual(refusedWhileIdle, .unsupported)

      // A user turn opening the activity window cannot make the same realtime-input
      // channel safe for unrelated background text.
      session.beginInputTurn()
      let refusedAfterWindow = await session.sendBackgroundAgentContext("agent finished")
      let snapshot = await session.inputLifecycleSnapshot()
      XCTAssertEqual(refusedAfterWindow, .unsupported)
      XCTAssertNil(
        snapshot.testingLastRealtimeInputText,
        "opening a user input window must not turn background output into a competing user message")
    }

    func testBackgroundAgentContextReturnsRetryWhenTheConfirmedSendFails() async {
      let delegate = RealtimeHubSessionDelegateSpy()
      let session = makeSession(provider: .openai, delegate: delegate)
      session.markReadyForTesting()

      // The checkpoint advances on this `true`, so `true` must mean confirmed
      // delivery: a failed provider send must report retry, not fire-and-forget.
      session.setTestingForcedSendError(RealtimeHubSessionTestError.forced)
      let failedSend = await session.sendBackgroundAgentContext("agent finished")
      XCTAssertEqual(failedSend, .retry)

      session.setTestingForcedSendError(nil)
      let confirmedSend = await session.sendBackgroundAgentContext("agent finished")
      XCTAssertEqual(confirmedSend, .delivered)
    }

    private func makeSession(
      provider: RealtimeHubProvider,
      delegate: RealtimeHubSessionDelegate,
      rawWebSocketFactory: @escaping (URL, DispatchQueue) -> RealtimeRawWebSocketTransport = {
        RawWebSocket(url: $0, queue: $1)
      }
    ) -> RealtimeHubSession {
      RealtimeHubSession(
        provider: provider,
        auth: .byokKey("fixture"),
        instructions: "fixture",
        rawWebSocketFactory: rawWebSocketFactory,
        delegate: delegate)
    }

    private func resumePostToolCycle(
      _ session: RealtimeHubSession,
      identity: RealtimeHubEventIdentity
    ) async -> RealtimePostToolContinuationStartResult {
      await withCheckedContinuation { continuation in
        session.resumeAfterToolOnlyCycle(identity: identity) { continuation.resume(returning: $0) }
      }
    }
  }

  private enum RealtimeHubSessionTestError: Error { case forced }

  @MainActor
  private final class RealtimeHubSessionDelegateSpy: RealtimeHubSessionDelegate {
    private(set) var connectCount = 0
    private(set) var errors: [String] = []
    var onConnect: (() -> Void)?
    var onError: ((RealtimeHubTransportFailure) -> Void)?

    func hubDidConnect(source: RealtimeHubSession) {
      connectCount += 1
      onConnect?()
    }
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
    func hubDidError(_ failure: RealtimeHubTransportFailure, source: RealtimeHubSession) {
      errors.append(failure.message)
      onError?(failure)
    }
  }

  private final class RealtimeTransportTracker: @unchecked Sendable {
    private let lock = NSLock()
    private var live = 0
    private var maximum = 0

    var liveCount: Int {
      lock.withLock { live }
    }

    var maximumLiveCount: Int {
      lock.withLock { maximum }
    }

    func opened() {
      lock.withLock {
        live += 1
        maximum = max(maximum, live)
      }
    }

    func closed() {
      lock.withLock {
        live -= 1
      }
    }
  }

  private final class ControllableRealtimeRawWebSocket: RealtimeRawWebSocketTransport,
    @unchecked Sendable
  {
    var onOpen: (() -> Void)?
    var onMessage: ((Data) -> Void)?
    var onClose: ((Int, String) -> Void)?
    var onError: ((RealtimeRawWebSocketFailure) -> Void)?
    var onInputAccepted: (() -> Void)?
    private(set) var closeRequested = false

    private let queue: DispatchQueue
    private let tracker: RealtimeTransportTracker
    private var open = false
    private var setupCompleted = false
    private var closeWaiters: [CheckedContinuation<Void, Never>] = []

    init(queue: DispatchQueue, tracker: RealtimeTransportTracker) {
      self.queue = queue
      self.tracker = tracker
    }

    func connect() {
      open = true
      tracker.opened()
      onOpen?()
    }

    func sendText(_ text: String, completion: (@Sendable (Error?) -> Void)?) {
      guard open else {
        completion?(NSError(domain: NSPOSIXErrorDomain, code: Int(POSIXErrorCode.ENOTCONN.rawValue)))
        return
      }
      completion?(nil)
      if !setupCompleted {
        setupCompleted = true
        onMessage?(Data(#"{"setupComplete":{}}"#.utf8))
      } else if text.contains(#""realtimeInput""#) {
        onInputAccepted?()
        onInputAccepted = nil
      }
    }

    func close() {
      closeRequested = true
    }

    func closeAndWait() async {
      await withCheckedContinuation { continuation in
        queue.async { [weak self] in
          guard let self else {
            continuation.resume()
            return
          }
          self.closeRequested = true
          if !self.open {
            continuation.resume()
          } else {
            self.closeWaiters.append(continuation)
          }
        }
      }
    }

    func acknowledgeClose() {
      queue.async { [weak self] in
        guard let self, self.open else { return }
        self.open = false
        self.tracker.closed()
        let waiters = self.closeWaiters
        self.closeWaiters.removeAll()
        for waiter in waiters {
          waiter.resume()
        }
      }
    }

    func fail(_ error: Error) {
      queue.async { [weak self] in
        self?.onError?(
          RealtimeRawWebSocketFailure(
            phase: .receive,
            message: "receive failed",
            underlyingError: error))
      }
    }
  }
#endif
