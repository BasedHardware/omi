import ApplicationServices
import Combine
import Foundation

/// One push-to-talk turn's worth of voice typing.
///
/// The session is the only thing that decides whether a turn dictates into the
/// focused app instead of asking Omi, and the only thing that delivers the
/// text. Nothing is delivered while the key is held: the turn is recorded
/// whole, transcribed once the key comes up, and pasted in one piece — the
/// transcript of a finished utterance is more accurate than any moving edge,
/// and text that is pasted once is never rewritten under the user.
///
/// The decision latches in one direction only: once a turn is typing it stays
/// typing, because a later, better transcript may change the words but must
/// never change their destination. *Not* typing never latches — a mid-hold
/// probe hears a couple of seconds of a sentence the user has barely started,
/// which is not evidence about the closing transcript.
@MainActor
final class VoiceTypeSession: ObservableObject {

  private let sink: TextInsertionSink
  private let isAccessibilityTrusted: () -> Bool
  private let captureAuthorization: () -> RuntimeOwnerAuthorizationSnapshot?
  private let isAuthorizationCurrent: (RuntimeOwnerAuthorizationSnapshot) -> Bool
  private var captureOwner: RuntimeOwnerAuthorizationSnapshot?
  @Published private var insertionOwner: RuntimeOwnerAuthorizationSnapshot?

  private enum Latch {
    case none
    case typing
    /// A type command that cannot be pasted (no Accessibility grant), but still
    /// belongs to voice typing — delivered by clipboard copy instead. Latched
    /// so one denied turn reports one fallback, not one per transcript.
    case blocked
  }

  /// What a finished turn delivered. The caller journals the text so the
  /// dictation joins the conversation history; a turn that never dictated has
  /// nothing to record.
  enum Completion: Equatable {
    /// Why a turn ended on the clipboard. The two reasons need different words:
    /// one is a permission the user can turn on, the other is a race with their
    /// own focus that nothing needs fixing for.
    enum CopyReason: Equatable {
      /// No Accessibility grant, so no insertion was attempted at all.
      case accessibilityDenied
      /// Omi was allowed to type, but the destination was not there to type
      /// into: focus moved, or no insertion could be dispatched. The text is on
      /// the clipboard rather than in the wrong app.
      case insertionUnavailable
    }

    case none
    /// The exact insertion was read back from the captured field.
    case pasted(String)
    /// Paste was dispatched to the captured app and the editor never showed it
    /// landing. Clipboard restoration still belongs to the sink.
    case pasteRequested(String)
    /// The text was left on the clipboard instead of being inserted.
    case copied(String, CopyReason)
    /// The editor may contain a partial insertion. The clipboard is unchanged;
    /// inspect the destination before deciding whether to retry manually.
    case insertionUncertain(String)

    var statusHint: String? {
      switch self {
      case .none, .pasted: return nil
      case .copied(_, .accessibilityDenied): return "Copied: turn on Accessibility to paste automatically"
      case .copied(_, .insertionUnavailable): return "Copied: press ⌘V to paste"
      // Plain enough to act on. "Insertion unconfirmed" read to people as an
      // error the dictation had hit, rather than as the one thing it means:
      // the words were sent and Omi could not watch them arrive.
      case .pasteRequested, .insertionUncertain: return "Couldn't confirm it landed — check the editor"
      }
    }

    var journalAcknowledgement: String? {
      switch self {
      case .none: return nil
      case .pasted(let text): return "Typed: \(text)"
      case .pasteRequested(let text): return "Paste requested; check the editor: \(text)"
      // A dictation that lands on the clipboard because the permission is off
      // reads as Omi failing. Say what to turn on, in the transcript the user
      // is already looking at — the status hint is gone a moment later, and
      // nothing else in the turn mentions Accessibility.
      case .copied(let text, .accessibilityDenied):
        return "Copied to clipboard: \(text)\n\nTurn on Accessibility for this Omi app "
          + "(System Settings → Privacy & Security → Accessibility) to have dictation "
          + "paste at your cursor automatically."
      case .copied(let text, .insertionUnavailable): return "Copied to clipboard: \(text)"
      case .insertionUncertain(let text):
        return "Dictation insertion unconfirmed; check the editor: \(text)"
      }
    }

    var isConfirmedDelivery: Bool {
      switch self {
      case .pasted, .copied: return true
      case .none, .pasteRequested, .insertionUncertain: return false
      }
    }

    var text: String? {
      switch self {
      case .none: return nil
      case .pasted(let text), .pasteRequested(let text), .copied(let text, _), .insertionUncertain(let text):
        return text
      }
    }
  }

