import Foundation

// MARK: - What onboarding actually learned

/// The facts the Second Brain onboarding genuinely established about this
/// user's setup, reduced to a plain value type.
///
/// Deliberately free of `@MainActor`, `AppState`, and every live service so the
/// guidance rules below stay pure and unit-testable — and, more importantly, so
/// every rule has to state its precondition explicitly. A suggestion that
/// depends on a connector the user skipped or a permission they denied is worse
/// than no suggestion at all: it is the app confidently telling a new user to
/// ask something it cannot answer.
struct SBSetupSnapshot: Equatable, Sendable {
  enum Listening: String, Equatable, Sendable {
    case disabled
    case always
    case meetingsOnly

    init(audioRecordingModeRaw: String, canHear: Bool) {
      guard canHear else {
        self = .disabled
        return
      }
      switch audioRecordingModeRaw {
      case AssistantSettings.AudioRecordingMode.always.rawValue:
        self = .always
      case AssistantSettings.AudioRecordingMode.onlyMeetings.rawValue:
        self = .meetingsOnly
      case AssistantSettings.AudioRecordingMode.off.rawValue:
        self = .disabled
      default:
        // An unknown persisted value is not evidence for a more permissive
        // mode. AssistantSettings normally heals this before it reaches us,
        // but the snapshot should remain conservative if it does not.
        self = .disabled
      }
    }
  }

  /// The answer to "what do your days look like" — a picked chip ("Founder")
  /// or the user's own words. Empty when the question was skipped.
  var role: String = ""
  /// Endonym of the system language when Omi listens in a different one;
  /// `nil` when they match. See `DayZeroChipSignals.languageMismatchName`.
  var systemLanguageName: String? = nil
  /// The capture mode the user chose on the last step. `skip()` leaves whatever
  /// was already configured, which is exactly what should be described.
  var listening: Listening = .disabled
  /// Screen Recording *granted*, not merely offered.
  var canSeeScreen: Bool = false
  /// Microphone *granted*, not merely offered.
  var canHear: Bool = false
  /// Context connectors observed as genuinely connected during onboarding —
  /// the ids from `SBOnboardingModel.contextRows` ("calendar", "gmail",
  /// "applenotes", "files", "chatgpt", "claude").
  var connectedContextIDs: Set<String> = []
  /// Display names of agents observed as connected, in row order.
  var connectedAgentNames: [String] = []
}

// MARK: - One orientation cue

/// A single "here is where I am and how you reach me" line.
///
/// Onboarding ends with the user knowing what Omi *is* and nothing about how to
/// summon it: the window closes and the app becomes invisible. These cues name
/// the real affordances — the menu bar item, the chord the user picked minutes
/// ago — and each one is emitted only when the affordance actually exists.
struct SBOrientationCue: Equatable, Identifiable, Sendable {
  let id: String
  /// SF Symbol name.
  let symbol: String
  let title: String
  /// Keycap tokens to render as chips (e.g. `["⌘", "O"]`). Empty when the cue
  /// is not about a keyboard chord.
  let keys: [String]
}

// MARK: - The rules

/// Derives the post-onboarding guidance — "what do I do now" — from what the
/// user's setup can actually support.
///
/// The dashboard has rendered this guidance since it was written
/// (`TryAskingPopupView` / `PromptSuggestionBanner`), but nothing ever produced
/// it: `PostOnboardingPromptSuggestions.save(_:)` was called from exactly one
/// place, the retired paged-intro onboarding, so the live Second Brain flow
/// finished with an empty array and both surfaces stayed permanently gated off.
enum SBPostOnboardingGuidance {
  /// Four fits the popup without scrolling and still leaves room for the
  /// orientation cues above it.
  static let maxSuggestions = 4

  /// The former tail question, "What can you help me with?", is gone: it
  /// returns a feature list with nothing to act on and over-indexed 3x among
  /// users who stopped after one question. A user who skipped everything gets
  /// the universal first question and the teach-me draft, both answerable.
  static let teachMeDraft = DayZeroChips.rememberDraft

