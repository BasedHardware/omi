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
  ///   - isSpeaking: Whether voice playback/synthesis is currently active.
  /// - Returns: True if playback should be halted immediately.
  static func shouldInterrupt(
    isUser: Bool,
    speaker: Int,
    text: String,
    isSpeaking: Bool
  ) -> Bool {
    guard isSpeaking else { return false }
    guard isUser || speaker == 0 else { return false }
    let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return false }
    return true
  }
}
