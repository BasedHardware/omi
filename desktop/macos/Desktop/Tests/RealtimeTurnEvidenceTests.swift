import VoiceTurnDomain
import XCTest

@testable import Omi_Computer

@MainActor
final class RealtimeTurnEvidenceTests: XCTestCase {
  func testLateResultStaysBoundToOriginalTurnUntilPersistenceFence() throws {
    let ledger = RealtimeTurnEvidenceLedger()
    let turnA = VoiceTurnID()
    let turnB = VoiceTurnID()
    let surface = AgentSurfaceReference.mainChat(chatId: "chat")
    let keyA = try XCTUnwrap(
      ledger.begin(
        ownerID: "owner-a", turnID: turnA, continuityKey: "voice:a", surface: surface))
    let keyB = try XCTUnwrap(
      ledger.begin(
        ownerID: "owner-a", turnID: turnB, continuityKey: "voice:b", surface: surface))
    let evidence = ConversationEvidence(
      id: "screen-a",
      kind: .screen,
      title: "PTT screen OCR",
      capturedAtMs: 1,
      availability: .available,
      extractionCompleteness: .complete,
      bodyText: "original turn")

    XCTAssertTrue(ledger.markPersistenceFence(key: keyA))
    XCTAssertTrue(ledger.resolve(key: keyA, evidence: evidence, state: .complete))
    XCTAssertEqual(ledger.evidence(for: keyA), evidence)
    XCTAssertNil(ledger.evidence(for: keyB))
    XCTAssertTrue(ledger.markEvidencePersisted(key: keyA))
    XCTAssertNil(ledger.entry(for: keyA))
    XCTAssertNotNil(ledger.entry(for: keyB))
  }

  func testOwnerRevocationDropsPendingCallbacksAndBoundsEntries() {
    let ledger = RealtimeTurnEvidenceLedger()
    for index in 0..<RealtimeTurnEvidenceLedger.maxEntries {
      XCTAssertNotNil(
        ledger.begin(
          ownerID: "owner-a",
          turnID: VoiceTurnID(),
          continuityKey: "voice:a-\(index)"))
    }
    XCTAssertNil(ledger.begin(ownerID: "owner-a", turnID: VoiceTurnID(), continuityKey: "voice:overflow"))
    XCTAssertEqual(ledger.count, RealtimeTurnEvidenceLedger.maxEntries)
    XCTAssertEqual(ledger.revoke(ownerID: "owner-a"), RealtimeTurnEvidenceLedger.maxEntries)
    XCTAssertEqual(ledger.count, 0)
  }

  func testOwnerTransitionRevokesAllPendingOwnersBeforeReplacement() {
    let ledger = RealtimeTurnEvidenceLedger()
    XCTAssertNotNil(ledger.begin(ownerID: "owner-a", turnID: VoiceTurnID(), continuityKey: "voice:a"))
    XCTAssertNotNil(ledger.begin(ownerID: "owner-b", turnID: VoiceTurnID(), continuityKey: "voice:b"))
    XCTAssertEqual(ledger.revokeAll(), 2)
    XCTAssertEqual(ledger.count, 0)
    XCTAssertNotNil(ledger.begin(ownerID: "owner-c", turnID: VoiceTurnID(), continuityKey: "voice:c"))
  }

  func testPermanentAppendFailuresRetireAfterFenceAndReleaseCapacity() throws {
    let ledger = RealtimeTurnEvidenceLedger()
    for index in 0..<RealtimeTurnEvidenceLedger.maxEntries {
      let key = try XCTUnwrap(
        ledger.begin(
          ownerID: "owner-a",
          turnID: VoiceTurnID(),
          continuityKey: "voice:failed-\(index)"))
      XCTAssertTrue(
        ledger.resolve(
          key: key,
          evidence: ConversationEvidence(
            id: "failed-\(index)",
            kind: .screen,
            title: "PTT screen OCR",
            capturedAtMs: 1,
            availability: .available,
            extractionCompleteness: .complete,
            bodyText: "failed"),
          state: .complete))
      XCTAssertTrue(ledger.markTerminal(key: key))
      XCTAssertTrue(ledger.markPersistenceFailed(key: key))
      XCTAssertTrue(ledger.markPersistenceFence(key: key))
    }
    XCTAssertEqual(ledger.count, 0)
    XCTAssertNotNil(ledger.begin(ownerID: "owner-a", turnID: VoiceTurnID(), continuityKey: "voice:recovered"))
  }