  /// The ordered candidate rules. Each pairs a question with the precondition
  /// that makes it answerable; a candidate whose precondition is false is never
  /// emitted.
  static func suggestions(for setup: SBSetupSnapshot) -> [String] {
    var candidates: [String] = [HomeSuggestionComposer.universalFirstQuestion]

    if let language = setup.systemLanguageName {
      candidates.append(DayZeroChips.switchLanguage(to: language))
    }
    // Screen Recording is the most immediately demonstrable capability: the
    // answer is on the user's display right now, whatever else they skipped.
    if setup.canSeeScreen {
      candidates.append(DayZeroChips.summarizeScreen)
    }
    if setup.connectedContextIDs.contains("calendar") {
      candidates.append(DayZeroChips.calendarToday)
    }
    if let roleQuestion = roleQuestion(for: setup) {
      candidates.append(roleQuestion)
    }
    if setup.canSeeScreen {
      // Screen history answers this within minutes; it ranks below the
      // connector-backed questions so the cap keeps one of each kind.
      candidates.append(DayZeroChips.lastHour)
    }
    if setup.connectedContextIDs.contains("gmail") {
      candidates.append("What email follow-ups matter most today?")
    }
    if setup.connectedContextIDs.contains("files") {
      candidates.append("What am I working on, based on my files?")
    }
    if setup.connectedContextIDs.contains("applenotes") {
      candidates.append("Summarize my recent notes.")
    }
    if let agent = setup.connectedAgentNames.first(where: { !$0.trimmed.isEmpty }) {
      candidates.append("What can \(agent.trimmed) do for me?")
    }
    candidates.append(teachMeDraft)

    return Array(dedupedNonEmpty(candidates).prefix(maxSuggestions))
  }

  /// A question tailored to the role the user picked, chosen from a fixed table
  /// rather than interpolated into a sentence — interpolation cannot survive the
  /// free-text answer the role step also accepts ("or just say it in your own
  /// words…"), and a broken sentence is a worse first impression than silence.
  ///
  /// Returns `nil` for an unrecognized/absent role, and for a role whose
  /// question depends on something this user does not have.
  static func roleQuestion(for setup: SBSetupSnapshot) -> String? {
    let hasPeopleContext =
      setup.connectedContextIDs.contains("gmail") || setup.connectedContextIDs.contains("calendar")
    let hasWorkContext = setup.connectedContextIDs.contains("files") || setup.canSeeScreen

    switch setup.role.trimmed.lowercased() {
    case "founder":
      return "What did I commit to this week?"
    case "sales", "consultant":
      // Naming people is only possible with a people-bearing connector.
      return hasPeopleContext ? "Who should I follow up with today?" : nil
    case "engineer":
      // "What was I working on" needs either indexed files or the screen.
      return hasWorkContext ? "What was I working on last?" : nil
    case "student":
      return "What should I study today?"
    case "analyst":
      return "What should I dig into today?"
    case "creator":
      return "What should I make today?"
    default:
      // "Other" and free text: no honest tailored question exists.
      return nil
    }
  }

  /// The orientation lines shown above the suggestions. Every cue is gated on
  /// the affordance genuinely existing — an unset chord or a denied microphone
  /// produces no cue rather than an instruction that does nothing.
  static func orientationCues(
    openShortcutTokens: [String],
    talkShortcutTokens: [String],
    setup: SBSetupSnapshot
  ) -> [SBOrientationCue] {
    // Describe how this window actually behaves — it stays where you leave it — then name the
    // persistent way back. The menu bar icon is named rather than left to the chord cue below because
    // the chord is conditional and the icon is always there.
    var cues: [SBOrientationCue] = [
      SBOrientationCue(
        id: "menubar",
        symbol: "menubar.arrow.up.rectangle",
        title: "I stay open while you work — switch back any time. My menu bar icon brings me back too.",
        keys: [])
    ]

    let openKeys = openShortcutTokens.compactMap { $0.trimmed.isEmpty ? nil : $0.trimmed }
    if !openKeys.isEmpty {
      cues.append(
        SBOrientationCue(
          id: "open",
          symbol: "keyboard",
          title: "Or bring me back from any app.",
          keys: openKeys))
    }

    // Hold-to-talk is only an instruction if the microphone can hear.
    let talkKeys = talkShortcutTokens.compactMap { $0.trimmed.isEmpty ? nil : $0.trimmed }
    if setup.canHear, !talkKeys.isEmpty {
      cues.append(
        SBOrientationCue(
          id: "talk",
          symbol: "waveform",
          title: "Hold to talk to me, hands-free.",
          keys: talkKeys))
    }

    cues.append(listeningCue(for: setup))
    return cues
  }

