import AppKit
import Combine
import Foundation

enum SBOnboardingLanguageCopy {
  static let question = "What language should Omi listen and reply in?"
}

/// Drives the Second Brain conversational onboarding: a real chat with Omi that
/// streams word-by-word, collects answers, and performs the SAME live side-effects
/// as the legacy wizard (name/language → backend, every permission, the summon
/// shortcut, a live screen+voice demo, agent + context connectors, capture,
/// completion). No fake steps — every widget does real work.
///
/// Core state + lifecycle + copy live here. The heavier per-step behavior
/// (permissions, shortcut, screen/voice demo, connectors) lives in
/// `SBOnboardingModel+Steps.swift`.
@MainActor
final class SBOnboardingModel: ObservableObject {
  enum CaptureSelection: Equatable {
    case onlyDuringMeetings
    case continuous

    var systemAudioCaptureMode: AssistantSettings.SystemAudioCaptureMode {
      switch self {
      case .onlyDuringMeetings: .onlyDuringMeetings
      case .continuous: .always
      }
    }

    var startsListeningImmediately: Bool {
      self == .continuous
    }
  }

  static let defaultCaptureSelection: CaptureSelection = .onlyDuringMeetings

  enum Step: Int, CaseIterable {
    case promise, name, howHeard, language, role
    case mic, systemAudio, screen, files, accessibility, automation
    case shortcutOpen, shortcutTalk, screenDemo, agents, context, capture
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

  struct AgentTogglePresentation: Equatable {
    let isOn: Bool
    let isDisabled: Bool
    let detail: String
  }

  typealias FileScanRunner = @MainActor (AppState) async -> LocalFileProfileState
  typealias StreamSleeper = @MainActor (UInt64) async -> Void

  @Published var step: Step = .promise
  @Published var thread: [Msg] = []
  /// The current Omi message streaming in (nil once committed).
  @Published var streamingText: String?
  @Published var typing = false
  @Published var showWidget = false

  // Per-step answers / state
  @Published var nameDraft = ""
  @Published var languageDraft = ""
  @Published var howHeard: String?
  @Published var roleDraft = ""
  @Published var role: String?

  // Permissions
  @Published var micState: PermState = .ask
  @Published var sysState: PermState = .ask
  @Published var scrState: PermState = .ask  // screen recording
  @Published var fdaState: PermState = .ask  // full disk access (files)
  @Published var accState: PermState = .ask  // accessibility
  @Published var autoState: PermState = .ask  // automation / Apple Events
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
  /// The chosen shortcut + which mechanism it uses (key hotkey vs modifier-hold).
  var chosenShortcut: ShortcutSettings.KeyboardShortcut?
  var chosenShortcutIsPTT = false
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

  // Connectors — keyed by a stable id ("openclaw", "calendar", …) → state string
  // ("idle" | "connecting" | "on" | "unavailable" | "needsSignIn").
  @Published var agentStates: [String: String] = [:]
  @Published var contextStates: [String: String] = [:]
  /// Actionable connector detail replaces the generic row subtitle after a
  /// failed functional probe. Values use bounded product copy; raw cookie,
  /// response, and exception data never reaches this projection.
  @Published var contextDetails: [String: String] = [:]

  unowned let appState: AppState
  let chatProvider: ChatProvider
  /// The same persisted connector authority the post-onboarding Home and Apps
  /// surfaces read. A context row is not connected until this store records a
  /// completed import, never merely because a browser session passed a probe.
  let importConnectorStatusStore: ImportConnectorStatusStore?
  /// Backend writes for editable answers are per-field serialized. Revisiting a
  /// question never lets an earlier request finish after the user's revision.
  private let answerWriteGate = OnboardingAnswerWriteGate()
  let fileScanRunner: FileScanRunner
  let streamSleeper: StreamSleeper
  private let onComplete: (() -> Void)?
  var streamTask: Task<Void, Never>?
  var streamGeneration = 0
  var displayedSteps: [Step] = []
  var localFileScanTask: Task<Void, Never>?
  var localFileScanID: UUID?
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

