import ApplicationServices
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
final class VoiceTypeSession {

  private let sink: TextInsertionSink
  private let isAccessibilityTrusted: () -> Bool

  private enum Latch {
    case none
    case typing
    /// A type command that cannot be delivered (no Accessibility grant). Latched
    /// so one denied turn reports one fallback, not one per transcript.
    case blocked
  }

  /// What a finished turn delivered. The caller journals the text so the
  /// dictation joins the conversation history; a turn that never dictated has
  /// nothing to record.
  enum Completion: Equatable {
    case none
    /// The text was pasted into the app that had focus when the key came up.
    case pasted(String)
    /// Focus moved (or the paste could not be posted), so the text was left on
    /// the clipboard for the user instead of being pasted into the wrong app.
    case copied(String)

    var text: String? {
      switch self {
      case .none: return nil
      case .pasted(let text), .copied(let text): return text
      }
    }
  }

  private var latch: Latch = .none
  /// Where the paste is aimed: the frontmost application when the key came
  /// up. Observed live before this existed: a dock click brought Omi's own
  /// window forward and a dictation was typed into it instead of the document.
  private var releaseFocusTarget: String?

  /// True once this turn has been recognised as a dictation.
  var claimsTurn: Bool { latch == .typing }

  init(
    sink: TextInsertionSink = PasteboardTextInsertionSink(),
    isAccessibilityTrusted: @escaping () -> Bool = { AXIsProcessTrusted() }
  ) {
    self.sink = sink
    self.isAccessibilityTrusted = isAccessibilityTrusted
  }

  func begin() {
    latch = .none
    releaseFocusTarget = nil
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
    case .blocked: return false
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
  func deliver(_ text: String) -> Completion {
    defer {
      latch = .none
      releaseFocusTarget = nil
    }
    guard latch == .typing else { return .none }
    let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
    // Nothing detected means nothing typed: not an empty paste, and not a
    // stray "." or "…" the recognizer produced from a breath.
    guard DictationPolisher.hasContent(trimmed) else { return .none }
    if let aimed = releaseFocusTarget {
      let current = sink.focusTarget()
      if current == nil || current != aimed {
        log("VoiceTypeSession: focus left the dictation target — copied \(trimmed.count) chars instead")
        sink.copy(trimmed)
        return .copied(trimmed)
      }
    }
    // Decided from where the caret is right now: the first word must not land
    // flush against the word before it ("voiceI think").
    let separator = sink.caretNeedsSeparatingSpace() ? " " : ""
    guard sink.paste(separator + trimmed) else {
      log("VoiceTypeSession: paste could not be posted — copied \(trimmed.count) chars instead")
      sink.copy(trimmed)
      return .copied(trimmed)
    }
    // The target's bundle id only (pid:bundle:window) — never the text.
    let target = (releaseFocusTarget ?? "?").split(separator: ":").dropFirst().first.map(String.init) ?? "?"
    log(
      "VoiceTypeSession: pasted \(trimmed.count) chars into \(target)"
        + (separator.isEmpty ? "" : " (continuing a line)"))
    return .pasted(trimmed)
  }

  /// Ends the turn without delivering anything (cancel, error, teardown).
  func abandon() {
    latch = .none
    releaseFocusTarget = nil
  }

  private func arm() -> Bool {
    guard isAccessibilityTrusted() else {
      latch = .blocked
      log("VoiceTypeSession: Accessibility not granted — releasing turn to chat")
      DesktopDiagnosticsManager.shared.recordFallback(
        area: "voice_typing",
        from: "paste_injection",
        to: "chat_query",
        reason: "policy",
        outcome: .degraded)
      return false
    }
    latch = .typing
    log("VoiceTypeSession: typing turn armed")
    return true
  }
}
