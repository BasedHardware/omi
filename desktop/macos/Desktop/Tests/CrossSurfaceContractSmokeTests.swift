import AppKit
import XCTest

@testable import Omi_Computer

/// Fast, deterministic contract coverage that joins the production seams shared
/// by main chat, realtime voice, and the floating-bar presentation.  Keep this
/// suite independent of the app process: network, TCC, audio capture, and
/// wall-clock deadlines belong to their respective integration suites.
@MainActor
final class CrossSurfaceContractSmokeTests: XCTestCase {
  private let reducer = VoiceTurnReducer()

  func testSharedChatIdentityContextAndJournalAdmissionStayCanonical() async throws {
    let provider = ChatProvider()
    let main = provider.mainChatSurfaceReference()
    let voice = main.realtimeVoiceCompanion()
    XCTAssertEqual(voice.externalRefKind, main.externalRefKind)
    XCTAssertEqual(voice.externalRefId, main.externalRefId)

    let typedRevision = try AgentContextRevision.make(
      source: .surface,
      payload: ["conversationId": main.externalRefId, "sessionId": "session-contract"],
      outcome: .available
    )
    let voiceRevision = try AgentContextRevision.make(
      source: .surface,
      payload: ["conversationId": voice.externalRefId, "sessionId": "session-contract"],
      outcome: .available
    )
    XCTAssertEqual(voiceRevision, typedRevision)

    let snapshot = KernelVoiceContextSnapshot(
      sessionId: "session-contract",
      conversationId: main.externalRefId,
      context: "",
      freshnessIdentity: typedRevision,
      turnIDs: ["typed-turn", "voice-turn"]
    )
    XCTAssertTrue(snapshot.isResolved)

    let continuityKey = "cross-surface:turn-1"
    let userID = KernelTurnProjection.stableTurnID(continuityKey: continuityKey, role: "user")
    let assistantID = KernelTurnProjection.stableTurnID(
      continuityKey: continuityKey,
      role: "assistant"
    )
    let userTurn = try journalTurn(
      surface: main,
      turnID: userID,
      sequence: 1,
      role: "user",
      content: "Typed and voice share this history"
    )
    let assistantTurn = try journalTurn(
      surface: voice,
      turnID: assistantID,
      sequence: 2,
      role: "assistant",
      content: "One canonical exchange."
    )
    let admitted = await provider.admitJournalExchange(
      continuityKey: continuityKey,
      userText: "Typed and voice share this history",
      assistantText: "One canonical exchange."
    ) {
      provider.projectJournalTurn(userTurn)
      provider.projectJournalTurn(assistantTurn)
      return true
    }

    XCTAssertEqual(admitted.user?.id, userID)
    XCTAssertEqual(admitted.assistant?.id, assistantID)
    XCTAssertEqual(provider.messages.map(\.id), [userID, assistantID])

    // A replay of the same canonical turn IDs cannot duplicate a visible row.
    provider.projectJournalTurn(try journalTurn(
      surface: voice,
      turnID: assistantID,
      sequence: 3,
      role: "assistant",
      content: "One canonical exchange."
    ))
    XCTAssertEqual(provider.messages.map(\.id), [userID, assistantID])
  }