  init(
    appState: AppState,
    chatProvider: ChatProvider,
    importConnectorStatusStore: ImportConnectorStatusStore? = nil,
    fileScanRunner: @escaping FileScanRunner = { appState in
      ChatToolExecutor.onboardingAppState = appState
      guard let authorization = RuntimeOwnerIdentity.captureAuthorizationSnapshot() else {
        return .failed(message: "Please sign in again before building your local profile.")
      }
      let outcome = await ChatToolExecutor.scanLocalFiles(
        expectedOwnerID: authorization.ownerID,
        authorizationSnapshot: authorization)
      guard !Task.isCancelled, RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else {
        return .failed(message: "Your account changed before Omi could save your local profile.")
      }
      guard outcome.didCompleteSuccessfully, outcome.hasReadableUserFileTarget else {
        return .failed(message: ConnectorImportOperations.localFilesFailureLine(for: outcome))
      }

      // Preserve the legacy post-scan owner: it derives the indexed-file
      // snapshot, writes aggregate local-file profile evidence, and updates the
      // knowledge graph. The conversational flow merely presents its outcome.
      let coordinator = OnboardingPagedIntroCoordinator()
      await coordinator.refreshSnapshotIfAvailable(
        expectedOwnerID: authorization.ownerID,
        authorizationSnapshot: authorization)
      guard !Task.isCancelled, RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else {
        return .failed(message: "Your account changed before Omi could save your local profile.")
      }
      let fileCount = coordinator.scanSnapshot?.fileCount ?? outcome.indexedFileCount
      if fileCount > 0, coordinator.localFileMemoriesSaved == 0 {
        return .failed(message: "Your files were indexed, but Omi couldn't save your profile memories. Try again.")
      }
      return .complete(
        fileCount: fileCount,
        memoryCount: coordinator.localFileMemoriesSaved,
        deniedFolders: outcome.deniedUserFolders)
    },
    streamSleeper: @escaping StreamSleeper = { nanoseconds in
      try? await Task.sleep(nanoseconds: nanoseconds)
    },
    onComplete: (() -> Void)?
  ) {
    self.appState = appState
    self.chatProvider = chatProvider
    self.importConnectorStatusStore = importConnectorStatusStore
    self.fileScanRunner = fileScanRunner
    self.streamSleeper = streamSleeper
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
  }

  deinit {
    if let nameObserver { NotificationCenter.default.removeObserver(nameObserver) }
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
    case .promise:
      return
        "Hey, I'm Omi, your second brain. I hear your conversations, remember everything, and handle the follow-ups. Three quick things:"
    case .name: return "What should I call you?"
    case .howHeard: return "Quick one. How did you hear about Omi?"
    case .language:
      return SBOnboardingLanguageCopy.question
    case .role:
      return
        "Nice to meet you, \(name). What do your days look like? Pick the closest, or tell me. It shapes what I make for you."
    case .mic:
      return "Let's give me senses. First, your microphone, so I hear your side of a conversation."
    case .systemAudio:
      return "Now system audio, so I hear the other side too: Zoom, Meet, calls."
    case .screen:
      return "Let me see your screen, so I can help with whatever you're looking at."
    case .files:
      return
        "Let me read your files, so I can point to your real documents. Read-only, it stays on this Mac, and you can turn it off anytime."
    case .accessibility:
      return "Turn on Accessibility, so I can use your shortcut and click and type for you."
    case .automation:
      return "Turn on Automation, so I can help with tasks in the apps you choose."
    case .shortcutOpen:
      return "How do you want to open me? Just press one of these to set it."
    case .shortcutTalk:
      return "And to talk to me, hands-free? Just hold one of these and say something."
    case .screenDemo:
      return "Here's the fun part."
    case .agents:
      return "Which AI assistants do you use? Turn on each installed assistant you want me to work with."
    case .context:
      return "The more I can see, the more I can help. Connect anything you want me to know:"
    case .capture:
      return
        "You're all set, \(name). One last thing: should I listen all the time, or only during your meetings?"
    }
  }

