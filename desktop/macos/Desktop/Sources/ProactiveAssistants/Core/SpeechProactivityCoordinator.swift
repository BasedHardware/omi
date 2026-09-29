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
  private let featureEnabled: () -> Bool
  private let conversationActive: () -> Bool

  init(
    featureEnabled: @escaping () -> Bool = { ContextBucketsFeature.isTranscriptProactivityEnabled },
    conversationActive: @escaping () -> Bool = { VoiceTurnCoordinator.shared.activeTurnID != nil }
  ) {
    self.featureEnabled = featureEnabled
    self.conversationActive = conversationActive
  }

  /// A speech window belongs to exactly one capture conversation. Carrying it
  /// across stop/start or an in-place rotation can disclose old speech in the
  /// next conversation and lets the previous cooldown suppress its first turn.
  func reset() {
    window = SpeechProactivityWindow()
    lastEvaluationAt = nil
    lastEvaluatedSegmentID = nil
  }

  @discardableResult
  func observe(_ slice: TranscriptSpeechSlice, now: Date = Date()) -> Bool {
    guard featureEnabled() else { return false }
    window.append(slice, seenAt: now)
    // Decide about the slice that just arrived, not about whatever user slice
    // the window still retains: another person speaking after the cooldown must
    // not re-open an evaluation grounded on a stale user utterance.
    let outcome = SpeechProactivityAdmission.decides(
      flagEnabled: true,
      conversationActive: conversationActive(),
      arrivingSlice: slice,
      lastEvaluationAt: lastEvaluationAt,
      lastEvaluatedSegmentID: lastEvaluatedSegmentID,
      now: now)
    guard outcome == .evaluate else { return false }
    lastEvaluationAt = now
    lastEvaluatedSegmentID = slice.segmentID
    let snapshot = window.snapshot()
    Task {
      await ContextProactivityEngine.shared.evaluateFromSpeech(speech: snapshot)
    }
    return true
  }
}
