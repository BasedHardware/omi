import VoiceTurnDomain
import XCTest

@testable import Omi_Computer

final class ConversationEvidenceTests: XCTestCase {
  func testNativeOCRUsesRuntimeEvidenceEnvelopeAndPreservesMetadata() throws {
    let turnID = VoiceTurnID(UUID(uuidString: "00000000-0000-0000-0000-000000000001")!)
    let evidence = ConversationEvidence.nativeScreenOCR(
      evidenceID: "screen-1",
      capturedAt: Date(timeIntervalSince1970: 123),
      text: "Example Workshop\n2026 Project Plan",
      turnID: turnID,
      frontmostApp: "ChatGPT",
      frontmostBundleID: "com.openai.chat")

    let metadata = ConversationEvidenceMetadataCodec.metadataJSON(
      existing: #"{"continuityKey":"voice:one","screen_context":"historical"}"#,
      adding: evidence)
    let root = try XCTUnwrap(
      JSONSerialization.jsonObject(with: Data(metadata.utf8)) as? [String: Any])
    XCTAssertEqual(root["continuityKey"] as? String, "voice:one")
    let envelope = try XCTUnwrap(ConversationEvidenceMetadataCodec.envelope(from: metadata))
    XCTAssertEqual(envelope.schema, "omi.evidence@1")
    XCTAssertEqual(envelope.items, [evidence])
    XCTAssertEqual(evidence.kind, .screen)
    XCTAssertEqual(evidence.availability, .available)
    XCTAssertEqual(evidence.extractionCompleteness, .complete)
    XCTAssertEqual(evidence.provenance?["frontmost_app"], "ChatGPT")
    XCTAssertNil(evidence.artifactId)
  }

  func testUTF8BodyIsBoundedAndMarkedPartial() {
    let evidence = ConversationEvidence(
      id: "oversized",
      kind: .document,
      title: "Document",
      capturedAtMs: 1,
      availability: .available,
      extractionCompleteness: .complete,
      bodyText: String(repeating: "é", count: 100_000))

    XCTAssertNotNil(evidence.bodyText)
    XCTAssertLessThanOrEqual(evidence.bodyText!.utf8.count, ConversationEvidence.maxBodyBytes)
    XCTAssertEqual(evidence.extractionCompleteness, .partial)
    XCTAssertTrue(evidence.digest?.hasPrefix("sha256:") == true)
  }

  func testUnavailableEvidenceCarriesNoBodyOrFilePath() {
    let evidence = ConversationEvidence.nativeScreenOCR(
      evidenceID: "screen-unavailable",
      capturedAt: Date(timeIntervalSince1970: 10),
      text: nil,
      turnID: VoiceTurnID())

    XCTAssertEqual(evidence.availability, .unavailable)
    XCTAssertEqual(evidence.extractionCompleteness, .none)
    XCTAssertNil(evidence.bodyText)
    XCTAssertNil(evidence.artifactId)
  }

  func testPendingNativeOCRCarriesStableSourceWithoutPretendingExtraction() {
    let turnID = VoiceTurnID(UUID(uuidString: "00000000-0000-0000-0000-000000000002")!)
    let evidence = ConversationEvidence.pendingNativeScreenOCR(
      evidenceID: "ptt-ocr:00000000-0000-0000-0000-000000000002",
      capturedAt: Date(timeIntervalSince1970: 20),
      turnID: turnID,
      frontmostApp: "ChatGPT",
      frontmostBundleID: "com.openai.chat")

    XCTAssertEqual(evidence.availability, .pending)
    XCTAssertEqual(evidence.extractionCompleteness, .none)
    XCTAssertNil(evidence.bodyText)
    XCTAssertFalse(evidence.isReadable)
    XCTAssertEqual(evidence.capturedAtMs, 20_000)
    XCTAssertEqual(evidence.provenance?["source"], "native_ptt_ocr")
    XCTAssertEqual(evidence.provenance?["turn_id"], turnID.rawValue.uuidString.lowercased())
  }

  func testDuplicateStableEvidenceDoesNotRewriteMetadata() {
    let evidence = ConversationEvidence(
      id: "one",
      kind: .attachment,
      title: "Typed attachment",
      capturedAtMs: 1,
      availability: .available,
      extractionCompleteness: .complete,
      bodyText: "hello")
    let first = ConversationEvidenceMetadataCodec.metadataJSON(existing: "{}", adding: evidence)
    let second = ConversationEvidenceMetadataCodec.metadataJSON(existing: first, adding: evidence)
    XCTAssertEqual(second, first)
  }

  func testAtomicJournalUpdateCarriesOneEvidenceItemOnExistingAppendWire() throws {
    let evidence = ConversationEvidence(
      id: "screen-atomic",
      kind: .screen,
      title: "PTT screen OCR",
      capturedAtMs: 1,
      availability: .available,
      extractionCompleteness: .complete,
      bodyText: "visible")
    let data = try XCTUnwrap(JSONEncoder().encode(evidence))
    let update = KernelJournalTurnUpdate(
      turnId: "user-turn",
      status: nil,
      content: nil,
      contentBlocksJSON: nil,
      appendContentBlocksJSON: nil,
      resourcesJSON: nil,
      appendResourcesJSON: nil,
      appendEvidenceJSON: String(decoding: data, as: UTF8.self),
      metadataJSON: nil,
      terminalRevision: false)

    let wire = update.dictionary
    let items = try XCTUnwrap(wire["appendEvidence"] as? [[String: Any]])
    XCTAssertEqual(items.count, 1)
    XCTAssertEqual(items[0]["id"] as? String, "screen-atomic")
    XCTAssertNil(wire["metadataJson"])
  }

  func testPTTOCRKeepsLongEvidenceSeparateFromShortTranscriptFallback() {
    let source = String(repeating: "é", count: 40_000)
    let snapshot = PTTContextVocabularyProvider.snapshot(
      capturedAt: Date(timeIntervalSince1970: 1),
      settingsVocabulary: [],
      immediateOCRText: source)

    XCTAssertEqual(snapshot.visibleText?.count, 2_000)
    XCTAssertTrue(snapshot.visibleTextWasTruncated)
    XCTAssertEqual(snapshot.evidenceText?.utf8.count, ConversationEvidence.maxBodyBytes)
    XCTAssertTrue(snapshot.evidenceTextWasTruncated)
  }
}