  func testThreePTTTurnsReconnectBargeAndTypingPreserveSingleCommit() throws {
    var model = VoiceTurnModel.idle

    let first = VoiceTurnID()
    model = startHubTurn(model, turnID: first, sessionID: VoiceSessionID())
    model = try claimAndCompleteHubTurn(model, turnID: first)
    XCTAssertEqual(model.turn?.phase, .terminal(.success))
    XCTAssertEqual(model.turn?.projection, .idle)
    model = reducer.reduce(model, .reset).model

    // Reconnect while the second physical PTT release is finalizing. The
    // reconnection must not make the delayed hub commit illegal.
    let second = VoiceTurnID()
    let originalSession = VoiceSessionID()
    model = startHubTurn(model, turnID: second, sessionID: originalSession)
    let reconnectReservation = reserveIdentity(model, turnID: second)
    model = reconnectReservation.model
    let reconnect = reducer.reduce(
      model,
      .providerReconnectStarted(
        turnID: second,
        identity: reconnectReservation.identity,
        previousSessionID: originalSession
      )
    )
    model = reconnect.model
    XCTAssertEqual(model.turn?.phase, .finalizing)
    let reconnectedSession = VoiceSessionID()
    model = reducer.reduce(
      model,
      .providerReconnected(
        turnID: second,
        identity: reconnectReservation.identity,
        sessionID: reconnectedSession
      )
    ).model
    XCTAssertEqual(model.turn?.phase, .finalizing)
    XCTAssertEqual(model.turn?.sessionID, reconnectedSession)
    model = try claimAndCompleteHubTurn(model, turnID: second)
    XCTAssertEqual(model.turn?.phase, .terminal(.success))
    model = reducer.reduce(model, .reset).model

    // The third turn barges into an active response, then normal typing leaves
    // the started PTT turn intact instead of cancelling it.
    let interrupted = VoiceTurnID()
    let interruptedSession = VoiceSessionID()
    model = startHubTurn(model, turnID: interrupted, sessionID: interruptedSession)
    model = claimHubTurn(model, turnID: interrupted)
    model = reducer.reduce(
      model,
      .hubCommitAccepted(turnID: interrupted, sessionID: interruptedSession, responseID: nil)
    ).model
    XCTAssertEqual(model.turn?.phase, .awaitingResponse)
    XCTAssertTrue(PushToTalkManager.admitsListeningStart(activeTurnID: interrupted, phase: .awaitingResponse))

    var shortcutGate = ModifierOnlyPTTActivationGate()
    XCTAssertEqual(shortcutGate.modifierStateChanged(isShortcutActive: true), .scheduleStart)
    XCTAssertTrue(shortcutGate.consumePendingStart())

    let third = VoiceTurnID()
    model = reducer.reduce(model, .start(turnID: third, ownerID: nil, intent: .hold)).model
    XCTAssertEqual(model.lastTerminal?.reason, .interruptedByBargeIn)
    XCTAssertEqual(model.turn?.id, third)
    XCTAssertEqual(model.turn?.phase, .recording)
    XCTAssertEqual(shortcutGate.nonModifierKeyPressed(), .none)
    XCTAssertTrue(shortcutGate.hasStartedTurn)

    let thirdSession = VoiceSessionID()
    model = reducer.reduce(
      model,
      .selectRoute(turnID: third, route: .hub(sessionID: thirdSession))
    ).model
    model = reducer.reduce(model, .finalize(turnID: third)).model
    model = try claimAndCompleteHubTurn(model, turnID: third)
    XCTAssertEqual(model.turn?.phase, .terminal(.success))
    XCTAssertEqual(model.turn?.projection, .idle)
  }

  func testTerminalRuntimeProjectionFailsClosedAndNotchChromeStaysPinned() throws {
    let store = AgentRuntimeStatusStore()
    let surface = AgentSurfaceReference.floatingPill(pillId: UUID())
    let failure = try XCTUnwrap(AgentRuntimeProcess.RuntimeMessage.parse(
      #"{"type":"error","protocolVersion":2,"sessionId":"session-contract","runId":"run-contract","message":"failed","failure":{"code":"provider_failed","source":"adapter_process","userMessage":"Provider failed"}}"#
    ))
    let staleDelta = try XCTUnwrap(AgentRuntimeProcess.RuntimeMessage.parse(
      #"{"type":"text_delta","protocolVersion":2,"sessionId":"session-contract","runId":"run-contract","delta":"late"}"#
    ))
    store.ingest(message: failure, surface: surface)
    store.ingest(message: staleDelta, surface: surface)
    XCTAssertEqual(store.projection(for: surface)?.status, .failed)
    XCTAssertEqual(store.projection(for: surface)?.errorMessage, "Provider failed")
    XCTAssertEqual(store.floatingPillProjections().compactMap(\.runId), ["run-contract"])

    let screen = NSRect(x: 1_920, y: -100, width: 1_728, height: 1_117)
    let transient = NSRect(x: 2_637, y: 959, width: 351, height: 58)
    let placement = FloatingControlBarGeometry.SurfacePlacement.notch(screenFrame: screen)
    for transition in [
      FloatingControlBarGeometry.SurfaceTransition.pushToTalk(expanded: true),
      .agentSwitcher(visible: true),
      .agentSwitcher(visible: false),
    ] {
      let frame = FloatingControlBarGeometry.surfaceTransitionFrame(
        currentFrame: transient,
        targetSize: NSSize(width: 430, height: 180),
        transition: transition,
        placement: placement
      )
      XCTAssertEqual(frame.midX, screen.midX, accuracy: 0.5)
      XCTAssertEqual(frame.maxY, screen.maxY, accuracy: 0.5)
    }
    for progress in [CGFloat(0), 0.5, 1] {
      XCTAssertEqual(
        NotchChromeLayout.width(
          chromeWidth: 268,
          expandedWidth: 900,
          switcherProgress: progress,
          isChatPresented: true
        ),
        268
      )
    }
  }

