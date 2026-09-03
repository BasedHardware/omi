import Combine
import CoreGraphics
import FirebaseAuth
import FirebaseCore
import Foundation
import OmiSupport

/// Remote-triggered onboarding rerun.
///
/// The PostHog flag `desktop-onboarding-rerun` is rolled out to everyone and carries a payload
/// such as `{"generation": 1, "min_account_age_days": 7, "active_questions_30d": 8}`. Each
/// client evaluates the rule locally, so every install that launches again is covered, not
/// only the users PostHog saw recently. A client reruns onboarding at most once per
/// generation: the generation is recorded before the reset, so a flag left on never loops.
///
/// Eligible: signed in, onboarding completed, account older than `min_account_age_days`, and
/// NOT active. Active means at least `active_questions_30d` questions in the last 30 days
/// with both Screen Recording and Microphone granted.
enum OnboardingRerunPolicy {
  static let flagName = "desktop-onboarding-rerun"
  static let appliedGenerationKey = "onboardingRerunAppliedGeneration"

  struct Rule: Equatable {
    var generation: Int
    var minAccountAgeDays: Int = 7
    var activeQuestions30d: Int = 8

    /// Accepts the payload as a JSON object, a JSON string, or a bare generation number.
    static func parse(_ payload: Any?) -> Rule? {
      switch payload {
      case let n as Int: return Rule(generation: n)
      case let d as Double: return Rule(generation: Int(d))
      case let s as String:
        if let n = Int(s.trimmingCharacters(in: .whitespacesAndNewlines)) { return Rule(generation: n) }
        guard let data = s.data(using: .utf8),
          let obj = try? JSONSerialization.jsonObject(with: data)
        else { return nil }
        return parse(obj)
      case let dict as [String: Any]:
        guard let generation = intValue(dict["generation"]) else { return nil }
        var rule = Rule(generation: generation)
        if let v = intValue(dict["min_account_age_days"]) { rule.minAccountAgeDays = v }
        if let v = intValue(dict["active_questions_30d"]) { rule.activeQuestions30d = v }
        return rule
      default: return nil
      }
    }

    private static func intValue(_ any: Any?) -> Int? {
      switch any {
      case let n as Int: return n
      case let d as Double: return Int(d)
      case let s as String: return Int(s)
      default: return nil
      }
    }
  }

  struct Profile: Equatable {
    var accountAgeDays: Int?
    var questionsLast30Days: Int
    var screenRecordingGranted: Bool
    var microphoneGranted: Bool
  }

  /// The generation to apply now, or nil (flag off, already applied, too new, or active).
  static func generationToApply(
    enabled: Bool, payload: Any?, appliedGeneration: Int, profile: Profile
  ) -> Int? {
    guard enabled, let rule = Rule.parse(payload), rule.generation > appliedGeneration else {
      return nil
    }
    // Unknown age counts as brand new: a rule with a minimum age never fires on it.
    guard (profile.accountAgeDays ?? 0) >= rule.minAccountAgeDays else { return nil }
    let active =
      profile.questionsLast30Days >= rule.activeQuestions30d
      && profile.screenRecordingGranted && profile.microphoneGranted
    return active ? nil : rule.generation
  }

  static func questionsInLast30Days(_ messages: [ChatMessageDB], now: Date = Date()) -> Int {
    let cutoff = now.addingTimeInterval(-30 * 24 * 3600)
    return messages.filter { $0.createdAt >= cutoff && $0.sender.lowercased() != "ai" }.count
  }
}

/// Launch-time glue: observes PostHog flag delivery and applies the policy once per generation.
@MainActor enum OnboardingRerunFlag {
  private static var observer: NSObjectProtocol?
  private static var sessionObserver: AnyCancellable?
  private static var evaluating = false

  @MainActor static func install() {
    guard observer == nil else { return }
    observer = NotificationCenter.default.addObserver(
      forName: PostHogManager.featureFlagsDidLoad, object: nil, queue: .main
    ) { _ in
      Task { @MainActor in await evaluate() }
    }
    // Flags usually arrive before the stored session is restored; re-evaluate once the user
    // is authenticated so the decision is made with the real signed-in state.
    sessionObserver = AuthState.shared.$sessionPhase
      .removeDuplicates()
      .sink { phase in
        guard phase == .authenticated else { return }
        Task { @MainActor in await evaluate() }
      }
    Task { @MainActor in await evaluate() }
  }

  /// Flag delivery as the app sees it. DEBUG builds accept `OMI_ONBOARDING_RERUN_PAYLOAD` (the
  /// JSON the flag would carry) so the rerun path can be exercised on a dev bundle without a
  /// live PostHog flag; release builds only ever read PostHog.
  static func deliveredRule() -> OnboardingRerunPolicy.Rule? {
    #if DEBUG
      // getenv, not ProcessInfo: BundleEnvironment applies the bundle's .env with setenv after
      // launch, and ProcessInfo.environment is a snapshot taken at first access.
      if let c = getenv("OMI_ONBOARDING_RERUN_PAYLOAD"), let raw = String(validatingCString: c),
        !raw.isEmpty
      {
        return OnboardingRerunPolicy.Rule.parse(raw)
      }
    #endif
    guard PostHogManager.shared.isFeatureEnabled(OnboardingRerunPolicy.flagName) else { return nil }
    return OnboardingRerunPolicy.Rule.parse(
      PostHogManager.shared.getFeatureFlagPayload(OnboardingRerunPolicy.flagName))
  }