  func testTerminalCleanupDoesNotDiscardUnresolvedEvidenceBeforeFence() throws {
    let ledger = RealtimeTurnEvidenceLedger()
    let key = try XCTUnwrap(
      ledger.begin(ownerID: "owner-a", turnID: VoiceTurnID(), continuityKey: "voice:pending"))
    XCTAssertTrue(ledger.attachJournalUserTurn(key: key, turnID: "user-turn"))
    XCTAssertTrue(ledger.markTerminal(key: key))
    XCTAssertTrue(ledger.markPersistenceFence(key: key))
    XCTAssertNotNil(ledger.entry(for: key))
    XCTAssertTrue(ledger.resolve(key: key, evidence: nil, state: .unavailable))
    XCTAssertNotNil(ledger.entry(for: key))
    XCTAssertTrue(ledger.markEvidencePersisted(key: key))
    XCTAssertNil(ledger.entry(for: key))
  }

  func testSuccessfulFallbackAllowsLateOCRBeforeUserRowIsRegistered() throws {
    let ledger = RealtimeTurnEvidenceLedger()
    let key = try XCTUnwrap(
      ledger.begin(ownerID: "owner-a", turnID: VoiceTurnID(), continuityKey: "voice:fallback"))
    XCTAssertTrue(ledger.markTerminal(key: key, allowsLateEvidence: true))
    let evidence = ConversationEvidence(
      id: "fallback-screen",
      kind: .screen,
      title: "PTT screen OCR",
      capturedAtMs: 1,
      availability: .available,
      extractionCompleteness: .complete,
      bodyText: "fallback row")
    XCTAssertTrue(ledger.resolve(key: key, evidence: evidence, state: .complete))
    XCTAssertEqual(ledger.evidence(for: key), evidence)
    XCTAssertTrue(ledger.attachJournalUserTurn(key: key, turnID: "fallback-user"))
    XCTAssertTrue(ledger.markPersistenceFence(key: key))
    XCTAssertTrue(ledger.markEvidencePersisted(key: key))
    XCTAssertNil(ledger.entry(for: key))
  }

  func testPendingDescriptorIsVisibleButCannotBeMarkedPersistedBeforeOCR() throws {
    let ledger = RealtimeTurnEvidenceLedger()
    let turnID = VoiceTurnID()
    let pending = ConversationEvidence.pendingNativeScreenOCR(
      evidenceID: "ptt-ocr:\(turnID.rawValue.uuidString.lowercased())",
      capturedAt: Date(timeIntervalSince1970: 3),
      turnID: turnID)
    let key = try XCTUnwrap(
      ledger.begin(
        ownerID: "owner-a",
        turnID: turnID,
        continuityKey: "voice:pending-descriptor",
        initialEvidence: pending,
        createdAt: Date(timeIntervalSince1970: 3)))

    XCTAssertEqual(ledger.evidence(for: key), pending)
    XCTAssertFalse(ledger.markEvidencePersisted(key: key))
    XCTAssertTrue(ledger.markPersistenceFence(key: key))
    XCTAssertNotNil(ledger.entry(for: key))

    let finalEvidence = ConversationEvidence.nativeScreenOCR(
      evidenceID: pending.id,
      capturedAt: Date(timeIntervalSince1970: 3),
      text: "form instructions",
      turnID: turnID)
    XCTAssertTrue(ledger.resolve(key: key, evidence: finalEvidence, state: .complete))
    XCTAssertTrue(ledger.markEvidencePersisted(key: key))
    XCTAssertNil(ledger.entry(for: key))
  }

  func testFallbackProjectionCarriesOCRIntoInitialUserJournalPayload() throws {
    let turnID = VoiceTurnID()
    let evidence = ConversationEvidence(
      id: "fallback-before-record",
      kind: .screen,
      title: "PTT screen OCR",
      capturedAtMs: 1,
      availability: .available,
      extractionCompleteness: .complete,
      bodyText: "form instructions")
    let projection = RealtimeStreamingJournalProjection(
      ownerID: "owner-a",
      continuityKey: RealtimeHubController.voiceContinuityKey(for: turnID),
      admissionSurface: .mainChat(chatId: "chat"),
      evidence: [evidence])
    let message = projection.userMessage(text: "Which documents do I select?")
    XCTAssertEqual(message.metadata?.evidence, [evidence])
    let metadata = message.journalWrite(
      origin: "realtime_voice",
      status: .completed,
      continuityKey: projection.continuityKey,
      messageSource: "realtime_voice"
    ).metadataJSON
    XCTAssertEqual(
      ConversationEvidenceMetadataCodec.envelope(from: metadata)?.items,
      [evidence])
  }

