import AppKit
import OmiTheme
import SwiftUI
import XCTest

@testable import Omi_Computer

/// Dropping a file on the chat composer only worked on its border. The interior is an `NSTextView`,
/// which sits above the composer's SwiftUI `.onDrop` layer and consumes file drags itself — so the
/// drop highlight lit only over the padding, and a release over the text never staged the file.
/// `OmiTextEditor` already solves this for the skill editor with `onFileDrop` / `onFileDragTargeted`;
/// these tests pin the same wiring on the chat composers, driven through the real `NSTextView` each
/// one puts on screen.
@MainActor
final class ChatComposerDropTests: XCTestCase {

  // MARK: - ChatInputView

  /// The interior of the main chat input stages a dropped file as an attachment — through the text
  /// view itself, the exact surface the reader drops onto, and without the file's path leaking
  /// into the draft the way AppKit's own drag handling inserts it.
  func testAFileDroppedOnTheChatInputsTextStagesAnAttachment() throws {
    let mount = try ChatInputMount()
    defer { mount.tearDown() }

    let url = try Self.composerDropProbeFile()
    defer { try? FileManager.default.removeItem(at: url) }

    XCTAssertTrue(
      mount.dropFileOnTheEditorText(url),
      "the chat input declined a file drag released over its text")

    XCTAssertEqual(
      mount.stagedURLs, [url],
      "a drop on the middle of the input never staged the file — only the border ever did")
    XCTAssertEqual(
      mount.draft, "",
      "the dropped file's path leaked into the draft instead of staging")
  }

  /// The task-sidebar chat passes no attachments binding, so its interior must keep declining
  /// drops. The staging callback is present anyway so the gate itself is what this asserts: if the
  /// editor's interior were wired unconditionally, this drop would stage.
  func testTheAttachmentLessInputKeepsDecliningInteriorDrops() throws {
    let mount = try ChatInputMount(attachmentsEnabled: false)
    defer { mount.tearDown() }

    let url = try Self.composerDropProbeFile()
    defer { try? FileManager.default.removeItem(at: url) }

    _ = mount.dropFileOnTheEditorText(url)

    XCTAssertTrue(
      mount.stagedURLs.isEmpty,
      "an input with no attachment support staged a dropped file from its interior")
  }

  // MARK: - Wiring tripwire

  /// The drop stroke the shell's `.onDrop` lights over its padding must also be lit from inside the
  /// editor. `isDropTargeted` is private to each composer and which closure a call site passes
  /// cannot be read back from a mounted view, so the highlight wiring is pinned where it is
  /// written; the staging half of the same wiring is covered behaviorally above.
  func testBothComposersLightTheDropStrokeFromInsideTheEditor() throws {
    // Both composers must pass `onFileDragTargeted` (and `onFileDrop`) to their `OmiTextEditor`
    // so the drop stroke lights over the text itself; ChatInputView keeps its pair gated on
    // `attachmentsEnabled` so the task sidebar never becomes a drop target.
    let hero = try composerSource("MainWindow/QueryShell/QueryHeroBar.swift")
    XCTAssertTrue(
      hero.contains("onFileDrop: { url in onAttachmentsAdded([url]) }"),
      "QueryHeroBar's editor interior no longer stages dropped files")
    XCTAssertTrue(
      hero.contains("onFileDragTargeted: { isDropTargeted = $0 }"),
      "QueryHeroBar's drop stroke no longer lights over the text")

    let input = try composerSource("MainWindow/Components/ChatInputView.swift")
    XCTAssertTrue(
      input.contains("onFileDragTargeted: attachmentsEnabled ? { isDropTargeted = $0 } : nil"),
      "ChatInputView's drop stroke no longer lights over the text")
    XCTAssertFalse(
      input.contains("onFileDragTargeted: { isDropTargeted = $0 }"),
      "ChatInputView wired its editor interior unconditionally — the task sidebar must keep "
        + "declining drops")
  }

  // MARK: - Shared drop harness

  /// A real file on disk, because the editor reads the drag with `urlReadingFileURLsOnly`.
  static func composerDropProbeFile() throws -> URL {
    let url = FileManager.default.temporaryDirectory
      .appendingPathComponent("omi-composer-drop-\(UUID().uuidString).png")
    try Data([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]).write(to: url)
    return url
  }

  private func composerSource(_ relativePath: String) throws -> String {
    let url = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources")
      .appendingPathComponent(relativePath)
    // omi-test-quality: source-inspection -- static contract: which callbacks a composer's OmiTextEditor call site passes cannot be read back from a mounted view
    return try String(contentsOf: url, encoding: .utf8)
  }

