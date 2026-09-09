import CoreGraphics
import VoiceTurnDomain
import XCTest

@testable import Omi_Computer

final class ConversationEvidenceTests: XCTestCase {
  func testNativeOCRUsesRuntimeEvidenceEnvelopeAndPreservesMetadata() throws {
    let turnID = VoiceTurnID(try XCTUnwrap(UUID(uuidString: "00000000-0000-0000-0000-000000000001")))
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

  func testUTF8BodyIsBoundedAndMarkedPartial() throws {
    let evidence = ConversationEvidence(
      id: "oversized",
      kind: .document,
      title: "Document",
      capturedAtMs: 1,
      availability: .available,
      extractionCompleteness: .complete,
      bodyText: String(repeating: "é", count: 100_000))

    let bodyText = try XCTUnwrap(evidence.bodyText)
    XCTAssertLessThanOrEqual(bodyText.utf8.count, ConversationEvidence.maxBodyBytes)
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

  func testPendingNativeOCRCarriesStableSourceWithoutPretendingExtraction() throws {
    let turnID = VoiceTurnID(try XCTUnwrap(UUID(uuidString: "00000000-0000-0000-0000-000000000002")))
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

  func testPreferredCaptureEmptyOCRDoesNotRecaptureFrontmost() async throws {
    XCTAssertEqual(
      PTTContextVocabularyProvider.immediateScreenTextSource(intent: .frozen(nil)),
      .preferredImage)
    XCTAssertEqual(
      PTTContextVocabularyProvider.immediateScreenTextSource(intent: .liveFrontmost),
      .liveFrontmostCapture)

    let spy = CaptureSelectionSpy()
    let failedFrozen = await PTTContextVocabularyProvider.captureImmediateScreenText(
      intent: .frozen(nil),
      extractFromPreferredImage: { _ in
        spy.preferred += 1
        return "should-not-run"
      },
      captureFrontmost: {
        spy.live += 1
        return "overlay-surface"
      })
    XCTAssertNil(failedFrozen)
    XCTAssertEqual(spy.preferred, 0)
    XCTAssertEqual(spy.live, 0)

    let image = try makeTestImage()
    spy.preferred = 0
    spy.live = 0
    let emptyPreferred = await PTTContextVocabularyProvider.captureImmediateScreenText(
      intent: .frozen(image),
      extractFromPreferredImage: { _ in
        spy.preferred += 1
        return nil
      },
      captureFrontmost: {
        spy.live += 1
        return "overlay-surface"
      })
    XCTAssertNil(emptyPreferred)
    XCTAssertEqual(spy.preferred, 1)
    XCTAssertEqual(spy.live, 0)

    spy.preferred = 0
    spy.live = 0
    let live = await PTTContextVocabularyProvider.captureImmediateScreenText(
      intent: .liveFrontmost,
      extractFromPreferredImage: { _ in
        spy.preferred += 1
        return "preferred"
      },
      captureFrontmost: {
        spy.live += 1
        return "frontmost"
      })
    XCTAssertEqual(live, "frontmost")
    XCTAssertEqual(spy.preferred, 0)
    XCTAssertEqual(spy.live, 1)

    let turnID = VoiceTurnID()
    let capturedAt = Date(timeIntervalSince1970: 9)
    let snapshot = PTTContextVocabularyProvider.snapshot(
      capturedAt: capturedAt,
      settingsVocabulary: [],
      immediateOCRText: "")
    XCTAssertNil(snapshot.evidenceText)
    XCTAssertEqual(snapshot.sourceCount, 0)

    let evidence = ConversationEvidence.nativeScreenOCR(
      evidenceID: "ptt-ocr:\(turnID.rawValue.uuidString.lowercased())",
      capturedAt: capturedAt,
      text: snapshot.evidenceText,
      turnID: turnID,
      frontmostApp: "Codex",
      frontmostBundleID: "com.openai.codex")
    XCTAssertEqual(evidence.availability, .unavailable)
    XCTAssertEqual(evidence.extractionCompleteness, .none)
    XCTAssertNil(evidence.bodyText)
    XCTAssertEqual(evidence.provenance?["frontmost_app"], "Codex")
    XCTAssertEqual(evidence.capturedAtMs, 9_000)
  }

  func testProvidedDigestDescribesRetainedBytesWhenBodyExists() {
    let retained = "visible form text"
    let mismatched = ConversationEvidence(
      id: "digest-mismatch",
      kind: .attachment,
      title: "notes.txt",
      capturedAtMs: 1,
      availability: .available,
      extractionCompleteness: .complete,
      bodyText: retained,
      digest: "sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff")
    let honest = ConversationEvidence(
      id: "digest-mismatch",
      kind: .attachment,
      title: "notes.txt",
      capturedAtMs: 1,
      availability: .available,
      extractionCompleteness: .complete,
      bodyText: retained)

    XCTAssertEqual(mismatched.bodyText, retained)
    XCTAssertEqual(mismatched.digest, honest.digest)
    XCTAssertNotEqual(
      mismatched.digest,
      "sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff")
  }

  func testTruncatedBodyDigestMatchesRetainedBytesNotCallerDigest() {
    let original = String(repeating: "é", count: 100_000)
    let evidence = ConversationEvidence(
      id: "truncated-digest",
      kind: .document,
      title: "Document",
      capturedAtMs: 1,
      availability: .available,
      extractionCompleteness: .complete,
      bodyText: original,
      digest: "sha256:0000000000000000000000000000000000000000000000000000000000000000")
    let retained = evidence.bodyText
    XCTAssertNotEqual(retained, original)
    let honestRetained = ConversationEvidence(
      id: "truncated-digest",
      kind: .document,
      title: "Document",
      capturedAtMs: 1,
      availability: .available,
      extractionCompleteness: .complete,
      bodyText: retained)

    XCTAssertEqual(evidence.extractionCompleteness, .partial)
    XCTAssertEqual(evidence.digest, honestRetained.digest)
  }

  func testBodylessEvidenceKeepsCallerDigest() {
    let digest = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    let evidence = ConversationEvidence(
      id: "bodyless",
      kind: .document,
      title: "artifact-only",
      capturedAtMs: 1,
      availability: .available,
      extractionCompleteness: .none,
      digest: digest,
      artifactId: "artifact-1")

    XCTAssertNil(evidence.bodyText)
    XCTAssertEqual(evidence.digest, digest)
    XCTAssertEqual(evidence.artifactId, "artifact-1")
  }

  func testEightEscapedBodiesStayWithinMetadataBudgetWithoutDroppingItems() throws {
    let escapingBody = String(repeating: "\"\\\n", count: ConversationEvidence.maxBodyBytes / 3)
    XCTAssertGreaterThanOrEqual(escapingBody.utf8.count, ConversationEvidence.maxBodyBytes - 3)
    let items = (0..<ConversationEvidence.maxItems).map { index in
      ConversationEvidence(
        id: "escape-\(index)",
        kind: .attachment,
        title: "notes-\(index).txt",
        capturedAtMs: 1,
        availability: .available,
        extractionCompleteness: .complete,
        bodyText: escapingBody)
    }
    let envelope = ConversationEvidenceEnvelope(items: items)
    let encodedObject = try XCTUnwrap(ConversationEvidenceMetadataCodec.encodeEnvelope(envelope))
    let encoded = try JSONSerialization.data(withJSONObject: encodedObject)

    XCTAssertEqual(envelope.items.count, ConversationEvidence.maxItems)
    XCTAssertLessThanOrEqual(encoded.count, ConversationEvidence.maxMetadataBytes)
    XCTAssertTrue(envelope.items.contains { $0.bodyText != nil })
    XCTAssertTrue(
      envelope.items.contains {
        $0.bodyText == nil && $0.availability == .partial && $0.extractionCompleteness == .partial
      })
    for item in envelope.items {
      let original = try XCTUnwrap(items.first { $0.id == item.id })
      XCTAssertEqual(item.digest, original.digest)
      if let body = item.bodyText {
        XCTAssertEqual(item.availability, .available)
        XCTAssertEqual(item.extractionCompleteness, .complete)
        XCTAssertEqual(body, original.bodyText)
      } else {
        XCTAssertEqual(item.availability, .partial)
        XCTAssertEqual(item.extractionCompleteness, .partial)
      }
    }
  }

  func testSmallEightItemEnvelopeKeepsEveryBody() throws {
    let items = (0..<ConversationEvidence.maxItems).map { index in
      ConversationEvidence(
        id: "small-\(index)",
        kind: .attachment,
        title: "small-\(index).txt",
        capturedAtMs: 1,
        availability: .available,
        extractionCompleteness: .complete,
        bodyText: "item-\(index)")
    }
    let envelope = ConversationEvidenceEnvelope(items: items)
    XCTAssertEqual(envelope.items.map(\.bodyText), items.map(\.bodyText))
    let encodedObject = try XCTUnwrap(ConversationEvidenceMetadataCodec.encodeEnvelope(envelope))
    let encoded = try JSONSerialization.data(withJSONObject: encodedObject)
    XCTAssertLessThanOrEqual(encoded.count, ConversationEvidence.maxMetadataBytes)
  }

  @MainActor
  func testJournalWriteEncodesBudgetedEnvelopeInsteadOfRejectingAdmission() throws {
    let escapingBody = String(repeating: "\"\\\n", count: ConversationEvidence.maxBodyBytes / 3)
    let evidence = (0..<ConversationEvidence.maxItems).map { index in
      ConversationEvidence(
        id: "journal-\(index)",
        kind: .attachment,
        title: "notes-\(index).txt",
        capturedAtMs: 1,
        availability: .available,
        extractionCompleteness: .complete,
        bodyText: escapingBody)
    }
    let message = ChatMessage(
      text: "remember these notes",
      sender: .user,
      metadata: MessageMetadata(evidence: evidence))
    let write = message.journalWrite(origin: "typed_chat", status: .completed, continuityKey: "typed:one")
    let root = try XCTUnwrap(
      JSONSerialization.jsonObject(with: Data(write.metadataJSON.utf8)) as? [String: Any])
    let rawEvidence = try XCTUnwrap(root[ConversationEvidenceMetadataCodec.metadataKey])
    let evidenceData = try JSONSerialization.data(withJSONObject: rawEvidence)
    let envelope = try XCTUnwrap(ConversationEvidenceMetadataCodec.envelope(from: write.metadataJSON))

    XCTAssertLessThanOrEqual(evidenceData.count, ConversationEvidence.maxMetadataBytes)
    XCTAssertLessThanOrEqual(write.metadataJSON.utf8.count, ConversationEvidence.maxMetadataBytes)
    XCTAssertEqual(envelope.items.count, ConversationEvidence.maxItems)
    XCTAssertTrue(envelope.items.contains { $0.bodyText != nil })
    XCTAssertTrue(envelope.items.contains { $0.bodyText == nil && $0.availability == .partial })
  }

  private func makeTestImage() throws -> CGImage {
    let context = try XCTUnwrap(
      CGContext(
        data: nil, width: 2, height: 2, bitsPerComponent: 8, bytesPerRow: 0,
        space: CGColorSpaceCreateDeviceRGB(),
        bitmapInfo: CGImageAlphaInfo.premultipliedFirst.rawValue
          | CGBitmapInfo.byteOrder32Little.rawValue))
    return try XCTUnwrap(context.makeImage())
  }
}

private final class CaptureSelectionSpy: @unchecked Sendable {
  var preferred = 0
  var live = 0
}
