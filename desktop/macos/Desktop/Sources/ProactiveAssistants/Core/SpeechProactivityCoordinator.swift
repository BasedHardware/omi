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
  private var lastEvaluatedSegmentID: String?

  private init() {}

  func observe(_ slice: TranscriptSpeechSlice, now: Date = Date()) {
    guard ContextBucketsFeature.isTranscriptProactivityEnabled else { return }
    window.append(slice, seenAt: now)
    // Decide about the slice that just arrived, not about whatever user slice
    // the window still retains: another person speaking after the cooldown must
    // not re-open an evaluation grounded on a stale user utterance.
    let outcome = SpeechProactivityAdmission.decides(
      flagEnabled: true,
      conversationActive: VoiceTurnCoordinator.shared.activeTurnID != nil,
      arrivingSlice: slice,
      lastEvaluationAt: lastEvaluationAt,
      lastEvaluatedSegmentID: lastEvaluatedSegmentID,
      now: now)
    guard outcome == .evaluate else { return }
    lastEvaluationAt = now
    lastEvaluatedSegmentID = slice.segmentID
    let snapshot = window.snapshot()
    Task {
      await ContextProactivityEngine.shared.evaluateFromSpeech(speech: snapshot)
    }
  }
}