  func testInitialFallbackPayloadCarriesPendingDescriptor() {
    let turnID = VoiceTurnID()
    let pending = ConversationEvidence.pendingNativeScreenOCR(
      evidenceID: "ptt-ocr:\(turnID.rawValue.uuidString.lowercased())",
      capturedAt: Date(timeIntervalSince1970: 5),
      turnID: turnID)
    let projection = RealtimeStreamingJournalProjection(
      ownerID: "owner-a",
      continuityKey: RealtimeHubController.voiceContinuityKey(for: turnID),
      admissionSurface: .mainChat(chatId: "chat"),
      evidence: [pending])

    XCTAssertEqual(projection.userMessage(text: "remember this").metadata?.evidence, [pending])
  }

  func testCancelledTurnWithoutAdmittedRowRejectsLateOCR() throws {
    let ledger = RealtimeTurnEvidenceLedger()
    let key = try XCTUnwrap(
      ledger.begin(ownerID: "owner-a", turnID: VoiceTurnID(), continuityKey: "voice:cancelled"))
    XCTAssertTrue(ledger.finishTerminal(key: key, allowsLateEvidence: false))
    XCTAssertFalse(
      ledger.resolve(
        key: key,
        evidence: ConversationEvidence(
          id: "stale",
          kind: .screen,
          title: "PTT screen OCR",
          capturedAtMs: 1,
          availability: .available,
          extractionCompleteness: .complete,
          bodyText: "stale"),
        state: .complete))
    XCTAssertNil(ledger.entry(for: key))
  }

  func testCapacityCancellationsReleaseSlotsForLaterSourcedTurn() throws {
    let ledger = RealtimeTurnEvidenceLedger()
    for index in 0..<RealtimeTurnEvidenceLedger.maxEntries {
      let key = try XCTUnwrap(
        ledger.begin(
          ownerID: "owner-a",
          turnID: VoiceTurnID(),
          continuityKey: "voice:cancel-\(index)"))
      XCTAssertTrue(ledger.finishTerminal(key: key, allowsLateEvidence: false))
    }
    XCTAssertEqual(ledger.count, 0)
    let sourced = try XCTUnwrap(
      ledger.begin(ownerID: "owner-a", turnID: VoiceTurnID(), continuityKey: "voice:sourced"))
    let evidence = ConversationEvidence.nativeScreenOCR(
      evidenceID: "sourced",
      capturedAt: Date(timeIntervalSince1970: 1),
      text: "visible form",
      turnID: sourced.turnID)
    XCTAssertTrue(ledger.resolve(key: sourced, evidence: evidence, state: .complete))
    XCTAssertEqual(ledger.evidence(for: sourced), evidence)
  }

  func testLateCallbackAfterCancelCannotAttachOwnerAData() throws {
    let ledger = RealtimeTurnEvidenceLedger()
    let turnA = VoiceTurnID()
    let keyA = try XCTUnwrap(
      ledger.begin(ownerID: "owner-a", turnID: turnA, continuityKey: "voice:a"))
    XCTAssertTrue(ledger.finishTerminal(key: keyA, allowsLateEvidence: false))
    let keyB = try XCTUnwrap(
      ledger.begin(ownerID: "owner-a", turnID: VoiceTurnID(), continuityKey: "voice:b"))
    XCTAssertFalse(
      ledger.resolve(
        key: keyA,
        evidence: ConversationEvidence.nativeScreenOCR(
          evidenceID: "stale-a",
          capturedAt: Date(timeIntervalSince1970: 1),
          text: "owner-a leftover",
          turnID: turnA),
        state: .complete))
    XCTAssertNil(ledger.evidence(for: keyA))
    XCTAssertNil(ledger.evidence(for: keyB))
  }