  var displayName: String {
    let n = nameDraft.trimmingCharacters(in: .whitespaces)
    let stored = AuthService.shared.givenName.trimmingCharacters(in: .whitespaces)
    if !n.isEmpty { return n.components(separatedBy: " ").first ?? n }
    if !stored.isEmpty { return stored }
    return "friend"
  }

  // MARK: lifecycle

  /// Persisted so quitting mid-onboarding (e.g. stepping away to grant a permission
  /// in System Settings) resumes where you left off instead of restarting.
  static let resumeStepKey = "sbOnboardingResumeStep"

  func begin() {
    guard thread.isEmpty && streamingText == nil else { return }
    // Re-hydrate the editable drafts from what was already saved, so stepping
    // back to (or resuming at) name/language/role shows the prior answer instead
    // of an empty field.
    rehydrateDrafts()
    // Resume where the user left off. Their earlier answers (name, language, role)
    // were already saved to the backend/settings, so we just re-enter at the saved
    // step; each permission step re-checks its grant on appear, so a permission
    // granted before the quit shows ✓ rather than prompting again.
    let savedRaw = UserDefaults.standard.integer(forKey: Self.resumeStepKey)
    recordSetupStateDisagreementAtRead(savedRaw: savedRaw)
    if savedRaw > Step.promise.rawValue, let resumed = Step(rawValue: savedRaw) {
      // Skip a resumed permission step the user granted while away.
      let target = firstUnaskedStep(from: resumed)
      step = target
      streamMessage(for: target)
      return
    }
    streamMessage(for: .promise)
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
    if savedRaw > Step.promise.rawValue, Step(rawValue: savedRaw) != nil {
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
    streamGeneration &+= 1
    let generation = streamGeneration
    if displayedSteps.last != step {
      displayedSteps.append(step)
    }
    showWidget = false
    typing = true
    let full = message(for: step)
    streamTask = Task { [weak self] in
      guard let self else { return }
      await self.streamSleeper(700_000_000)
      guard !Task.isCancelled, self.streamGeneration == generation else { return }
      self.typing = false
      self.streamingText = "▍"
      let words = full.split(separator: " ").map(String.init)
      var i = 0
      while i < words.count {
        guard !Task.isCancelled, self.streamGeneration == generation else { return }
        i += 1 + Int.random(in: 0...1)
        let shown = words.prefix(min(i, words.count)).joined(separator: " ")
        if i < words.count {
          self.streamingText = shown + " ▍"
        } else {
          self.streamingText = full
        }
        await self.streamSleeper(UInt64((55 + Int.random(in: 0...95)) * 1_000_000))
      }
      guard !Task.isCancelled, self.streamGeneration == generation else { return }
      self.thread.append(Msg(isOmi: true, text: full))
      self.streamingText = nil
      self.showWidget = true
      self.onStepShown(step)
    }
  }

  /// Hook fired right after a step's message finishes streaming and its widget
  /// appears — used to kick off per-step live work (screen capture, demo setup).
  private func onStepShown(_ step: Step) {
    switch step {
    case .mic: precheckPerm("microphone")
    case .systemAudio: precheckPerm("system_audio")
    case .screen: precheckPerm("screen_recording")
    case .files: precheckPerm("full_disk_access")
    case .accessibility: precheckPerm("accessibility")
    case .automation: precheckPerm("automation")
    case .shortcutOpen, .shortcutTalk: armShortcutSummon()
    case .screenDemo: startScreenDemo()
    case .agents: refreshAgentStates()
    case .context: refreshContextStates()
    default: break
    }
  }

  func advance(userAnswer: String?, to next: Step) {
    if let userAnswer, !userAnswer.isEmpty {
      thread.append(Msg(isOmi: false, text: userAnswer))
    }
    teardownStep(step)
    // Don't ask for a permission the user has already granted — skip straight to
    // the first step that still needs an answer.
    let target = firstUnaskedStep(from: next)
    step = target
    UserDefaults.standard.set(target.rawValue, forKey: Self.resumeStepKey)
    streamMessage(for: target)
  }

  func goBack() {
    guard let previous = previousStep(before: step) else { return }
    teardownStep(step)
    cancelPermissionPollForCurrentStep()
    streamGeneration &+= 1
    streamTask?.cancel()
    streamTask = nil
    typing = false
    streamingText = nil
    retractCurrentExchange()
    if displayedSteps.last == step {
      displayedSteps.removeLast()
    }
    step = previous
    if displayedSteps.last != previous {
      displayedSteps.append(previous)
    }
    UserDefaults.standard.set(previous.rawValue, forKey: Self.resumeStepKey)
    if thread.contains(where: { $0.isOmi && $0.text == message(for: previous) }) {
      showWidget = true
      onStepShown(previous)
    } else {
      streamMessage(for: previous)
    }
  }

  private func retractCurrentExchange() {
    if thread.last?.isOmi == false {
      thread.removeLast()
    }
    if thread.last?.isOmi == true, thread.last?.text == message(for: step) {
      thread.removeLast()
    }
    if thread.last?.isOmi == false {
      thread.removeLast()
    }
  }

  private func previousStep(before current: Step) -> Step? {
    if displayedSteps.last == current, let previous = displayedSteps.dropLast().last {
      return previous
    }
    var rawValue = current.rawValue - 1
    while let candidate = Step(rawValue: rawValue) {
      guard let key = permissionKey(for: candidate), isGranted(key) else { return candidate }
      rawValue -= 1
    }
    return nil
  }

  var canGoBack: Bool {
    step != .promise
  }

  /// Tear down any live monitors/tasks a step installed before leaving it.
  private func teardownStep(_ step: Step) {
    switch step {
    case .files:
      localFileScanTask?.cancel()
      if case .scanning = localFileProfileState {
        localFileProfileState = .idle
      }
    case .shortcutOpen, .shortcutTalk: disarmShortcutSummon()
    case .screenDemo: teardownVoiceDemo()
    default: break
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
  /// Back) or resuming a name/language/role step shows the prior value, not an
  /// empty field. Only fills empties — never clobbers in-progress typing.
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
    if howHeard == nil {
      let saved = UserDefaults.standard.string(forKey: DefaultsKey.onboardingHowDidYouHearSource)
      if let saved, !saved.isEmpty { howHeard = saved }
    }
    if languageDraft.isEmpty, AssistantSettings.shared.hasExplicitVoiceLanguages,
      let code = AssistantSettings.shared.voiceLanguages.first,
      let language = AssistantSettings.supportedLanguages.first(where: {
        $0.code == AssistantSettings.normalizeTranscriptionLanguageCode(code)
      })
    {
      languageDraft = language.name
    }
  }

  // MARK: promise / name / language / role

  func answerPromise() { advance(userAnswer: "Set me up", to: .name) }

  func answerName() {
    let trimmed = nameDraft.trimmingCharacters(in: .whitespaces)
    guard !trimmed.isEmpty else { return }
    answerWriteGate.enqueue(.name) { [trimmed] in
      await AuthService.shared.updateGivenName(trimmed)
    }
    advance(userAnswer: trimmed, to: .howHeard)
  }

  /// Record the acquisition source (analytics + backend, like the legacy step),
  /// then move on.
  func pickHowHeard(_ source: String) {
    howHeard = source
    UserDefaults.standard.set(source, forKey: DefaultsKey.onboardingHowDidYouHearSource)
    AnalyticsManager.shared.onboardingHowDidYouHear(source: source)
    answerWriteGate.enqueue(.acquisitionSource) { [source] in
      _ = try? await APIClient.shared.updateOnboardingAcquisitionSource(source)
    }
    advance(userAnswer: source, to: .language)
  }

  /// Set the user's spoken language locally + on the backend (mirrors the legacy
  /// confirmLanguages, single-primary). Advances optimistically.
  func pickLanguage(code: String, name: String) {
    languageDraft = name
    AssistantSettings.shared.voiceLanguages = [code]
    answerWriteGate.enqueue(.language) { [code] in
      _ = try? await APIClient.shared.updateUserLanguage(code)
    }
    advance(userAnswer: name, to: .role)
  }

  func answerLanguageText() {
    guard let language = Self.languageSelection(for: languageDraft) else { return }
    pickLanguage(code: language.code, name: language.name)
  }

  func pickRole(_ r: String) {
    role = r
    UserDefaults.standard.set(r, forKey: DefaultsKey.onboardingRole)
    advance(userAnswer: r, to: .mic)
  }

  func answerRoleText() {
    let t = roleDraft.trimmingCharacters(in: .whitespaces)
    guard !t.isEmpty else { return }
    pickRole(t)
  }

  // MARK: capture choice → completes onboarding

  func capture(_ selection: CaptureSelection) {
    AssistantSettings.shared.systemAudioCaptureMode = selection.systemAudioCaptureMode
    complete(startListening: selection.startsListeningImmediately)
  }

  /// Skip the rest of onboarding: mark it complete and drop straight to the Chat
  /// tab (with the personalized opener), without force-enabling capture or screen
  /// analysis the user chose to bypass. They can turn those on later.
  func skip() {
    teardownAll()
    AnalyticsManager.shared.onboardingCompleted()
    chatProvider.stopAgent(owner: .mainChat)
    UserDefaults.standard.set(true, forKey: DefaultsKey.onboardingJustCompleted)
    UserDefaults.standard.removeObject(forKey: Self.resumeStepKey)
    // Greet the user in the Home chat with the personalized opener + starters.
    chatProvider.presentOnboardingOpener()
    ChatToolExecutor.onboardingAppState = nil
    OnboardingChatPersistence.clear()
    ChatDraftStore.shared.clear(.onboardingMain)
    ChatDraftStore.shared.clear(.onboardingFloating)
    onComplete?()
    Task { [weak self] in
      guard let self else { return }
      await self.chatProvider.finishOnboardingJournal()
      self.appState.hasCompletedOnboarding = true
    }
  }

  /// Replicates the essential real side-effects of the legacy handleOnboardingComplete().
  private func complete(startListening: Bool) {
    teardownAll()
    AnalyticsManager.shared.onboardingCompleted()
    chatProvider.stopAgent(owner: .mainChat)
    UserDefaults.standard.set(true, forKey: DefaultsKey.onboardingJustCompleted)
    UserDefaults.standard.removeObject(forKey: Self.resumeStepKey)
    // Do NOT mark file indexing complete here. Onboarding never actually scans, so
    // setting this flag "faked" the Files connector as connected while indexing
    // nothing — and, worse, permanently suppressed the Home view's automatic
    // first-run backfill (`scheduleInitialFileIndexing`, gated on this flag being
    // false) and every later rescan. Leaving it false lets that existing silent
    // backfill actually index the standard folders once the app is up, so the
    // Files connector becomes truly connected with real content.
    chatProvider.isOnboarding = false
    // Greet the user in the Home chat with the personalized opener + starters.
    chatProvider.presentOnboardingOpener()
    ChatToolExecutor.onboardingAppState = nil
    OnboardingChatPersistence.clear()
    ChatDraftStore.shared.clear(.onboardingMain)
    ChatDraftStore.shared.clear(.onboardingFloating)

    onComplete?()
    Task { [weak self] in
      guard let self else { return }
      await self.chatProvider.finishOnboardingJournal()
      self.appState.hasCompletedOnboarding = true
    }

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
      if startListening { appState.startTranscription() }
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
    localFileScanTask?.cancel()
    localFileScanTask = nil
    localFileScanID = nil
    for pollTask in pollTasks.values {
      pollTask.cancel()
    }
    pollTasks.removeAll()
    disarmShortcutSummon()
    teardownVoiceDemo()
  }
}
