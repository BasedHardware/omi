import Foundation

/// Delivers the Interject classification instruction into the live hub session.
///
/// `sendBackgroundAgentContext` returns `false` when the session cannot accept
/// context yet (cold hub, Gemini idle, `q.async` race). A fire-and-forget
/// `Task` dropped that `false` and never retried — hold-⌥ classified nothing.
/// This keeps one pending instruction per PTT generation, retries on the same
/// capability signals card delivery uses (`hubDidConnect` /
/// `hubDidOpenInputWindow`), and cancels an unconfirmed inject when PTT ends
/// so a late send cannot land in the next turn.
@MainActor
final class InterjectClassificationDelivery {
  static let shared = InterjectClassificationDelivery()

  private var isVoiceSessionLive: @MainActor () -> Bool
  private var injectInstruction: @MainActor (String) async -> Bool
  private var scheduleWork: @MainActor (@escaping @MainActor () async -> Void) -> Void

  /// Set while a PTT generation is open. A second `pttDidStart` (tap-to-lock)
  /// must not enqueue another copy.
  private(set) var activeGeneration: UInt64?
  private(set) var pendingInstruction: String?
  private var generation: UInt64 = 0
  private var isDelivering = false

  init(
    isVoiceSessionLive: @escaping @MainActor () -> Bool = {
      RealtimeHubController.shared.hasLiveVoiceSession
    },
    injectInstruction: @escaping @MainActor (String) async -> Bool = {
      await RealtimeHubController.shared.injectTrustedTurnInstruction($0)
    },
    scheduleWork: @escaping @MainActor (@escaping @MainActor () async -> Void) -> Void = { work in
      Task { @MainActor in await work() }
    }
  ) {
    self.isVoiceSessionLive = isVoiceSessionLive
    self.injectInstruction = injectInstruction
    self.scheduleWork = scheduleWork
  }

  // MARK: - Entry points

  /// Arm at most one inject for this PTT generation.
  func pttDidStart(
    shouldAttach: Bool,
    instruction: String = InterjectVoiceFeedbackRouting.trustedTurnInstruction
  ) {
    if activeGeneration != nil { return }
    guard shouldAttach else { return }
    generation += 1
    activeGeneration = generation
    pendingInstruction = instruction
    scheduleDelivery()
  }

  /// Drop an unconfirmed inject so it cannot leak into the next turn.
  func pttDidEnd() {
    let hadUnconfirmed = pendingInstruction != nil
    activeGeneration = nil
    pendingInstruction = nil
    if hadUnconfirmed {
      log(
        "InterjectClassificationDelivery: PTT ended before the classification inject confirmed — dropped"
      )
    }
  }

  func voiceSessionDidConnect() {
    scheduleDelivery()
  }

  func voiceSessionDidOpenInputWindow() {
    scheduleDelivery()
  }

  // MARK: - Delivery

  private func scheduleDelivery() {
    guard pendingInstruction != nil, activeGeneration != nil, !isDelivering else { return }
    guard isVoiceSessionLive() else {
      log("InterjectClassificationDelivery: no live voice session — instruction stays pending")
      return
    }
    isDelivering = true
    scheduleWork { [weak self] in
      await self?.deliverPending()
    }
  }

  private func deliverPending() async {
    defer { isDelivering = false }
    guard let instruction = pendingInstruction else { return }
    let startedGeneration = activeGeneration

    let delivered = await injectInstruction(instruction)
    guard delivered else {
      log(
        "InterjectClassificationDelivery: session refused classification inject — will retry on connect/input-window"
      )
      return
    }

    // A DidEnd (or a newer generation) during the in-flight send wins: do not
    // treat a stale confirm as this generation's success, and do not clear a
    // newer pending instruction.
    guard activeGeneration == startedGeneration else { return }
    pendingInstruction = nil
    log("InterjectClassificationDelivery: classification instruction confirmed")
  }

  // MARK: - Testing

  func resetForTesting() {
    isVoiceSessionLive = { RealtimeHubController.shared.hasLiveVoiceSession }
    injectInstruction = { await RealtimeHubController.shared.injectTrustedTurnInstruction($0) }
    scheduleWork = { work in Task { @MainActor in await work() } }
    activeGeneration = nil
    pendingInstruction = nil
    generation = 0
    isDelivering = false
  }

  func configureForTesting(
    isVoiceSessionLive: @escaping @MainActor () -> Bool,
    injectInstruction: @escaping @MainActor (String) async -> Bool,
    scheduleWork: @escaping @MainActor (@escaping @MainActor () async -> Void) -> Void
  ) {
    self.isVoiceSessionLive = isVoiceSessionLive
    self.injectInstruction = injectInstruction
    self.scheduleWork = scheduleWork
    activeGeneration = nil
    pendingInstruction = nil
    generation = 0
    isDelivering = false
  }
}
