import AppKit
import Combine
import Foundation

/// The height-relevant identity of a step's widget — see `SBOnboardingModel.widgetShape`.
///
/// A value type rather than a set of `onChange`s in the view, so "the widget grew, scroll to it" is
/// one rule with one place to add the next widget's state to, instead of a modifier per `@Published`
/// property that someone has to remember.
struct SBOnboardingWidgetShape: Equatable {
  var step: SBOnboardingModel.Step
  var localFileProfile: SBOnboardingModel.LocalFileProfileState
  var permission: SBPermissionStepAction?
  var screenDemoReady: Bool
  var screenDemoUnavailable: Bool
  var screenDemoDone: Bool
  var shortcutRegistrationError: String? = nil
  var seePhase: SBOnboardingModel.SeePhase = .permission
  var writePhase: SBOnboardingModel.WritePhase = .intro
  var writeDetectionTimedOut = false
}

/// Drives the Second Brain scenario onboarding: a deterministic chat with Omi
/// whose permission asks immediately precede real browser, card, PTT, memory,
/// task, and capture payoffs.
///
/// Core state + lifecycle + copy live here. The heavier per-step behavior
/// (permissions, shortcut, screen/voice demo, connectors) lives in
/// `SBOnboardingModel+Steps.swift`.
@MainActor
final class SBOnboardingModel: ObservableObject {
  enum CaptureSelection: Equatable {
    case onlyMeetings
    case always

    var audioRecordingMode: AssistantSettings.AudioRecordingMode {
      switch self {
      case .onlyMeetings: .onlyMeetings
      case .always: .always
      }
    }
  }

  static let defaultCaptureSelection: CaptureSelection = .onlyMeetings

  enum Step: Int, CaseIterable {
    case hello, see, card, talk, write, ready

    // onboarding-legacy: unreferenced after scenario onboarding; removal tracked separately.
    // DesktopHomeView still names the old initial sentinel while checking for stale resume state.
    static let promise = Step.hello
  }

  /// The see beat is two moments, not one: the permission answer, then the user's own click that
  /// opens the browser. Folding them together is how the page used to pop up over the sentence
  /// that announced it.
  enum SeePhase: String, Codable, Equatable {
    case permission
    case openPage
    case waitingForPage
  }

  enum CardPhase: String, Codable, Equatable {
    case waitingForAction
    case notifications
  }

  enum TalkPhase: String, Codable, Equatable {
    case microphone
    case shortcut
    case demo
  }

  enum WritePhase: String, Codable, Equatable {
    /// The note is described and offered; nothing has left Omi yet.
    case intro
    case waitingForSend
    case review
  }

  /// "How did you hear about Omi?" options (mirrors the legacy step).
  static let howHeardSources = [
    "Social media", "YouTube", "Friend", "Search engine", "AI chat", "Podcast", "Colleague", "Product Hunt", "Other",
  ]

  struct Msg: Identifiable {
    let id = UUID()
    let isOmi: Bool
    var text: String
  }

  enum PermState: Equatable { case ask, waiting, on }

  enum LocalFileProfileState: Equatable {
    case idle
    case scanning
    case complete(fileCount: Int, memoryCount: Int, deniedFolders: [String])
    case failed(message: String)

    var isTerminal: Bool {
      switch self {
      case .complete, .failed: true
      case .idle, .scanning: false
      }
    }
  }

  @Published var step: Step = .hello
  @Published var thread: [Msg] = []
  /// The current Omi message streaming in (nil once committed).
  @Published var streamingText: String?
  @Published var typing = false
  @Published var showWidget = false

  // Per-step answers / state
  @Published var nameDraft = ""
  @Published var roleDraft = ""
  @Published var role: String?
  @Published var seePhase: SeePhase = .permission
  @Published var cardPhase: CardPhase = .waitingForAction
  @Published var talkPhase: TalkPhase = .microphone
  @Published var writePhase: WritePhase = .intro
  /// The scripted card is fired once per visit to the card beat, whichever of page detection or the
  /// beat's message finishes first.
  var scenarioCardPresented = false
  /// Seams for the two moments the scenario leaves Omi and comes back. Production opens the rendered
  /// page in the default browser and summons the shell the way the menu bar does; tests observe.
  var scenarioPageOpener: (URL) -> Bool = { NSWorkspace.shared.open($0) }
  var scenarioPageLocator: OnboardingScenarioPageLocator = .bundled
  var scenarioReturnToOmi: () -> Void = { AppDelegate.summonWindowTarget()?.openMainAppWindow() }
  @Published var scenarioTaskChips: [String] = []
  /// The task the note implies; written only on "Looks right".
  var scenarioProposedTaskTitle: String?
  @Published var scenarioMemoryChips: [String] = []
  @Published var scenarioWriteNote: String?
  @Published var scenarioWriteDetectionTimedOut = false
  @Published var scenarioWritesPending = false
  var scenarioWriteReceipts: Set<String> = []