  static func listeningCue(for setup: SBSetupSnapshot) -> SBOrientationCue {
    guard setup.canHear, setup.listening != .disabled else {
      return SBOrientationCue(
        id: "listening",
        symbol: "mic.slash",
        title: "I can't hear yet. Turn on the microphone in Settings whenever you want me to.",
        keys: [])
    }
    switch setup.listening {
    case .disabled:
      return SBOrientationCue(
        id: "listening",
        symbol: "mic.slash",
        title: "I can't hear yet. Turn on the microphone in Settings whenever you want me to.",
        keys: [])
    case .always:
      return SBOrientationCue(
        id: "listening",
        symbol: "ear",
        title: "I'm listening now, and I'll remember what matters.",
        keys: [])
    case .meetingsOnly:
      return SBOrientationCue(
        id: "listening",
        symbol: "person.2",
        title: "I'll start listening when a call starts.",
        keys: [])
    }
  }

  private static func dedupedNonEmpty(_ values: [String]) -> [String] {
    var seen = Set<String>()
    var out: [String] = []
    for value in values {
      let trimmed = value.trimmed
      guard !trimmed.isEmpty, seen.insert(trimmed.lowercased()).inserted else { continue }
      out.append(trimmed)
    }
    return out
  }
}

extension String {
  fileprivate var trimmed: String { trimmingCharacters(in: .whitespacesAndNewlines) }
}

// MARK: - Live wiring

@MainActor
extension SBOnboardingModel {
  /// What this run of onboarding established, read from the authorities that
  /// actually know — the permission flags on `AppState`, the connector states
  /// the connector steps resolved, and the capture mode already written to
  /// `AssistantSettings` by `capture(_:)`.
  ///
  /// Permission checks OR the step state with `AppState` because either alone
  /// can lag: the step state is only ever set from a real `isGranted` check,
  /// and `AppState` is authoritative for a grant made outside this flow.
  var postOnboardingSetup: SBSetupSnapshot {
    let canHear = micState == .on || appState.hasMicrophonePermission
    return SBSetupSnapshot(
      role: role ?? roleDraft,
      systemLanguageName: DayZeroChipSignals.live().systemLanguageName,
      listening: SBSetupSnapshot.Listening(
        audioRecordingModeRaw: appState.audioRecordingMode.rawValue,
        canHear: canHear),
      // Match the dashboard's capture health contract. TCC can remain granted
      // after signing changes or a ScreenCaptureKit failure, so permission or
      // the onboarding row alone is not enough to promise screen access.
      canSeeScreen: CaptureListeningLogic.captureStatus(appState: appState, isCaptureMonitoring: false) != .blocked,
      canHear: canHear,
      connectedContextIDs: Set(contextStates.filter { $0.value == "on" }.map(\.key)),
      connectedAgentNames: agentRows.filter { agentStates[$0.id] == "on" }.map(\.name)
    )
  }

  /// Produce and persist the post-onboarding guidance. Called from the single
  /// shared handoff both exit paths run, so the dashboard's suggestion surfaces
  /// are populated whether the user finished or skipped.
  func savePostOnboardingGuidance() {
    PostOnboardingPromptSuggestions.save(SBPostOnboardingGuidance.suggestions(for: postOnboardingSetup))
  }
}
