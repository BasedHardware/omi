import Foundation

/// Pure policy deciding when incoming ambient speech interrupts active voice output.
///
/// When the assistant is speaking (proactive advice, voice response, or TTS)
/// and the user begins speaking, barge-in halts playback immediately so Omi
/// never talks over the user.
enum VoiceBargeInPolicy: Sendable {
  /// Evaluates whether an incoming transcript segment warrants interrupting voice playback.
  ///
  /// - Parameters:
  ///   - isUser: Whether diarization flagged the segment as the user.
  ///   - speaker: Speaker identifier (0 is the primary user).
  ///   - text: Transcript utterance text.
  ///   - previouslyHeard: The text already stored for this segment id, if the segment is a
  ///     re-delivery rather than a new one.
  ///   - isSpeaking: Whether voice playback/synthesis is currently active.
  /// - Returns: True if playback should be halted immediately.
  static func shouldInterrupt(
    isUser: Bool,
    speaker: Int,
    text: String,
    previouslyHeard: String? = nil,
    isSpeaking: Bool
  ) -> Bool {
    guard isSpeaking else { return false }
    guard isUser || speaker == 0 else { return false }
    let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return false }
    return !newSpeech(in: trimmed, alreadyHeard: previouslyHeard).isEmpty
  }

  /// The part of a segment nobody has heard yet.
  ///
  /// A backend segment is re-delivered as it grows, in place and under one id, and a
  /// re-delivery arrives whether or not the speaker added anything. Treating every arrival
  /// as fresh speech makes the assistant interrupt itself with the user's *own question*:
  /// observed live, the second turn of a conversation was cut off 4.4s into playback by a
  /// re-delivery of the segment that asked it, byte-identical to the copy already stored.
  ///
  /// Only what the segment gained is new speech. A segment that grew from a different
  /// prefix — the recognizer revised what it already emitted — counts as new in full, since
  /// there is no way to tell a revision from a continuation.
  static func newSpeech(in text: String, alreadyHeard: String?) -> Substring {
    guard let alreadyHeard else { return text[...] }
    let previous = alreadyHeard.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !previous.isEmpty else { return text[...] }
    guard text.hasPrefix(previous) else { return text[...] }
    let addition = text.dropFirst(previous.count)
    guard let start = addition.firstIndex(where: { !$0.isWhitespace && !$0.isPunctuation })
    else { return "" }
    return addition[start...]
  }
}