  private func startHubTurn(
    _ initial: VoiceTurnModel,
    turnID: VoiceTurnID,
    sessionID: VoiceSessionID
  ) -> VoiceTurnModel {
    var model = reducer.reduce(initial, .start(turnID: turnID, ownerID: nil, intent: .hold)).model
    model = reducer.reduce(model, .selectRoute(turnID: turnID, route: .hub(sessionID: sessionID))).model
    return reducer.reduce(model, .finalize(turnID: turnID)).model
  }

  private func claimHubTurn(_ initial: VoiceTurnModel, turnID: VoiceTurnID) -> VoiceTurnModel {
    let claim = reducer.reduce(initial, .hubCommitClaimed(turnID: turnID))
    XCTAssertTrue(claim.effects.contains(.commitClaimedHubInput(turnID: turnID)))
    let duplicate = reducer.reduce(claim.model, .hubCommitClaimed(turnID: turnID))
    XCTAssertEqual(duplicate.model.invalidTransitionCount, 1)
    XCTAssertFalse(duplicate.effects.contains(.commitClaimedHubInput(turnID: turnID)))
    return claim.model
  }

  private func claimAndCompleteHubTurn(_ initial: VoiceTurnModel, turnID: VoiceTurnID) throws -> VoiceTurnModel {
    var model = claimHubTurn(initial, turnID: turnID)
    guard case .hub(let routedSessionID) = model.turn?.route else {
      XCTFail("Claimed hub input must retain its canonical route")
      return model
    }
    let sessionID = try XCTUnwrap(routedSessionID)
    model = reducer.reduce(
      model,
      .hubCommitAccepted(turnID: turnID, sessionID: sessionID, responseID: nil)
    ).model
    let providerIdentity = try XCTUnwrap(model.turn?.providerEffectIdentity)
    model = reducer.reduce(
      model,
      .providerTurnFinishedScoped(
        turnID: turnID,
        identity: providerIdentity,
        sessionID: sessionID,
        responseID: nil
      )
    ).model
    guard case .writing(let journalIdentity) = model.turn?.journalFinalization else {
      XCTFail("Provider completion must open the journal fence")
      return model
    }
    return reducer.reduce(
      model,
      .journalAccepted(turnID: turnID, identity: journalIdentity)
    ).model
  }

  private func reserveIdentity(
    _ model: VoiceTurnModel,
    turnID: VoiceTurnID
  ) -> (model: VoiceTurnModel, identity: VoiceEffectIdentity) {
    let effectID = model.turn?.nextEffectID ?? 0
    return (
      reducer.reduce(model, .effectIdentityReserved(turnID: turnID)).model,
      VoiceEffectIdentity(turnID: turnID, effectID: effectID)
    )
  }

  private func journalTurn(
    surface: AgentSurfaceReference,
    turnID: String,
    sequence: Int,
    role: String,
    content: String
  ) throws -> KernelJournalTurn {
    try XCTUnwrap(KernelJournalTurn(dictionary: [
      "conversationId": surface.externalRefId,
      "turnId": turnID,
      "turnSeq": sequence,
      "conversationGeneration": 1,
      "generationBaseTurnSeq": 0,
      "producerId": "producer:\(turnID)",
      "payloadHash": "sha256:\(turnID)",
      "role": role,
      "surfaceKind": surface.surfaceKind,
      "externalRefKind": surface.externalRefKind,
      "externalRefId": surface.externalRefId,
      "content": content,
      "createdAtMs": sequence,
      "updatedAtMs": sequence,
      "origin": role == "user" ? "typed_chat" : "realtime_voice",
      "status": "completed",
      "contentBlocks": [],
      "resources": [],
      "metadataJson": "{}",
    ], surfaceFallback: surface))
  }
}
