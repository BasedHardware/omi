import VoiceTurnDomain
import XCTest

@testable import Omi_Computer

final class RealtimeHubSessionHandoffPolicyTests: XCTestCase {
  @MainActor
  func testPhysicalReplacementGateDrainsBeforeStartingAndCoalescesDuplicates() async {
    let gate = RealtimeHubTransportReplacementGate()
    let stopEntered = expectation(description: "old transport stop entered")
    let replacementStarted = expectation(description: "replacement started")
    var releaseStop: CheckedContinuation<Void, Never>?
    var events: [String] = []

    XCTAssertTrue(
      gate.replace(
        stop: {
          events.append("stop")
          stopEntered.fulfill()
          await withCheckedContinuation { releaseStop = $0 }
          events.append("drained")
        },
        start: {
          events.append("start")
          replacementStarted.fulfill()
        }))
    await fulfillment(of: [stopEntered], timeout: 1)

    XCTAssertFalse(
      gate.replace(
        stop: { XCTFail("coalesced replacement must not stop twice") },
        start: { XCTFail("coalesced replacement must not start twice") }))
    XCTAssertEqual(events, ["stop"])

    releaseStop?.resume()
    await fulfillment(of: [replacementStarted], timeout: 1)
    XCTAssertEqual(events, ["stop", "drained", "start"])
    XCTAssertFalse(gate.isPending)
  }

  @MainActor
  func testPhysicalReplacementGateCancellationStillWaitsForDrainAndNeverStarts() async {
    let gate = RealtimeHubTransportReplacementGate()
    let stopEntered = expectation(description: "stop entered")
    let gateBecameIdle = expectation(description: "gate became idle")
    var releaseStop: CheckedContinuation<Void, Never>?
    var startCount = 0

    XCTAssertTrue(
      gate.replace(
        stop: {
          stopEntered.fulfill()
          await withCheckedContinuation { releaseStop = $0 }
        },
        start: { startCount += 1 }))
    await fulfillment(of: [stopEntered], timeout: 1)
    Task {
      await gate.waitUntilIdle()
      gateBecameIdle.fulfill()
    }

    gate.cancel()
    XCTAssertTrue(gate.isPending, "cancellation cannot advertise idle before physical drain")
    XCTAssertEqual(startCount, 0)
    releaseStop?.resume()
    await fulfillment(of: [gateBecameIdle], timeout: 1)
    XCTAssertFalse(gate.isPending)
    XCTAssertEqual(startCount, 0)
  }

  @MainActor
  func testCancelTurnWaitsForTransportAcknowledgementBeforeControllerRewarm() async throws {
    let controller = RealtimeHubController()
    let fixture = try await installDelayedTransport(on: controller, ownerScope: .signedOut)
    let rewarmed = expectation(description: "controller rewarmed")
    controller.testingWarmAfterDrain = { rewarmed.fulfill() }
    let coordinator = VoiceTurnCoordinator.shared
    coordinator.reset()
    let turnID = RealtimeAutomationTurnHarness.begin(on: coordinator)

    XCTAssertTrue(controller.cancelTurn(turnID: turnID))
    await Task.yield()
    XCTAssertTrue(controller.sessionReplacementGate.isPending)
    XCTAssertEqual(fixture.tracker.liveCount, 1)

    fixture.transport.acknowledgeClose()
    await fulfillment(of: [rewarmed], timeout: 1)
    XCTAssertEqual(fixture.tracker.liveCount, 0)
    XCTAssertFalse(controller.sessionReplacementGate.isPending)
    coordinator.reset()
  }

  @MainActor
  func testStaleOwnerReadinessWaitsForTransportAcknowledgementBeforeRewarm() async throws {
    let controller = RealtimeHubController()
    let staleOwner = RealtimeHubOwnerScope.authenticated("stale-\(UUID().uuidString)")
    let fixture = try await installDelayedTransport(on: controller, ownerScope: staleOwner)
    let rewarmed = expectation(description: "controller rewarmed")
    controller.testingWarmAfterDrain = { rewarmed.fulfill() }

    XCTAssertFalse(controller.isTransportReady)
    await Task.yield()
    XCTAssertTrue(controller.sessionReplacementGate.isPending)
    XCTAssertEqual(fixture.tracker.liveCount, 1)

    fixture.transport.acknowledgeClose()
    await fulfillment(of: [rewarmed], timeout: 1)
    XCTAssertEqual(fixture.tracker.liveCount, 0)
    XCTAssertNil(controller.session)
  }