  // Permissions
  @Published var micState: PermState = .ask
  @Published var sysState: PermState = .ask
  @Published var scrState: PermState = .ask  // screen recording
  @Published var fdaState: PermState = .ask  // full disk access (files)
  @Published var accState: PermState = .ask  // accessibility
  @Published var autoState: PermState = .ask  // automation / Apple Events
  @Published var notifState: PermState = .ask  // notifications
  @Published var localFileProfileState: LocalFileProfileState = .idle

  var launchAtLogin: Bool = LaunchAtLoginManager.shared.isEnabled

  /// One-shot guard: fire a single throwaway ScreenCaptureKit capture to surface
  /// the "bypass the private window picker" consent in-context once Screen
  /// Recording is granted, so the live screen demo doesn't hit that prompt.
  var didPrimeScreenCapture = false

  // Summon shortcut
  @Published var shortcutTokens: [String] = []
  @Published var shortcutPicked = false
  @Published var shortcutPressed = false
  @Published var shortcutRecording = false
  /// Set when the chosen Open Omi chord passed the local test press but Carbon could not claim it.
  /// Keep the stage active so the user can choose another chord instead of finishing with a shortcut
  /// that appears to work only inside onboarding.
  @Published var shortcutRegistrationError: String?
  /// Set when the user pressed a bare key while recording. `acceptsRecordedChord` refuses it — a
  /// bare `L` bound as a **global** hotkey makes every `L` typed anywhere open Omi — and the refusal
  /// used to be silent, so the step simply stopped responding with nothing said. Cleared the moment
  /// a valid chord arrives or the stage re-arms.
  @Published var shortcutNeedsModifier = false
  /// The chosen shortcut + which mechanism it uses (key hotkey vs modifier-hold).
  var chosenShortcut: ShortcutSettings.KeyboardShortcut?
  var chosenShortcutIsPTT = false
  var pendingModifierOnlyShortcut: ShortcutSettings.KeyboardShortcut?
  /// Each shortcut stage keeps its own choice so stepping back does not make a
  /// user re-select a key they already confirmed.
  var openShortcutSelection: ShortcutSettings.KeyboardShortcut?
  var talkShortcutSelection: ShortcutSettings.KeyboardShortcut?
  var shortcutMonitors: [Any] = []
  /// Main menu stashed while the shortcut step's key monitor is armed (menu key
  /// equivalents like ⌘O would otherwise swallow the press before we see it).
  var savedMainMenu: NSMenu?

  // Screen + voice demo
  @Published var screenThings: [String] = []
  @Published var screenDemoLoading = false
  @Published var voiceHeard = false
  @Published var voiceAnswer: String?
  /// True once Omi has actually answered the demo question (the notch shows a
  /// response). The screen-demo Continue button stays hidden until then, so the
  /// user can't skip past before seeing the "fun part" work.
  @Published var screenDemoDone = false
  /// The hold-to-talk demo is armed only after the bridge has initialized its
  /// kernel context. Showing the chord sooner invites a first PTT turn while its
  /// only response route is still cold.
  @Published var screenDemoPTTReady = false
  /// Bridge startup can fail before an authenticated response route exists. In
  /// that state, leave PTT unarmed and offer an explicit retry or skip instead
  /// of presenting a shortcut which cannot answer.
  @Published var screenDemoPTTUnavailable = false
  var voiceCancellable: AnyCancellable?
  var voiceTimeout: Task<Void, Never>?
  var screenDemoSetupTask: Task<Void, Never>?
  var scenarioDetectionTask: Task<Void, Never>?
  var scenarioCardTimeoutTask: Task<Void, Never>?
  let scenarioDates = OnboardingScenarioDates.make()
  let scenarioPageNonce = UUID().uuidString.lowercased()
  var scenarioPageDirectory = FileManager.default.temporaryDirectory
    .appendingPathComponent("omi-onboarding-\(UUID().uuidString)", isDirectory: true)
  var beatStartedAt = Date()
  var beatExitRecorded = false

