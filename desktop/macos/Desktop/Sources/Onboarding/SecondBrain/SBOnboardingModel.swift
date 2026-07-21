import AppKit
import Combine
import Foundation

/// Drives the Second Brain conversational onboarding: a real chat with Omi that
/// streams word-by-word, collects answers, and performs the SAME live side-effects
/// as the legacy wizard (name → Firebase/backend, permissions incl. Full Disk
/// Access, capture mode, completion). No fake steps — every widget does real work.
@MainActor
final class SBOnboardingModel: ObservableObject {
  enum Step: Int, CaseIterable {
    case promise, name, role, meet, perm, files, ptt, launch, calendar, wow, capture
  }

  struct Msg: Identifiable {
    let id = UUID()
    let isOmi: Bool
    var text: String
  }

  enum PermState: Equatable { case ask, waiting, on }

  @Published private(set) var step: Step = .promise
  @Published private(set) var thread: [Msg] = []
  /// The current Omi message streaming in (nil once committed).
  @Published private(set) var streamingText: String?
  @Published private(set) var typing = false
  @Published private(set) var showWidget = false

  // Per-step answers / state
  @Published var nameDraft = ""
  @Published var roleDraft = ""
  @Published private(set) var role: String?
  @Published private(set) var meet: String?  // "video" | "inperson" | "both"
  @Published private(set) var micState: PermState = .ask
  @Published private(set) var sysState: PermState = .ask
  @Published private(set) var fdaState: PermState = .ask
  @Published private(set) var accState: PermState = .ask  // accessibility, for the PTT shortcut
  @Published var launchAtLogin: Bool = LaunchAtLoginManager.shared.isEnabled
  @Published private(set) var calState: String = "idle"  // idle | connecting | on | needsSignIn
  @Published private(set) var wowPick: Int?
  /// Real chat at the wow step: true while Omi is answering the tapped question.
  @Published private(set) var wowAsking = false
  private var wowAnswerIndex: Int?
  private var wowCancellable: AnyCancellable?

  private unowned let appState: AppState
  private let chatProvider: ChatProvider
  private let onComplete: (() -> Void)?
  private var streamTask: Task<Void, Never>?
  private var pollTask: Task<Void, Never>?

  init(appState: AppState, chatProvider: ChatProvider, onComplete: (() -> Void)?) {
    self.appState = appState
    self.chatProvider = chatProvider
    self.onComplete = onComplete
  }

  // MARK: copy (verbatim from the design, + the new files step)

  private func message(for step: Step) -> String {
    let name = displayName
    switch step {
    case .promise:
      return
        "Hey — I'm Omi, your second brain. I listen to your conversations — rooms, calls, everyday life — remember everything, and do the follow-ups. Three things first:"
    case .name: return "What should I call you?"
    case .role:
      return
        "Nice to meet you, \(name). What do your days look like? Pick the closest — or just tell me. It shapes what I produce: lecture notes, CRM updates, client recaps, standup summaries…"
    case .meet: return "Where do your most important conversations happen?"
    case .perm:
      switch meet {
      case "video":
        return
          "You picked video calls — so I need to hear them. macOS will ask once. Everything else I'll ask for only when you first need it."
      case "inperson":
        return
          "For conversations in a room, I just need your microphone. Everything else I'll ask for only when you first need it."
      default:
        return
          "Rooms and calls — so two things: your mic for the room, system audio for the calls."
      }
    case .files:
      return
        "One more thing that makes me sharper: let me read your files. Then my answers can cite your actual documents — the spec, the deck, the note. It's read-only and stays on this Mac."
    case .ptt:
      return
        "The fastest way to reach me: hold fn and just talk — I answer out loud, hands-free, from anywhere. To catch that shortcut everywhere, macOS needs to grant me Accessibility."
    case .launch:
      return
        "So I'm there the moment you need me — even after a restart or a quit — let me open at login. You can always turn this off later."
    case .calendar:
      return
        "Now your calendar. Then I know when meetings start, prepare beforehand, and capture automatically."
    case .wow:
      return "From day one I can answer things like:"
    case .capture:
      return
        "You're set, \(name). ⌘⇧O opens me anywhere; hold fn to talk. Last choice — I can listen all the time (pause anytime from the notch), or only when your calendar says you're in a meeting:"
    }
  }