  @MainActor static func evaluate(defaults: UserDefaults = .standard) async {
    guard !evaluating else { return }
    let applied = defaults.integer(forKey: OnboardingRerunPolicy.appliedGenerationKey)
    guard let rule = deliveredRule(), rule.generation > applied else { return }
    // Signed out (or the session is not restored yet): decide later, record nothing.
    guard AuthState.shared.isSignedIn else { return }
    // Signed in but never finished onboarding: record the generation so their first, fresh
    // onboarding is not followed by a second one.
    guard defaults.bool(forKey: .hasCompletedOnboarding) else {
      defaults.set(rule.generation, forKey: OnboardingRerunPolicy.appliedGenerationKey)
      log("OnboardingRerun: generation \(rule.generation) recorded without rerun (not onboarded)")
      return
    }
    evaluating = true
    defer { evaluating = false }
    let profile = await currentProfile()
    guard
      let generation = OnboardingRerunPolicy.generationToApply(
        enabled: true,
        payload: [
          "generation": rule.generation,
          "min_account_age_days": rule.minAccountAgeDays,
          "active_questions_30d": rule.activeQuestions30d,
        ],
        appliedGeneration: applied, profile: profile)
    else {
      // Active or too new: this generation does not apply to them; keep it pending so a later
      // drop in usage does not matter either (the decision is per generation, made once).
      defaults.set(rule.generation, forKey: OnboardingRerunPolicy.appliedGenerationKey)
      log("OnboardingRerun: generation \(rule.generation) skipped, profile=\(profile)")
      PostHogManager.shared.track(
        "Onboarding Rerun Skipped",
        properties: [
          "generation": rule.generation, "questions_30d": profile.questionsLast30Days,
          "account_age_days": profile.accountAgeDays ?? -1,
        ])
      return
    }
    defaults.set(generation, forKey: OnboardingRerunPolicy.appliedGenerationKey)
    log("OnboardingRerun: generation \(generation) — rerunning onboarding, profile=\(profile)")
    PostHogManager.shared.track(
      "Onboarding Rerun Triggered",
      properties: [
        "generation": generation, "questions_30d": profile.questionsLast30Days,
        "account_age_days": profile.accountAgeDays ?? -1,
      ])
    // Same steps as the manual Reset Onboarding action, minus the relaunch: the home view
    // drops `hasCompletedOnboarding` on this notification and mounts onboarding in place.
    NotificationCenter.default.post(name: .resetOnboardingRequested, object: nil)
    OnboardingFlow.clearPersistedState(in: defaults)
    defaults.removeObject(forKey: .hasCompletedOnboarding)
    OnboardingChatPersistence.clear()
  }

  /// Backend timestamps arrive with or without fractional seconds.
  private static func parseBackendDate(_ raw: String) -> Date? {
    let f = ISO8601DateFormatter()
    f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    if let d = f.date(from: raw) { return d }
    f.formatOptions = [.withInternetDateTime]
    return f.date(from: raw)
  }

  private static func localDataDirectoryCreationDate() -> Date? {
    let dir = DesktopLocalProfile.applicationSupportURL()
    return (try? dir.resourceValues(forKeys: [.creationDateKey]))?.creationDate
  }

  @MainActor private static func currentProfile() async -> OnboardingRerunPolicy.Profile {
    var ageDays: Int?
    if FirebaseApp.app() != nil, let created = Auth.auth().currentUser?.metadata.creationDate {
      ageDays = Int(Date().timeIntervalSince(created) / 86_400)
    } else if let created = try? await APIClient.shared.getUserProfile().createdAt,
      let date = parseBackendDate(created)
    {
      ageDays = Int(Date().timeIntervalSince(date) / 86_400)
    } else if let created = localDataDirectoryCreationDate() {
      // No account timestamp reachable: the local data folder is at least as old as this
      // install's onboarding, which is a lower bound on the account's age.
      ageDays = Int(Date().timeIntervalSince(created) / 86_400)
      log("OnboardingRerun: account age from local data folder (\(ageDays ?? -1)d)")
    }
    var questions = 0
    if let messages = try? await APIClient.shared.getMessages(limit: 200) {
      questions = OnboardingRerunPolicy.questionsInLast30Days(messages)
    } else {
      // Backend unavailable: fall back to the local lifetime question counter.
      questions = RatingPromptManager.shared.questionCount
    }
    return OnboardingRerunPolicy.Profile(
      accountAgeDays: ageDays,
      questionsLast30Days: questions,
      screenRecordingGranted: CGPreflightScreenCaptureAccess(),
      microphoneGranted: AudioCaptureService.checkPermission())
  }
}