  private var latch: Latch = .none
  /// The exact field, selection and value revision captured at release.
  private var releaseFocusTarget: TextInsertionTarget?
  /// Which turn owns the session, bumped whenever one takes it over.
  ///
  /// Delivery spans the editor's settling window, so a push-to-talk turn can
  /// begin while an earlier delivery is still awaiting its read-back. Without
  /// this, that older turn's epilogue reset the newer turn's state on its way
  /// out — `latch = .none` sent the second dictation to chat as a question,
  /// and `captureOwner = nil` left it delivering nothing.
  private var generation = 0

  /// True once this turn has been recognised as a dictation — whether or not
  /// it can be pasted. A blocked turn still owns the turn: the words are
  /// dictation, not a question, regardless of what delivers them.
  var claimsTurn: Bool { latch == .typing || latch == .blocked }

  init(
    sink: TextInsertionSink = PasteboardTextInsertionSink(),
    isAccessibilityTrusted: @escaping () -> Bool = { AXIsProcessTrusted() },
    captureAuthorization: @escaping () -> RuntimeOwnerAuthorizationSnapshot? = {
      RuntimeOwnerIdentity.captureAuthorizationSnapshot()
    },
    isAuthorizationCurrent: @escaping (RuntimeOwnerAuthorizationSnapshot) -> Bool = {
      RuntimeOwnerIdentity.isAuthorizationCurrent($0)
    }
  ) {
    self.sink = sink
    self.isAccessibilityTrusted = isAccessibilityTrusted
    self.captureAuthorization = captureAuthorization
    self.isAuthorizationCurrent = isAuthorizationCurrent
    sink.insertionReceiptDidChange = { [weak self] in self?.objectWillChange.send() }
  }

  func begin() {
    generation &+= 1
    latch = .none
    releaseFocusTarget = nil
    captureOwner = captureAuthorization()
    invalidateUndoLastDictation()
  }

  /// Receipt availability only: menu tracking may temporarily own AX focus.
  /// Reading this projection never consumes a receipt or authorizes an edit.
  var canUndoLastDictation: Bool {
    guard let owner = insertionOwner, isAuthorizationCurrent(owner), isAccessibilityTrusted() else { return false }
    return sink.canUndoInsertion
  }

  @discardableResult
  func undoLastDictation() -> Bool {
    defer { invalidateUndoLastDictation() }
    guard canUndoLastDictation else { return false }
    // The sink validates the exact current field, full value and caret here,
    // after menu dismissal. We never activate or guess the original target.
    return sink.undoInsertion()
  }

  func invalidateUndoLastDictation() {
    insertionOwner = nil
    sink.discardInsertionReceipt()
  }

  /// Decides from a transcript — a mid-hold probe's or the closing one —
  /// whether this turn dictates. Returns whether the turn belongs to voice
  /// typing. Latches only towards typing.
  ///
  /// - Parameter lenient: accept a close mishearing of the wake word, not just
  ///   the exact word. The mid-hold probe passes this because the on-device
  ///   model mishears "type" from a short opening clip; the closing decode
  ///   uses the strict test.
  @discardableResult
  func claim(transcript: String, lenient: Bool = false) -> Bool {
    switch latch {
    case .blocked: return true
    case .typing: return true
    case .none: break
    }
    let dictates =
      lenient
      ? VoiceTypeCommandParser.opensLikeDictation(transcript)
      : { if case .typing = VoiceTypeCommandParser.decide(transcript) { return true } else { return false } }()
    guard dictates else { return false }
    return arm()
  }

  /// The text this turn dictates, from its closing transcript, or nil when the
  /// turn is not a dictation.
  ///
  /// A turn already claimed reads the transcript leniently: the closing
  /// transcript comes from a different recognizer than the probe that claimed
  /// the turn, and it may spell the wake word differently ("Tie, hello").
  /// Losing the whole dictation over the wake word's spelling would be far
  /// worse than one stray word.
  func payload(from transcript: String) -> String? {
    guard claim(transcript: transcript) else { return nil }
    return VoiceTypeCommandParser.payloadAssumingDictation(transcript)
  }

  /// Records where the paste is aimed. Called at key-up on every route,
  /// before any transcription runs, so the seconds the recognizer takes
  /// cannot move the target.
  func noteRelease() {
    releaseFocusTarget = sink.focusTarget()
  }

