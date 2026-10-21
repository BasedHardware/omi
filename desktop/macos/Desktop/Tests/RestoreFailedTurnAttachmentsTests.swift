import AppKit
import XCTest

@testable import Omi_Computer

/// A failed turn must not destroy the pixels the question was about: the send
/// path snapshots staged attachments and its exit cleanup deletes app-owned
/// files whether the turn succeeded or failed, so the failure branch re-stages
/// them — "Try again" re-sends the same image instead of a caption for files
/// that are gone.
@MainActor
final class RestoreFailedTurnAttachmentsTests: XCTestCase {
  private func tinyJPEGData() -> Data {
    let image = NSImage(
      size: NSSize(width: 2, height: 2),
      flipped: false,
      drawingHandler: { rect in
        NSColor.red.setFill()
        rect.fill()
        return true
      })
    guard let tiff = image.tiffRepresentation,
      let rep = NSBitmapImageRep(data: tiff),
      let jpeg = rep.representation(
        using: NSBitmapImageRep.FileType.jpeg,
        properties: [NSBitmapImageRep.PropertyKey.compressionFactor: 0.8])
    else { return Data() }
    return jpeg
  }

  private func stagedFrameAttachment() throws -> ChatAttachment {
    let attachment = try XCTUnwrap(
      RecentScreenFrameStaging.attachment(appName: "ChatGPT", jpegData: tinyJPEGData()))
    return attachment
  }

  func testAppOwnedFrameIsRestagedWithAFreshFileWhenItsFileIsAlreadyGone() throws {
    let provider = ChatProvider()
    let original = try stagedFrameAttachment()
    // Simulate the failed turn's exit cleanup: the temp file is deleted before
    // the restore runs, so only the in-memory bytes survive.
    let originalURL = try XCTUnwrap(original.appOwnedFileURL)
    try FileManager.default.removeItem(at: originalURL)

    provider.restoreFailedTurnAttachments([original], turnOwner: .mainChat)

    XCTAssertEqual(provider.pendingAttachments.count, 1, "the frame goes back in the composer")
    let restored = try XCTUnwrap(provider.pendingAttachments.first)
    let restoredURL = try XCTUnwrap(restored.appOwnedFileURL)
    defer { try? FileManager.default.removeItem(at: restoredURL) }
    XCTAssertNotEqual(restoredURL, originalURL, "a fresh app-owned file, not the deleted one")
    XCTAssertTrue(FileManager.default.fileExists(atPath: restoredURL.path))
    XCTAssertFalse((restored.data ?? Data()).isEmpty, "the pixels themselves survived")
  }

  func testUserPickedFilesAreRestoredAsTheyAre() throws {
    let provider = ChatProvider()
    let sourceURL = FileManager.default.temporaryDirectory
      .appendingPathComponent("restore-test-\(UUID().uuidString).jpg")
    try Data([0xFF, 0xD8]).write(to: sourceURL)
    defer { try? FileManager.default.removeItem(at: sourceURL) }
    let userFile = try XCTUnwrap(ChatAttachment.from(url: sourceURL))

    provider.restoreFailedTurnAttachments([userFile], turnOwner: .mainChat)

    XCTAssertEqual(provider.pendingAttachments.count, 1)
    XCTAssertNil(provider.pendingAttachments.first?.appOwnedFileURL)
    XCTAssertEqual(provider.pendingAttachments.first?.localFileURL, sourceURL)
  }

  func testRestoreIsSkippedForNonMainChatTurnsAndEmptyLists() {
    let provider = ChatProvider()
    provider.restoreFailedTurnAttachments([], turnOwner: .mainChat)
    provider.restoreFailedTurnAttachments(
      [ChatAttachment(fileName: "x.png", mimeType: "image/png")], turnOwner: .floatingDefault)
    XCTAssertTrue(provider.pendingAttachments.isEmpty)
  }
}
