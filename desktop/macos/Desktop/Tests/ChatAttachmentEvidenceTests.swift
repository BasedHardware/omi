import XCTest

@testable import Omi_Computer

@MainActor
final class ChatAttachmentEvidenceTests: XCTestCase {
  func testSupportedTextAttachmentPreservesUTF8AndSourceMetadata() async throws {
    let sourceText = "Company: Example Workshop\nUnits: 320\n✅"
    let fileURL = try writeTemporaryFile(named: "plan.json", contents: sourceText)
    defer { try? FileManager.default.removeItem(at: fileURL) }

    let attachment = ChatAttachment(
      id: "local-plan",
      fileName: "plan.json",
      mimeType: "application/json",
      serverId: "server-plan",
      localFileURL: fileURL,
      state: .uploaded
    )

    let capturedEvidence = await ChatAttachmentEvidence.capture(
      attachments: [attachment],
      capturedAt: Date(timeIntervalSince1970: 1_700_000_000)
    )
    let evidence = try XCTUnwrap(capturedEvidence.first)

    XCTAssertEqual(evidence.id, "attachment:local-plan")
    XCTAssertEqual(evidence.kind, .attachment)
    XCTAssertEqual(evidence.title, "plan.json")
    XCTAssertNil(evidence.artifactId)
    XCTAssertEqual(evidence.availability, .available)
    XCTAssertEqual(evidence.extractionCompleteness, .complete)
    XCTAssertEqual(evidence.bodyText, sourceText)
    XCTAssertEqual(evidence.capturedAtMs, 1_700_000_000_000)
    XCTAssertEqual(evidence.provenance?["filename"], "plan.json")
    XCTAssertEqual(evidence.provenance?["attachment_id"], "local-plan")
    XCTAssertEqual(evidence.provenance?["server_id"], "server-plan")
    XCTAssertFalse(evidence.provenance?.values.contains(fileURL.path) == true)
  }

  func testMissingAndNonTextAttachmentsAreUnavailable() async throws {
    let missingURL = FileManager.default.temporaryDirectory
      .appendingPathComponent("missing-\(UUID().uuidString).txt")
    let directoryURL = FileManager.default.temporaryDirectory
      .appendingPathComponent("directory-\(UUID().uuidString).txt")
    try FileManager.default.createDirectory(at: directoryURL, withIntermediateDirectories: false)
    defer { try? FileManager.default.removeItem(at: directoryURL) }
    let missing = ChatAttachment(
      id: "missing",
      fileName: "missing.txt",
      mimeType: "text/plain",
      localFileURL: missingURL,
      state: .localOnly
    )
    let directory = ChatAttachment(
      id: "directory",
      fileName: "directory.txt",
      mimeType: "text/plain",
      localFileURL: directoryURL,
      state: .localOnly
    )
    let image = ChatAttachment(
      id: "image",
      fileName: "screen.png",
      mimeType: "image/png",
      state: .uploaded
    )

    let evidence = await ChatAttachmentEvidence.capture(attachments: [missing, directory, image])

    XCTAssertEqual(evidence.count, 3)
    for item in evidence {
      XCTAssertEqual(item.availability, .unavailable)
      XCTAssertEqual(item.extractionCompleteness, .none)
      XCTAssertNil(item.bodyText)
    }
  }

  func testLongTextIsByteBoundedAndMarkedPartial() async throws {
    let longText = String(repeating: "🙂", count: ConversationEvidence.maxBodyBytes / 4 + 16)
    let fileURL = try writeTemporaryFile(named: "large.txt", contents: longText)
    defer { try? FileManager.default.removeItem(at: fileURL) }

    let attachment = ChatAttachment(
      id: "large",
      fileName: "large.txt",
      mimeType: "text/plain",
      localFileURL: fileURL,
      state: .localOnly
    )
    let capturedEvidence = await ChatAttachmentEvidence.capture(attachments: [attachment])
    let evidence = try XCTUnwrap(capturedEvidence.first)
    let body = try XCTUnwrap(evidence.bodyText)

    XCTAssertEqual(evidence.availability, .partial)
    XCTAssertEqual(evidence.extractionCompleteness, .partial)
    XCTAssertLessThanOrEqual(body.utf8.count, ConversationEvidence.maxBodyBytes)
    XCTAssertEqual(String(data: Data(body.utf8), encoding: .utf8), body)
    XCTAssertNotEqual(body, longText)
  }

