import VoiceTurnDomain
import XCTest

@testable import Omi_Computer

@MainActor
final class FirstRunPTTAccountingTests: XCTestCase {
  private final class ObservationCounter: @unchecked Sendable {
    var value = 0
  }

  private let ownerID = "first-run-ptt-accounting-owner"
  private var ownerFixture: RuntimeOwnerAuthorityTestFixture?

  override func setUp() async throws {
    let fixture = RuntimeOwnerAuthorityTestFixture()
    ownerFixture = fixture
    await fixture.establish(authOwnerID: ownerID)
    VoiceTurnCoordinator.shared.reset()
  }

  override func tearDown() async throws {
    let manager = PushToTalkManager.shared
    manager.cleanup()
    manager.configureVoiceTurnCoordinator(barState: FloatingControlBarState())
    VoiceTurnCoordinator.shared.reset()
    await ownerFixture?.restore()
    ownerFixture = nil
  }

  func testTooShortSilentRejectionProducesNoCompletionObservation() {
    let counter = ObservationCounter()
    let observation = observeCompletions(counter)
    defer { NotificationCenter.default.removeObserver(observation) }

    let settings = ShortcutSettings.shared
    let previousMode = settings.pttTranscriptionMode
    let previousOverride = settings.pttTranscriptionModeDemoOverride
    let previousSounds = settings.pttSoundsEnabled
    let previousMute = settings.pttMuteSystemAudio
    defer {
      settings.pttTranscriptionMode = previousMode
      settings.pttTranscriptionModeDemoOverride = previousOverride
      settings.pttSoundsEnabled = previousSounds
      settings.pttMuteSystemAudio = previousMute
    }
    settings.pttTranscriptionMode = .batch
    settings.pttTranscriptionModeDemoOverride = nil
    settings.pttSoundsEnabled = false
    settings.pttMuteSystemAudio = false

    let started = PushToTalkManager.shared.beginPushToTalkForAutomation()
    XCTAssertEqual(started["listening"], "true")
    let ended = PushToTalkManager.shared.endPushToTalkForAutomation()

    XCTAssertEqual(ended["finalized"], "true")
    XCTAssertEqual(VoiceTurnCoordinator.shared.model.lastTerminal?.reason, .tooShort)
    XCTAssertEqual(counter.value, 0)
  }

  func testCommittedNonemptyTranscriptProducesOneCompletionObservation() async throws {
    let count = try await runAcceptedRealtimeTurn(duplicateCompletionCallback: false)

    XCTAssertEqual(count, 1)
  }

  func testRealtimeCompletionAndJournalAcceptanceTogetherStillProduceOneObservation() async throws {
    let count = try await runAcceptedRealtimeTurn(duplicateCompletionCallback: true)

    XCTAssertEqual(count, 1)
  }

  private func runAcceptedRealtimeTurn(duplicateCompletionCallback: Bool) async throws -> Int {
    let coordinator = VoiceTurnCoordinator.shared
    coordinator.reset()
    let controller = RealtimeHubController()
    let sessionID = VoiceSessionID()
    let responseID = VoiceResponseID("first-run-accounting-response")
    let session = RealtimeHubSession(
      provider: .openai,
      auth: .byokKey("fixture"),
      instructions: "fixture",
      delegate: controller)
    controller.session = session
    controller.sessionProvider = .openai
    controller.voiceSessionID = sessionID
    controller.voiceResponseID = responseID
    controller.sessionOwnerBinding = .init(
      sourceID: ObjectIdentifier(session),
      ownerScope: .authenticated(ownerID))

    let turnID = RealtimeAutomationTurnHarness.begin(on: coordinator)
    coordinator.publish(.selectRoute(turnID: turnID, route: .hub(sessionID: sessionID)))
    coordinator.publish(.finalize(turnID: turnID))
    coordinator.publish(
      .hubCommitAccepted(
        turnID: turnID,
        sessionID: sessionID,
        responseID: responseID))
    let providerIdentity = try XCTUnwrap(coordinator.activeTurn?.providerEffectIdentity)
    coordinator.publish(
      .providerResponseStartedScoped(
        turnID: turnID,
        identity: providerIdentity,
        sessionID: sessionID,
        responseID: responseID))

    controller.turnTranscript = "Ship the onboarding proof"
    controller.providerTranscriptFinalized = true
    controller.assistantText = "Done"
    controller.turnIdempotencyKey = "voice:\(turnID.rawValue.uuidString.lowercased())"
    controller.prefetchedVoiceContextTurnIDs = KernelTurnProjection.stableTurnIDs(
      continuityKey: controller.turnIdempotencyKey)

    let terminal = expectation(description: "journal acceptance terminalized the realtime turn")
    let snapshot = coordinator.observeSnapshots { model in
      guard model.lastTerminal?.turnID == turnID, model.lastTerminal?.reason == .success else { return }
      terminal.fulfill()
    }
    defer { snapshot.cancel() }
    coordinator.setEffectHandler { effect in
      guard case .finalizeJournal(let finalizedTurnID, let identity) = effect else { return }
      controller.finalizeJournal(turnID: finalizedTurnID, identity: identity)
    }

    let counter = ObservationCounter()
    let observation = observeCompletions(counter)
    defer { NotificationCenter.default.removeObserver(observation) }
    let eventIdentity = RealtimeHubEventIdentity(turnID: turnID, responseID: responseID)

    controller.hubDidFinishTurn(identity: eventIdentity, source: session)
    if duplicateCompletionCallback {
      controller.hubDidFinishTurn(identity: eventIdentity, source: session)
    }
    await controller.awaitTurnPersistenceFence()
    await fulfillment(of: [terminal], timeout: 1)

    XCTAssertEqual(coordinator.model.lastTerminal?.reason, .success)
    return counter.value
  }

  private func observeCompletions(_ counter: ObservationCounter) -> NSObjectProtocol {
    NotificationCenter.default.addObserver(
      forName: .firstRunVoiceTurnCompleted,
      object: nil,
      queue: nil
    ) { _ in
      counter.value += 1
    }
  }
}