  unowned let appState: AppState
  let chatProvider: ChatProvider
  /// Backend writes for editable answers are per-field serialized. Revisiting a
  /// question never lets an earlier request finish after the user's revision.
  private let answerWriteGate = OnboardingAnswerWriteGate()
  private let onComplete: (() -> Void)?
  var streamTask: Task<Void, Never>?
  /// Permission-grant pollers, one per permission key. Keyed so requesting a
  /// second permission (the meetings "both" mic+system-audio step) never cancels
  /// a still-running poll for the first and strands it on "macOS…".
  var pollTasks: [String: Task<Void, Never>] = [:]
  /// Observes late-arriving names (Apple sends the name only on first auth;
  /// otherwise it's fetched from the backend after sign-in). `givenName` is plain
  /// UserDefaults, not observable, so without this a name landing after the name
  /// step already streamed would never fill in.
  /// `nonisolated(unsafe)` so the nonisolated `deinit` can remove it — the token is
  /// only ever written on the main actor and `removeObserver` is thread-safe.
  nonisolated(unsafe) private var nameObserver: NSObjectProtocol?
  nonisolated(unsafe) private var scenarioCardActionObserver: NSObjectProtocol?

  init(
    appState: AppState,
    chatProvider: ChatProvider,
    onComplete: (() -> Void)?
  ) {
    self.appState = appState
    self.chatProvider = chatProvider
    self.onComplete = onComplete
    // Isolate any onboarding chat/voice turns to the throwaway `.onboarding()`
    // journal surface so they never pollute the real Chat tab. Cleared on
    // complete()/skip(), after which the Chat tab reloads the clean default surface.
    chatProvider.beginOnboardingJournal()
    // Detect the user's real name automatically (mirrors the legacy paged intro):
    // seed the editable field from what we already know, kick a backend fetch if we
    // don't have it yet, and adopt an async arrival — so onboarding greets by name
    // instead of "friend"/blank (regression from the SB redesign; see #9919).
    let known = AuthService.shared.givenName.trimmingCharacters(in: .whitespaces)
    if !known.isEmpty { nameDraft = known }
    AuthService.shared.loadNameFromBackendIfNeeded()
    nameObserver = NotificationCenter.default.addObserver(
      forName: .authNameDidUpdate, object: nil, queue: .main
    ) { [weak self] _ in
      MainActor.assumeIsolated { self?.adoptAsyncName() }
    }
    scenarioCardActionObserver = NotificationCenter.default.addObserver(
      forName: .omiFloatingBarCardAction, object: nil, queue: .main
    ) { [weak self] notification in
      guard let action = notification.userInfo?["action"] as? String else { return }
      MainActor.assumeIsolated { self?.handleScenarioCardAction(action) }
    }
  }

  deinit {
    if let nameObserver { NotificationCenter.default.removeObserver(nameObserver) }
    if let scenarioCardActionObserver { NotificationCenter.default.removeObserver(scenarioCardActionObserver) }
  }

  /// Adopt a name that landed after init — but only fill an empty field, never
  /// overwrite what the user has typed.
  private func adoptAsyncName() {
    let resolved = AuthService.shared.givenName.trimmingCharacters(in: .whitespaces)
    guard !resolved.isEmpty, nameDraft.trimmingCharacters(in: .whitespaces).isEmpty else { return }
    nameDraft = resolved
  }

  // MARK: copy

  func message(for step: Step) -> String {
    let name = displayName
    switch step {
    case .hello:
      return
        "Hi, I'm Omi. I sit at the top of your screen and pay attention to what you're doing, "
        + "so I can help before you ask. Rather than explain it, let's do one real thing together. "
        + "About four minutes. What should I call you?"
    case .see:
      return
        "First, what I notice. I'll show you a demo order page in your browser. "
        + "To see it the way you do, I need Screen Recording."
    case .card:
      return
        "That's a card, up at the notch. When I spot something on screen worth a heads-up, I show one there "
        + "and then get out of the way. Answer it, and I'll bring you back here."
    case .talk:
      return "Now ask me about that order, out loud. I need the microphone."
    case .write:
      return
        "Last one. Tell a friend about it. I've drafted a note to Sam in a demo mailbox: "
        + "say whatever you'd actually say, then press Send. Nothing leaves your Mac, and I'll bring you back."
    case .ready:
      return
        "That's the whole idea: I watch, I speak up, I remember. Now let's do it with your real work. "
        + "I'll guide you from the notch, five short steps. One question first: when should I listen, \(name)?"
    }
  }

