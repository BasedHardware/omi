import AppKit
import CoreGraphics
import Foundation
import OmiSupport

// MARK: - Realtime Hub Controller (Phase 1)
//
// Owns one persistent, warm RealtimeHubSession as the physical voice provider
// driver. The kernel remains the single semantic router and tool authority. It:
//   • keeps the WS warm between PTT turns (no reopen per press),
//   • feeds mic PCM in and plays the model's spoken reply out
//     (provider native audio → StreamingPCMPlayer; selected app voice fallback → FloatingBarVoicePlaybackService),
//   • submits every model tool call to the kernel's durable external-run ledger;
//     Swift executes only the generated realtime-owned commands returned through
//     the validated authorized-tool envelope.
//
// Provider tool proposals are untrusted until the kernel resolves the canonical
// route and authorizes the active run/attempt capability.

#if DEBUG
/// Deterministic provider decisions for the hermetic desktop profile. This type
/// is absent from release builds and is reachable only through `ptt_test_turn`.
struct RealtimeLocalProfileTurnPlan: Equatable {
  struct Spawn: Equatable {
    let objective: String
    let title: String
  }

  static let exactMemoryAgentRequest =
    "Have an agent look through my memories today and surface one surprising insight."

  let assistantText: String
  let spawn: Spawn?

  static func make(
    transcript rawTranscript: String,
    voiceContext: String,
    localProfileEnabled: Bool
  ) -> Self? {
    guard localProfileEnabled else { return nil }
    let transcript = rawTranscript.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !transcript.isEmpty else { return nil }

    if transcript == exactMemoryAgentRequest {
      return Self(
        assistantText: "I started a background agent to review today's memories.",
        spawn: Spawn(objective: transcript, title: "Today's memory insight"))
    }

    if transcript.localizedCaseInsensitiveContains("what was the last thing i asked you for"),
      let reference = lastHarnessReference(in: voiceContext)
    {
      return Self(
        assistantText: "The last request was the background-agent task tagged \(reference).",
        spawn: nil)
    }

    if let marker = lastHarnessReference(in: transcript) {
      return Self(assistantText: "Stub saw marker: \(marker)", spawn: nil)
    }
    return Self(assistantText: "Hermetic realtime stub response.", spawn: nil)
  }

  private static func lastHarnessReference(in text: String) -> String? {
    guard
      let expression = try? NSRegularExpression(
        pattern: #"(?:GAUNTLET|RESILIENCE)[A-Z0-9-]*"#),
      let match = expression.matches(
        in: text, range: NSRange(text.startIndex..., in: text)).last,
      let range = Range(match.range, in: text)
    else { return nil }
    return String(text[range])
  }
}
#endif

/// A canonical spawn receipt proves that the child exists, but it does not
/// authorize the realtime provider to narrate the child's eventual outcome.
/// Provider continuations remain necessary for transport completion, but are
/// not presented to the user for that turn.
enum RealtimeAcceptedSpawnPresentationPolicy {
  static func suppressesProviderContinuation(hasCanonicalSpawnReceipt: Bool) -> Bool {
    hasCanonicalSpawnReceipt
  }

  static func requiresProviderContinuation(hasCanonicalSpawnReceipt: Bool) -> Bool {
    !hasCanonicalSpawnReceipt
  }
}

/// Keeps the response glow tied to perceived playback instead of raw PCM chunk
/// boundaries. Realtime providers can leave short gaps between streamed audio
/// buffers; clearing the glow on every empty queue makes the notch resize and
/// shimmer restart repeatedly.
@MainActor
final class RealtimeResponseGlowGate {
  private let idleClearDelay: TimeInterval
  private let scheduler: DelayedActionScheduling
  private let setActive: (Bool, VoiceOutputLease?) -> Void
  private var idleClearCancellation: DelayedActionCancellation?
  private var lease: VoiceOutputLease?
  private(set) var isActive = false

  init(
    idleClearDelay: TimeInterval = 0.75,
    scheduler: DelayedActionScheduling? = nil,
    setActive: @escaping (Bool, VoiceOutputLease?) -> Void
  ) {
    self.idleClearDelay = idleClearDelay
    self.scheduler = scheduler ?? TaskDelayedActionScheduler()
    self.setActive = setActive
  }

  func markPlaybackActive(lease: VoiceOutputLease) {
    idleClearCancellation?.cancel()
    idleClearCancellation = nil
    self.lease = lease
    guard !isActive else { return }
    isActive = true
    setActive(true, lease)
  }

  func scheduleIdleClear() {
    idleClearCancellation?.cancel()
    let expectedLease = lease
    idleClearCancellation = scheduler.schedule(after: idleClearDelay) { [weak self] in
      guard let self, self.lease == expectedLease else { return }
      self.idleClearCancellation = nil
      self.isActive = false
      self.lease = nil
      self.setActive(false, expectedLease)
    }
  }

  func clearImmediately() {
    idleClearCancellation?.cancel()
    idleClearCancellation = nil
    let expectedLease = lease
    lease = nil
    guard isActive else {
      setActive(false, expectedLease)
      return
    }
    isActive = false
    setActive(false, expectedLease)
  }
}
