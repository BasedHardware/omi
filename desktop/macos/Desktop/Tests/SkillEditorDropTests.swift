import AppKit
import XCTest

@testable import OmiTheme

/// Dropping a SKILL.md on the skill editor inserted the file's *path*: AppKit's NSTextView handles
/// a file drag itself and covers any SwiftUI `.onDrop` layered behind it, so the host's handler —
/// the one that reads the file — only ever ran on the few points of padding around the text.
final class SkillEditorDropTests: XCTestCase {
  private func pasteboard(named name: String) -> NSPasteboard {
    let board = NSPasteboard(name: NSPasteboard.Name(rawValue: name))
    board.clearContents()
    return board
  }

  /// The discriminator the editor's drag overrides run on: file drags go to the host's callback,
  /// text drags stay with AppKit so ordinary editing is untouched.
  @MainActor
  func testFileDragsAreDistinguishedFromTextDrags() throws {
    let files = pasteboard(named: "omi.test.filedrag.\(UUID().uuidString)")
    files.writeObjects([URL(fileURLWithPath: "/tmp/SKILL.md") as NSURL])
    XCTAssertTrue(OmiTextEditor.dragCarriesFile(files))

    let text = pasteboard(named: "omi.test.textdrag.\(UUID().uuidString)")
    text.setString("---\nname: x\n---\n", forType: .string)
    XCTAssertFalse(
      OmiTextEditor.dragCarriesFile(text), "dragged skill text must still drop into the editor")

    let empty = pasteboard(named: "omi.test.emptydrag.\(UUID().uuidString)")
    XCTAssertFalse(OmiTextEditor.dragCarriesFile(empty))
  }
}
