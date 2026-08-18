import Foundation

/// Transcript-driven decide loop. Observes ambient transcript slices as they
/// land on the main actor, keeps the bounded speech window, and — when a user
/// utterance admits evaluation — hands a Sendable snapshot to the engine actor
/// for a director evaluation grounded on the live speech.
@MainActor
final class SpeechProactivityCoordinator {
  static let shared = SpeechProactivityCoordinator()

  private var window = SpeechProactivityWindow()
  private var lastEvaluationAt: Date?

  private init() {}

  func observe(_ slice: TranscriptSpeechSlice, now: Date = Date()) {
    guard ContextBucketsFeature.isTranscriptProactivityEnabled else { return }
    window.append(slice, seenAt: now)
    let outcome = SpeechProactivityAdmission.decides(
      flagEnabled: true,
      conversationActive: VoiceTurnCoordinator.shared.activeTurnID != nil,
      latestUserSlice: window.latestUserSlice,
      lastEvaluationAt: lastEvaluationAt,
      now: now)
    guard outcome == .evaluate else { return }
    lastEvaluationAt = now
    let snapshot = window.snapshot()
    Task {
      await ContextProactivityEngine.shared.evaluateFromSpeech(speech: snapshot)
    }
  }
}
