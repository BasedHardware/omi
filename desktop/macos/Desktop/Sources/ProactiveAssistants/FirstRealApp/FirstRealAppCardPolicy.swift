import Foundation

/// Where this install stands with respect to the one-time "I can see …" card.
///
/// Three states have to be distinguishable and only two of them are values, so
/// *absent* carries the third: this build has never looked at this install.
/// A single `Bool` cannot do that — `false` would be indistinguishable from
/// "never written", which is exactly the ambiguity that made the launch-at-login
/// V1 migration re-enable a setting the user had turned off.
enum FirstRealAppCardState: String, Equatable, CaseIterable {
  /// This install is a fresh one that has not been shown the card yet.
  case pending
  /// The card has fired, or the install gate decided it never will.
  case consumed
}

/// Pure, clock-free decision layer for the first-real-app tap-to-ask card.
///
/// The card fires **exactly once per fresh install** — the first time the user
/// brings a real (non-Omi, non-system-UI) app to the front after onboarding —
/// and never at all for someone who was already onboarded when this build
/// arrived. Getting that wrong in either direction is expensive: firing twice
/// makes the notch feel like an ad, and firing for a two-year user teaches them
/// to ignore the surface. So the whole thing decides here, with no clock, no
/// `UserDefaults`, and no window server, and the coordinator only supplies
/// inputs and performs effects.
enum FirstRealAppCardPolicy {
  /// How long the app must stay frontmost before it counts as "the user opened
  /// it". Matches `IntegrationNudgePolicy.requiredDwell`'s intent: long enough
  /// that ⌘-Tab cycling does not fire one, short enough that the card lands
  /// while the user is still looking at what prompted it.
  static let requiredDwell: TimeInterval = 3

  /// How long the card stays up. Persistent cards have no timeout of their own;
  /// this one gets a bounded life because an un-acted first-run card sitting in
  /// the notch forever is clutter, not an offer.
  static let visibleDuration: TimeInterval = 60

  /// The exact draft the tap puts in the composer. Not sent — the user presses
  /// return. Seeing the question before asking it is the point.
  static let prompt = "Summarize what's on my screen"

  /// Foreground bundles that are system UI rather than "an app the user opened".
  /// `loginwindow` and the screen saver own the front during login and lock;
  /// Dock owns it while Launchpad or a Dock menu is open; System Settings owns
  /// it during a permission grant — which is precisely when onboarding hands
  /// the front away, and a card about System Settings would be Omi describing
  /// its own setup detour.
  static let excludedBundleIdentifiers: Set<String> = [
    "com.apple.loginwindow",
    "com.apple.ScreenSaver.Engine",
    "com.apple.dock",
    "com.apple.systemuiserver",
    "com.apple.controlcenter",
    "com.apple.notificationcenterui",
    "com.apple.systempreferences",
  ]

  /// Why a candidate card did not fire. Closed set; every case is reachable.
  enum Suppression: String, Equatable, CaseIterable {
    /// Already fired, or the install gate retired it for an existing user.
    case alreadyConsumed = "already_consumed"
    /// The install gate has not run yet, so eligibility is unknown.
    case gateNotRun = "gate_not_run"
    /// Onboarding is still on screen; the card would compete with it.
    case onboardingIncomplete = "onboarding_incomplete"
    /// Omi is frontmost — the 19%-of-first-questions defect this card exists to
    /// avoid is Omi describing its own window.
    case omiFrontmost = "omi_frontmost"
    /// System UI, not an app the user chose to open.
    case systemUI = "system_ui"
    /// No frontmost bundle identifier, or no localized name to put in the copy.
    case unknownApp = "unknown_app"
    /// No signed-in owner, so the notification has no owner to fence against.
    case notSignedIn = "not_signed_in"
  }

  enum Decision: Equatable {
    case fire
    case suppress(Suppression)

    var isFire: Bool { self == .fire }

    var suppression: Suppression? {
      guard case .suppress(let reason) = self else { return nil }
      return reason
    }
  }