  /// `ChatInputView` in a window, with the `NSTextView` it puts on screen located rather than
  /// assumed — the same mounting discipline as `QueryComposerTests`.
  @MainActor
  private final class ChatInputMount {
    let window: NSWindow
    private let host: NSHostingView<Host>
    private let textView: NSTextView
    private let box: DraftBox

    init(attachmentsEnabled: Bool = true) throws {
      box = DraftBox()
      host = NSHostingView(
        rootView: Host(
          box: box,
          attachmentsEnabled: attachmentsEnabled))
      host.frame = NSRect(x: 0, y: 0, width: 560, height: 120)
      window = NSWindow(
        contentRect: host.frame, styleMask: [.titled], backing: .buffered, defer: false)
      window.contentView = host
      host.layoutSubtreeIfNeeded()
      guard let found = Self.firstTextView(in: host) else {
        throw XCTSkip("SwiftUI built no NSTextView for the chat input in this environment")
      }
      textView = found
    }

    var stagedURLs: [URL] { host.rootView.probe.stagedURLs }
    var draft: String { box.text }

    /// A file drag released over the editor's own text — entered, performed, and settled.
    func dropFileOnTheEditorText(_ url: URL) -> Bool {
      let board = NSPasteboard(name: NSPasteboard.Name("omi.test.chatDrop.\(UUID().uuidString)"))
      board.clearContents()
      board.writeObjects([url as NSURL])
      let info = FileDragInfo(pasteboard: board)
      _ = textView.draggingEntered(info)
      let accepted = textView.performDragOperation(info)
      host.layoutSubtreeIfNeeded()
      return accepted
    }

    func tearDown() {
      window.contentView = nil
    }

    private static func firstTextView(in view: NSView) -> NSTextView? {
      if let textView = view as? NSTextView { return textView }
      for subview in view.subviews {
        if let found = firstTextView(in: subview) { return found }
      }
      return nil
    }
  }

  private struct Host: View {
    let box: DraftBox
    var attachmentsEnabled = true
    let probe = DropProbe()

    var body: some View {
      ChatInputView(
        onSend: { _ in },
        isSending: false,
        mode: .constant(.act),
        inputText: Binding(get: { box.text }, set: { box.text = $0 }),
        attachments: attachmentsEnabled ? .constant([]) : nil,
        onAttachmentsAdded: { urls in probe.stagedURLs.append(contentsOf: urls) }
      )
      .padding()
    }
  }

  @MainActor
  private final class DraftBox {
    var text = ""
  }

  @MainActor
  private final class DropProbe {
    var stagedURLs: [URL] = []
  }
}

/// One file drag in flight, as Finder begins one. Only `draggingPasteboard` is read on the paths
/// under test; the rest satisfy the protocol with inert values. The protocol's requirements are
/// MainActor-isolated in the SDK except the deprecated `draggedImage`, so the class is `@MainActor`
/// with that one member `nonisolated`.
@MainActor
final class FileDragInfo: NSObject, NSDraggingInfo {
  let draggingPasteboard: NSPasteboard

  init(pasteboard: NSPasteboard) {
    self.draggingPasteboard = pasteboard
    super.init()
  }

  var draggingDestinationWindow: NSWindow? { nil }
  var draggingSourceOperationMask: NSDragOperation { .copy }
  var draggingLocation: NSPoint { .zero }
  var draggedImageLocation: NSPoint { .zero }
  var draggingSequenceNumber: Int { 1 }
  var draggingSource: Any? { nil }
  nonisolated var draggedImage: NSImage? { nil }
  var slidesOnExit: Bool { false }
  var animatesToDestination = false
  var draggingFormation: NSDraggingFormation {
    get { .none }
    set {}
  }
  var numberOfValidItemsForDrop = 1
  var springLoadingHighlight: NSSpringLoadingHighlight { .none }

  func enumerateDraggingItems(
    options: NSDraggingItemEnumerationOptions, for view: NSView?, classes: [AnyClass],
    searchOptions: [NSPasteboard.ReadingOptionKey: Any],
    using block: @escaping (NSDraggingItem, Int, UnsafeMutablePointer<ObjCBool>) -> Void
  ) {}

  func slideDraggedImage(to screenPoint: NSPoint) {}
  func resetSpringLoading() {}

  func draggingItem(index: Int) -> NSDraggingItem {
    NSDraggingItem(pasteboardWriter: NSPasteboardItem())
  }

  func hitTestForRefreshedDirtyView() -> NSView? { nil }
}