  func testLongTextCutThroughUTF8ScalarRepairsOnlyBoundaryBytes() async throws {
    let emojiCount = ConversationEvidence.maxBodyBytes / 4
    let longText = "a" + String(repeating: "🙂", count: emojiCount)
    let fileURL = try writeTemporaryFile(named: "cut.txt", contents: longText)
    defer { try? FileManager.default.removeItem(at: fileURL) }

    let attachment = ChatAttachment(
      id: "cut",
      fileName: "cut.txt",
      mimeType: "text/plain",
      localFileURL: fileURL,
      state: .localOnly
    )
    let capturedEvidence = await ChatAttachmentEvidence.capture(attachments: [attachment])
    let evidence = try XCTUnwrap(capturedEvidence.first)
    let body = try XCTUnwrap(evidence.bodyText)

    XCTAssertEqual(evidence.extractionCompleteness, .partial)
    XCTAssertEqual(body, "a" + String(repeating: "🙂", count: emojiCount - 1))
    XCTAssertLessThanOrEqual(body.utf8.count, ConversationEvidence.maxBodyBytes)
  }

  func testInvalidUTF8InShortOrMiddleOfLongFileIsUnavailable() async throws {
    let shortURL = try writeTemporaryData(
      named: "invalid-short.txt",
      data: Data([0x6F, 0x80, 0x6B])
    )
    defer { try? FileManager.default.removeItem(at: shortURL) }
    let longData = Data([0x6F, 0xFF, 0x6B]) + Data(repeating: 0x61, count: ConversationEvidence.maxBodyBytes)
    let longURL = try writeTemporaryData(named: "invalid-middle.txt", data: longData)
    defer { try? FileManager.default.removeItem(at: longURL) }

    let attachments = [
      ChatAttachment(
        id: "invalid-short",
        fileName: "invalid-short.txt",
        mimeType: "text/plain",
        localFileURL: shortURL,
        state: .localOnly
      ),
      ChatAttachment(
        id: "invalid-middle",
        fileName: "invalid-middle.txt",
        mimeType: "text/plain",
        localFileURL: longURL,
        state: .localOnly
      ),
    ]

    let evidence = await ChatAttachmentEvidence.capture(attachments: attachments)

    XCTAssertEqual(evidence.count, 2)
    for item in evidence {
      XCTAssertEqual(item.availability, .unavailable)
      XCTAssertEqual(item.extractionCompleteness, .none)
      XCTAssertNil(item.bodyText)
    }
  }

  func testCapturedEvidenceMapsToUserMessageMetadata() async throws {
    let sourceText = "<p>Option agreement</p>"
    let fileURL = try writeTemporaryFile(named: "agreement.html", contents: sourceText)
    defer { try? FileManager.default.removeItem(at: fileURL) }
    let attachment = ChatAttachment(
      id: "agreement",
      fileName: "agreement.html",
      mimeType: "text/html",
      localFileURL: fileURL,
      state: .localOnly
    )

    let evidence = await ChatAttachmentEvidence.capture(attachments: [attachment])
    let metadata = MessageMetadata(evidence: evidence)
    let userMessage = ChatMessage(
      text: "Remember this agreement",
      sender: .user,
      metadata: metadata,
      attachments: [attachment]
    )

    XCTAssertEqual(userMessage.metadata?.evidence, evidence)
    XCTAssertEqual(userMessage.metadata?.evidence.first?.bodyText, sourceText)
  }

  private func writeTemporaryFile(named name: String, contents: String) throws -> URL {
    try writeTemporaryData(named: name, data: Data(contents.utf8))
  }

  private func writeTemporaryData(named name: String, data: Data) throws -> URL {
    let url = FileManager.default.temporaryDirectory
      .appendingPathComponent("\(UUID().uuidString)-\(name)")
    try data.write(to: url)
    return url
  }
}
