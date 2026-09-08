import VoiceTurnDomain
import XCTest

@testable import Omi_Computer

@MainActor
final class RealtimeTurnEvidenceTests: XCTestCase {
  func testLateResultStaysBoundToOriginalTurnUntilPersistenceFence() {
    let ledger = RealtimeTurnEvidenceLedger()
    let turnA = VoiceTurnID()
    let turnB = VoiceTurnID()
    let surface = AgentSurfaceReference.mainChat(chatId: "chat")
    let keyA = try! XCTUnwrap(
      ledger.begin(
        ownerID: "owner-a", turnID: turnA, continuityKey: "voice:a", surface: surface))
    let keyB = try! XCTUnwrap(
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

  func testPermanentAppendFailuresRetireAfterFenceAndReleaseCapacity() {
    let ledger = RealtimeTurnEvidenceLedger()
    for index in 0..<RealtimeTurnEvidenceLedger.maxEntries {
      let key = try! XCTUnwrap(
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

  func testTerminalCleanupDoesNotDiscardUnresolvedEvidenceBeforeFence() {
    let ledger = RealtimeTurnEvidenceLedger()
    let key = try! XCTUnwrap(
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

  func testSuccessfulFallbackAllowsLateOCRBeforeUserRowIsRegistered() {
    let ledger = RealtimeTurnEvidenceLedger()
    let key = try! XCTUnwrap(
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

  func testPendingDescriptorIsVisibleButCannotBeMarkedPersistedBeforeOCR() {
    let ledger = RealtimeTurnEvidenceLedger()
    let turnID = VoiceTurnID()
    let pending = ConversationEvidence.pendingNativeScreenOCR(
      evidenceID: "ptt-ocr:\(turnID.rawValue.uuidString.lowercased())",
      capturedAt: Date(timeIntervalSince1970: 3),
      turnID: turnID)
    let key = try! XCTUnwrap(
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

  func testCancelledTurnWithoutAdmittedRowRejectsLateOCR() {
    let ledger = RealtimeTurnEvidenceLedger()
    let key = try! XCTUnwrap(
      ledger.begin(ownerID: "owner-a", turnID: VoiceTurnID(), continuityKey: "voice:cancelled"))
    XCTAssertTrue(ledger.markTerminal(key: key))
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
    XCTAssertTrue(ledger.markPersistenceFence(key: key))
    XCTAssertNil(ledger.entry(for: key))
  }
}