  /// What the current step's widget is showing, reduced to the things that change its **height**.
  ///
  /// The card is a fixed 540 × 640 with a bottom-anchored column, so a widget that grows *in place*
  /// — without appending to the thread — is clipped by the card's lower edge unless something
  /// scrolls. That is exactly how the Files step shipped with its Continue unreachable: the scan
  /// finishing swapped a two-line "scanning…" widget for a four-element "your profile is ready"
  /// one, no `thread`/`showWidget`/`streamingText` change fired, and the button rendered below the
  /// fold with nothing to tell the user it was there. `showAIAssistants` already had a bespoke
  /// `onChange` for the same reason; this is that rule for every widget instead of one.
  var widgetShape: SBOnboardingWidgetShape {
    SBOnboardingWidgetShape(
      step: step,
      localFileProfile: localFileProfileState,
      permission: permissionKey(for: step).map { permissionPrimaryAction($0) },
      screenDemoReady: screenDemoPTTReady,
      screenDemoUnavailable: screenDemoPTTUnavailable,
      screenDemoDone: screenDemoDone,
      shortcutRegistrationError: shortcutRegistrationError,
      seePhase: seePhase,
      writePhase: writePhase,
      writeDetectionTimedOut: scenarioWriteDetectionTimedOut
    )
  }

  var displayName: String {
    let n = nameDraft.trimmingCharacters(in: .whitespaces)
    let stored = AuthService.shared.givenName.trimmingCharacters(in: .whitespaces)
    if !n.isEmpty { return n.components(separatedBy: " ").first ?? n }
    if !stored.isEmpty { return stored }
    return "friend"
  }

  var selectedResponseLanguageName: String {
    let code = AssistantSettings.shared.voiceLanguages.first ?? "en"
    let baseCode = AssistantSettings.baseLanguageCode(code)
    return AssistantSettings.supportedLanguages.first {
      AssistantSettings.baseLanguageCode($0.code) == baseCode
    }?.name ?? code
  }

  /// The chosen open-Omi chord as individual tokens, rendered as keycap chips in
  /// `captureWidget` (e.g. ⌘ + O) rather than plain glyphs in the message copy.
  var summonTokens: [String] { ShortcutSettings.shared.askOmiShortcut.displayTokens }

  // MARK: lifecycle

  /// Persisted so quitting mid-onboarding (e.g. stepping away to grant a permission
  /// in System Settings) resumes where you left off instead of restarting.
  static let resumeStepKey = "sbOnboardingResumeStep"

  /// Persisted when the talk chord is completed.
  static let shortcutsCompletedKey = "sbOnboardingShortcutsCompleted"
  nonisolated static let seePhaseKey = "sbOnboardingSeePhase"
  nonisolated static let cardPhaseKey = "sbOnboardingCardPhase"
  nonisolated static let talkPhaseKey = "sbOnboardingTalkPhase"
  nonisolated static let writePhaseKey = "sbOnboardingWritePhase"
  nonisolated static let writeReceiptsKey = "sbOnboardingWriteReceipts"

  /// Layout version of the persisted `resumeStepKey` value.
  ///
  /// `Step`'s raw values are written to disk, so inserting a case renumbers
  /// every later step and silently reinterprets any resume state written by an
  /// older build. Version 3 replaces the prior nineteen-stage layout wholesale
  /// with six scenario beats, so older values deliberately restart at `hello`.
  static let resumeStepSchemaKey = "sbOnboardingResumeStepSchema"
  static let resumeStepSchemaVersion = 3

  /// Translate a persisted resume step into the current layout.
  ///
  /// Pure so the schema-3 restart rule is testable without `UserDefaults`.
  static func migratedResumeStepRaw(savedRaw: Int, storedSchema: Int) -> Int {
    guard storedSchema >= resumeStepSchemaVersion else { return Step.hello.rawValue }
    return savedRaw
  }

