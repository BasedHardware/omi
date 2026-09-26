import AppKit
import Foundation

/// What the app can honestly answer for a user Omi knows nothing about yet.
///
/// Day-0 evidence (2026-09 activation analysis, 291 new macOS users): ~30% of
/// first messages are a suggestion chip pasted verbatim, and three of the six
/// chips asked about data that cannot exist on day 0 ("what did I spend my time
/// on this week", "highest-leverage thing"). Users who stopped after one or two
/// questions over-indexed 3x on exactly those empty-state answers; users who
/// kept going asked for things with an artifact at the end: the screen, a task,
/// a fact they just taught Omi. Every chip below is gated on the signal that
/// makes it answerable right now, with zero history.
struct DayZeroChipSignals: Equatable, Sendable {
  /// Screen Recording is granted and live in this process (a grant made after
  /// launch only takes effect on relaunch, so it does not count yet).
  var canSeeScreen = false
  /// Screen analysis is on, so screen history exists to answer "the last hour".
  var screenHistoryEnabled = false
  /// Endonym of the system language when it differs from the language Omi
  /// listens and replies in (e.g. "Español"). `nil` when they already match.
  var systemLanguageName: String? = nil

  /// Reads the live signals. Cheap and synchronous: no I/O, no model.
  @MainActor
  static func live() -> DayZeroChipSignals {
    let grantedNow = CGPreflightScreenCaptureAccess()
    let liveInThisProcess =
      grantedNow
      && !ScreenRecordingPermissionPolicy.needsRelaunchToApply(
        grantedNow: grantedNow, grantedAtLaunch: ScreenCaptureService.grantedAtProcessStart)
    return DayZeroChipSignals(
      canSeeScreen: liveInThisProcess,
      screenHistoryEnabled: liveInThisProcess && UserDefaults.standard.bool(forKey: .screenAnalysisEnabled),
      systemLanguageName: languageMismatchName(
        systemLanguageCode: Locale.current.language.languageCode?.identifier,
        omiLanguageCode: AssistantSettings.shared.transcriptionLanguage)
    )
  }

  /// The endonym of the system language when Omi is set to a different one.
  /// Language only (no region): "pt-BR" on a "pt" system is not a mismatch.
  static func languageMismatchName(systemLanguageCode: String?, omiLanguageCode: String) -> String? {
    guard let systemLanguageCode, !systemLanguageCode.isEmpty else { return nil }
    let system = systemLanguageCode.lowercased()
    let omi = omiLanguageCode.lowercased().split(separator: "-").first.map(String.init) ?? "en"
    guard system != omi else { return nil }
    let endonym = Locale(identifier: system).localizedString(forLanguageCode: system)
    guard let endonym, !endonym.isEmpty else { return nil }
    return endonym.prefix(1).uppercased() + endonym.dropFirst()
  }
}

enum DayZeroChips {
  /// Screen-grounded: the single best-performing first question in the sample
  /// (57% got a real description of the user's work; every one produced a
  /// follow-up). Phrased as a summary so the answer is an artifact, not a list.
  static let summarizeScreen = "Summarize what's on my screen"
  /// Screen history answers this within minutes of install; memory recall needs days.
  static let lastHour = "What have I been working on in the last hour?"
  /// Task extraction from what is in front of the user was the strongest
  /// zero-history capability observed; this makes it user-invoked.
  static let screenToTasks = "Turn what's on my screen into tasks"
  /// The teach-and-quiz thread was the longest observed first session. This
  /// chip is a draft, not a send: it lands in the composer for the user to finish.
  static let rememberDraft = "Remember that I…"
  /// Emitted by `SBPostOnboardingGuidance` from the onboarding connector state;
  /// the Home top-up has no live connector signal, so it does not offer this.
  static let calendarToday = "What's on my calendar today?"

  static func switchLanguage(to name: String) -> String { "Switch to \(name)" }

  /// The top-up chips for a user with no personalized questions yet, in
  /// priority order. Never the week-scale questions, never "what can you do".
  static func chips(for signals: DayZeroChipSignals) -> [String] {
    var chips: [String] = []
    if let name = signals.systemLanguageName {
      // A large minority of macOS signups write in a non-Latin script and
      // discover language switching by trial; make it the first thing they see.
      chips.append(switchLanguage(to: name))
    }
    if signals.canSeeScreen {
      chips.append(summarizeScreen)
      if signals.screenHistoryEnabled {
        chips.append(lastHour)
      }
      chips.append(screenToTasks)
    }
    chips.append(rememberDraft)
    return chips
  }

  /// Chips that prefill the composer instead of sending. Exact-match on the
  /// chip text so the two send sites cannot drift from the chip list.
  static func isDraftPrompt(_ text: String) -> Bool {
    text.trimmingCharacters(in: .whitespacesAndNewlines) == rememberDraft
  }

  /// The composer text for a draft chip: the ellipsis becomes a trailing space
  /// so the caret lands where the user continues the sentence.
  static func draftText(for chip: String) -> String {
    guard isDraftPrompt(chip) else { return chip }
    return String(rememberDraft.dropLast()) + " "
  }
}
