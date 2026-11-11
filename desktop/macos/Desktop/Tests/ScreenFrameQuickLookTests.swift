import XCTest

@testable import Omi_Computer

/// What can be pinned about the Quick Look viewer without a running panel.
///
/// The panel itself — whether the responder chain accepts it, whether it opens, whether the bytes
/// reach it — is not reachable from a unit test and is not reachable from a screenshot either:
/// `capture_main_window_png` uses `cacheDisplay`, which draws Omi's own content view and nothing
/// else, and Quick Look's panel is a system window. That half is verified by the
/// `screen_frame_quick_look_probe` automation action instead, which reads the live panel back.
/// What is left here is the part that decides whether the panel gets a *usable* file: the title it
/// shows, the extension that picks its renderer, the path it is written to, and the promise that
/// nothing survives the panel closing.
final class ScreenFrameQuickLookTests: XCTestCase {

  override func tearDown() {
    QuickLookScratch.purge()
    super.tearDown()
  }

  // MARK: - The extension is the UTI

  /// Quick Look picks its renderer from the UTI, and the UTI comes from the extension — so this is
  /// sniffed from the bytes rather than assumed from the source. A frame written with the wrong
  /// extension does not render badly, it renders not at all.
  func testExtensionIsSniffedFromTheBytesNotAssumed() {
    XCTAssertEqual(QuickLookScratch.fileExtension(for: Data([0xFF, 0xD8, 0xFF, 0xE0])), "jpg")
    XCTAssertEqual(
      QuickLookScratch.fileExtension(for: Data([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A])), "png")
    XCTAssertEqual(QuickLookScratch.fileExtension(for: Data("GIF89a".utf8)), "gif")
  }

  /// Unrecognised bytes default to JPEG because that is what both the capture pipeline and the
  /// egress pipeline emit — never to no extension at all, which Quick Look cannot type.
  func testUnknownBytesFallBackToJPEGRatherThanNoExtension() {
    XCTAssertEqual(QuickLookScratch.fileExtension(for: Data([0x00, 0x01, 0x02])), "jpg")
    XCTAssertEqual(QuickLookScratch.fileExtension(for: Data()), "jpg")
  }

  // MARK: - The id is not a path

  /// Frame ids come from the server and Rewind row ids come from a database; neither is a name
  /// this code chose. Anything that is not a letter or a digit is replaced, so no id can climb out
  /// of the scratch directory or collide with a directory separator.
  func testIdsNeverBecomePathComponents() throws {
    let url = try QuickLookScratch.write(Data([0xFF, 0xD8, 0xFF]), id: "../../etc/passwd")
    XCTAssertEqual(
      url.deletingLastPathComponent().standardizedFileURL,
      QuickLookScratch.directory.standardizedFileURL)
    XCTAssertFalse(url.lastPathComponent.contains("/"))
    XCTAssertEqual(url.pathExtension, "jpg")
  }

  /// An id made entirely of characters that get stripped still has to produce a file.
  func testAnIdThatSanitisesToNothingStillYieldsAFile() throws {
    let url = try QuickLookScratch.write(Data([0x89, 0x50, 0x4E, 0x47]), id: "///")
    XCTAssertTrue(url.lastPathComponent.hasPrefix("---"))
    XCTAssertEqual(url.pathExtension, "png")
    XCTAssertTrue(FileManager.default.fileExists(atPath: url.path))
  }

  /// **Sanitising collapses distinct ids onto the same string.** `frame/a` and `frame?a` both
  /// become `frame-a`, and two long ids can agree for their first 32 characters — so a name built
  /// from the id alone lets one frame's bytes overwrite another's, and both preview items then
  /// point at whichever landed last. Quick Look would show the wrong screenshot, which for this
  /// feature means showing a frame the reader did not ask to look at.
  func testFramesWhoseIdsSanitiseAlikeStillGetSeparateFiles() throws {
    let png = Data([0x89, 0x50, 0x4E, 0x47])
    let a = try QuickLookScratch.write(png, id: "frame/a")
    let b = try QuickLookScratch.write(png, id: "frame?a")
    let long1 = try QuickLookScratch.write(png, id: String(repeating: "x", count: 80) + "-one")
    let long2 = try QuickLookScratch.write(png, id: String(repeating: "x", count: 80) + "-two")

    XCTAssertNotEqual(a, b)
    XCTAssertNotEqual(long1, long2)
    XCTAssertEqual(
      Set([a, b, long1, long2].map(\.lastPathComponent)).count, 4,
      "four writes must occupy four files, or one frame is showing another frame's pixels")
  }