  func begin() {
    guard thread.isEmpty && streamingText == nil else { return }
    // Re-hydrate the editable drafts from what was already saved, so stepping
    // back to (or resuming at) name/language/role shows the prior answer instead
    // of an empty field.
    rehydrateDrafts()
    restoreScenarioProgress()
    // Resume where the user left off. Their earlier answers (name, language, role)
    // were already saved to the backend/settings, so we just re-enter at the saved
    // step; each permission step re-checks its grant on appear, so a permission
    // granted before the quit shows ✓ rather than prompting again.
    // Restart a resume state written for the retired nineteen-stage layout, and
    // stamp the new layout before anything consumes its raw enum value.
    let persistedRaw = UserDefaults.standard.integer(forKey: Self.resumeStepKey)
    let storedSchema = UserDefaults.standard.integer(forKey: Self.resumeStepSchemaKey)
    let savedRaw = Self.migratedResumeStepRaw(savedRaw: persistedRaw, storedSchema: storedSchema)
    if storedSchema < Self.resumeStepSchemaVersion {
      // Stamp the schema BEFORE rewriting the value. Two `UserDefaults` writes
      // are not one atomic transaction, and the two orderings fail differently
      // if the process dies between them:
      //
      //   value first — the stamp can be lost and the already-migrated value can
      //     be interpreted again on the next launch.
      //   stamp first — the old value can survive, but it is always validated
      //     against the new enum before use.
      //
      // Neither is atomic; only one of them can throw away progress.
      UserDefaults.standard.set(Self.resumeStepSchemaVersion, forKey: Self.resumeStepSchemaKey)
      if savedRaw != persistedRaw {
        UserDefaults.standard.set(savedRaw, forKey: Self.resumeStepKey)
      }
    }
    recordSetupStateDisagreementAtRead(savedRaw: savedRaw)
    if savedRaw > Step.hello.rawValue, let resumed = Step(rawValue: savedRaw) {
      let target = firstUnaskedStep(from: resumed)
      if target == .talk,
        UserDefaults.standard.bool(forKey: Self.shortcutsCompletedKey)
      {
        talkPhase = .demo
      }
      step = target
      streamMessage(for: target)
      return
    }
    guard
      SBOnboardingIntroGate.shouldPlay(resumeStepRaw: savedRaw, promiseStepRaw: Step.hello.rawValue)
    else {
      startAmbientOnboardingMusic()
      streamMessage(for: .hello)
      return
    }
    // Marked before playing: a quit or crash mid-intro still counts as seen, so the
    // intro can never re-arm itself into a loop.
    SBOnboardingIntroGate.markPlayed()
    OmiOnboardingCinematic.present { [weak self] _ in
      guard let self else { return }
      // The bed carries over from the intro into the chat onboarding, so the music
      // does not stop and restart across the hand-off.
      self.startAmbientOnboardingMusic()
      self.streamMessage(for: .hello)
    }
  }

  func persistScenarioProgress() {
    let defaults = UserDefaults.standard
    defaults.set(seePhase.rawValue, forKey: Self.seePhaseKey)
    defaults.set(cardPhase.rawValue, forKey: Self.cardPhaseKey)
    defaults.set(talkPhase.rawValue, forKey: Self.talkPhaseKey)
    defaults.set(writePhase.rawValue, forKey: Self.writePhaseKey)
    defaults.set(Array(scenarioWriteReceipts).sorted(), forKey: Self.writeReceiptsKey)
  }

  private func restoreScenarioProgress() {
    let defaults = UserDefaults.standard
    if let raw = defaults.string(forKey: Self.seePhaseKey), let value = SeePhase(rawValue: raw) { seePhase = value }
    if let raw = defaults.string(forKey: Self.cardPhaseKey), let value = CardPhase(rawValue: raw) { cardPhase = value }
    if let raw = defaults.string(forKey: Self.talkPhaseKey), let value = TalkPhase(rawValue: raw) { talkPhase = value }
    if let raw = defaults.string(forKey: Self.writePhaseKey), let value = WritePhase(rawValue: raw) {
      writePhase = value
    }
    scenarioWriteReceipts = Set(defaults.stringArray(forKey: Self.writeReceiptsKey) ?? [])
  }

  /// The ambient bed under the chat-style onboarding. Honours the user's persisted
  /// mute, so a muted intro stays muted here.
  private func startAmbientOnboardingMusic() {
    OmiOnboardingCinematic.startAmbientMusic()
  }

  /// Detection only: the existing completion flag remains the UI gate. These
  /// bounded signals reveal when that gate says setup is complete while the SB
  /// stage, persisted resume state, or setup journal still says it is active.
  private func recordSetupStateDisagreementAtRead(savedRaw: Int) {
    guard appState.hasCompletedOnboarding else { return }
    DesktopDiagnosticsManager.shared.recordStateAuthoritySignal(
      seam: .onboardingSetupState,
      from: "completed_flag",
      to: "sb_stage",
      direction: "completed_flag_with_active_stage")
    if savedRaw > Step.hello.rawValue, Step(rawValue: savedRaw) != nil {
      DesktopDiagnosticsManager.shared.recordStateAuthoritySignal(
        seam: .onboardingSetupState,
        from: "completed_flag",
        to: "persisted_resume",
        direction: "completed_flag_with_resume_state")
    }
    if chatProvider.isOnboarding {
      DesktopDiagnosticsManager.shared.recordStateAuthoritySignal(
        seam: .onboardingSetupState,
        from: "completed_flag",
        to: "setup_journal",
        direction: "completed_flag_with_active_journal")
    }
  }