  func testBargedInPriorTurnKeepsUnfinishedWriteAndAcceptsLateOCR() throws {
    let ledger = RealtimeTurnEvidenceLedger()
    let turnA = VoiceTurnID()
    let keyA = try XCTUnwrap(
      ledger.begin(ownerID: "owner-a", turnID: turnA, continuityKey: "voice:a"))
    XCTAssertTrue(ledger.finishTerminal(key: keyA, allowsLateEvidence: true))
    XCTAssertNotNil(ledger.entry(for: keyA))
    let producingRow = KernelTurnProjection.stableTurnID(continuityKey: "voice:a", role: "user")
    XCTAssertTrue(ledger.attachJournalUserTurn(key: keyA, turnID: producingRow))
    let evidence = ConversationEvidence.nativeScreenOCR(
      evidenceID: "ptt-ocr:\(turnA.rawValue.uuidString.lowercased())",
      capturedAt: Date(timeIntervalSince1970: 2),
      text: "prior turn screen",
      turnID: turnA)
    XCTAssertTrue(ledger.resolve(key: keyA, evidence: evidence, state: .complete))
    XCTAssertEqual(ledger.entry(for: keyA)?.journalUserTurnID, producingRow)
    XCTAssertTrue(ledger.markEvidencePersisted(key: keyA))
    XCTAssertTrue(ledger.markPersistenceFence(key: keyA))
    XCTAssertNil(ledger.entry(for: keyA))
    XCTAssertNotNil(
      ledger.begin(ownerID: "owner-a", turnID: VoiceTurnID(), continuityKey: "voice:b"))
  }

  func testDictationProducingRowCanReceiveSourceDespiteDifferentContinuityKey() throws {
    let ledger = RealtimeTurnEvidenceLedger()
    let turnID = VoiceTurnID()
    let reservationKey = RealtimeHubController.voiceContinuityKey(for: turnID)
    let dictationKey = "voice-typing-\(turnID)"
    let key = try XCTUnwrap(
      ledger.begin(ownerID: "owner-a", turnID: turnID, continuityKey: reservationKey))
    let producingRow = KernelTurnProjection.stableTurnID(continuityKey: dictationKey, role: "user")
    XCTAssertNotEqual(
      producingRow,
      KernelTurnProjection.stableTurnID(continuityKey: reservationKey, role: "user"))
    XCTAssertTrue(ledger.attachJournalUserTurn(key: key, turnID: producingRow))
    XCTAssertTrue(
      RealtimeTurnEvidenceTerminalPolicy.finish(ledger: ledger, key: key, persistPending: false))
    XCTAssertNotNil(ledger.entry(for: key), "admitted dictation row must keep late OCR")
    let evidence = ConversationEvidence.nativeScreenOCR(
      evidenceID: "ptt-ocr:\(turnID.rawValue.uuidString.lowercased())",
      capturedAt: Date(timeIntervalSince1970: 3),
      text: "typed this sentence",
      turnID: turnID)
    XCTAssertTrue(ledger.resolve(key: key, evidence: evidence, state: .complete))
    XCTAssertEqual(ledger.entry(for: key)?.journalUserTurnID, producingRow)
    XCTAssertTrue(ledger.markEvidencePersisted(key: key))
    XCTAssertTrue(ledger.markPersistenceFence(key: key))
    XCTAssertNil(ledger.entry(for: key))
  }

  func testFallbackTypedQuestionBindUsesAdmittedClientTurnIdentity() throws {
    let ledger = RealtimeTurnEvidenceLedger()
    let turnID = VoiceTurnID()
    let key = try XCTUnwrap(
      ledger.begin(
        ownerID: "owner-a",
        turnID: turnID,
        continuityKey: RealtimeHubController.voiceContinuityKey(for: turnID)))
    let clientTurnId = UUID().uuidString
    let producingRow = ChatProvider.messageIds(forAttemptId: clientTurnId).user
    XCTAssertEqual(producingRow, clientTurnId)
    XCTAssertTrue(ledger.attachJournalUserTurn(key: key, turnID: producingRow))
    let evidence = ConversationEvidence.nativeScreenOCR(
      evidenceID: "ptt-ocr:\(turnID.rawValue.uuidString.lowercased())",
      capturedAt: Date(timeIntervalSince1970: 4),
      text: "what's on this form",
      turnID: turnID)
    XCTAssertTrue(ledger.resolve(key: key, evidence: evidence, state: .complete))
    XCTAssertEqual(ledger.entry(for: key)?.journalUserTurnID, producingRow)
  }

