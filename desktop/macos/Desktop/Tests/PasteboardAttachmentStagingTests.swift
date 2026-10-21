import AppKit
import OmiTheme
import XCTest

@testable import Omi_Computer

/// The ⌘V attachment path: the classifier decides text-vs-attachments, and the
/// staging turns pasteboard content into the same staged attachments the
/// paperclip produces (user files for copied files, app-owned temp files for
/// pasted image bytes).
@MainActor
final class PasteboardAttachmentStagingTests: XCTestCase {
  private func makeBoard() -> NSPasteboard {
    let board = NSPasteboard(name: NSPasteboard.Name("paste-tests-\(UUID().uuidString)"))
    board.clearContents()
    return board
  }

  // MARK: - Classifier (what ⌘V routes to staging vs text paste)

  func testScreenshotOnBoardClassifiesAsAttachments() {
    let board = makeBoard()
    board.setData(twoByTwoTIFF(), forType: .tiff)
    XCTAssertTrue(OmiTextEditor.pasteCarriesAttachments(board))
  }

  func testCopiedFileOnBoardClassifiesAsAttachments() {
    let board = makeBoard()
    board.setData(tempJPEGURL().dataRepresentation, forType: .fileURL)
    XCTAssertTrue(OmiTextEditor.pasteCarriesAttachments(board))
  }

  func testTextOnlyBoardIsATextPaste() {
    let board = makeBoard()
    board.setString("just words", forType: .string)
    XCTAssertFalse(OmiTextEditor.pasteCarriesAttachments(board))
  }

  func testTextRidingAlongKeepsItATextPaste() {
    // Copying a paragraph out of a web page carries image flavors beside the
    // text; that must stay a text paste — no phantom attachments.
    let board = makeBoard()
    board.setData(twoByTwoTIFF(), forType: .tiff)
    board.setString("a copied paragraph", forType: .string)
    XCTAssertFalse(OmiTextEditor.pasteCarriesAttachments(board))
  }

  func testEmptyBoardIsATextPaste() {
    XCTAssertFalse(OmiTextEditor.pasteCarriesAttachments(makeBoard()))
  }

  // MARK: - Staging (pasteboard content → staged attachments)

  func testPastedScreenshotStagesAsAppOwnedJPEG() async throws {
    let board = makeBoard()
    board.setData(twoByTwoTIFF(), forType: .tiff)

    let staged = await PasteboardAttachmentStaging.stageAttachments(from: board)

    XCTAssertEqual(staged.count, 1)
    let attachment = try XCTUnwrap(staged.first)
    XCTAssertTrue(attachment.isImage)
    let ownedURL = try XCTUnwrap(attachment.appOwnedFileURL)
    XCTAssertEqual(
      ownedURL.deletingLastPathComponent(), PasteboardAttachmentStaging.imagesDirectoryForTesting,
      "a pasted shot stages into the app-owned staging directory, directly inside it")
    XCTAssertTrue(FileManager.default.fileExists(atPath: ownedURL.path))
    let bytes = try XCTUnwrap(attachment.data)
    XCTAssertFalse(bytes.isEmpty)
    XCTAssertNotNil(NSImage(data: bytes), "the staged file decodes back to pixels")
    try? FileManager.default.removeItem(at: ownedURL)
  }

  func testCopiedFileStagesAsUserFileWithoutAppOwnership() async throws {
    let sourceURL = tempJPEGURL()
    let board = makeBoard()
    board.setData(sourceURL.dataRepresentation, forType: .fileURL)

    let staged = await PasteboardAttachmentStaging.stageAttachments(from: board)

    XCTAssertEqual(staged.count, 1)
    let attachment = try XCTUnwrap(staged.first)
    XCTAssertNil(
      attachment.appOwnedFileURL,
      "a copied file belongs to the user; the app must never delete it")
    XCTAssertEqual(attachment.localFileURL, sourceURL)
  }

  func testUnreadableBoardStagesNothing() async {
    let staged = await PasteboardAttachmentStaging.stageAttachments(from: makeBoard())
    XCTAssertTrue(staged.isEmpty)
  }

  func testCopiedImageFileDoesNotDoubleStage() async throws {
    // A copied image file carries its file URL *and* image flavors; staging
    // both would paste the same picture twice — once as a user file, once as
    // an app-owned copy.
    let sourceURL = tempJPEGURL()
    let board = makeBoard()
    board.setData(sourceURL.dataRepresentation, forType: .fileURL)
    board.setData(twoByTwoTIFF(), forType: .tiff)

    let staged = await PasteboardAttachmentStaging.stageAttachments(from: board)

    XCTAssertEqual(staged.count, 1)
    let attachment = try XCTUnwrap(staged.first)
    XCTAssertNil(attachment.appOwnedFileURL, "the file flavor wins; no app-owned copy beside it")
  }

  // MARK: - Fixtures

  /// A 2×2 red TIFF — the flavor a ⌘⇧⌃4 capture puts on the board.
  private func twoByTwoTIFF() -> Data {
    let rep = NSBitmapImageRep(
      bitmapDataPlanes: nil, pixelsWide: 2, pixelsHigh: 2, bitsPerSample: 8,
      samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB,
      bytesPerRow: 0, bitsPerPixel: 0)
    guard let rep else { return Data() }
    rep.size = NSSize(width: 2, height: 2)
    for x in 0..<2 {
      for y in 0..<2 {
        rep.setColor(NSColor.red, atX: x, y: y)
      }
    }
    return rep.tiffRepresentation ?? Data()
  }

  private func tempJPEGURL() -> URL {
    let url = FileManager.default.temporaryDirectory.appendingPathComponent("paste-test-\(UUID().uuidString).jpg")
    let tiny = NSImage(
      size: NSSize(width: 2, height: 2),
      flipped: false,
      drawingHandler: { rect in
        NSColor.red.setFill()
        rect.fill()
        return true
      })
    let tiff = tiny.tiffRepresentation ?? Data()
    let any = NSBitmapImageRep(data: tiff)
    let jpeg =
      any?.representation(
        using: NSBitmapImageRep.FileType.jpeg,
        properties: [NSBitmapImageRep.PropertyKey.compressionFactor: 0.8]
      ) ?? Data()
    try? jpeg.write(to: url)
    return url
  }
}
