import Foundation

/// Delivers the Interject classification instruction into the live hub session.
///
/// `sendTrustedTurnInstruction` returns `false` when the session cannot accept
/// context yet (cold hub, Gemini idle, replacement socket). A fire-and-forget
/// `Task` dropped that `false` and never retried — hold-⌥ classified nothing.
/// This keeps one pending instruction per PTT generation, retries on the same
/// capability signals card delivery uses (`hubDidConnect` /
/// `hubDidOpenInputWindow`), and uses `deliveryQueued` so a signal that arrives
/// mid-send is replayed afterwards instead of swallowed.
///
/// Finalize (PTT-up) and cancel must not share a drop. Gemini often cannot
/// accept the inject until `beginInputTurn` opens the activity window — which
/// runs at commit or when a replacement socket is ready, both after finalize.
/// Release keeps the pending instruction for that window; only cancel/abandon
/// drops it.
@MainActor
final class InterjectClassificationDelivery {
  static let shared = InterjectClassificationDelivery()

  private var isVoiceSessionLive: @MainActor () -> Bool
  private var injectInstruction: @MainActor (String) async -> Bool
  private var abandonInstruction: @MainActor () -> Void
  private var scheduleWork: @MainActor (@escaping @MainActor () async -> Void) -> Void

  /// Set while a PTT hold is open. A second `pttDidStart` (tap-to-lock)
  /// must not enqueue another copy. Finalize clears this without dropping the
  /// pending inject so the input-window retry can still land.
  private(set) var isHoldOpen = false
  private(set) var activeGeneration: UInt64?
  private(set) var pendingInstruction: String?
  private var generation: UInt64 = 0
  private var isDelivering = false
  private var deliveryQueued = false

  init(
    isVoiceSessionLive: @escaping @MainActor () -> Bool = {
      RealtimeHubController.shared.hasLiveVoiceSession
    },
    injectInstruction: @escaping @MainActor (String) async -> Bool = {
      await RealtimeHubController.shared.injectTrustedTurnInstruction($0)
    },
    abandonInstruction: @escaping @MainActor () -> Void = {
      RealtimeHubController.shared.clearTrustedTurnInstruction()
    },
    scheduleWork: @escaping @MainActor (@escaping @MainActor () async -> Void) -> Void = { work in
      Task { @MainActor in await work() }
    }
  ) {
    self.isVoiceSessionLive = isVoiceSessionLive
    self.injectInstruction = injectInstruction
    self.abandonInstruction = abandonInstruction
    self.scheduleWork = scheduleWork
  }

  // MARK: - Entry points

  /// Arm at most one inject for this PTT generation.
  func pttDidStart(
    shouldAttach: Bool,
    instruction: String = InterjectVoiceFeedbackRouting.trustedTurnInstruction
  ) {
    if isHoldOpen { return }
    guard shouldAttach else {
      abandonPendingInstruction()
      return
    }
    isHoldOpen = true
    generation += 1
    activeGeneration = generation
    pendingInstruction = instruction
    scheduleDelivery()
  }

  /// PTT-up / finalize: end the hold but keep an unconfirmed inject so this
  /// turn's `hubDidOpenInputWindow` can still deliver it.
  func pttDidRelease() {
    isHoldOpen = false
  }

  /// Cancel / abandon: drop an unconfirmed inject so it cannot leak into the
  /// next turn.
  func pttDidCancel() {
    let hadUnconfirmed = pendingInstruction != nil
    abandonPendingInstruction()
    if hadUnconfirmed {
      log(
        "InterjectClassificationDelivery: PTT cancelled before the classification inject confirmed — dropped"
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
    guard pendingInstruction != nil, activeGeneration != nil else { return }
    if isDelivering {
      deliveryQueued = true
      return
    }
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
    defer {
      isDelivering = false
      if deliveryQueued {
        deliveryQueued = false
        scheduleDelivery()
      }
    }
    guard let instruction = pendingInstruction else { return }
    let startedGeneration = activeGeneration

    let delivered = await injectInstruction(instruction)
    guard delivered else {
      log(
        "InterjectClassificationDelivery: session refused classification inject — will retry on connect/input-window"
      )
      return
    }

    // A cancel (or a newer generation) during the in-flight send wins: do not
    // treat a stale confirm as this generation's success, and do not clear a
    // newer pending instruction.
    guard activeGeneration == startedGeneration else { return }
    pendingInstruction = nil
    log("InterjectClassificationDelivery: classification instruction confirmed")
  }

  private func abandonPendingInstruction() {
    isHoldOpen = false
    activeGeneration = nil
    pendingInstruction = nil
    deliveryQueued = false
    abandonInstruction()
  }

  // MARK: - Testing

  func resetForTesting() {
    isVoiceSessionLive = { RealtimeHubController.shared.hasLiveVoiceSession }
    injectInstruction = { await RealtimeHubController.shared.injectTrustedTurnInstruction($0) }
    abandonInstruction = { RealtimeHubController.shared.clearTrustedTurnInstruction() }
    scheduleWork = { work in Task { @MainActor in await work() } }
    isHoldOpen = false
    activeGeneration = nil
    pendingInstruction = nil
    generation = 0
    isDelivering = false
    deliveryQueued = false
  }

  func configureForTesting(
    isVoiceSessionLive: @escaping @MainActor () -> Bool,
    injectInstruction: @escaping @MainActor (String) async -> Bool,
    scheduleWork: @escaping @MainActor (@escaping @MainActor () async -> Void) -> Void,
    abandonInstruction: @escaping @MainActor () -> Void = {}
  ) {
    self.isVoiceSessionLive = isVoiceSessionLive
    self.injectInstruction = injectInstruction
    self.abandonInstruction = abandonInstruction
    self.scheduleWork = scheduleWork
    isHoldOpen = false
    activeGeneration = nil
    pendingInstruction = nil
    generation = 0
    isDelivering = false
    deliveryQueued = false
  }
}