  func streamMessage(for step: Step) {
    streamTask?.cancel()
    showWidget = false
    typing = true
    let full = message(for: step)
    streamTask = Task { [weak self] in
      try? await Task.sleep(nanoseconds: 700_000_000)
      guard let self, !Task.isCancelled else { return }
      self.typing = false
      self.streamingText = "▍"
      let words = full.split(separator: " ").map(String.init)
      var i = 0
      while i < words.count {
        i += 1 + Int.random(in: 0...1)
        let shown = words.prefix(min(i, words.count)).joined(separator: " ")
        if i < words.count {
          self.streamingText = shown + " ▍"
        } else {
          self.streamingText = full
        }
        if Task.isCancelled { return }
        try? await Task.sleep(nanoseconds: UInt64((55 + Int.random(in: 0...95)) * 1_000_000))
      }
      guard !Task.isCancelled else { return }
      self.thread.append(Msg(isOmi: true, text: full))
      OnboardingScenarioJournal().append(who: "omi", text: full)
      self.streamingText = nil
      self.showWidget = true
      self.onStepShown(step)
    }
  }

  /// Hook fired right after a step's message finishes streaming and its widget
  /// appears — used to kick off per-step live work (screen capture, demo setup).
  private func onStepShown(_ step: Step) {
    switch step {
    case .see:
      switch seePhase {
      case .permission: precheckPerm("screen_recording")
      case .openPage: break
      // A relaunch mid-hand-off: the page may still be open, so watch for it without opening a
      // second copy over the user.
      case .waitingForPage: startOrderPageDetection()
      }
    case .card:
      if cardPhase == .notifications { precheckPerm("notifications") } else { presentScenarioCard() }
    case .talk:
      switch talkPhase {
      case .microphone: precheckPerm("microphone")
      case .shortcut: armShortcutSummon()
      case .demo: startScreenDemo()
      }
    case .write:
      // Never opened from here: the browser appears on the user's click, not on a streamed sentence.
      // After a relaunch mid-hand-off, only the watch for Send resumes.
      if writePhase == .waitingForSend { startComposeDetection() }
    case .hello, .ready: break
    }
  }

  func advance(
    userAnswer: String?,
    to next: Step,
    skipped: Bool = false,
    permission: String? = nil,
    granted: Bool? = nil,
    detection: String? = nil
  ) {
    if let userAnswer, !userAnswer.isEmpty {
      thread.append(Msg(isOmi: false, text: userAnswer))
      OnboardingScenarioJournal().append(who: "user", text: userAnswer)
    }
    recordBeatExit(
      skipped: skipped,
      permission: permission,
      granted: granted,
      detection: detection)
    teardownStep(step)
    // Don't ask for a permission the user has already granted — skip straight to
    // the first step that still needs an answer.
    let target = firstUnaskedStep(from: next)
    step = target
    beatStartedAt = Date()
    beatExitRecorded = false
    UserDefaults.standard.set(target.rawValue, forKey: Self.resumeStepKey)
    streamMessage(for: target)
  }

  /// Return to the immediately preceding onboarding stage without discarding
  /// any answer the user already supplied. The conversational transcript stays
  /// intact; the re-rendered widget is the editable source of truth for that
  /// stage, so a user can revise (for example) Student to Founder.
  func goBack() {
    guard let previous = Step(rawValue: step.rawValue - 1) else { return }
    teardownStep(step)
    cancelPermissionPollForCurrentStep()
    rehydrateDrafts()
    step = previous
    beatStartedAt = Date()
    beatExitRecorded = false
    UserDefaults.standard.set(previous.rawValue, forKey: Self.resumeStepKey)
    streamMessage(for: previous)
  }

  var canGoBack: Bool { step != .hello }

  var canSkipOnboarding: Bool {
    Self.canSkipOnboarding(
      step: step,
      shortcutsCompleted: UserDefaults.standard.bool(forKey: Self.shortcutsCompletedKey))
  }

  static func canSkipOnboarding(step: Step, shortcutsCompleted: Bool) -> Bool {
    step.rawValue > Step.talk.rawValue && shortcutsCompleted
  }