  func testTerminalPolicyLicensesLateWriteOnlyForPendingOrAdmittedRow() {
    XCTAssertTrue(
      RealtimeTurnEvidenceTerminalPolicy.allowsLateEvidence(
        persistPending: true, producingRowAdmitted: false))
    XCTAssertTrue(
      RealtimeTurnEvidenceTerminalPolicy.allowsLateEvidence(
        persistPending: false, producingRowAdmitted: true))
    XCTAssertFalse(
      RealtimeTurnEvidenceTerminalPolicy.allowsLateEvidence(
        persistPending: false, producingRowAdmitted: false))
    XCTAssertFalse(RealtimeTurnEvidenceTerminalPolicy.shouldFenceAtTerminal(allowsLateEvidence: true))
    XCTAssertTrue(RealtimeTurnEvidenceTerminalPolicy.shouldFenceAtTerminal(allowsLateEvidence: false))
  }

  func testSlowAdmissionKeepsEvidenceUntilWriteSettles() async throws {
    let evidenceLedger = RealtimeTurnEvidenceLedger()
    let persistenceLedger = RealtimeTurnPersistenceLedger()
    let turnID = VoiceTurnID()
    let continuityKey = RealtimeHubController.voiceContinuityKey(for: turnID)
    let key = try XCTUnwrap(
      evidenceLedger.begin(ownerID: "owner-a", turnID: turnID, continuityKey: continuityKey))
    let latch = MainActorLatch()
    let write = persistenceLedger.enqueue(continuityKey: continuityKey, retainingReceipt: false) {
      await latch.wait()
      return true
    }

    XCTAssertTrue(persistenceLedger.pendingContinuityKeys.contains(continuityKey))
    XCTAssertTrue(
      RealtimeTurnEvidenceTerminalPolicy.finish(
        ledger: evidenceLedger, key: key, persistPending: true))
    XCTAssertNotNil(evidenceLedger.entry(for: key))

    let evidence = ConversationEvidence.nativeScreenOCR(
      evidenceID: "ptt-ocr:\(turnID.rawValue.uuidString.lowercased())",
      capturedAt: Date(timeIntervalSince1970: 6),
      text: "slow admission screen",
      turnID: turnID)
    XCTAssertTrue(evidenceLedger.resolve(key: key, evidence: evidence, state: .complete))
    let producingRow = KernelTurnProjection.stableTurnID(
      continuityKey: "voice-typing-\(turnID)", role: "user")
    XCTAssertTrue(evidenceLedger.attachJournalUserTurn(key: key, turnID: producingRow))

    latch.release()
    let accepted = await write.value
    XCTAssertTrue(accepted)
    XCTAssertTrue(evidenceLedger.markEvidencePersisted(key: key))
    XCTAssertTrue(evidenceLedger.markPersistenceFence(key: key))
    XCTAssertNil(evidenceLedger.entry(for: key))
  }

  func testRejectedProducingWriteRetiresReservationAndRefusesLateAdmission() async throws {
    let evidenceLedger = RealtimeTurnEvidenceLedger()
    let persistenceLedger = RealtimeTurnPersistenceLedger()
    let turnID = VoiceTurnID()
    let continuityKey = RealtimeHubController.voiceContinuityKey(for: turnID)
    let key = try XCTUnwrap(
      evidenceLedger.begin(ownerID: "owner-a", turnID: turnID, continuityKey: continuityKey))
    let latch = MainActorLatch()
    let write = persistenceLedger.enqueue(continuityKey: continuityKey, retainingReceipt: false) {
      await latch.wait()
      return false
    }

    XCTAssertTrue(
      RealtimeTurnEvidenceTerminalPolicy.finish(
        ledger: evidenceLedger, key: key, persistPending: true))
    XCTAssertNotNil(evidenceLedger.entry(for: key))

    latch.release()
    let accepted = await write.value
    XCTAssertFalse(accepted)
    XCTAssertTrue(
      RealtimeTurnEvidenceTerminalPolicy.retireRejectedWrite(ledger: evidenceLedger, key: key))
    XCTAssertNil(evidenceLedger.entry(for: key))
    XCTAssertFalse(
      evidenceLedger.attachJournalUserTurn(
        key: key,
        turnID: KernelTurnProjection.stableTurnID(continuityKey: continuityKey, role: "user")))
    XCTAssertFalse(
      evidenceLedger.resolve(
        key: key,
        evidence: ConversationEvidence.nativeScreenOCR(
          evidenceID: "stale",
          capturedAt: Date(timeIntervalSince1970: 7),
          text: "invented",
          turnID: turnID),
        state: .complete))
  }