  @MainActor
  func testProviderFailoverPreservesChoiceButWaitsForOldTransportAcknowledgement() async throws {
    let controller = RealtimeHubController()
    let fixture = try await installDelayedTransport(on: controller, ownerScope: .signedOut)
    let rewarmed = expectation(description: "alternate provider rewarmed")
    controller.testingWarmAfterDrain = { rewarmed.fulfill() }

    XCTAssertTrue(controller.failoverToAlternateProvider(reason: "other"))
    XCTAssertEqual(controller.fallbackProvider, RealtimeHubSettings.shared.provider.alternate)
    await Task.yield()
    XCTAssertEqual(fixture.tracker.liveCount, 1)
    XCTAssertTrue(controller.sessionReplacementGate.isPending)

    fixture.transport.acknowledgeClose()
    await fulfillment(of: [rewarmed], timeout: 1)
    XCTAssertEqual(fixture.tracker.liveCount, 0)
    XCTAssertNil(controller.session)
  }

  @MainActor
  func testEnsureWarmProviderMismatchWaitsForTransportAcknowledgementBeforeRewarm() async throws {
    let controller = RealtimeHubController()
    let fixture = try await installDelayedTransport(on: controller, ownerScope: .signedOut)
    let rewarmed = expectation(description: "mismatched provider rewarmed")
    controller.testingWarmAfterDrain = { rewarmed.fulfill() }
    controller.fallbackProvider = .openai

    controller.ensureWarm()
    await Task.yield()

    XCTAssertTrue(controller.sessionReplacementGate.isPending)
    XCTAssertEqual(fixture.tracker.liveCount, 1)
    XCTAssertNil(controller.session)

    fixture.transport.acknowledgeClose()
    await fulfillment(of: [rewarmed], timeout: 1)
    XCTAssertEqual(fixture.tracker.liveCount, 0)
    XCTAssertFalse(controller.sessionReplacementGate.isPending)
  }

  @MainActor
  func testBargeInFailoverWaitsForTransportAcknowledgementBeforeSpecializedStart() async throws {
    let defaults = UserDefaults.standard
    let keyName = BYOKProvider.openai.storageKey
    let previousKey = defaults.object(forKey: keyName)
    defaults.set("barge-in-fixture", forKey: keyName)
    defer {
      if let previousKey {
        defaults.set(previousKey, forKey: keyName)
      } else {
        defaults.removeObject(forKey: keyName)
      }
    }

    let controller = RealtimeHubController()
    let fixture = try await installDelayedTransport(on: controller, ownerScope: .signedOut)
    controller.prefetchedVoiceContextOwnerScope = .signedOut
    controller.prefetchedVoiceContextSessionID = "fixture-session"
    controller.prefetchedVoiceContextFreshnessIdentity = "fixture-freshness"
    let turnID = VoiceTurnID()
    let responseID = VoiceResponseID("barge-in-response")
    controller.replacementAudioBuffer = RealtimeReplacementAudioBuffer(
      turnID: turnID,
      responseID: responseID,
      identity: VoiceEffectIdentity(turnID: turnID, effectID: 1))
    controller.voiceResponseID = responseID
    controller.pendingBargeInOwnerScope = .signedOut
    let specializedStart = expectation(description: "specialized replacement started")
    var specializedStartCount = 0
    controller.testingSessionStartAfterDrain = { provider, auth, ownerScope in
      specializedStartCount += 1
      XCTAssertEqual(provider, .openai)
      XCTAssertEqual(ownerScope, .signedOut)
      XCTAssertFalse(auth.isEphemeral)
      specializedStart.fulfill()
      return true
    }

    XCTAssertTrue(controller.failoverBargeInReplacement(from: .gemini, reason: "fixture"))
    await Task.yield()

    XCTAssertTrue(controller.sessionReplacementGate.isPending)
    XCTAssertEqual(fixture.tracker.liveCount, 1)
    XCTAssertEqual(specializedStartCount, 0)
    XCTAssertNotNil(controller.replacementAudioBuffer)

    fixture.transport.acknowledgeClose()
    await fulfillment(of: [specializedStart], timeout: 1)
    XCTAssertEqual(fixture.tracker.liveCount, 0)
    XCTAssertEqual(specializedStartCount, 1)
    XCTAssertNotNil(controller.replacementAudioBuffer)
  }