  /// Pastes the dictated text into the app that had focus at release, and
  /// ends the turn. If focus has moved since, the text is copied instead —
  /// the user gets it with one ⌘V rather than finding it in the wrong window.
  func deliver(_ text: String) async -> Completion {
    let generation = self.generation
    /// Whether this call still owns the session, or a turn has begun under it
    /// while the editor was settling.
    func stillOwnsTheSession() -> Bool { generation == self.generation }
    defer {
      // Only ever tear down the turn this call actually delivered.
      if stillOwnsTheSession() {
        latch = .none
        releaseFocusTarget = nil
        captureOwner = nil
      }
    }
    let blocked = latch == .blocked
    guard latch == .typing || blocked else { return .none }
    guard let owner = captureOwner, isAuthorizationCurrent(owner) else {
      invalidateUndoLastDictation()
      return .none
    }
    let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
    // Nothing detected means nothing typed: not an empty paste, and not a
    // stray "." or "…" the recognizer produced from a breath.
    guard DictationPolisher.hasContent(trimmed) else { return .none }
    // No Accessibility grant: a paste would not land, so go straight to the
    // clipboard rather than trying and failing silently.
    guard !blocked, isAccessibilityTrusted() else {
      log("VoiceTypeSession: Accessibility not granted — copied \(trimmed.count) chars instead of pasting")
      copyFallback(trimmed)
      return .copied(trimmed, .accessibilityDenied)
    }
    guard let aimed = releaseFocusTarget, sink.focusTarget() == aimed else {
      log("VoiceTypeSession: dictation target unavailable or changed — copied \(trimmed.count) chars instead")
      copyFallback(trimmed)
      return .copied(trimmed, .insertionUnavailable)
    }
    let separator = aimed.needsSeparatingSpace ? " " : ""
    switch await sink.paste(separator + trimmed, into: aimed) {
    case .inserted:
      break
    case .pastePosted:
      log("VoiceTypeSession: paste of \(trimmed.count) chars into \(aimed.bundleIdentifier) was not read back")
      DesktopDiagnosticsManager.shared.recordFallback(
        area: "voice_typing", from: "clipboard_paste", to: "insertion_unconfirmed",
        reason: "other", outcome: .degraded)
      return .pasteRequested(trimmed)
    case .notInserted:
      log("VoiceTypeSession: no insertion dispatched — copied \(trimmed.count) chars instead")
      // Preserve line continuation only when the destination is still the
      // exact unchanged capture.
      copyFallback(sink.focusTarget() == aimed ? separator + trimmed : trimmed)
      return .copied(trimmed, .insertionUnavailable)
    case .uncertain:
      log("VoiceTypeSession: insertion could not be verified for \(trimmed.count) chars")
      DesktopDiagnosticsManager.shared.recordFallback(
        area: "voice_typing", from: "ax_selected_text", to: "insertion_unconfirmed",
        reason: "other", outcome: .degraded)
      invalidateUndoLastDictation()
      return .insertionUncertain(trimmed)
    }
    // Undo belongs to the turn that made the insertion, and only while that
    // turn is still the session's: a newer turn must not offer to take back an
    // older turn's text.
    if stillOwnsTheSession() { insertionOwner = owner }
    // Bundle id only — never a field value or Accessibility identifier.
    let target = aimed.bundleIdentifier
    log(
      "VoiceTypeSession: pasted \(trimmed.count) chars into \(target)"
        + (separator.isEmpty ? "" : " (continuing a line)"))
    return .pasted(trimmed)
  }

  /// Ends the turn without delivering anything (cancel, error, teardown).
  func abandon() {
    latch = .none
    releaseFocusTarget = nil
    captureOwner = nil
    // Manager terminal cleanup also calls abandon after successful delivery.
    // The short-lived insertion receipt survives that cleanup, until the next
    // begin, owner revocation, explicit invalidation, or target mismatch.
  }

  private func copyFallback(_ text: String) {
    sink.copy(text)
    if latch != .blocked {
      DesktopDiagnosticsManager.shared.recordFallback(
        area: "voice_typing", from: "paste_injection", to: "clipboard_copy",
        reason: "policy", outcome: .degraded)
    }
  }

  private func arm() -> Bool {
    guard isAccessibilityTrusted() else {
      latch = .blocked
      // Still owns the turn — see `claimsTurn` — so it never reaches the
      // realtime model; only the delivery mechanism (copy, not paste) changes.
      log("VoiceTypeSession: Accessibility not granted — will copy instead of paste")
      DesktopDiagnosticsManager.shared.recordFallback(
        area: "voice_typing",
        from: "paste_injection",
        to: "clipboard_copy",
        reason: "policy",
        outcome: .degraded)
      return true
    }
    latch = .typing
    log("VoiceTypeSession: typing turn armed")
    return true
  }
}
