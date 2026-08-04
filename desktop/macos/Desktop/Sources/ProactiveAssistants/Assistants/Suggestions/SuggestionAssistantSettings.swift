import Foundation

/// Settings for the live suggestion assistant.
///
/// Default-on by product decision, departing from `48239de8` ("proactive notifications off by
/// default for all users"). Enabling this assistant is independent of the other four —
/// a user who wants live suggestions should not have to turn on Focus or Memory too.
@MainActor
class SuggestionAssistantSettings {
  static let shared = SuggestionAssistantSettings()

  // MARK: - UserDefaults Keys

  private let enabledKey = "suggestionAssistantEnabled"
  private let analysisPromptKey = "suggestionAnalysisPrompt"
  private let cooldownKey = "suggestionCooldownInterval"
  private let minConfidenceKey = "suggestionMinConfidence"
  private let promptVersionKey = "suggestionPromptVersion"

  // MARK: - Default Values

  /// On by default, by product decision.
  ///
  /// This deliberately departs from `48239de8`, which made proactive notifications opt-in
  /// after ~25% click-through over 90 days. The bet is that the two structural changes here
  /// — evaluating on real dwell rather than a blind 600s timer, and refusing to spend at all
  /// unless grounding found something the user does not already have on screen — move
  /// precision enough to justify being on. That is a hypothesis, not a measurement; if
  /// click-through does not move, this default is the first thing to revert.
  ///
  /// Delivery is still bounded independently by the shared 0–5 notification frequency, and
  /// cost by dwell, cooldown, and the 40/day evaluation budget.
  private let defaultEnabled = true

  /// Minimum time between *evaluations*, not between delivered suggestions. Gating on
  /// evaluation is what bounds cost when the user cmd-tabs rapidly.
  private let defaultCooldown: TimeInterval = 180.0

  /// Matches Insight's bar. Below this the suggestion is dropped without a notification.
  private let defaultMinConfidence: Double = 0.85

  private let currentPromptVersion = 1

  /// System prompt. Inherits the shape of the shipped Insight prompt — which was never
  /// the defect — and adds the grounding contract: a suggestion must use what Omi knows,
  /// not merely narrate the screen.
  static let defaultAnalysisPrompt = """
    You look at what the user is doing right now and decide whether Omi should say something.

    Omi has memory of the user — their history, commitments, and what they have been working on.
    That memory is your advantage. A suggestion is worth an interruption when it tells the user
    something they do NOT already have in front of them.

    CORE QUESTION: Given what is on screen AND what Omi knows about this user, is there something
    genuinely worth saying right now?

    Call has_suggestion=true ONLY when ALL of these hold:
    1. It is specific to what is on screen right now — not generic wisdom
    2. The user likely does NOT already know it
    3. It is actionable, or it changes what the user does next

    Set has_suggestion=false when:
    - You would be narrating something the user can plainly see
    - You are reaching. If you have to stretch, there is nothing there
    - It repeats something in RECENT SUGGESTIONS (compare by meaning, not wording)
    - The only thing you can say is generic advice that would fit any screen

    WHAT QUALIFIES (high bar):
    - A commitment the user made that this screen is relevant to
    - A concrete mistake visible on screen they may not have noticed
    - A connection between this screen and something they saw or said earlier
    - A specific, lesser-known tool or shortcut that solves exactly what they are struggling with
    - Something on this page worth their attention that they are likely to scroll past

    GOOD EXAMPLES (this is the quality bar):
    - "You told Sarah you'd send the deck Friday — this is that thread"
    - "You've scheduled this for 2026 — double-check the year"
    - "This is the role you saved last week — you know someone there"
    - "Sensitive credentials visible in terminal — mask before sharing"
    - "You stashed changes 2 hours ago — remember to git stash pop"
    - "Replying to group thread, not DM — check the recipient"

    BAD EXAMPLES (never produce these):
    - "Set your first goal to get started" (pointing at UI the user can see)
    - "Click Allow to grant permission" (narrating the screen)
    - "Press Cmd+Enter to send" (a shortcut everyone knows)
    - "Consider adding tests" (vague, generic)
    - "You have a lot of tabs open" (unsolicited judgment)
    - "Take a break / Stay hydrated" (we are not a health app)

    CATEGORIES:
    - "commitment" — something the user said they would do
    - "mistake" — something visibly wrong or about to go wrong
    - "opportunity" — something worth acting on that they may miss
    - "connection" — a link to something they saw, said, or saved earlier
    - "other"

    CONFIDENCE:
    - 0.90-1.0  preventing a real mistake, or surfacing a commitment they are about to miss
    - 0.75-0.89 a non-obvious connection or opportunity they would genuinely miss
    - 0.60-0.74 useful, but they might get there themselves
    - below 0.60 do not suggest

    FORMAT: under 100 characters. Lead with the actionable part. Write like a sharp friend,
    not a corporate assistant. Never open with: Confirm, Ensure, Clarify, Consider,
    Prioritize, Remember, Review, Align, Make sure, Don't forget.
    """