  @MainActor
  func testDuplicateTransportTerminalCallbacksAndLateStaleCallbackFinishReducerOnce() async throws {
    let controller = RealtimeHubController()
    let fixture = try await installDelayedTransport(on: controller, ownerScope: .signedOut)
    let coordinator = VoiceTurnCoordinator.shared
    coordinator.reset()
    defer { coordinator.reset() }
    let turnID = RealtimeAutomationTurnHarness.begin(on: coordinator)
    let sessionID = try XCTUnwrap(controller.voiceSessionID)
    coordinator.publish(.selectRoute(turnID: turnID, route: .hub(sessionID: sessionID)))
    let terminalized = expectation(description: "reducer terminalized")
    var observedTerminal = false
    let observation = coordinator.observeSnapshots { model in
      guard model.turn?.id == turnID, model.turn?.phase.isTerminal == true,
        !observedTerminal
      else { return }
      observedTerminal = true
      terminalized.fulfill()
    }
    defer { observation.cancel() }

    fixture.transport.emitErrorCloseAndDuplicateError()
    await fulfillment(of: [terminalized], timeout: 1)
    await Task.yield()

    XCTAssertNil(controller.session, "the first terminal callback must fence the source immediately")
    fixture.transport.emitErrorCloseAndDuplicateError()
    await Task.yield()
    let terminals = coordinator.timelineSnapshot().filter {
      $0.turnID == turnID && $0.terminalReason != nil
    }
    XCTAssertEqual(terminals.count, 1)
    XCTAssertEqual(coordinator.model.turn?.phase, .terminal(.providerFailed))

    controller.sessionReplacementGate.cancel()
    fixture.transport.acknowledgeClose()
    await controller.sessionReplacementGate.waitUntilIdle()
  }

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

  @MainActor
  private func installDelayedTransport(
    on controller: RealtimeHubController,
    ownerScope: RealtimeHubOwnerScope
  ) async throws -> (
    transport: DelayedAckRealtimeTransport,
    tracker: DelayedAckTransportTracker
  ) {
    let tracker = DelayedAckTransportTracker()
    var installedTransport: DelayedAckRealtimeTransport?
    let opened = expectation(description: "fixture transport opened")
    let session = RealtimeHubSession(
      provider: .gemini,
      auth: .byokKey("fixture"),
      instructions: "fixture",
      rawWebSocketFactory: { _, queue in
        let transport = DelayedAckRealtimeTransport(queue: queue, tracker: tracker)
        transport.onOpened = { opened.fulfill() }
        installedTransport = transport
        return transport
      },
      delegate: controller)
    controller.session = session
    controller.voiceSessionID = VoiceSessionID()
    controller.sessionProvider = .gemini
    controller.sessionAuth = .byokKey("fixture")
    controller.sessionOwnerBinding = RealtimeHubController.PhysicalSessionOwnerBinding(
      sourceID: ObjectIdentifier(session),
      ownerScope: ownerScope)
    controller.hubConnected = true
    session.start()
    await fulfillment(of: [opened], timeout: 1)
    return (try XCTUnwrap(installedTransport), tracker)
  }
}

private final class DelayedAckTransportTracker: @unchecked Sendable {
  private let lock = NSLock()
  private var live = 0

  var liveCount: Int { lock.withLock { live } }

  func opened() {
    lock.withLock { live += 1 }
  }

  func closed() {
    lock.withLock { live -= 1 }
  }
}

private final class DelayedAckRealtimeTransport: RealtimeRawWebSocketTransport,
  @unchecked Sendable
{
  var onOpen: (() -> Void)?
  var onMessage: ((Data) -> Void)?
  var onClose: ((Int, String) -> Void)?
  var onError: ((RealtimeRawWebSocketFailure) -> Void)?
  var onOpened: (() -> Void)?

  private let queue: DispatchQueue
  private let tracker: DelayedAckTransportTracker
  private var open = false
  private var waiters: [CheckedContinuation<Void, Never>] = []

  init(queue: DispatchQueue, tracker: DelayedAckTransportTracker) {
    self.queue = queue
    self.tracker = tracker
  }

  func connect() {
    open = true
    tracker.opened()
    onOpened?()
    onOpen?()
  }

  func sendText(_ text: String, completion: (@Sendable (Error?) -> Void)?) {
    completion?(nil)
  }

  func close() {}

  func closeAndWait() async {
    await withCheckedContinuation { continuation in
      queue.async { [weak self] in
        guard let self else {
          continuation.resume()
          return
        }
        if self.open {
          self.waiters.append(continuation)
        } else {
          continuation.resume()
        }
      }
    }
  }

  func acknowledgeClose() {
    queue.async { [weak self] in
      guard let self, self.open else { return }
      self.open = false
      self.tracker.closed()
      let waiters = self.waiters
      self.waiters.removeAll()
      for waiter in waiters {
        waiter.resume()
      }
    }
  }

  func emitErrorCloseAndDuplicateError() {
    queue.async { [weak self] in
      guard let self else { return }
      let failure = RealtimeRawWebSocketFailure(
        phase: .receive,
        message: "fixture transport failure")
      self.onError?(failure)
      self.onClose?(1011, "fixture remote close reason")
      self.onError?(failure)
    }
  }
}
