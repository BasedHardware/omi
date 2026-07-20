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
    /// Distinct calendar days the first-win surface was seen (same-day tab
    /// switches must not burn the window down).
    var firstWinVisits = 0
    var lastFirstWinDayStamp: String?
    /// Set once the user leaves first-win for good (completed or timed out).
    var graduated = false
  }

  /// First-win stops insisting after this window — a user who skipped
  /// microphone/screen permissions must not live on a stale checklist.
  static let firstWinMaxAge: TimeInterval = 48 * 60 * 60

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
  /// account activated long ago (possibly on another machine). Only accounts
  /// whose history predates first-win graduate silently; once first-win has
  /// shown, a rising count is this user's FIRST conversation landing and must
  /// complete that step normally (keeping the ask step and celebration).
  func applyLifetimeCounts(conversations: Int?, memories: Int?) {
    guard !automationForcedFirstWin else { return }
    guard !isActivated else { return }
    if let conversations, conversations > 0 {
      if progress.firstWinFirstShownAt == nil {
        mutate {
          $0.conversationCaptured = true
          $0.graduated = true
        }
      } else {
        markConversationCaptured(title: nil)
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
  /// permission-skippers eventually land on the Today hub anyway. Visits are
  /// counted per distinct calendar day — navigating to Home six times in one
  /// session is one visit, not a graduation.
  func noteFirstWinShown() {
    let currentTime = now()
    let dayStamp = Self.dayStampFormatter.string(from: currentTime)
    mutate {
      if $0.firstWinFirstShownAt == nil {
        $0.firstWinFirstShownAt = currentTime
      }
      if $0.lastFirstWinDayStamp != dayStamp {
        $0.lastFirstWinDayStamp = dayStamp
        $0.firstWinVisits += 1
      }
      if let firstShown = $0.firstWinFirstShownAt,
        currentTime.timeIntervalSince(firstShown) > Self.firstWinMaxAge
      {
        $0.graduated = true
      }
    }
  }

  private static let dayStampFormatter: DateFormatter = {
    let formatter = DateFormatter()
    formatter.calendar = Calendar(identifier: .gregorian)
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.dateFormat = "yyyy-MM-dd"
    return formatter
  }()

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
    // Transient session UI state must never survive an owner change — the
    // next account must not inherit the previous account's celebration.
    celebrationPending = false
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