  var displayName: String {
    let n = role == nil ? nameDraft.trimmingCharacters(in: .whitespaces) : nameDraft.trimmingCharacters(in: .whitespaces)
    let stored = AuthService.shared.givenName.trimmingCharacters(in: .whitespaces)
    if !n.isEmpty { return n.components(separatedBy: " ").first ?? n }
    if !stored.isEmpty { return stored }
    return "friend"
  }

  var progressFraction: Double { Double(step.rawValue + 1) / Double(Step.allCases.count) }
  var totalSteps: Int { Step.allCases.count }
  var currentStepIndex: Int { step.rawValue }

  // MARK: lifecycle

  func begin() {
    guard thread.isEmpty && streamingText == nil else { return }
    streamMessage(for: .promise)
  }

  private func streamMessage(for step: Step) {
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
    }
  }

  private func advance(userAnswer: String?, to next: Step) {
    if let userAnswer, !userAnswer.isEmpty {
      thread.append(Msg(isOmi: false, text: userAnswer))
    }
    step = next
    streamMessage(for: next)
  }

  // MARK: step actions (all perform REAL work)

  func answerPromise() { advance(userAnswer: "Set me up", to: .name) }

  func answerName() {
    let trimmed = nameDraft.trimmingCharacters(in: .whitespaces)
    guard !trimmed.isEmpty else { return }
    Task { await AuthService.shared.updateGivenName(trimmed) }
    advance(userAnswer: trimmed, to: .role)
  }

  func pickRole(_ r: String) {
    role = r
    UserDefaults.standard.set(r, forKey: "onboardingRole")
    advance(userAnswer: r, to: .meet)
  }

  func answerRoleText() {
    let t = roleDraft.trimmingCharacters(in: .whitespaces)
    guard !t.isEmpty else { return }
    pickRole(t)
  }

  func pickMeet(_ key: String, label: String) {
    meet = key
    advance(userAnswer: label, to: .perm)
  }

  /// The permission rows shown at the perm step, matched to how they meet.
  var permKeys: [String] {
    switch meet {
    case "video": return ["system_audio"]
    case "inperson": return ["microphone"]
    default: return ["microphone", "system_audio"]
    }
  }

  func requestPerm(_ key: String) {
    switch key {
    case "microphone":
      micState = .waiting
      appState.requestMicrophonePermission()
      pollPermission(key)
    case "system_audio":
      sysState = .waiting
      appState.triggerSystemAudioPermission()
      pollPermission(key)
    default: break
    }
  }

  func requestFullDiskAccess() {
    fdaState = .waiting
    if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles") {
      NSWorkspace.shared.open(url)
    }
    pollPermission("full_disk_access")
  }

  private func pollPermission(_ key: String) {
    pollTask?.cancel()
    pollTask = Task { [weak self] in
      for _ in 0..<40 {  // ~20s
        try? await Task.sleep(nanoseconds: 500_000_000)
        guard let self, !Task.isCancelled else { return }
        self.appState.checkAllPermissions()
        if key == "full_disk_access" { self.appState.checkFullDiskAccess() }
        if self.isGranted(key) {
          self.setPermOn(key)
          return
        }
      }
    }
  }

  private func isGranted(_ key: String) -> Bool {
    switch key {
    case "microphone": return appState.hasMicrophonePermission
    case "system_audio": return appState.hasSystemAudioPermission
    case "full_disk_access": return appState.hasFullDiskAccess
    case "accessibility": return appState.hasAccessibilityPermission && !appState.isAccessibilityBroken
    default: return false
    }
  }

  private func setPermOn(_ key: String) {
    switch key {
    case "microphone": micState = .on
    case "system_audio": sysState = .on
    case "full_disk_access": fdaState = .on
    case "accessibility": accState = .on
    default: break
    }
  }

  func state(for key: String) -> PermState {
    switch key {
    case "microphone": return micState
    case "system_audio": return sysState
    default: return .ask
    }
  }

  var anyPermGranted: Bool {
    permKeys.contains { isGranted($0) }
  }

  func answerPerms() {
    advance(userAnswer: anyPermGranted ? "Granted" : "Maybe later", to: .files)
  }

  func answerFiles() {
    advance(userAnswer: fdaState == .on ? "Files on" : "Skip for now", to: .ptt)
  }

  // MARK: push-to-talk (Accessibility permission for the global shortcut)

  func requestAccessibility() {
    accState = .waiting
    appState.triggerAccessibilityPermission()
    pollPermission("accessibility")
  }

  func answerPtt() {
    advance(userAnswer: accState == .on ? "Accessibility on" : "Maybe later", to: .launch)
  }

  // MARK: launch at login (app reopens after a quit / restart)

  func toggleLaunch(_ on: Bool) {
    _ = LaunchAtLoginManager.shared.setEnabled(on)
    launchAtLogin = LaunchAtLoginManager.shared.isEnabled
  }

  func answerLaunch() {
    advance(userAnswer: launchAtLogin ? "Open at login" : "No auto-open", to: .calendar)
  }

  func connectCalendar() {
    guard calState == "idle" else { return }
    calState = "connecting"
    Task { [weak self] in
      let status = await CalendarReaderService.shared.verifyConnection()
      guard let self else { return }
      self.calState = status.isConnected ? "on" : "needsSignIn"
      if status.isConnected {
        self.advance(userAnswer: "Calendar connected", to: .wow)
      }
    }
  }

  func skipCalendar() { advance(userAnswer: "Skip for now", to: .wow) }

  /// The wow moment: actually ask Omi the tapped question and stream the real
  /// answer into the onboarding thread — a live chat, not a canned line.
  func askWow(_ question: String) {
    guard !wowAsking else { return }
    wowAsking = true
    wowAnswerIndex = nil
    streamTask?.cancel()
    streamingText = nil
    thread.append(Msg(isOmi: false, text: question))
    typing = true
    showWidget = false
    Task { _ = await chatProvider.sendMainDraft(question) }
    wowCancellable = chatProvider.$messages
      .receive(on: RunLoop.main)
      .sink { [weak self] messages in
        guard let self else { return }
        guard let ai = messages.last(where: { $0.sender == .ai }),
          !ai.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        else { return }
        self.typing = false
        if let idx = self.wowAnswerIndex, idx < self.thread.count {
          self.thread[idx].text = ai.text
        } else {
          self.thread.append(Msg(isOmi: true, text: ai.text))
          self.wowAnswerIndex = self.thread.count - 1
        }
        if !ai.isStreaming {
          self.wowAsking = false
          self.showWidget = true
          self.wowCancellable = nil
        }
      }
  }

  func answerWow() {
    wowCancellable = nil
    wowAsking = false
    advance(userAnswer: "Continue", to: .capture)
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

  /// Replicates the essential real side-effects of the legacy handleOnboardingComplete().
  private func complete(startListening: Bool) {
    streamTask?.cancel()
    pollTask?.cancel()
    AnalyticsManager.shared.onboardingCompleted()
    chatProvider.stopAgent(owner: .mainChat)
    UserDefaults.standard.set(true, forKey: "onboardingJustCompleted")
    if !AppBuild.usesLazyDevPermissions {
      UserDefaults.standard.set(true, forKey: "hasCompletedFileIndexing")
    }
    chatProvider.isOnboarding = false
    ChatToolExecutor.onboardingAppState = nil
    OnboardingChatPersistence.clear()
    ChatDraftStore.shared.clear(.onboardingMain)
    ChatDraftStore.shared.clear(.onboardingFloating)

    onComplete?()
    DispatchQueue.main.async { [appState] in appState.hasCompletedOnboarding = true }

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
    if startListening {
      Task { [appState] in
        appState.startTranscription()
        await appState.reconcileCapture()
      }
    }
    Task {
      let welcome = "Run omi for two days to start receiving helpful insights"
      let exists = await ActionItemStorage.shared.actionItemExists(description: welcome)
      if !exists {
        _ = await TasksStore.shared.createTask(description: welcome, dueAt: Date(), priority: "low")
      }
    }
  }
}
