import Foundation

/// Decides whether the cinematic intro plays for this launch.
///
/// The intro is a first-impression, not a loading screen: it plays once, on a genuine
/// first run, and never again. Two situations must not see it:
///
/// - **A resume.** Granting Screen Recording restarts the process by design, and the
///   permission steps persist `SBOnboardingModel.resumeStepKey` so the user returns
///   where they left off. Replaying an 8.6s intro on the way back to step 9 would read
///   as the app having forgotten them.
/// - **A second run.** Onboarding can be re-entered (Reset Onboarding, a signed-out
///   re-auth). The intro earns its length exactly once.
///
/// Reduce Motion deliberately does *not* suppress it — `OmiCinematicTiming.current`
/// already swaps in a cross-fade table, so the intro stays but stops moving.
enum SBOnboardingIntroGate {
  /// Terminal fact: this install has seen the intro. One writer (`markPlayed`).
  static let playedKey = "sbOnboardingIntroPlayed"

  /// - Parameters:
  ///   - resumeStepRaw: `SBOnboardingModel.resumeStepKey`, 0 when nothing is persisted.
  ///   - promiseStepRaw: raw value of the first step, so this stays correct if steps are renumbered.
  ///   - alreadyPlayed: `playedKey`.
  static func shouldPlay(resumeStepRaw: Int, promiseStepRaw: Int, alreadyPlayed: Bool) -> Bool {
    guard !alreadyPlayed else { return false }
    return resumeStepRaw <= promiseStepRaw
  }

  static func shouldPlay(resumeStepRaw: Int, promiseStepRaw: Int, defaults: UserDefaults = .standard) -> Bool {
    shouldPlay(
      resumeStepRaw: resumeStepRaw,
      promiseStepRaw: promiseStepRaw,
      alreadyPlayed: defaults.bool(forKey: playedKey))
  }

  /// Recorded *before* the intro starts, not after it ends: a user who quits mid-intro
  /// has still seen it, and a crash during playback must not arm it to replay forever.
  static func markPlayed(defaults: UserDefaults = .standard) {
    defaults.set(true, forKey: playedKey)
  }

  static func reset(defaults: UserDefaults = .standard) {
    defaults.removeObject(forKey: playedKey)
  }
}
