import XCTest

@testable import Omi_Computer

@MainActor
final class VoiceTypeTargetSafetyTests: XCTestCase {
  private final class Editor: DictationTextAccess {
    var field = "first-field"
    var value = "Original "
    var selection = NSRange(location: 9, length: 0)
    var readable = true
    var writable = true
    var writeSucceeds = true
    var writes: [String] = []
    var didSelect: (() -> Void)?
    var didWrite: (() -> Void)?

    func readFocusedText() -> FocusedDictationText? {
      guard readable else { return nil }
      return FocusedDictationText(
        elementID: AnyHashable(field), processID: 42, bundleIdentifier: "test.editor",
        value: value, selection: selection, canReplaceSelection: writable)
    }

    func replaceSelection(_ text: String, in target: TextInsertionTarget) -> Bool {
      guard writeSucceeds, readFocusedText()?.target == target else { return false }
      writes.append(text)
      value = (value as NSString).replacingCharacters(in: selection, with: text)
      selection = NSRange(location: selection.location + (text as NSString).length, length: 0)
      didWrite?()
      return true
    }

    func select(_ range: NSRange, in target: TextInsertionTarget) -> Bool {
      guard readFocusedText()?.target == target else { return false }
      selection = range
      didSelect?()
      return true
    }
  }

  @MainActor
  private final class Fixture {
    let editor = Editor()
    let authority = RuntimeOwnerAuthorizationAuthority()
    var owner = "owner-A"
    var trusted = true
    var clock: TimeInterval = 100
    var clipboard = "User clipboard"
    var postedPastes: [String] = []
    lazy var sink = PasteboardTextInsertionSink(
      access: editor, now: { [unowned self] in clock },
      clipboardPaste: { [unowned self] text, _ in
        postedPastes.append(text)
        return true
      },
      clipboardCopy: { [unowned self] in clipboard = $0 })
    lazy var session = VoiceTypeSession(
      sink: sink, isAccessibilityTrusted: { [unowned self] in trusted },
      captureAuthorization: { [unowned self] in authority.capture(ownerID: owner, expectedOwnerID: nil) },
      isAuthorizationCurrent: { [unowned self] in authority.isCurrent($0, ownerID: owner) })

    func begin() {
      session.begin()
      session.noteRelease()
      XCTAssertTrue(session.claim(transcript: "Type hello"))
    }

    func deliver(_ text: String = "Hello") {
      XCTAssertEqual(session.deliver(text), .pasted(text))
    }
  }

  func testSwitchingFieldsInTheSameAppCopiesInsteadOfWriting() {
    let fixture = Fixture()
    fixture.begin()
    fixture.editor.field = "second-field"
    XCTAssertEqual(fixture.session.deliver("Hello"), .copied("Hello"))
    XCTAssertTrue(fixture.editor.writes.isEmpty)
    XCTAssertTrue(fixture.postedPastes.isEmpty)
    XCTAssertEqual(fixture.clipboard, "Hello")
  }

  func testMovingCaretOrEditingTheSameFieldInvalidatesCapture() {
    for moveCaret in [true, false] {
      let fixture = Fixture()
      fixture.begin()
      if moveCaret { fixture.editor.selection.location = 2 } else { fixture.editor.value = "Changed! " }
      XCTAssertEqual(fixture.session.deliver("Hello"), .copied("Hello"))
      XCTAssertTrue(fixture.editor.writes.isEmpty)
      XCTAssertTrue(fixture.postedPastes.isEmpty)
    }
  }

  func testUnreadableTargetAndRevokedAccessibilityCopySafely() {
    for denied in [true, false] {
      let fixture = Fixture()
      if !denied { fixture.editor.readable = false }
      fixture.begin()
      if denied { fixture.trusted = false }
      XCTAssertEqual(fixture.session.deliver("Hello"), .copied("Hello"))
      XCTAssertTrue(fixture.editor.writes.isEmpty)
      XCTAssertTrue(fixture.postedPastes.isEmpty)
      XCTAssertFalse(fixture.session.canUndoLastDictation)
    }
  }

  func testReadableEditorWithoutWritableAXKeepsPasteButCannotUndo() {
    let fixture = Fixture()
    fixture.editor.writable = false
    fixture.begin()
    fixture.deliver()
    XCTAssertEqual(fixture.postedPastes, ["Hello"])
    XCTAssertFalse(fixture.session.canUndoLastDictation)
    XCTAssertFalse(fixture.session.undoLastDictation())
    XCTAssertTrue(fixture.editor.writes.isEmpty)
  }