  /// Everything the fire/don't-fire decision depends on, gathered by the caller.
  struct Input: Equatable {
    /// `nil` means the install gate has not recorded a verdict yet.
    var state: FirstRealAppCardState?
    var frontmostBundleIdentifier: String?
    var frontmostAppName: String?
    var omiBundleIdentifier: String?
    var isOnboardingComplete: Bool
    var isSignedIn: Bool

    init(
      state: FirstRealAppCardState?,
      frontmostBundleIdentifier: String?,
      frontmostAppName: String?,
      omiBundleIdentifier: String? = nil,
      isOnboardingComplete: Bool = true,
      isSignedIn: Bool = true
    ) {
      self.state = state
      self.frontmostBundleIdentifier = frontmostBundleIdentifier
      self.frontmostAppName = frontmostAppName
      self.omiBundleIdentifier = omiBundleIdentifier
      self.isOnboardingComplete = isOnboardingComplete
      self.isSignedIn = isSignedIn
    }
  }

  static func decide(_ input: Input) -> Decision {
    // Consumed outranks everything so the steady state — every app switch for
    // the rest of the install's life — settles on one cheap comparison and one
    // unambiguous reason.
    switch input.state {
    case .consumed: return .suppress(.alreadyConsumed)
    case nil: return .suppress(.gateNotRun)
    case .pending: break
    }
    guard input.isOnboardingComplete else { return .suppress(.onboardingIncomplete) }
    guard let bundleIdentifier = input.frontmostBundleIdentifier, !bundleIdentifier.isEmpty,
      let appName = input.frontmostAppName, !appName.isEmpty
    else { return .suppress(.unknownApp) }
    if let omiBundleIdentifier = input.omiBundleIdentifier, bundleIdentifier == omiBundleIdentifier {
      return .suppress(.omiFrontmost)
    }
    guard !excludedBundleIdentifiers.contains(bundleIdentifier) else { return .suppress(.systemUI) }
    guard input.isSignedIn else { return .suppress(.notSignedIn) }
    return .fire
  }

  // MARK: - Install gate

  /// What the once-per-install gate should persist, if anything.
  enum InstallGate: Equatable {
    /// A verdict already exists; leave it alone.
    case alreadyRecorded
    /// Write this verdict now.
    case record(FirstRealAppCardState)
  }

  /// Version gate. The card is a *fresh install* moment: someone who finished
  /// onboarding on an older build has been using Omi for a while and does not
  /// need to be told it can see their screen. Their marker is written straight
  /// to `consumed` the first time this build looks, so the card never fires for
  /// them and no later launch reconsiders. Same shape as
  /// `LaunchAtLoginPreference.migrationDecision`.
  ///
  /// Recording `pending` (rather than nothing) for a user mid-onboarding is
  /// what makes the gate a true one-shot: without it, a fresh user who quit
  /// during onboarding would come back on the next launch with onboarding
  /// complete and be mistaken for an existing user.
  static func installGate(
    state: FirstRealAppCardState?,
    hasCompletedOnboarding: Bool
  ) -> InstallGate {
    guard state == nil else { return .alreadyRecorded }
    return .record(hasCompletedOnboarding ? .consumed : .pending)
  }

  // MARK: - Copy

  static func title(appName: String) -> String {
    "I can see \(appName)"
  }

  /// The body names the user's *real* push-to-talk chord, because the whole
  /// point is discovery: PTT is otherwise two hover lines on the notch. A user
  /// who cleared the chord gets the tap-only copy rather than an instruction
  /// naming a shortcut that does not exist.
  static func body(pttChordTokens: [String]) -> String {
    let chord =
      pttChordTokens
      .map { $0.trimmingCharacters(in: .whitespaces) }
      .filter { !$0.isEmpty }
      .joined(separator: " ")
    guard !chord.isEmpty else { return "Tap to ask me anything about it." }
    return "Hold \(chord) and ask me anything about it — or tap to type."
  }
}