  func testSuccessfulTerminalWithoutProducingRowDoesNotLeakReservation() throws {
    let ledger = RealtimeTurnEvidenceLedger()
    let key = try XCTUnwrap(
      ledger.begin(ownerID: "owner-a", turnID: VoiceTurnID(), continuityKey: "voice:success-no-row"))
    XCTAssertFalse(
      RealtimeTurnEvidenceTerminalPolicy.allowsLateEvidence(
        persistPending: false, producingRowAdmitted: false))
    XCTAssertTrue(
      RealtimeTurnEvidenceTerminalPolicy.finish(ledger: ledger, key: key, persistPending: false))
    XCTAssertNil(ledger.entry(for: key))
    XCTAssertFalse(
      ledger.attachJournalUserTurn(
        key: key,
        turnID: KernelTurnProjection.stableTurnID(continuityKey: "voice:success-no-row", role: "user")))
  }

  func testUnlicensedTerminalRefusesLateBindWhileReservationStillExists() throws {
    let ledger = RealtimeTurnEvidenceLedger()
    let key = try XCTUnwrap(
      ledger.begin(ownerID: "owner-a", turnID: VoiceTurnID(), continuityKey: "voice:unlicensed"))
    XCTAssertTrue(ledger.markTerminal(key: key, allowsLateEvidence: false))
    XCTAssertNotNil(ledger.entry(for: key))
    XCTAssertFalse(
      ledger.attachJournalUserTurn(
        key: key,
        turnID: KernelTurnProjection.stableTurnID(continuityKey: "voice:unlicensed", role: "user")))
  }

  func testRejectedOrMissingJournalReceiptRetiresUnlicensedCapture() throws {
    let ledger = RealtimeTurnEvidenceLedger()
    let turnID = VoiceTurnID()
    let continuityKey = RealtimeHubController.voiceContinuityKey(for: turnID)
    let key = try XCTUnwrap(
      ledger.begin(ownerID: "owner-a", turnID: turnID, continuityKey: continuityKey))

    XCTAssertTrue(
      RealtimeTurnEvidenceTerminalPolicy.applyJournalReceipt(
        ledger: ledger, key: key, accepted: false))
    XCTAssertNil(ledger.entry(for: key))
    XCTAssertFalse(
      ledger.resolve(
        key: key,
        evidence: ConversationEvidence.nativeScreenOCR(
          evidenceID: "stale",
          capturedAt: Date(timeIntervalSince1970: 8),
          text: "invented late capture",
          turnID: turnID),
        state: .complete))
  }

  func testRejectedJournalReceiptPreservesAdmittedPendingWrite() throws {
    let ledger = RealtimeTurnEvidenceLedger()
    let turnID = VoiceTurnID()
    let continuityKey = RealtimeHubController.voiceContinuityKey(for: turnID)
    let key = try XCTUnwrap(
      ledger.begin(ownerID: "owner-a", turnID: turnID, continuityKey: continuityKey))
    let producingRow = KernelTurnProjection.stableTurnID(continuityKey: continuityKey, role: "user")
    XCTAssertTrue(ledger.attachJournalUserTurn(key: key, turnID: producingRow))

    XCTAssertTrue(
      RealtimeTurnEvidenceTerminalPolicy.applyJournalReceipt(
        ledger: ledger, key: key, accepted: false))
    XCTAssertNotNil(ledger.entry(for: key))
    let evidence = ConversationEvidence.nativeScreenOCR(
      evidenceID: "ptt-ocr:\(turnID.rawValue.uuidString.lowercased())",
      capturedAt: Date(timeIntervalSince1970: 9),
      text: "admitted row screen",
      turnID: turnID)
    XCTAssertTrue(ledger.resolve(key: key, evidence: evidence, state: .complete))
    XCTAssertEqual(ledger.evidence(for: key), evidence)
    XCTAssertEqual(ledger.entry(for: key)?.journalUserTurnID, producingRow)
  }

