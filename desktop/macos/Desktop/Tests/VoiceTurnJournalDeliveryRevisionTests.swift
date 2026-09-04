import XCTest

@testable import Omi_Computer
@testable import VoiceTurnDomain

#if DEBUG
  /// FM6 (#12743): the turn-done funnel journals the assistant row at
  /// provider-response-finish, before the reducer's playback fence resolves,
  /// and `.success` used to seal that row `.completed` unconditionally — so an
  /// answer that was never spoken became canonical completed history. These
  /// tests pin the corrected contract through production APIs: the funnel's
  /// optimistic write stays `.completed` while playback is still pending, and
  /// the reducer's terminal revises the sealed row exactly when the terminal
  /// proves the answer never reached the user.
  @MainActor
  final class VoiceTurnJournalDeliveryRevisionTests: XCTestCase {

    // MARK: - Policy: `.success` is delivery-gated once delivery is known

    func testSuccessWithoutDeliveryCannotClaimCompletion() {
      // The FM6 probe: on merged main this returned `.completed`, sealing the
      // 12:45 potion answer (turn_81b) as completed while only "Let me
      // verify." was ever spoken.
      XCTAssertEqual(
        VoiceTurnJournalStatusPolicy.status(for: .success, answerDelivered: false), .failed)
      XCTAssertEqual(
        VoiceTurnJournalStatusPolicy.status(for: .success, delivery: .notDelivered), .failed)
    }

    func testSuccessWithDeliveryStillJournalsCompleted() {
      XCTAssertEqual(
        VoiceTurnJournalStatusPolicy.status(for: .success, answerDelivered: true), .completed)
      XCTAssertEqual(
        VoiceTurnJournalStatusPolicy.status(for: .success, delivery: .delivered), .completed)
    }

    func testPendingDeliveryAtTheTurnDoneWriteStaysCompleted() {
      // The funnel writes while playback is usually still draining: "not yet
      // drained" must never be read as "never played". The optimistic seal is
      // what the reducer's terminal later revises.
      XCTAssertEqual(VoiceTurnJournalStatusPolicy.status(for: .success), .completed)
      XCTAssertEqual(
        VoiceTurnJournalStatusPolicy.status(for: .success, delivery: .pending), .completed)
    }

    // MARK: - Revision policy: what may revise a sealed `.completed` row

    func testUndeliveredSuccessTerminalRevisesTheSealedRow() {
      XCTAssertEqual(
        VoiceJournalSealedRowRevisionPolicy.revision(
          forTerminalReason: .success, answerDelivered: false, sealedCompletedRowExists: true),
        .init(status: .failed, terminalReason: "answer_not_delivered"))
    }

    func testDeliveredSuccessTerminalLeavesTheSealedRowAlone() {
      XCTAssertNil(
        VoiceJournalSealedRowRevisionPolicy.revision(
          forTerminalReason: .success, answerDelivered: true, sealedCompletedRowExists: true))
    }

    func testPlaybackFailureAfterSealingRevisesTheSealedRow() {
      XCTAssertEqual(
        VoiceJournalSealedRowRevisionPolicy.revision(
          forTerminalReason: .playbackFailed, answerDelivered: false, sealedCompletedRowExists: true),
        .init(status: .failed, terminalReason: "playback_failed"))
    }

    func testBargeInKeepsMergedDeliverySemanticsOnTheSealedRow() {
      // A barge-in after playback drained interrupts the silence, not the
      // answer (#12730): the sealed row stays completed. A barge-in that cut
      // the reply before it drained revises it.
      XCTAssertNil(
        VoiceJournalSealedRowRevisionPolicy.revision(
          forTerminalReason: .interruptedByBargeIn, answerDelivered: true,
          sealedCompletedRowExists: true))
      XCTAssertNil(
        VoiceJournalSealedRowRevisionPolicy.revision(
          forTerminalReason: .explicitInterrupt, answerDelivered: true,
          sealedCompletedRowExists: true))
      XCTAssertEqual(
        VoiceJournalSealedRowRevisionPolicy.revision(
          forTerminalReason: .interruptedByBargeIn, answerDelivered: false,
          sealedCompletedRowExists: true),
        .init(status: .failed, terminalReason: "interrupted_by_barge_in"))
    }

    func testLaterJournalFailureNeverRewritesADeliveredAnswer() {
      // Analytics contract: a later journal failure must not rewrite a
      // delivered response as missing — and no non-delivery terminal may be
      // reinterpreted after the fact.
      XCTAssertNil(
        VoiceJournalSealedRowRevisionPolicy.revision(
          forTerminalReason: .journalFailed, answerDelivered: true, sealedCompletedRowExists: true))
      XCTAssertNil(
        VoiceJournalSealedRowRevisionPolicy.revision(
          forTerminalReason: .journalFailed, answerDelivered: false,
          sealedCompletedRowExists: true))
      XCTAssertNil(
        VoiceJournalSealedRowRevisionPolicy.revision(
          forTerminalReason: .providerFailed, answerDelivered: true, sealedCompletedRowExists: true))
    }

    func testRevisionRequiresASealedRow() {
      // Terminals for turns the funnel never sealed optimistically (the
      // capture-time journaling paths already carry their outcome) revise
      // nothing.
      XCTAssertNil(
        VoiceJournalSealedRowRevisionPolicy.revision(
          forTerminalReason: .success, answerDelivered: false, sealedCompletedRowExists: false))
      XCTAssertNil(
        VoiceJournalSealedRowRevisionPolicy.revision(
          forTerminalReason: .playbackFailed, answerDelivered: false,
          sealedCompletedRowExists: false))
    }

    // MARK: - Coordinator: the real reducer produces the delivery verdict

    /// Drives one non-hub voice turn through the production reducer to a
    /// provider-finished state with a spoken full answer, mirroring the
    /// turn-done funnel's preconditions.
    private func providerFinishedTurn() throws -> (VoiceTurnCoordinator, VoiceTurnID) {
      DesktopDiagnosticsManager.shared.resetForTests()
      defer { DesktopDiagnosticsManager.shared.resetForTests() }
      let coordinator = VoiceTurnCoordinator(scheduler: ManualDeadlineScheduler())
      let turnID = coordinator.begin(intent: .hold)
      coordinator.publish(.selectRoute(turnID: turnID, route: .deepgramBatch))
      coordinator.publish(.finalize(turnID: turnID))
      coordinator.publish(.transcriptionStarted(turnID: turnID))
      coordinator.publish(.transcriptionFinal(turnID: turnID, text: "the potion question"))
      let providerIdentity = try XCTUnwrap(coordinator.activeTurn?.providerEffectIdentity)
      coordinator.publish(
        .providerResponseStartedScoped(
          turnID: turnID,
          identity: providerIdentity,
          sessionID: nil,
          responseID: nil))
      return (coordinator, turnID)
    }

    func testSuccessTerminalWithoutAnyPlaybackRevisesSealedRow() throws {
      // The provider finished and the journal accepted, but no full-answer
      // playback ever drained: the reducer still terminalizes `.success`, and
      // the journal must not claim the user heard the answer.
      let (coordinator, turnID) = try providerFinishedTurn()
      let token = try XCTUnwrap(coordinator.nonHubCompletionToken(for: turnID))

      XCTAssertTrue(coordinator.completeNonHubProvider(token, outcome: .journalAccepted))
      XCTAssertEqual(coordinator.model.lastTerminal?.turnID, turnID)
      XCTAssertEqual(coordinator.model.lastTerminal?.reason, .success)
      XCTAssertFalse(coordinator.lastTerminalAnswerDelivered)

      let terminal = try XCTUnwrap(coordinator.model.lastTerminal)
      let status = VoiceTurnJournalStatusPolicy.status(
        for: terminal.reason,
        answerDelivered: coordinator.lastTerminalAnswerDelivered)
      XCTAssertEqual(status, .failed)
      XCTAssertEqual(
        VoiceJournalSealedRowRevisionPolicy.revision(
          forTerminalReason: terminal.reason,
          answerDelivered: coordinator.lastTerminalAnswerDelivered,
          sealedCompletedRowExists: true),
        .init(status: .failed, terminalReason: "answer_not_delivered"))
    }

    func testDrainedSuccessTerminalKeepsSealedRowCompleted() throws {
      // Healthy turn: playback drained before the terminal, so the funnel's
      // optimistic `.completed` row was the truth all along.
      let (coordinator, turnID) = try providerFinishedTurn()
      guard
        case .acquired(let lease) = coordinator.acquireOutput(
          .selectedVoiceFallback, turnID: turnID)
      else { return XCTFail("expected output lease") }
      let token = try XCTUnwrap(coordinator.nonHubCompletionToken(for: turnID))

      XCTAssertTrue(coordinator.releaseOutput(lease))
      XCTAssertTrue(coordinator.fullAnswerDrained(turnID: turnID))
      XCTAssertTrue(coordinator.completeNonHubProvider(token, outcome: .journalAccepted))
      XCTAssertEqual(coordinator.model.lastTerminal?.reason, .success)
      XCTAssertTrue(coordinator.lastTerminalAnswerDelivered)

      XCTAssertEqual(
        VoiceTurnJournalStatusPolicy.status(
          for: .success, answerDelivered: coordinator.lastTerminalAnswerDelivered),
        .completed)
      XCTAssertNil(
        VoiceJournalSealedRowRevisionPolicy.revision(
          forTerminalReason: .success,
          answerDelivered: coordinator.lastTerminalAnswerDelivered,
          sealedCompletedRowExists: true))
    }

    func testPlaybackFailureAfterProviderFinishTerminalizesUndelivered() throws {
      // The audio lane errored while the funnel's write was still sealing the
      // row: the reducer terminalizes `.playbackFailed` and the sealed row is
      // revised with that truncation cause.
      let (coordinator, turnID) = try providerFinishedTurn()
      guard
        case .acquired(let lease) = coordinator.acquireOutput(
          .selectedVoiceFallback, turnID: turnID)
      else { return XCTFail("expected output lease") }

      coordinator.publish(
        .playbackFailedScoped(
          turnID: turnID,
          identity: lease.identity,
          leaseID: lease.id,
          message: "synthetic playback error"))

      XCTAssertEqual(coordinator.model.lastTerminal?.turnID, turnID)
      XCTAssertEqual(coordinator.model.lastTerminal?.reason, .playbackFailed)
      XCTAssertFalse(coordinator.lastTerminalAnswerDelivered)
      XCTAssertEqual(
        VoiceJournalSealedRowRevisionPolicy.revision(
          forTerminalReason: .playbackFailed,
          answerDelivered: coordinator.lastTerminalAnswerDelivered,
          sealedCompletedRowExists: true),
        .init(status: .failed, terminalReason: "playback_failed"))
    }

    // MARK: - Ledger: the revision chains after the funnel's in-flight write

    func testFollowUpRunsOnlyAfterTheOriginalWriteAndKeepsTheFence() async {
      // The revision must never beat the funnel write it corrects, and the
      // next turn's context fence (awaitPendingObligations) must still observe
      // it before the journal settles.
      let ledger = RealtimeTurnPersistenceLedger()
      let gate = SuspendedFollowUpGate()
      var order: [String] = []

      let original = ledger.enqueue(continuityKey: "voice:fm6", retainingReceipt: true) {
        await gate.suspendOriginal()
        order.append("original")
        return true
      }
      await gate.waitUntilSuspended()

      let followUp = ledger.enqueueFollowUp(continuityKey: "voice:fm6") {
        order.append("follow-up")
        return true
      }
      XCTAssertEqual(order, [], "the follow-up must wait for the original write")

      await gate.resumeOriginal()
      await ledger.awaitPendingObligations()
      XCTAssertEqual(order, ["original", "follow-up"])
      _ = await original.value
      _ = await followUp.value
      XCTAssertTrue(ledger.pendingContinuityKeys.isEmpty)
    }

    func testFollowUpPreservesTheOriginalWriteRetainedReceipt() async {
      // The chained follow-up takes over the obligation slot, so the original
      // write's receipt semantics must survive through it: acceptance still
      // reflects the original kernel write, not the follow-up's revision.
      let ledger = RealtimeTurnPersistenceLedger()
      let gate = SuspendedFollowUpGate()

      _ = ledger.enqueue(continuityKey: "voice:fm6-receipt", retainingReceipt: true) {
        await gate.suspendOriginal()
        return true
      }
      await gate.waitUntilSuspended()
      let followUp = ledger.enqueueFollowUp(continuityKey: "voice:fm6-receipt") { true }
      await gate.resumeOriginal()
      _ = await followUp.value

      XCTAssertEqual(
        ledger.receipt(for: "voice:fm6-receipt"),
        .init(continuityKey: "voice:fm6-receipt", accepted: true))
      XCTAssertTrue(ledger.pendingContinuityKeys.isEmpty)
    }

    func testFollowUpWithoutInFlightObligationRunsDirectly() async {
      let ledger = RealtimeTurnPersistenceLedger()
      let followUp = ledger.enqueueFollowUp(continuityKey: "voice:fm6-fresh") { true }
      let accepted = await followUp.value
      XCTAssertTrue(accepted)
      XCTAssertTrue(ledger.pendingContinuityKeys.isEmpty)
    }
  }

  /// Deterministic deadline scheduler (mirrors the coordinator suite's): no
  /// wall-clock timers fire during these tests.
  @MainActor
  private final class ManualDeadlineScheduler: VoiceTurnDeadlineScheduling {
    private final class Cancellation: VoiceTurnDeadlineCancellation {
      var isCancelled = false
      func cancel() { isCancelled = true }
    }

    func schedule(
      deadline: VoiceTurnDeadline,
      after interval: TimeInterval,
      action: @escaping @MainActor () -> Void
    ) -> VoiceTurnDeadlineCancellation {
      _ = interval
      _ = deadline
      return Cancellation()
    }
  }

  /// Deterministic suspension point for ledger tests: the original write parks
  /// until the test releases it, so ordering is observed without wall-clock
  /// sleeps.
  private actor SuspendedFollowUpGate {
    private var suspended = false
    private var waiters: [CheckedContinuation<Void, Never>] = []
    private var resumption: CheckedContinuation<Void, Never>?

    func suspendOriginal() async {
      await withCheckedContinuation { continuation in
        resumption = continuation
        suspended = true
        let current = waiters
        waiters.removeAll()
        for waiter in current { waiter.resume() }
      }
    }

    func waitUntilSuspended() async {
      guard !suspended else { return }
      await withCheckedContinuation { continuation in
        waiters.append(continuation)
      }
    }

    func resumeOriginal() {
      resumption?.resume()
      resumption = nil
    }
  }
#endif