  /// Tear down any live monitors/tasks a step installed before leaving it.
  private func teardownStep(_ step: Step) {
    scenarioDetectionTask?.cancel()
    scenarioDetectionTask = nil
    scenarioCardTimeoutTask?.cancel()
    scenarioCardTimeoutTask = nil
    switch step {
    case .card:
      scenarioCardPresented = false
    case .talk:
      disarmShortcutSummon()
      teardownVoiceDemo()
    case .hello, .see, .write, .ready: break
    }
  }

  /// A permission poll is scoped to the page that requested it. If Back leaves
  /// that page while macOS is still open, stop the stale poll so a late grant
  /// cannot overwrite the newly displayed page's state. The system grant itself
  /// is still observed if the user returns to this page.
  private func cancelPermissionPollForCurrentStep() {
    guard let key = permissionKey(for: step) else { return }
    pollTasks[key]?.cancel()
    pollTasks[key] = nil
    if permState(key) == .waiting {
      resetPermToAsk(key)
    }
  }

  /// Re-fill the editable drafts from already-saved answers so revisiting (via
  /// Back) or resuming a name/role step shows the prior value, not an empty
  /// field. Only fills empties — never clobbers in-progress typing.
  private func rehydrateDrafts() {
    if nameDraft.isEmpty {
      let n = AuthService.shared.givenName.trimmingCharacters(in: .whitespaces)
      if !n.isEmpty { nameDraft = n }
    }
    if role == nil {
      let saved = UserDefaults.standard.string(forKey: .onboardingRole) ?? ""
      if !saved.isEmpty {
        role = saved
        if roleDraft.isEmpty { roleDraft = saved }
      }
    }
  }

  // MARK: scenario answers

  func answerName() {
    let trimmed = nameDraft.trimmingCharacters(in: .whitespaces)
    guard !trimmed.isEmpty else { return }
    answerWriteGate.enqueue(.name) { [trimmed] in
      await AuthService.shared.updateGivenName(trimmed)
      OnboardingScenarioJournal().append(who: "system", text: "Updated the user's given name")
    }
    advance(userAnswer: trimmed, to: .see)
  }

  // MARK: capture choice → completes onboarding

  func capture(_ selection: CaptureSelection) {
    AssistantSettings.shared.audioRecordingMode = selection.audioRecordingMode
    let answer = selection == .always ? "Always" : "Only in meetings"
    thread.append(Msg(isOmi: false, text: answer))
    OnboardingScenarioJournal().append(who: "user", text: answer)
    OnboardingScenarioJournal().append(who: "system", text: "Updated the capture preference")
    recordBeatExit(skipped: false)
    complete()
  }

  /// The one handoff both exit paths run when onboarding ends.
  ///
  /// `skip()` and `complete()` used to carry byte-identical
  /// copies of this sequence, which is how the post-onboarding guidance came to
  /// be produced by neither: there was no single place that owned "onboarding is
  /// over, hand the user to the app". There is now, so a step added here can
  /// never reach one door and not the other.
  ///
  /// `clearOnboardingChatFlag` is the only real difference between the two
  /// paths, and it is ordered exactly where each path had it.
  func finishOnboardingHandoff(clearOnboardingChatFlag: Bool, skipped: Bool = false) {
    teardownAll()
    // Fades rather than cuts: onboarding's last beat should not end on a click.
    OmiOnboardingCinematic.stopAmbientMusic()
    AnalyticsManager.shared.onboardingCompleted()
    chatProvider.stopAgent(owner: .mainChat)
    UserDefaults.standard.set(true, forKey: DefaultsKey.onboardingJustCompleted)
    UserDefaults.standard.removeObject(forKey: Self.resumeStepKey)
    UserDefaults.standard.removeObject(forKey: OnboardingScenarioDefaults.pageAOpenedKey)
    if clearOnboardingChatFlag { chatProvider.isOnboarding = false }
    // Answer "what do I do now" before anything renders it. Must precede
    // `presentOnboardingOpener()`, which reads these saved suggestions to build
    // the Chat tab's starter chips.
    savePostOnboardingGuidance()
    // Greet the user in the Home chat with the personalized opener + starters.
    chatProvider.presentOnboardingOpener()
    ChatToolExecutor.onboardingAppState = nil
    OnboardingChatPersistence.clear()
    ChatDraftStore.shared.clear(.onboardingMain)
    ChatDraftStore.shared.clear(.onboardingFloating)
    // **Mark onboarding done before anything can await, and before the last window can close.**
    //
    // `applicationShouldTerminateAfterLastWindowClosed` returns true while this flag is false --
    // deliberately, so a half-finished onboarding does not leave a menu-bar process behind. That
    // makes the flag load-bearing for process lifetime, not just for which view renders. Setting
    // it after `await finishOnboardingJournal()` left a window in which the onboarding window had
    // already gone away and the flag was still false, and the app quit on the user at the exact
    // moment they finished. It then reran onboarding on next launch, because the flag never got
    // written -- observed twice in a row on a bundle whose onboarding was not pre-seeded.
    //
    // The `[weak self]` made it worse rather than safer: `teardownAll()` runs at the top of this
    // function, so a deallocated model meant `guard let self else { return }` skipped the write
    // entirely and onboarding could never complete at all.
    //
    // The journal is genuinely async and genuinely optional. Completion is neither.
    OnboardingFlow.markCompleted(for: RuntimeOwnerIdentity.currentOwnerId())
    appState.hasCompletedOnboarding = true
    UserDefaults.standard.set(true, forKey: OnboardingScenarioDefaults.firstRunPendingKey)
    OnboardingScenarioJournal().append(who: "system", text: "Completed scenario onboarding handoff")
    NotificationCenter.default.post(
      name: .omiOnboardingScenarioCompleted,
      object: nil,
      userInfo: ["skipped": skipped]
    )
    onComplete?()
    Task { [chatProvider] in
      await chatProvider.finishOnboardingJournal()
    }
  }