  func testVerifiedInsertionUndoDeletesOnlyDictationAndPreservesClipboard() {
    let fixture = Fixture()
    fixture.editor.value = "Original"
    fixture.editor.selection.location = 8
    fixture.begin()
    fixture.deliver("Hello 🌍")
    XCTAssertEqual(fixture.editor.value, "Original Hello 🌍")
    // Successful manager terminal cleanup must not revoke the receipt.
    fixture.session.abandon()
    XCTAssertTrue(fixture.session.canUndoLastDictation)
    XCTAssertTrue(fixture.session.undoLastDictation())
    XCTAssertEqual(fixture.editor.value, "Original")
    XCTAssertEqual(fixture.editor.selection, NSRange(location: 8, length: 0))
    XCTAssertEqual(fixture.clipboard, "User clipboard")
    XCTAssertTrue(fixture.postedPastes.isEmpty)
    XCTAssertFalse(fixture.session.undoLastDictation())
  }

  func testReplacingSelectedContentDoesNotOfferDestructiveUndo() {
    let fixture = Fixture()
    fixture.editor.selection = NSRange(location: 0, length: 8)
    fixture.begin()
    fixture.deliver()
    XCTAssertEqual(fixture.editor.value, "Hello ")
    XCTAssertFalse(fixture.session.canUndoLastDictation)
  }

  func testUserEditOrCaretMoveRevokesUndoWithoutTouchingTheirWork() {
    for moveCaret in [true, false] {
      let fixture = Fixture()
      fixture.begin()
      fixture.deliver()
      if moveCaret { fixture.editor.selection.location = 1 } else { fixture.editor.value += " My next edit" }
      let expected = fixture.editor.value
      XCTAssertFalse(fixture.session.undoLastDictation())
      XCTAssertEqual(fixture.editor.value, expected)
      XCTAssertEqual(fixture.editor.writes, ["Hello"])
    }
  }

  func testUndoRevalidatesContentAfterSelectingTheInsertedRange() {
    let fixture = Fixture()
    fixture.begin()
    fixture.deliver()
    fixture.editor.didSelect = { fixture.editor.value += " Concurrent user edit" }
    XCTAssertFalse(fixture.session.undoLastDictation())
    XCTAssertEqual(fixture.editor.value, "Original Hello Concurrent user edit")
    XCTAssertEqual(fixture.editor.writes, ["Hello"])
  }

  func testNewTurnAndExpiryRevokeUndo() {
    for newTurn in [true, false] {
      let fixture = Fixture()
      fixture.begin()
      fixture.deliver()
      if newTurn { fixture.session.begin() } else { fixture.clock += 30 }
      XCTAssertFalse(fixture.session.undoLastDictation())
      XCTAssertEqual(fixture.editor.value, "Original Hello")
    }
  }

  func testOwnerChangeAndSameOwnerReauthenticationRevokeUndoAndDelivery() {
    for sameOwner in [true, false] {
      for delivered in [true, false] {
        let fixture = Fixture()
        fixture.begin()
        if delivered { fixture.deliver() }
        fixture.authority.beginTransition()
        if !sameOwner { fixture.owner = "owner-B" }
        fixture.authority.endTransition(ownerID: fixture.owner)
        XCTAssertFalse(fixture.session.undoLastDictation())
        if !delivered {
          XCTAssertEqual(fixture.session.deliver("Hello"), .none)
          XCTAssertTrue(fixture.editor.writes.isEmpty)
        }
        XCTAssertEqual(fixture.clipboard, "User clipboard")
      }
    }
  }

  func testSuccessfulAXReplyWithoutVerifiedTextFallsBackToCopyWithoutAnotherPaste() {
    let fixture = Fixture()
    fixture.begin()
    fixture.editor.didWrite = { fixture.editor.value = "Unexpected editor contents" }
    XCTAssertEqual(fixture.session.deliver("Hello"), .copied("Hello"))
    XCTAssertEqual(fixture.editor.writes, ["Hello"])
    XCTAssertEqual(fixture.editor.value, "Unexpected editor contents")
    XCTAssertEqual(fixture.clipboard, "Hello")
    XCTAssertTrue(fixture.postedPastes.isEmpty)
    XCTAssertFalse(fixture.session.canUndoLastDictation)
  }

  func testFailedAddressedWriteDoesNotRetryAnUncertainMutationWithPaste() {
    let fixture = Fixture()
    fixture.begin()
    fixture.editor.writeSucceeds = false
    XCTAssertEqual(fixture.session.deliver("Hello"), .copied("Hello"))
    XCTAssertTrue(fixture.postedPastes.isEmpty)
    XCTAssertFalse(fixture.session.canUndoLastDictation)
  }

  func testFailedWriteKeepsSeparatorForManualPasteIntoUnchangedTarget() {
    let fixture = Fixture()
    fixture.editor.value = "Original"
    fixture.editor.selection = NSRange(location: 8, length: 0)
    fixture.begin()
    fixture.editor.writeSucceeds = false
    XCTAssertEqual(fixture.session.deliver("Hello"), .copied("Hello"))
    XCTAssertEqual(fixture.clipboard, " Hello")
    XCTAssertEqual(fixture.editor.value, "Original")
    XCTAssertTrue(fixture.postedPastes.isEmpty)
  }
}
