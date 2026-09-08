import Combine
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
    var appliesWrite = true
    var replacementResult: DictationTextReplacementResult = .applied
    var writes: [String] = []
    var didSelect: (() -> Void)?
    var didWrite: (() -> Void)?

    func readFocusedText() -> FocusedDictationText? {
      guard readable else { return nil }
      return FocusedDictationText(
        elementID: AnyHashable(field), processID: 42, bundleIdentifier: "test.editor",
        value: value, selection: selection, canReplaceSelection: writable)
    }

    func replaceSelection(_ text: String, in target: TextInsertionTarget) -> DictationTextReplacementResult {
      guard writeSucceeds, readFocusedText()?.target == target else { return .notAttempted }
      writes.append(text)
      if appliesWrite {
        value = (value as NSString).replacingCharacters(in: selection, with: text)
        selection = NSRange(location: selection.location + (text as NSString).length, length: 0)
      }
      didWrite?()
      return replacementResult
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
    var receiptSleeper: (@MainActor (TimeInterval) async throws -> Void)?
    lazy var sink = makeSink()

    private func makeSink() -> PasteboardTextInsertionSink {
      let paste: (String, TextInsertionTarget) -> Bool = { [unowned self] text, _ in
        postedPastes.append(text)
        return true
      }
      let copy: (String) -> Void = { [unowned self] in clipboard = $0 }
      if let receiptSleeper {
        return PasteboardTextInsertionSink(
          access: editor, now: { [unowned self] in clock },
          clipboardPaste: paste, clipboardCopy: copy,
          sleepForReceiptExpiry: receiptSleeper)
      }
      return PasteboardTextInsertionSink(
        access: editor, now: { [unowned self] in clock },
        clipboardPaste: paste, clipboardCopy: copy)
    }

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

  func testReadableEditorWithoutWritableAXRequestsPasteWithoutClaimingDelivery() {
    let fixture = Fixture()
    fixture.editor.writable = false
    fixture.begin()
    let completion = fixture.session.deliver("Hello")
    XCTAssertEqual(completion, .pasteRequested("Hello"))
    XCTAssertFalse(completion.isConfirmedDelivery)
    XCTAssertEqual(completion.statusHint, "Paste requested — check the editor")
    XCTAssertEqual(fixture.postedPastes, ["Hello"])
    XCTAssertEqual(fixture.clipboard, "User clipboard", "no copy-for-retry fallback follows a dispatched paste")
    XCTAssertFalse(fixture.session.canUndoLastDictation)
    XCTAssertFalse(fixture.session.undoLastDictation())
    XCTAssertTrue(fixture.editor.writes.isEmpty)
  }

  func testSinkReportsPasteDispatchSeparatelyFromVerifiedInsertion() throws {
    let fixture = Fixture()
    fixture.editor.writable = false
    let target = try XCTUnwrap(fixture.sink.focusTarget())
    XCTAssertEqual(fixture.sink.paste("Hello", into: target), .pastePosted)
    XCTAssertEqual(fixture.postedPastes, ["Hello"])
    XCTAssertFalse(fixture.sink.canUndoInsertion)
    XCTAssertEqual(fixture.editor.value, "Original ", "dispatch alone supplies no insertion evidence")
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

  func testSuccessfulAXReplyWithoutVerifiedTextReportsUncertaintyWithoutCopying() {
    let fixture = Fixture()
    fixture.begin()
    fixture.editor.didWrite = { fixture.editor.value = "Unexpected editor contents" }
    XCTAssertEqual(fixture.session.deliver("Hello"), .insertionUncertain("Hello"))
    XCTAssertEqual(fixture.editor.writes, ["Hello"])
    XCTAssertEqual(fixture.editor.value, "Unexpected editor contents")
    XCTAssertEqual(fixture.clipboard, "User clipboard")
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

  func testMenuFocusAvailabilityReadsPreserveReceiptUntilTheAction() {
    for menuHasReadableElement in [true, false] {
      let fixture = Fixture()
      fixture.begin()
      fixture.deliver()
      fixture.editor.readable = menuHasReadableElement
      fixture.editor.field = "menu"
      XCTAssertTrue(fixture.session.canUndoLastDictation)
      XCTAssertTrue(fixture.session.canUndoLastDictation)
      XCTAssertEqual(fixture.editor.writes, ["Hello"])
      // Native menu dismissal restores focus. The action still validates it.
      fixture.editor.readable = true
      fixture.editor.field = "first-field"
      XCTAssertTrue(fixture.session.undoLastDictation())
      XCTAssertEqual(fixture.editor.value, "Original ")
    }
  }

  func testAvailabilityDoesNotAuthorizeUndoIntoAMenuOrAnotherField() {
    for readable in [true, false] {
      let fixture = Fixture()
      fixture.begin()
      fixture.deliver()
      fixture.editor.readable = readable
      fixture.editor.field = "second-field"
      XCTAssertTrue(fixture.session.canUndoLastDictation)
      XCTAssertFalse(fixture.session.undoLastDictation())
      XCTAssertEqual(fixture.editor.writes, ["Hello"])
      XCTAssertEqual(fixture.editor.value, "Original Hello")
      fixture.editor.readable = true
      fixture.editor.field = "first-field"
      XCTAssertFalse(fixture.session.canUndoLastDictation, "a rejected action consumes the receipt")
    }
  }

  func testEarlyExpiryWakeReschedulesAndPublishesAtTheMonotonicDeadline() async {
    let fixture = Fixture()
    let sleeperStarted = expectation(description: "expiry sleep started")
    let sleeperRescheduled = expectation(description: "early wake rescheduled")
    var durations: [TimeInterval] = []
    var resumeExpiry: CheckedContinuation<Void, Never>?
    fixture.receiptSleeper = { remaining in
      durations.append(remaining)
      await withCheckedContinuation { continuation in
        resumeExpiry = continuation
        if durations.count == 1 { sleeperStarted.fulfill() } else { sleeperRescheduled.fulfill() }
      }
    }
    fixture.begin()
    fixture.deliver()
    await fulfillment(of: [sleeperStarted], timeout: 1)
    let expired = expectation(description: "receipt expiry published")
    var publications = 0
    let subscription = fixture.session.objectWillChange.sink {
      publications += 1
      expired.fulfill()
    }
    fixture.clock += 5
    resumeExpiry?.resume()
    await fulfillment(of: [sleeperRescheduled], timeout: 1)
    XCTAssertEqual(durations, [30, 25])
    XCTAssertEqual(publications, 0)
    XCTAssertTrue(fixture.session.canUndoLastDictation)
    fixture.clock += 25
    resumeExpiry?.resume()
    await fulfillment(of: [expired], timeout: 1)
    XCTAssertFalse(fixture.session.canUndoLastDictation)
    XCTAssertEqual(fixture.editor.value, "Original Hello")
    subscription.cancel()
  }

  func testOwnerRevocationAndExpiryStillOverrideMenuAvailability() {
    for expire in [true, false] {
      let fixture = Fixture()
      fixture.begin()
      fixture.deliver()
      fixture.editor.readable = false
      XCTAssertTrue(fixture.session.canUndoLastDictation)
      if expire { fixture.clock += 30 } else { fixture.authority.beginTransition() }
      XCTAssertFalse(fixture.session.canUndoLastDictation)
      fixture.editor.readable = true
      XCTAssertFalse(fixture.session.undoLastDictation())
      XCTAssertEqual(fixture.editor.value, "Original Hello")
    }
  }

  func testPartialMutationWithFailedAXReplyIsUncertainAndNeverCopiedForRetry() {
    let fixture = Fixture()
    fixture.begin()
    // Models AXUIElementSetAttributeValue returning a failure after only part
    // of the requested replacement reached the editor.
    fixture.editor.replacementResult = .uncertain
    fixture.editor.didWrite = {
      fixture.editor.value = "Original Hel"
      fixture.editor.selection = NSRange(location: 12, length: 0)
    }
    XCTAssertEqual(fixture.session.deliver("Hello"), .insertionUncertain("Hello"))
    XCTAssertEqual(fixture.editor.value, "Original Hel")
    XCTAssertEqual(fixture.editor.writes, ["Hello"])
    XCTAssertEqual(fixture.clipboard, "User clipboard")
    XCTAssertTrue(fixture.postedPastes.isEmpty)
    XCTAssertFalse(fixture.session.canUndoLastDictation)
  }

  func testFailedDispatchedAXRequestWithUnchangedRereadRemainsUncertain() {
    let fixture = Fixture()
    fixture.begin()
    fixture.editor.appliesWrite = false
    fixture.editor.replacementResult = .uncertain
    XCTAssertEqual(fixture.session.deliver("Hello"), .insertionUncertain("Hello"))
    XCTAssertEqual(fixture.editor.value, "Original ")
    XCTAssertEqual(fixture.clipboard, "User clipboard")
    XCTAssertTrue(fixture.postedPastes.isEmpty)
    XCTAssertFalse(fixture.session.canUndoLastDictation)
  }

  func testFailedAXReplyWithExactVerifiedResultIsAConfirmedInsertion() {
    let fixture = Fixture()
    fixture.begin()
    fixture.editor.replacementResult = .uncertain
    fixture.deliver()
    XCTAssertEqual(fixture.editor.value, "Original Hello")
    XCTAssertTrue(fixture.session.undoLastDictation())
    XCTAssertEqual(fixture.editor.value, "Original ")
    XCTAssertEqual(fixture.clipboard, "User clipboard")
  }

  func testCompletionProjectionsNeverDescribeAnUncertainInsertionAsCopiedOrTyped() {
    let uncertain = VoiceTypeSession.Completion.insertionUncertain("Hello")
    XCTAssertEqual(uncertain.statusHint, "Insertion unconfirmed — check the editor")
    XCTAssertEqual(uncertain.journalAcknowledgement, "Dictation insertion unconfirmed; check the editor: Hello")
    XCTAssertEqual(uncertain.text, "Hello")
    XCTAssertFalse(uncertain.isConfirmedDelivery)

    let requested = VoiceTypeSession.Completion.pasteRequested("Hello")
    XCTAssertEqual(requested.statusHint, "Paste requested — check the editor")
    XCTAssertEqual(requested.journalAcknowledgement, "Paste requested; check the editor: Hello")
    XCTAssertEqual(requested.text, "Hello")
    XCTAssertFalse(requested.isConfirmedDelivery)

    let copied = VoiceTypeSession.Completion.copied("Hello")
    XCTAssertEqual(copied.statusHint, "Copied — press ⌘V to paste")
    XCTAssertEqual(copied.journalAcknowledgement, "Copied to clipboard: Hello")
    XCTAssertTrue(copied.isConfirmedDelivery)

    let pasted = VoiceTypeSession.Completion.pasted("Hello")
    XCTAssertNil(pasted.statusHint)
    XCTAssertEqual(pasted.journalAcknowledgement, "Typed: Hello")
    XCTAssertTrue(pasted.isConfirmedDelivery)

    let none = VoiceTypeSession.Completion.none
    XCTAssertNil(none.statusHint)
    XCTAssertNil(none.journalAcknowledgement)
    XCTAssertFalse(none.isConfirmedDelivery)
  }

}