  /// Skip the rest of onboarding: mark it complete and drop straight to the Chat
  /// tab (with the personalized opener), without force-enabling capture or screen
  /// analysis the user chose to bypass. They can turn those on later.
  func skip() {
    recordBeatExit(skipped: true)
    OnboardingScenarioJournal().append(who: "user", text: "Skip onboarding")
    finishOnboardingHandoff(clearOnboardingChatFlag: false, skipped: true)
  }

  /// Replicates the essential real side-effects of the legacy handleOnboardingComplete().
  private func complete() {
    // Do NOT mark file indexing complete here. Onboarding never actually scans, so
    // setting this flag "faked" the Files connector as connected while indexing
    // nothing — and, worse, permanently suppressed the Home view's automatic
    // first-run backfill (`scheduleInitialFileIndexing`, gated on this flag being
    // false) and every later rescan. Leaving it false lets that existing silent
    // backfill actually index the standard folders once the app is up, so the
    // Files connector becomes truly connected with real content.
    finishOnboardingHandoff(clearOnboardingChatFlag: true, skipped: false)

    Task {
      await AgentVMService.shared.startPipeline()
      await GoalGenerationService.shared.generateNow()
    }
    applyLaunchAtLoginSelection()

    if AppBuild.usesLazyDevPermissions {
      AssistantSettings.shared.screenAnalysisEnabled = false
    } else {
      AssistantSettings.shared.screenAnalysisEnabled = true
      if !ProactiveAssistantsPlugin.shared.isMonitoring {
        ProactiveAssistantsPlugin.shared.startMonitoring { _, _ in }
      }
    }
    Task { [appState] in
      appState.startTranscription()
      await appState.reconcileCapture()
    }
    // NOTE: previously this created a "Run omi for two days…" welcome task. That
    // seeded onboarding scaffolding into the user's real Tasks surface (there is no
    // hidden/system-task concept to hang it on), so it's been removed — onboarding
    // must not leave artifacts in product data.
  }

  /// Apply the user's launch-at-login selection at completion — **preserve** their
  /// choice (`launchAtLogin`) rather than force-enabling it, and report the actual
  /// value to analytics. Previously this unconditionally called `setEnabled(true)`,
  /// which overrode a user who declined auto-start. The `setEnabled`/`report` seams
  /// keep this hermetic in tests (no real login-item registration side effects).
  func applyLaunchAtLoginSelection(
    setEnabled: (Bool) -> Bool = { LaunchAtLoginManager.shared.setEnabled($0) },
    report: (Bool) -> Void = {
      AnalyticsManager.shared.launchAtLoginChanged(enabled: $0, source: "sb_onboarding_complete")
    }
  ) {
    let enabled = launchAtLogin
    if setEnabled(enabled) {
      report(enabled)
    }
  }

  /// Cancel every live task/monitor this model owns. Safe to call repeatedly.
  private func teardownAll() {
    streamTask?.cancel()
    scenarioDetectionTask?.cancel()
    scenarioDetectionTask = nil
    scenarioCardTimeoutTask?.cancel()
    scenarioCardTimeoutTask = nil
    for pollTask in pollTasks.values {
      pollTask.cancel()
    }
    pollTasks.removeAll()
    disarmShortcutSummon()
    teardownVoiceDemo()
  }
}