  func testAcceptedJournalReceiptFencesPendingCaptureInsteadOfRetiring() throws {
    let ledger = RealtimeTurnEvidenceLedger()
    let turnID = VoiceTurnID()
    let continuityKey = RealtimeHubController.voiceContinuityKey(for: turnID)
    let key = try XCTUnwrap(
      ledger.begin(ownerID: "owner-a", turnID: turnID, continuityKey: continuityKey))

    XCTAssertTrue(
      RealtimeTurnEvidenceTerminalPolicy.applyJournalReceipt(
        ledger: ledger, key: key, accepted: true))
    XCTAssertNotNil(ledger.entry(for: key))
    XCTAssertEqual(ledger.entry(for: key)?.persistenceFenced, true)
    let evidence = ConversationEvidence.nativeScreenOCR(
      evidenceID: "ptt-ocr:\(turnID.rawValue.uuidString.lowercased())",
      capturedAt: Date(timeIntervalSince1970: 10),
      text: "late ocr after accepted write",
      turnID: turnID)
    XCTAssertTrue(ledger.resolve(key: key, evidence: evidence, state: .complete))
    XCTAssertEqual(ledger.evidence(for: key), evidence)
  }

  #if DEBUG
    // These three tests drive `RealtimeTurnEvidenceLedger.testingAttachRealtimeUserEvidence`,
    // a seam that exists only in DEBUG builds. `swift test -c release` compiles this file
    // too (the UserNotifications release regression step), so the release build must not see them.
    func testOCRBeforeJournalRowDoesNotAttachAndLaterAdmissionCarriesEvidence() async throws {
      try await withNativeEvidenceTestOwner { ownerID in
        let controller = RealtimeHubController()
        let turnID = VoiceTurnID()
        let continuityKey = RealtimeHubController.voiceContinuityKey(for: turnID)
        let surface = AgentSurfaceReference.mainChat(chatId: "chat")
        let key = try XCTUnwrap(
          controller.turnEvidenceLedger.begin(
            ownerID: ownerID, turnID: turnID, continuityKey: continuityKey, surface: surface))
        var attachCount = 0
        controller.turnEvidenceLedger.testingAttachRealtimeUserEvidence = { _, _, _, _ in
          attachCount += 1
          return true
        }

        controller.resolveNativeTurnEvidence(
          turnID: turnID,
          ownerID: ownerID,
          capturedAt: Date(timeIntervalSince1970: 11),
          text: "form instructions")

        XCTAssertEqual(attachCount, 0)
        let resolved = try XCTUnwrap(controller.turnEvidenceLedger.evidence(for: key))
        XCTAssertEqual(resolved.bodyText, "form instructions")
        XCTAssertEqual(controller.turnEvidenceLedger.entry(for: key)?.persistenceFailed, false)
        XCTAssertNil(controller.turnEvidenceLedger.entry(for: key)?.journalUserTurnID)

        let projection = RealtimeStreamingJournalProjection(
          ownerID: ownerID, continuityKey: continuityKey, admissionSurface: surface,
          evidence: [resolved])
        XCTAssertEqual(projection.userMessage(text: "which form?").metadata?.evidence, [resolved])

        XCTAssertTrue(
          controller.turnEvidenceLedger.attachJournalUserTurn(key: key, turnID: projection.userTurnID))
        let persisted = await controller.persistNativeEvidenceAfterJournalAdmission(
          ownerID: ownerID, continuityKey: continuityKey)
        XCTAssertTrue(persisted)
        XCTAssertEqual(attachCount, 1)
        XCTAssertEqual(controller.turnEvidenceLedger.entry(for: key)?.evidencePersisted, true)
        XCTAssertEqual(controller.turnEvidenceLedger.entry(for: key)?.persistenceFailed, false)
      }
    }