  private init() {
    UserDefaults.standard.register(defaults: [
      enabledKey: defaultEnabled,
      cooldownKey: defaultCooldown,
      minConfidenceKey: defaultMinConfidence,
    ])
    migratePromptIfNeeded()
  }

  /// Reset a saved prompt when the shipped default changes, so existing users pick up
  /// prompt improvements instead of being pinned to an old version forever.
  private func migratePromptIfNeeded() {
    let saved = UserDefaults.standard.integer(forKey: promptVersionKey)
    if saved < currentPromptVersion {
      UserDefaults.standard.removeObject(forKey: analysisPromptKey)
      UserDefaults.standard.set(currentPromptVersion, forKey: promptVersionKey)
    }
  }

  // MARK: - Properties

  var isEnabled: Bool {
    get { UserDefaults.standard.bool(forKey: enabledKey) }
    set {
      UserDefaults.standard.set(newValue, forKey: enabledKey)
      NotificationCenter.default.post(name: .assistantSettingsDidChange, object: nil)
    }
  }

  /// Applies an explicit user toggle and records the activation denominator only
  /// when the persisted value actually changes. Remote sync, startup/default
  /// registration, and resets continue to call `isEnabled` directly and stay
  /// deliberately silent.
  @discardableResult
  func applyUserEnabledChange(_ value: Bool) -> Bool {
    let previous = isEnabled
    isEnabled = value
    guard
      SuggestionAssistantTelemetry.settingChangeIsPersistedChange(
        oldValue: previous,
        newValue: value
      )
    else { return false }
    AnalyticsManager.shared.suggestionAssistantSettingChanged(setting: .enabled, value: value)
    return true
  }

  var analysisPrompt: String {
    get { UserDefaults.standard.string(forKey: analysisPromptKey) ?? Self.defaultAnalysisPrompt }
    set { UserDefaults.standard.set(newValue, forKey: analysisPromptKey) }
  }

  var cooldownInterval: TimeInterval {
    get {
      let value = UserDefaults.standard.double(forKey: cooldownKey)
      return value > 0 ? value : defaultCooldown
    }
    set { UserDefaults.standard.set(newValue, forKey: cooldownKey) }
  }

  var minConfidence: Double {
    get {
      let value = UserDefaults.standard.double(forKey: minConfidenceKey)
      return value > 0 ? value : defaultMinConfidence
    }
    set { UserDefaults.standard.set(newValue, forKey: minConfidenceKey) }
  }

  /// Whether the app is excluded from screen analysis. Delegates to the single Rewind
  /// exclusion list rather than keeping a second one — the user set those exclusions
  /// once and expects them to mean "do not look at this".
  func isAppExcluded(_ appName: String) -> Bool {
    RewindSettings.shared.isAppExcluded(appName)
  }

  func resetToDefaults() {
    isEnabled = defaultEnabled
    cooldownInterval = defaultCooldown
    minConfidence = defaultMinConfidence
    UserDefaults.standard.removeObject(forKey: analysisPromptKey)
  }
}
