import AppKit
import Combine
import Foundation

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

  @Published var step: Step = .promise
  @Published var thread: [Msg] = []
  /// The current Omi message streaming in (nil once committed).
  @Published var streamingText: String?
  @Published var typing = false
  @Published var showWidget = false

  // Per-step answers / state
  @Published var nameDraft = ""
  @Published var languageDraft = ""
  @Published var languageName: String?
  @Published var roleDraft = ""
  @Published var role: String?

  // Permissions
  @Published var micState: PermState = .ask
  @Published var sysState: PermState = .ask
  @Published var scrState: PermState = .ask  // screen recording
  @Published var fdaState: PermState = .ask  // full disk access (files)
  @Published var accState: PermState = .ask  // accessibility
  @Published var autoState: PermState = .ask  // automation / Apple Events

  var launchAtLogin: Bool = LaunchAtLoginManager.shared.isEnabled

  // Summon shortcut
  @Published var shortcutTokens: [String] = []
  @Published var shortcutPicked = false
  @Published var shortcutPressed = false
  /// The chosen shortcut + which mechanism it uses (key hotkey vs modifier-hold).
  var chosenShortcut: ShortcutSettings.KeyboardShortcut?
  var chosenShortcutIsPTT = false
  var shortcutMonitors: [Any] = []
  /// Main menu stashed while the shortcut step's key monitor is armed (menu key
  /// equivalents like ⌘O would otherwise swallow the press before we see it).
  var savedMainMenu: NSMenu?

  // Screen + voice demo
  @Published var screenThings: [String] = []
  @Published var screenDemoLoading = false
  @Published var voiceHeard = false
  @Published var voiceAnswer: String?
  var voiceCancellable: AnyCancellable?
  var voiceTimeout: Task<Void, Never>?

  // Connectors — keyed by a stable id ("openclaw", "calendar", …) → state string
  // ("idle" | "connecting" | "on" | "unavailable" | "needsSignIn").
  @Published var agentStates: [String: String] = [:]
  @Published var contextStates: [String: String] = [:]

  unowned let appState: AppState
  let chatProvider: ChatProvider
  private let onComplete: (() -> Void)?
  var streamTask: Task<Void, Never>?
  /// Permission-grant pollers, one per permission key. Keyed so requesting a
  /// second permission (the meetings "both" mic+system-audio step) never cancels
  /// a still-running poll for the first and strands it on "macOS…".
  var pollTasks: [String: Task<Void, Never>] = [:]

  init(appState: AppState, chatProvider: ChatProvider, onComplete: (() -> Void)?) {
    self.appState = appState
    self.chatProvider = chatProvider
    self.onComplete = onComplete
    // Isolate any onboarding chat/voice turns to the throwaway `.onboarding()`
    // journal surface so they never pollute the real Chat tab. Cleared on
    // complete()/skip(), after which the Chat tab reloads the clean default surface.
    chatProvider.isOnboarding = true
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
      return "What language do you speak? I'll listen and reply in it."
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
      return "Let me read your files, so I can point to your real documents. Read-only."
    case .accessibility:
      return "Turn on Accessibility, so I can use your shortcut and click and type for you."
    case .automation:
      return "Turn on Automation, so I can control your other apps and get things done."
    case .shortcutOpen:
      return "How do you want to open me? Just press one of these to set it."
    case .shortcutTalk:
      return "And to talk to me, hands-free? Just hold one of these and say something."
    case .screenDemo:
      return "Here's the fun part."
    case .agents:
      return "Want me to do things for you? Connect an agent and I'll put it to work."
    case .context:
      return "The more I can see, the more I can help. Connect anything you want me to know:"
    case .capture:
      return
        "You're all set, \(name). \(summonHint) reaches me anytime. One last thing: should I listen all the time, or only during your meetings?"
    }
  }

  var displayName: String {
    let n = nameDraft.trimmingCharacters(in: .whitespaces)
    let stored = AuthService.shared.givenName.trimmingCharacters(in: .whitespaces)
    if !n.isEmpty { return n.components(separatedBy: " ").first ?? n }
    if !stored.isEmpty { return stored }
    return "friend"
  }

  /// Human hint for the chosen open-Omi shortcut, used in the capture copy.
  var summonHint: String {
    let tokens = ShortcutSettings.shared.askOmiShortcut.displayTokens
    return tokens.isEmpty ? "Your shortcut" : tokens.joined()
  }

  // MARK: lifecycle

  /// Persisted so quitting mid-onboarding (e.g. stepping away to grant a permission
  /// in System Settings) resumes where you left off instead of restarting.
  static let resumeStepKey = "sbOnboardingResumeStep"

  func begin() {
    guard thread.isEmpty && streamingText == nil else { return }
    // Resume where the user left off. Their earlier answers (name, language, role)
    // were already saved to the backend/settings, so we just re-enter at the saved
    // step; each permission step re-checks its grant on appear, so a permission
    // granted before the quit shows ✓ rather than prompting again.
    let savedRaw = UserDefaults.standard.integer(forKey: Self.resumeStepKey)
    if savedRaw > Step.promise.rawValue, let resumed = Step(rawValue: savedRaw) {
      step = resumed
      streamMessage(for: resumed)
      return
    }
    streamMessage(for: .promise)
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
      self.streamingText = nil
      self.showWidget = true
      self.onStepShown(step)
    }
  }

  /// Hook fired right after a step's message finishes streaming and its widget
  /// appears — used to kick off per-step live work (screen capture, demo setup).
  private func onStepShown(_ step: Step) {
    switch step {
    case .language: prefillDetectedLanguage()
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
    step = next
    UserDefaults.standard.set(next.rawValue, forKey: Self.resumeStepKey)
    streamMessage(for: next)
  }

  /// Tear down any live monitors/tasks a step installed before leaving it.
  private func teardownStep(_ step: Step) {
    switch step {
    case .shortcutOpen, .shortcutTalk: disarmShortcutSummon()
    case .screenDemo: teardownVoiceDemo()
    default: break
    }
  }

  // MARK: promise / name / language / role

  func answerPromise() { advance(userAnswer: "Set me up", to: .name) }

  func answerName() {
    let trimmed = nameDraft.trimmingCharacters(in: .whitespaces)
    guard !trimmed.isEmpty else { return }
    Task { await AuthService.shared.updateGivenName(trimmed) }
    advance(userAnswer: trimmed, to: .howHeard)
  }

  /// Record the acquisition source (analytics + backend, like the legacy step),
  /// then move on.
  func pickHowHeard(_ source: String) {
    UserDefaults.standard.set(source, forKey: DefaultsKey.onboardingHowDidYouHearSource)
    AnalyticsManager.shared.onboardingHowDidYouHear(source: source)
    Task { try? await APIClient.shared.updateOnboardingAcquisitionSource(source) }
    advance(userAnswer: source, to: .language)
  }

  /// Set the user's spoken language locally + on the backend (mirrors the legacy
  /// confirmLanguages, single-primary). Advances optimistically.
  func pickLanguage(code: String, name: String) {
    languageName = name
    AssistantSettings.shared.voiceLanguages = [code]
    Task { _ = try? await APIClient.shared.updateUserLanguage(code) }
    advance(userAnswer: name, to: .role)
  }

  /// Auto-detect the Mac's language and pre-fill it so the picker defaults to it
  /// (the user can still type to change). Only fills an empty field once.
  func prefillDetectedLanguage() {
    guard languageDraft.isEmpty, languageName == nil else { return }
    let raw = Locale.current.language.languageCode?.identifier ?? Locale.preferredLanguages.first ?? "en"
    let code = AssistantSettings.normalizeTranscriptionLanguageCode(raw)
    if let match = AssistantSettings.supportedLanguages.first(where: { $0.code == code }) {
      languageDraft = match.name
    }
  }

  func answerLanguageText() {
    let raw = languageDraft.trimmingCharacters(in: .whitespaces)
    guard !raw.isEmpty else { return }
    let code = AssistantSettings.normalizeTranscriptionLanguageCode(raw)
    let name = AssistantSettings.supportedLanguages.first { $0.code == code }?.name ?? raw
    pickLanguage(code: code, name: name)
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

  func captureContinuous() {
    AssistantSettings.shared.systemAudioCaptureMode = .always
    complete(startListening: true)
  }

  func captureMeetingsOnly() {
    AssistantSettings.shared.systemAudioCaptureMode = .onlyDuringMeetings
    complete(startListening: false)
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
    chatProvider.isOnboarding = false
    // Greet the user in the Home chat with the personalized opener + starters.
    chatProvider.presentOnboardingOpener()
    ChatToolExecutor.onboardingAppState = nil
    OnboardingChatPersistence.clear()
    ChatDraftStore.shared.clear(.onboardingMain)
    ChatDraftStore.shared.clear(.onboardingFloating)
    onComplete?()
    // Wipe the default main-chat journal so the Chat tab opens clean (any stray
    // demo turns lived on the .onboarding() surface; this clears the default
    // surface the tab actually loads) before we reveal it.
    Task { [weak self] in
      guard let self else { return }
      _ = await self.chatProvider.clearDefaultJournalForOnboardingReset()
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
    if !AppBuild.usesLazyDevPermissions {
      UserDefaults.standard.set(true, forKey: DefaultsKey.hasCompletedFileIndexing)
    }
    chatProvider.isOnboarding = false
    // Greet the user in the Home chat with the personalized opener + starters.
    chatProvider.presentOnboardingOpener()
    ChatToolExecutor.onboardingAppState = nil
    OnboardingChatPersistence.clear()
    ChatDraftStore.shared.clear(.onboardingMain)
    ChatDraftStore.shared.clear(.onboardingFloating)

    onComplete?()
    // Wipe the default main-chat journal so the Chat tab opens clean before reveal.
    Task { [weak self] in
      guard let self else { return }
      _ = await self.chatProvider.clearDefaultJournalForOnboardingReset()
      self.appState.hasCompletedOnboarding = true
    }

    Task {
      await AgentVMService.shared.startPipeline()
      await GoalGenerationService.shared.generateNow()
    }
    _ = LaunchAtLoginManager.shared.setEnabled(true)

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
    Task {
      let welcome = "Run omi for two days to start receiving helpful insights"
      let exists = await ActionItemStorage.shared.actionItemExists(description: welcome)
      if !exists {
        _ = await TasksStore.shared.createTask(description: welcome, dueAt: Date(), priority: "low")
      }
    }
  }

  /// Cancel every live task/monitor this model owns. Safe to call repeatedly.
  private func teardownAll() {
    streamTask?.cancel()
    pollTasks.values.forEach { $0.cancel() }
    pollTasks.removeAll()
    disarmShortcutSummon()
    teardownVoiceDemo()
    FloatingControlBarManager.shared.hide()
  }
}
