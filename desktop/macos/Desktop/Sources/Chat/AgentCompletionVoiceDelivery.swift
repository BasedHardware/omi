import Combine
import Foundation

/// Bridges completed background-agent runs into the live realtime voice
/// conversation.
///
/// The kernel journals a completed run and the floating pill shows it, but a
/// live voice session has no eyes: nothing tells the realtime model that the
/// agent it spawned has finished. This service watches run projections for
/// transitions into a terminal state on background surfaces, reads the
/// canonical completion delta from the kernel (`peekCompletedAgentDelta`,
/// exactly-once via the per-surface checkpoint), and injects the delta prompt
/// into the live provider session as untrusted context. No synthetic response
/// is requested — the voice turn coordinator's output authority is untouched;
/// the model mentions the completion at the next natural turn boundary and can
/// answer follow-ups. The checkpoint advances only after the session confirms
/// the send, so an undelivered completion is retried instead of lost.
@MainActor
final class AgentCompletionVoiceDelivery {
  static let shared = AgentCompletionVoiceDelivery()

  /// Background surfaces whose terminal transitions can carry a user-facing
  /// completion. Primary conversational surfaces (main_chat, realtime_voice,
  /// task_chat, …) reach a terminal state on every ordinary answer and must
  /// not trigger kernel delta reads.
  static let triggerSurfaceKinds: Set<String> = ["floating_bar", "service", "workstream"]

  struct Delta {
    let ids: [String]
    let prompt: String
    let completedAtHighWaterMs: Int?
  }

  private let isVoiceSessionLive: @MainActor () -> Bool
  private let peekDelta: @MainActor () async -> Delta?
  private let injectContext: @MainActor (String) async -> Bool
  private let acknowledge: @MainActor (Delta) -> Void
  private let scheduleWork: @MainActor (@escaping @MainActor () async -> Void) -> Void

  private var cancellable: AnyCancellable?
  private var lastStatusBySurface: [String: AgentRunProjectionStatus] = [:]
  private var deliveryInFlight = false
  private var deliveryQueued = false
  /// The shared instance stays completely inert — no status subscription, no
  /// delivery, no reach into the agent runtime — until `start()` runs at app
  /// launch. This keeps `voiceSessionDidConnect()`, which the realtime hub calls
  /// from `hubDidConnect` (exercised by RealtimeHub unit tests), a no-op in any
  /// context that never started the service.
  private var hasStarted: Bool

  init(
    isVoiceSessionLive: (@MainActor () -> Bool)? = nil,
    peekDelta: (@MainActor () async -> Delta?)? = nil,
    injectContext: (@MainActor (String) async -> Bool)? = nil,
    acknowledge: (@MainActor (Delta) -> Void)? = nil,
    scheduleWork: (@MainActor (@escaping @MainActor () async -> Void) -> Void)? = nil,
    hasStarted: Bool = false
  ) {
    self.hasStarted = hasStarted
    self.isVoiceSessionLive =
      isVoiceSessionLive ?? { RealtimeHubController.shared.hasLiveVoiceSession }
    self.peekDelta =
      peekDelta
      ?? {
        guard
          let delta = await DesktopCoordinatorService.shared.peekCompletedAgentDelta(
            surface: .realtimeVoice())
        else { return nil }
        return Delta(
          ids: delta.ids,
          prompt: delta.prompt,
          completedAtHighWaterMs: delta.completedAtHighWaterMs)
      }
    self.injectContext =
      injectContext
      ?? { text in
        await RealtimeHubController.shared.injectBackgroundAgentCompletionContext(text)
      }
    self.acknowledge =
      acknowledge
      ?? { delta in
        DesktopCoordinatorService.shared.acknowledgeCompletedAgentDelta(
          surface: .realtimeVoice(),
          ids: delta.ids,
          completedAtHighWaterMs: delta.completedAtHighWaterMs)
      }
    self.scheduleWork = scheduleWork ?? { work in Task { await work() } }
  }

  /// Idempotent; called once from app launch.
  func start() {
    guard cancellable == nil else { return }
    hasStarted = true
    cancellable = AgentRuntimeStatusStore.shared.$projectionsBySurface
      .sink { [weak self] projections in
        self?.observe(projections)
      }
  }

  /// A newly connected voice session drains completions that finished while no
  /// session was live (their checkpoint was deliberately left unadvanced). Inert
  /// until `start()` so the realtime hub's `hubDidConnect` hook never drives the
  /// unstarted shared instance into the agent runtime during tests.
  func voiceSessionDidConnect() {
    guard hasStarted else { return }
    scheduleDelivery()
  }

  /// A warm session opened an input window (Gemini `activityStart`) and can now
  /// accept injected context. Same capability signal as `voiceSessionDidConnect`:
  /// retry a completion that `sendBackgroundAgentContext` refused while the
  /// session was connected-but-idle (its checkpoint is still unadvanced).
  func voiceSessionDidOpenInputWindow() {
    guard hasStarted else { return }
    scheduleDelivery()
  }

  func observe(_ projections: [String: AgentRunProjection]) {
    var fired = false
    for (key, projection) in projections {
      let previous = lastStatusBySurface[key]
      lastStatusBySurface[key] = projection.status
      guard
        projection.status.isTerminal,
        previous != projection.status,
        previous?.isTerminal != true,
        Self.triggerSurfaceKinds.contains(projection.surface.surfaceKind)
      else { continue }
      fired = true
    }
    // Prune surfaces that disappeared so a cleared-and-recreated surface is a
    // fresh transition rather than a suppressed repeat.
    lastStatusBySurface = lastStatusBySurface.filter { projections[$0.key] != nil }
    if fired {
      scheduleDelivery()
    }
  }

  private func scheduleDelivery() {
    if deliveryInFlight {
      deliveryQueued = true
      return
    }
    deliveryInFlight = true
    scheduleWork { [weak self] in
      await self?.runDelivery()
    }
  }

  private func runDelivery() async {
    defer {
      deliveryInFlight = false
      if deliveryQueued {
        deliveryQueued = false
        scheduleDelivery()
      }
    }
    guard isVoiceSessionLive() else { return }
    guard let delta = await peekDelta() else { return }
    guard await injectContext(delta.prompt) else {
      log("AgentCompletionVoiceDelivery: completion context not delivered; checkpoint unadvanced")
      return
    }
    acknowledge(delta)
    log("AgentCompletionVoiceDelivery: delivered \(delta.ids.count) completion(s) to live voice session")
  }
}