    func testOCRAfterBoundUserRowAndFinalizedStreamingAttachesOnce() async throws {
      try await withNativeEvidenceTestOwner { ownerID in
        let controller = RealtimeHubController()
        let turnID = VoiceTurnID()
        let continuityKey = RealtimeHubController.voiceContinuityKey(for: turnID)
        let surface = AgentSurfaceReference.mainChat(chatId: "chat")
        let producingRow = KernelTurnProjection.stableTurnID(continuityKey: continuityKey, role: "user")
        let key = try XCTUnwrap(
          controller.turnEvidenceLedger.begin(
            ownerID: ownerID, turnID: turnID, continuityKey: continuityKey, surface: surface))
        XCTAssertTrue(controller.turnEvidenceLedger.attachJournalUserTurn(key: key, turnID: producingRow))

        let projection = RealtimeStreamingJournalProjection(
          ownerID: ownerID, continuityKey: continuityKey, admissionSurface: surface)
        XCTAssertTrue(
          controller.streamingJournalWriteLedger.begin(projection: projection) { _ in true })
        let finalized = await controller.streamingJournalWriteLedger.finalize(
          continuityKey: continuityKey
        ) { _ in true }
        XCTAssertEqual(finalized, .completed(true))
        XCTAssertFalse(controller.streamingJournalWriteLedger.contains(continuityKey: continuityKey))

        var attachedTurnIDs: [String] = []
        await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
          controller.turnEvidenceLedger.testingAttachRealtimeUserEvidence = { _, _, userTurnID, _ in
            attachedTurnIDs.append(userTurnID)
            continuation.resume()
            return true
          }
          controller.resolveNativeTurnEvidence(
            turnID: turnID,
            ownerID: ownerID,
            capturedAt: Date(timeIntervalSince1970: 12),
            text: "visible form")
        }

        XCTAssertEqual(attachedTurnIDs, [producingRow])
        XCTAssertEqual(controller.turnEvidenceLedger.entry(for: key)?.evidencePersisted, true)
      }
    }

    func testOCRWhileStreamingLedgerContainsKeyWaitsForRecordTask() async throws {
      try await withNativeEvidenceTestOwner { ownerID in
        let controller = RealtimeHubController()
        let turnID = VoiceTurnID()
        let continuityKey = RealtimeHubController.voiceContinuityKey(for: turnID)
        let surface = AgentSurfaceReference.mainChat(chatId: "chat")
        let key = try XCTUnwrap(
          controller.turnEvidenceLedger.begin(
            ownerID: ownerID, turnID: turnID, continuityKey: continuityKey, surface: surface))
        let projection = RealtimeStreamingJournalProjection(
          ownerID: ownerID, continuityKey: continuityKey, admissionSurface: surface)
        let recordLatch = MainActorLatch()
        var events: [String] = []
        XCTAssertTrue(
          controller.streamingJournalWriteLedger.begin(projection: projection) { _ in
            await recordLatch.wait()
            events.append("record")
            return true
          })
        await Task.yield()

        await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
          controller.turnEvidenceLedger.testingAttachRealtimeUserEvidence = { _, _, _, _ in
            events.append("attach")
            continuation.resume()
            return true
          }
          controller.resolveNativeTurnEvidence(
            turnID: turnID,
            ownerID: ownerID,
            capturedAt: Date(timeIntervalSince1970: 13),
            text: "streaming screen")
          XCTAssertEqual(events, [])
          XCTAssertEqual(controller.turnEvidenceLedger.entry(for: key)?.persistenceFailed, false)
          recordLatch.release()
        }

        XCTAssertEqual(events, ["record", "attach"])
        XCTAssertEqual(controller.turnEvidenceLedger.entry(for: key)?.evidencePersisted, true)
      }
    }
  #endif
}

@MainActor
private func withNativeEvidenceTestOwner(
  _ body: (String) async throws -> Void
) async throws {
  if let ownerID = RuntimeOwnerIdentity.currentOwnerId() {
    try await body(ownerID)
    return
  }
  let defaults = UserDefaults.standard
  let previous = defaults.string(forKey: .authUserId)
  let ownerID = "evidence-attach-\(UUID().uuidString.lowercased())"
  defaults.set(ownerID, forKey: .authUserId)
  defer {
    if let previous {
      defaults.set(previous, forKey: .authUserId)
    } else {
      defaults.removeObject(forKey: .authUserId)
    }
  }
  guard RuntimeOwnerIdentity.currentOwnerId() == ownerID else {
    throw XCTSkip("could not install a test owner identity")
  }
  try await body(ownerID)
}

@MainActor
private final class MainActorLatch {
  private var continuation: CheckedContinuation<Void, Never>?
  private var released = false

  func wait() async {
    if released { return }
    await withCheckedContinuation { continuation in
      if released {
        continuation.resume()
      } else {
        self.continuation = continuation
      }
    }
  }

  func release() {
    released = true
    continuation?.resume()
    continuation = nil
  }
}
