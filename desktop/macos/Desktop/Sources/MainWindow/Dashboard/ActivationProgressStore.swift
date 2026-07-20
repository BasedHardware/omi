import Combine
import Foundation

/// Tracks whether the signed-in user has reached desktop activation.
///
/// The July 2026 usage study found retention is decided in the first 48 hours
/// by proof-of-delivery: a real conversation captured (8.9× retained-vs-churned
/// lift) and a first question asked (the median churned user never sends one).
/// Home renders the first-win surface until both happen, then permanently
/// switches to the Today hub.
///
/// Marks are product-side signals written adjacent to (never inside) the
/// telemetry call sites — product authority stays independent from analytics.
/// State is persisted per owner so an account switch never shows another
/// user's progress, and lifetime counts auto-complete the flow so a veteran
/// on a fresh Mac never sees the checklist.
@MainActor
final class ActivationProgressStore: ObservableObject {
  static let shared = ActivationProgressStore()

  struct Progress: Codable, Equatable {
    var askedOmi = false
    var conversationCaptured = false
    var firstConversationTitle: String?
    var firstWinFirstShownAt: Date?
    var firstWinVisits = 0
    /// Set once the user leaves first-win for good (completed or timed out).
    var graduated = false
  }

  /// First-win stops insisting after this window or visit count — a user who
  /// skipped microphone/screen permissions must not live on a stale checklist.
  static let firstWinMaxAge: TimeInterval = 48 * 60 * 60
  static let firstWinMaxVisits = 5

  @Published private(set) var progress = Progress()

  /// One-time transient flag: both activation marks just completed in this
  /// session, so Home may show its quiet "second brain is live" greeting
  /// once. Never persisted.
  @Published private(set) var celebrationPending = false

  private let defaults: UserDefaults
  private let ownerIDProvider: () -> String?
  private let now: () -> Date
  private var activeOwnerID: String?
  private nonisolated(unsafe) var ownerObserver: NSObjectProtocol?

  init(
    defaults: UserDefaults = .standard,
    ownerIDProvider: (() -> String?)? = nil,
    now: @escaping () -> Date = Date.init
  ) {
    self.defaults = defaults
    self.ownerIDProvider = ownerIDProvider ?? { RuntimeOwnerIdentity.currentOwnerId() }
    self.now = now
    reloadForCurrentOwner()
    ownerObserver = NotificationCenter.default.addObserver(
      forName: .runtimeOwnerDidChange, object: nil, queue: .main
    ) { [weak self] _ in
      Task { @MainActor in
        self?.reloadForCurrentOwner()
      }
    }
  }

  deinit {
    if let ownerObserver { NotificationCenter.default.removeObserver(ownerObserver) }
  }

  var isActivated: Bool {
    progress.graduated || (progress.askedOmi && progress.conversationCaptured)
  }

  /// Whether Home should render the first-win surface. Requires the lifetime
  /// counts to be loaded (`countsKnown`) — while they are still nil the Today
  /// hub renders, so a veteran signing in on a new machine never flashes the
  /// checklist before their data arrives.
  func shouldShowFirstWin(countsKnown: Bool) -> Bool {
    if automationForcedFirstWin { return true }
    guard countsKnown else { return false }
    return !isActivated
  }

  /// Lifetime counts arrived — a history of captured conversations means this
  /// account activated long ago (possibly on another machine).
  func applyLifetimeCounts(conversations: Int?, memories: Int?) {
    guard !automationForcedFirstWin else { return }
    guard !isActivated else { return }
    if let conversations, conversations > 0 {
      mutate {
        $0.conversationCaptured = true
        // An account with real conversation history is past first-win even if
        // this machine never saw a query.
        $0.graduated = true
      }
    }
    _ = memories  // memory counts alone don't graduate: onboarding import seeds them
  }

  func markAskedOmi() {
    guard !progress.askedOmi else { return }
    mutate { $0.askedOmi = true }
  }

  func markConversationCaptured(title: String?) {
    guard !progress.conversationCaptured else { return }
    mutate {
      $0.conversationCaptured = true
      $0.firstConversationTitle = title
    }
  }

  /// Called when the first-win surface renders; applies the time-box so
  /// permission-skippers eventually land on the Today hub anyway.
  func noteFirstWinShown() {
    let currentTime = now()
    mutate {
      if $0.firstWinFirstShownAt == nil {
        $0.firstWinFirstShownAt = currentTime
      }
      $0.firstWinVisits += 1
      if let firstShown = $0.firstWinFirstShownAt,
        currentTime.timeIntervalSince(firstShown) > Self.firstWinMaxAge
          || $0.firstWinVisits > Self.firstWinMaxVisits
      {
        $0.graduated = true
      }
    }
  }

  // MARK: - Persistence

  func consumeCelebration() {
    celebrationPending = false
  }

  // MARK: - Automation bridge (non-prod QA only)

  /// QA override so a seeded account with history can render the first-win
  /// surface. Transient, bridge-gated; never affects production behavior.
  @Published private(set) var automationForcedFirstWin = false

  func registerAutomationActions() {
    guard DesktopAutomationLaunchOptions.isEnabled, !didRegisterAutomationActions else { return }
    didRegisterAutomationActions = true
    DesktopAutomationActionRegistry.shared.register(
      name: "activation_force_first_win",
      summary: "Force or release the Home first-win surface for QA",
      params: ["enabled"]
    ) { [weak self] params in
      guard let self else { return ["error": "activation store deallocated"] }
      self.automationForcedFirstWin = (params["enabled"] ?? "true") != "false"
      return ["forced": String(self.automationForcedFirstWin)]
    }
    DesktopAutomationActionRegistry.shared.register(
      name: "activation_state",
      summary: "Dump activation progress for the current owner",
      params: []
    ) { [weak self] _ in
      guard let self else { return ["error": "activation store deallocated"] }
      return [
        "asked_omi": String(self.progress.askedOmi),
        "conversation_captured": String(self.progress.conversationCaptured),
        "graduated": String(self.progress.graduated),
        "activated": String(self.isActivated),
        "forced_first_win": String(self.automationForcedFirstWin),
      ]
    }
  }

  private var didRegisterAutomationActions = false

  private func mutate(_ change: (inout Progress) -> Void) {
    var updated = progress
    change(&updated)
    guard updated != progress else { return }
    let wasActivated = progress.askedOmi && progress.conversationCaptured
    let becomesActivated = updated.askedOmi && updated.conversationCaptured
    if !wasActivated, becomesActivated, !updated.graduated {
      celebrationPending = true
    }
    progress = updated
    persist()
  }

  private func persist() {
    guard let ownerID = normalizedOwnerID() else { return }
    defaults.set(
      try? JSONEncoder().encode(progress),
      forKey: ScopedDefaultsKey.homeActivationProgress(ownerID: ownerID)
    )
  }

  private func reloadForCurrentOwner() {
    let ownerID = normalizedOwnerID()
    activeOwnerID = ownerID
    guard let ownerID,
      let data = defaults.data(forKey: ScopedDefaultsKey.homeActivationProgress(ownerID: ownerID)),
      let stored = try? JSONDecoder().decode(Progress.self, from: data)
    else {
      progress = Progress()
      return
    }
    progress = stored
  }

  private func normalizedOwnerID() -> String? {
    let trimmed = ownerIDProvider()?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    return trimmed.isEmpty ? nil : trimmed
  }
}
