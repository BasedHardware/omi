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
    /// Reads that must pass before an applied write becomes visible, the way a
    /// web-backed editor applies one on a later run-loop turn.
    var readsBeforeWriteIsVisible = 0
    /// Where the editor parks the caret once it has applied the write, for
    /// editors that do not collapse it after the inserted text.
    var caretAfterWrite: NSRange?
    private var pendingWrite: (value: String, selection: NSRange)?
    private(set) var reads = 0
    var writes: [String] = []
    var didSelect: (() -> Void)?
    var didWrite: (() -> Void)?

    func readFocusedText() -> FocusedDictationText? {
      reads += 1
      guard readable else { return nil }
      if let pendingWrite {
        if readsBeforeWriteIsVisible > 0 {
          readsBeforeWriteIsVisible -= 1
        } else {
          value = pendingWrite.value
          selection = pendingWrite.selection
          self.pendingWrite = nil
        }
      }
      return FocusedDictationText(
        elementID: AnyHashable(field), processID: 42, bundleIdentifier: "test.editor",
        value: value, selection: selection, canReplaceSelection: writable)
    }

    func replaceSelection(_ text: String, in target: TextInsertionTarget) -> DictationTextReplacementResult {
      guard writeSucceeds, readFocusedText()?.target == target else { return .notAttempted }
      writes.append(text)
      if appliesWrite {
        let written = (value as NSString).replacingCharacters(in: selection, with: text)
        let caret =
          caretAfterWrite ?? NSRange(location: selection.location + (text as NSString).length, length: 0)
        if readsBeforeWriteIsVisible > 0 {
          pendingWrite = (written, caret)
        } else {
          value = written
          selection = caret
        }
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
    /// Whether a dispatched Cmd-V reaches the editor, as it does in an app
    /// that reads the pasteboard but exposes no writable selected text.
    var pasteLands = false
    /// Wall-clock a verification tick costs, for an app whose Accessibility
    /// server answers slowly enough that ten reads would hold the turn.
    var verificationTickCost: TimeInterval = 0
    var receiptSleeper: (@MainActor (TimeInterval) async throws -> Void)?
    lazy var sink = makeSink()

    private func makeSink() -> PasteboardTextInsertionSink {
      let paste: (String, TextInsertionTarget) -> Bool = { [unowned self] text, _ in
        postedPastes.append(text)
        if pasteLands {
          editor.value = (editor.value as NSString).replacingCharacters(in: editor.selection, with: text)
          editor.selection = NSRange(
            location: editor.selection.location + (text as NSString).length, length: 0)
        }
        return true
      }
      let copy: (String) -> Void = { [unowned self] in clipboard = $0 }
      // Verification polling runs its reads back to back: the editor fake
      // decides when the insertion becomes visible, not the wall clock.
      let noVerificationDelay: @MainActor (TimeInterval) async throws -> Void = { [unowned self] _ in
        clock += verificationTickCost
      }
      if let receiptSleeper {
        return PasteboardTextInsertionSink(
          access: editor, now: { [unowned self] in clock },
          clipboardPaste: paste, clipboardCopy: copy,
          sleepForReceiptExpiry: receiptSleeper, sleepForVerification: noVerificationDelay)
      }
      return PasteboardTextInsertionSink(
        access: editor, now: { [unowned self] in clock },
        clipboardPaste: paste, clipboardCopy: copy,
        sleepForVerification: noVerificationDelay)
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

    func deliver(_ text: String = "Hello") async {
      let delivered = await session.deliver(text)
      XCTAssertEqual(delivered, .pasted(text))
    }
  }

  func testSwitchingFieldsInTheSameAppCopiesInsteadOfWriting() async {
    let fixture = Fixture()
    fixture.begin()
    fixture.editor.field = "second-field"
    let delivered = await fixture.session.deliver("Hello")
    XCTAssertEqual(delivered, .copied("Hello"))
    XCTAssertTrue(fixture.editor.writes.isEmpty)
    XCTAssertTrue(fixture.postedPastes.isEmpty)
    XCTAssertEqual(fixture.clipboard, "Hello")
  }

  func testMovingCaretOrEditingTheSameFieldInvalidatesCapture() async {
    for moveCaret in [true, false] {
      let fixture = Fixture()
      fixture.begin()
      if moveCaret { fixture.editor.selection.location = 2 } else { fixture.editor.value = "Changed! " }
      let delivered = await fixture.session.deliver("Hello")
      XCTAssertEqual(delivered, .copied("Hello"))
      XCTAssertTrue(fixture.editor.writes.isEmpty)
      XCTAssertTrue(fixture.postedPastes.isEmpty)
    }
  }

  func testUnreadableTargetAndRevokedAccessibilityCopySafely() async {
    for denied in [true, false] {
      let fixture = Fixture()
      if !denied { fixture.editor.readable = false }
      fixture.begin()
      if denied { fixture.trusted = false }
      let delivered = await fixture.session.deliver("Hello")
      XCTAssertEqual(delivered, .copied("Hello"))
      XCTAssertTrue(fixture.editor.writes.isEmpty)
      XCTAssertTrue(fixture.postedPastes.isEmpty)
      XCTAssertFalse(fixture.session.canUndoLastDictation)
    }
  }

  func testReadableEditorWithoutWritableAXRequestsPasteWithoutClaimingDelivery() async {
    let fixture = Fixture()
    fixture.editor.writable = false
    fixture.begin()
    let completion = await fixture.session.deliver("Hello")
    XCTAssertEqual(completion, .pasteRequested("Hello"))
    XCTAssertFalse(completion.isConfirmedDelivery)
    XCTAssertEqual(completion.statusHint, "Couldn't confirm it landed — check the editor")
    XCTAssertEqual(fixture.postedPastes, ["Hello"])
    XCTAssertEqual(fixture.clipboard, "User clipboard", "no copy-for-retry fallback follows a dispatched paste")
    XCTAssertFalse(fixture.session.canUndoLastDictation)
    XCTAssertFalse(fixture.session.undoLastDictation())
    XCTAssertTrue(fixture.editor.writes.isEmpty)
  }

  func testSinkReportsPasteDispatchSeparatelyFromVerifiedInsertion() async throws {
    let fixture = Fixture()
    fixture.editor.writable = false
    let target = try XCTUnwrap(fixture.sink.focusTarget())
    let result = await fixture.sink.paste("Hello", into: target)
    XCTAssertEqual(result, .pastePosted)
    XCTAssertEqual(fixture.postedPastes, ["Hello"])
    XCTAssertFalse(fixture.sink.canUndoInsertion)
    XCTAssertEqual(fixture.editor.value, "Original ", "dispatch alone supplies no insertion evidence")
  }

  func testVerifiedInsertionUndoDeletesOnlyDictationAndPreservesClipboard() async {
    let fixture = Fixture()
    fixture.editor.value = "Original"
    fixture.editor.selection.location = 8
    fixture.begin()
    await fixture.deliver("Hello 🌍")
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

  func testReplacingSelectedContentDoesNotOfferDestructiveUndo() async {
    let fixture = Fixture()
    fixture.editor.selection = NSRange(location: 0, length: 8)
    fixture.begin()
    await fixture.deliver()
    XCTAssertEqual(fixture.editor.value, "Hello ")
    XCTAssertFalse(fixture.session.canUndoLastDictation)
  }

  func testUserEditOrCaretMoveRevokesUndoWithoutTouchingTheirWork() async {
    for moveCaret in [true, false] {
      let fixture = Fixture()
      fixture.begin()
      await fixture.deliver()
      if moveCaret { fixture.editor.selection.location = 1 } else { fixture.editor.value += " My next edit" }
      let expected = fixture.editor.value
      XCTAssertFalse(fixture.session.undoLastDictation())
      XCTAssertEqual(fixture.editor.value, expected)
      XCTAssertEqual(fixture.editor.writes, ["Hello"])
    }
  }

  func testUndoRevalidatesContentAfterSelectingTheInsertedRange() async {
    let fixture = Fixture()
    fixture.begin()
    await fixture.deliver()
    fixture.editor.didSelect = { fixture.editor.value += " Concurrent user edit" }
    XCTAssertFalse(fixture.session.undoLastDictation())
    XCTAssertEqual(fixture.editor.value, "Original Hello Concurrent user edit")
    XCTAssertEqual(fixture.editor.writes, ["Hello"])
  }

  func testNewTurnAndExpiryRevokeUndo() async {
    for newTurn in [true, false] {
      let fixture = Fixture()
      fixture.begin()
      await fixture.deliver()
      if newTurn { fixture.session.begin() } else { fixture.clock += 30 }
      XCTAssertFalse(fixture.session.undoLastDictation())
      XCTAssertEqual(fixture.editor.value, "Original Hello")
    }
  }

  func testOwnerChangeAndSameOwnerReauthenticationRevokeUndoAndDelivery() async {
    for sameOwner in [true, false] {
      for delivered in [true, false] {
        let fixture = Fixture()
        fixture.begin()
        if delivered { await fixture.deliver() }
        fixture.authority.beginTransition()
        if !sameOwner { fixture.owner = "owner-B" }
        fixture.authority.endTransition(ownerID: fixture.owner)
        XCTAssertFalse(fixture.session.undoLastDictation())
        if !delivered {
          let delivered = await fixture.session.deliver("Hello")
          XCTAssertEqual(delivered, .none)
          XCTAssertTrue(fixture.editor.writes.isEmpty)
        }
        XCTAssertEqual(fixture.clipboard, "User clipboard")
      }
    }
  }

  func testSuccessfulAXReplyWithoutVerifiedTextReportsUncertaintyWithoutCopying() async {
    let fixture = Fixture()
    fixture.begin()
    fixture.editor.didWrite = { fixture.editor.value = "Unexpected editor contents" }
    let delivered = await fixture.session.deliver("Hello")
    XCTAssertEqual(delivered, .insertionUncertain("Hello"))
    XCTAssertEqual(fixture.editor.writes, ["Hello"])
    XCTAssertEqual(fixture.editor.value, "Unexpected editor contents")
    XCTAssertEqual(fixture.clipboard, "User clipboard")
    XCTAssertTrue(fixture.postedPastes.isEmpty)
    XCTAssertFalse(fixture.session.canUndoLastDictation)
  }

  func testFailedAddressedWriteDoesNotRetryAnUncertainMutationWithPaste() async {
    let fixture = Fixture()
    fixture.begin()
    fixture.editor.writeSucceeds = false
    let delivered = await fixture.session.deliver("Hello")
    XCTAssertEqual(delivered, .copied("Hello"))
    XCTAssertTrue(fixture.postedPastes.isEmpty)
    XCTAssertFalse(fixture.session.canUndoLastDictation)
  }

  func testFailedWriteKeepsSeparatorForManualPasteIntoUnchangedTarget() async {
    let fixture = Fixture()
    fixture.editor.value = "Original"
    fixture.editor.selection = NSRange(location: 8, length: 0)
    fixture.begin()
    fixture.editor.writeSucceeds = false
    let delivered = await fixture.session.deliver("Hello")
    XCTAssertEqual(delivered, .copied("Hello"))
    XCTAssertEqual(fixture.clipboard, " Hello")
    XCTAssertEqual(fixture.editor.value, "Original")
    XCTAssertTrue(fixture.postedPastes.isEmpty)
  }

  func testMenuFocusAvailabilityReadsPreserveReceiptUntilTheAction() async {
    for menuHasReadableElement in [true, false] {
      let fixture = Fixture()
      fixture.begin()
      await fixture.deliver()
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

  func testAvailabilityDoesNotAuthorizeUndoIntoAMenuOrAnotherField() async {
    for readable in [true, false] {
      let fixture = Fixture()
      fixture.begin()
      await fixture.deliver()
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
    await fixture.deliver()
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

  func testOwnerRevocationAndExpiryStillOverrideMenuAvailability() async {
    for expire in [true, false] {
      let fixture = Fixture()
      fixture.begin()
      await fixture.deliver()
      fixture.editor.readable = false
      XCTAssertTrue(fixture.session.canUndoLastDictation)
      if expire { fixture.clock += 30 } else { fixture.authority.beginTransition() }
      XCTAssertFalse(fixture.session.canUndoLastDictation)
      fixture.editor.readable = true
      XCTAssertFalse(fixture.session.undoLastDictation())
      XCTAssertEqual(fixture.editor.value, "Original Hello")
    }
  }

  func testPartialMutationWithFailedAXReplyIsUncertainAndNeverCopiedForRetry() async {
    let fixture = Fixture()
    fixture.begin()
    // Models AXUIElementSetAttributeValue returning a failure after only part
    // of the requested replacement reached the editor.
    fixture.editor.replacementResult = .uncertain
    fixture.editor.didWrite = {
      fixture.editor.value = "Original Hel"
      fixture.editor.selection = NSRange(location: 12, length: 0)
    }
    let delivered = await fixture.session.deliver("Hello")
    XCTAssertEqual(delivered, .insertionUncertain("Hello"))
    XCTAssertEqual(fixture.editor.value, "Original Hel")
    XCTAssertEqual(fixture.editor.writes, ["Hello"])
    XCTAssertEqual(fixture.clipboard, "User clipboard")
    XCTAssertTrue(fixture.postedPastes.isEmpty)
    XCTAssertFalse(fixture.session.canUndoLastDictation)
  }

  func testFailedDispatchedAXRequestWithUnchangedRereadRemainsUncertain() async {
    let fixture = Fixture()
    fixture.begin()
    fixture.editor.appliesWrite = false
    fixture.editor.replacementResult = .uncertain
    let delivered = await fixture.session.deliver("Hello")
    XCTAssertEqual(delivered, .insertionUncertain("Hello"))
    XCTAssertEqual(fixture.editor.value, "Original ")
    XCTAssertEqual(fixture.clipboard, "User clipboard")
    XCTAssertTrue(fixture.postedPastes.isEmpty)
    XCTAssertFalse(fixture.session.canUndoLastDictation)
  }

  func testFailedAXReplyWithExactVerifiedResultIsAConfirmedInsertion() async {
    let fixture = Fixture()
    fixture.begin()
    fixture.editor.replacementResult = .uncertain
    await fixture.deliver()
    XCTAssertEqual(fixture.editor.value, "Original Hello")
    XCTAssertTrue(fixture.session.undoLastDictation())
    XCTAssertEqual(fixture.editor.value, "Original ")
    XCTAssertEqual(fixture.clipboard, "User clipboard")
  }

  func testAnEditorThatAppliesTheWriteOnALaterReadIsAConfirmedInsertion() async {
    // Web-backed and Electron editors apply an addressed write a run-loop turn
    // or two after the request. A single immediate read called those correct
    // insertions unverified, and the bar sent the user off to check an editor
    // that already had the dictation in it.
    let fixture = Fixture()
    fixture.begin()
    fixture.editor.readsBeforeWriteIsVisible = 3
    await fixture.deliver()
    XCTAssertEqual(fixture.editor.value, "Original Hello")
    XCTAssertTrue(fixture.session.canUndoLastDictation)
  }

  func testAnEditorThatParksTheCaretElsewhereStillConfirmsTheInsertion() async {
    // The exact expected value is in the captured field, so the text landed.
    // Where the editor then left the caret is the receipt's business.
    let fixture = Fixture()
    fixture.begin()
    fixture.editor.caretAfterWrite = NSRange(location: 0, length: 0)
    let delivered = await fixture.session.deliver("Hello")
    XCTAssertEqual(delivered, .pasted("Hello"))
    XCTAssertEqual(fixture.editor.value, "Original Hello")
    XCTAssertEqual(fixture.clipboard, "User clipboard")
    XCTAssertFalse(fixture.session.canUndoLastDictation, "no verified caret, no range to take back")
  }

  func testAPasteReadBackFromTheEditorIsAConfirmedInsertion() async {
    let fixture = Fixture()
    fixture.editor.writable = false
    fixture.pasteLands = true
    fixture.begin()
    let delivered = await fixture.session.deliver("Hello")
    XCTAssertEqual(delivered, .pasted("Hello"))
    XCTAssertEqual(fixture.postedPastes, ["Hello"])
    XCTAssertEqual(fixture.editor.value, "Original Hello")
    XCTAssertEqual(fixture.clipboard, "User clipboard", "a landed paste is never copied for retry")
    XCTAssertFalse(fixture.session.canUndoLastDictation, "Cmd-V hands back no inserted range")
  }

  func testAnAcknowledgedWriteThatChangedNothingFallsBackToPaste() async {
    // The Chromium shape, measured live: AXSelectedText reports settable, the
    // write is answered with success, and the field is untouched. Before this
    // the turn ended as an unverified insertion and the dictation was lost.
    let fixture = Fixture()
    fixture.editor.appliesWrite = false
    fixture.pasteLands = true
    fixture.begin()
    let delivered = await fixture.session.deliver("Hello")
    XCTAssertEqual(delivered, .pasted("Hello"))
    XCTAssertEqual(fixture.editor.writes, ["Hello"], "the addressed write is still tried first")
    XCTAssertEqual(fixture.postedPastes, ["Hello"])
    XCTAssertEqual(fixture.editor.value, "Original Hello")
    XCTAssertEqual(fixture.clipboard, "User clipboard")
    XCTAssertFalse(fixture.session.canUndoLastDictation, "Cmd-V hands back no inserted range")
  }

  func testADroppedWriteThatCannotBePastedEitherIsReportedNotTyped() async {
    let fixture = Fixture()
    fixture.editor.appliesWrite = false
    fixture.begin()
    let delivered = await fixture.session.deliver("Hello")
    XCTAssertEqual(delivered, .pasteRequested("Hello"))
    XCTAssertEqual(fixture.postedPastes, ["Hello"])
    XCTAssertEqual(fixture.editor.value, "Original ")
    XCTAssertEqual(fixture.clipboard, "User clipboard", "a dispatched paste is never copied for retry")
  }

  func testAnEditorThatMovedUnderAnAcknowledgedWriteIsNeverRetriedWithPaste() async {
    // Anything other than the captured field, caret and revision may hold a
    // half-applied write. Only an untouched field earns the Cmd-V retry.
    let fixture = Fixture()
    fixture.begin()
    fixture.editor.didWrite = {
      fixture.editor.value = "Original Hel"
      fixture.editor.selection = NSRange(location: 12, length: 0)
    }
    let delivered = await fixture.session.deliver("Hello")
    XCTAssertEqual(delivered, .insertionUncertain("Hello"))
    XCTAssertTrue(fixture.postedPastes.isEmpty)
    XCTAssertEqual(fixture.clipboard, "User clipboard")
  }

  func testASlowAccessibilityServerCannotStretchVerificationPastItsWindow() async {
    // Every read is a synchronous AX round trip. Against an app whose AX
    // server answers slowly, the read count alone would let verification hold
    // the turn for seconds, so the elapsed window ends it first.
    let fixture = Fixture()
    fixture.begin()
    // An errored reply keeps the turn on the single verification pass: an
    // acknowledged write that changed nothing goes on to Cmd-V instead.
    fixture.editor.appliesWrite = false
    fixture.editor.replacementResult = .uncertain
    fixture.verificationTickCost = 0.2
    let delivered = await fixture.session.deliver("Hello")
    XCTAssertEqual(delivered, .insertionUncertain("Hello"))
    // Two capture reads (release, delivery) and two inside the paste (its own
    // pre-read and the write's guard), then the 0.4s window admits three
    // verification reads at 0.2s a tick — not the ten the count allows.
    XCTAssertEqual(fixture.editor.reads, 7, "the window, not the read count, ended the wait")
  }

  func testCompletionProjectionsNeverDescribeAnUncertainInsertionAsCopiedOrTyped() {
    let uncertain = VoiceTypeSession.Completion.insertionUncertain("Hello")
    XCTAssertEqual(uncertain.statusHint, "Couldn't confirm it landed — check the editor")
    XCTAssertEqual(uncertain.journalAcknowledgement, "Dictation insertion unconfirmed; check the editor: Hello")
    XCTAssertEqual(uncertain.text, "Hello")
    XCTAssertFalse(uncertain.isConfirmedDelivery)

    let requested = VoiceTypeSession.Completion.pasteRequested("Hello")
    XCTAssertEqual(requested.statusHint, "Couldn't confirm it landed — check the editor")
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
