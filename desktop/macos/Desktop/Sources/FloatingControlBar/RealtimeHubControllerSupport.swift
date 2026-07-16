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