  /// The launch-time promise. It lives on a static rather than in the singleton's initialiser
  /// because `shared` is lazy: with the purge in `init`, a session where nobody opened Quick Look
  /// never ran it, and the frames a force-quit left behind sat there for the whole session —
  /// which is the exact case the launch purge exists to cover.
  func testStaleScratchIsPurgeableWithoutOpeningAPanel() throws {
    _ = try QuickLookScratch.write(Data([0xFF, 0xD8, 0xFF]), id: "left-behind")
    XCTAssertTrue(FileManager.default.fileExists(atPath: QuickLookScratch.directory.path))

    ScreenFrameQuickLook.purgeStaleScratch()

    XCTAssertFalse(FileManager.default.fileExists(atPath: QuickLookScratch.directory.path))
  }

  // MARK: - Nothing outlives the panel

  /// The reason this is a directory we own rather than loose files in the system's temp: purging
  /// is one `removeItem` whose effect can be asserted, instead of a filename pattern to trust.
  /// A *server* frame's bytes matter here — "delete this screenshot from the note" cannot reach a
  /// stray copy in `/tmp`, so the copy must not still be there.
  func testPurgeRemovesEveryMaterialisedFrame() throws {
    _ = try QuickLookScratch.write(Data([0xFF, 0xD8, 0xFF]), id: "frame-a")
    _ = try QuickLookScratch.write(Data([0xFF, 0xD8, 0xFF]), id: "frame-b")
    XCTAssertTrue(FileManager.default.fileExists(atPath: QuickLookScratch.directory.path))

    QuickLookScratch.purge()

    XCTAssertFalse(FileManager.default.fileExists(atPath: QuickLookScratch.directory.path))
  }

  // MARK: - What the panel's title bar says

  /// The window title is a real affordance, not decoration: it is the only place a Rewind moment
  /// says which app and which moment it was. The window title is the specific thing; the app name
  /// is the true fallback.
  func testARewindMomentIsTitledByItsWindowThenItsApp() {
    let titled = QuickLookFrame(screenshot: screenshot(app: "Xcode", window: "ScreenFrameQuickLook.swift"))
    XCTAssertTrue(titled.title.hasPrefix("ScreenFrameQuickLook.swift — "))

    let untitled = QuickLookFrame(screenshot: screenshot(app: "Xcode", window: nil))
    XCTAssertTrue(untitled.title.hasPrefix("Xcode — "))

    // A window title that only repeats the app name is not the specific thing it claims to be.
    let echoing = QuickLookFrame(screenshot: screenshot(app: "Xcode", window: "Xcode"))
    XCTAssertTrue(echoing.title.hasPrefix("Xcode — "))
  }

  /// An empty title would open a Quick Look window that reads as a failed load, so there is always
  /// something.
  func testATitleIsNeverEmpty() {
    let frame = QuickLookFrame(id: "x", source: .remote(URL(string: "https://example.com/a.jpg")!), title: "")
    XCTAssertEqual(frame.title, "Screenshot")
  }

  /// A persisted frame is titled by its caption, and a caption-less one still gets a name.
  func testAPersistedFrameIsTitledByItsCaption() throws {
    let captioned = try XCTUnwrap(QuickLookFrame(frame: persisted(caption: "The migration plan")))
    XCTAssertTrue(captioned.title.hasPrefix("The migration plan — "))

    let bare = try XCTUnwrap(QuickLookFrame(frame: persisted(caption: "")))
    XCTAssertTrue(bare.title.hasPrefix("Screenshot — "))
  }

  /// A `content_url` that does not parse has nothing to open. The frame drops out of the set
  /// rather than becoming a panel that opens onto nothing — which is what a `nil` return buys the
  /// caller, since `quickLookFrames` `compactMap`s over exactly this.
  func testAFrameWithAnUnopenableURLIsSkippedRatherThanShown() {
    XCTAssertNil(QuickLookFrame(frame: persisted(caption: "fine", contentURL: "")))
  }

  // MARK: - Fixtures

  private func screenshot(app: String, window: String?) -> Screenshot {
    Screenshot(
      id: 7,
      timestamp: Date(timeIntervalSince1970: 1_756_000_000),
      appName: app,
      windowTitle: window,
      imagePath: "a.jpg",
      videoChunkPath: nil,
      frameOffset: nil)
  }

  private func persisted(
    caption: String, contentURL: String = "https://example.com/frame.jpg"
  ) -> ConversationScreenFrame {
    ConversationScreenFrame(
      id: "frame-1",
      capturedAt: Date(timeIntervalSince1970: 1_756_000_000),
      role: "strip",
      rank: 0,
      caption: caption,
      labels: [],
      sourceBadge: nil,
      focalRegion: nil,
      width: 1600,
      height: 1000,
      contentURL: contentURL,
      thumbnailURL: "https://example.com/thumb.jpg",
      urlExpiresAt: Date(timeIntervalSince1970: 1_756_003_600),
      ground: nil)
  }
}
