import Foundation

enum FirstRunStep: String, Codable, CaseIterable, Sendable {
  case inactive
  case openWork
  case setReminder
  case drift
  case backToWork
  case summary
  case done
  case dismissed

  var isActive: Bool {
    switch self {
    case .openWork, .setReminder, .drift, .backToWork, .summary: return true
    case .inactive, .done, .dismissed: return false
    }
  }
}

enum FirstRunFocusPath: String, Codable, Sendable {
  case assistant
  case fallback
}

struct FirstRunDwell: Codable, Equatable, Sendable {
  let context: FirstRunObservedContext
  let startedAt: Date
}

enum FirstRunPendingEffect: Codable, Equatable, Sendable {
  case advance(step: FirstRunStep, deadline: Date)
  case focus(site: String, deadline: Date)
  case focusSnooze(deadline: Date)
  case reminder(id: String)
  case conversation(idempotencyKey: String)
}

struct FirstRunState: Codable, Equatable, Sendable {
  static let currentVersion = 1

  var version = currentVersion
  var step: FirstRunStep = .inactive
  var startedAt: Date?
  var stepStartedAt: Date?
  var launches = 0
  var stepsCompleted = 0
  var projectContext: ContextReminderKey?
  var reminderID: String?
  var reminderText: String?
  var actionItemID: String?
  var conversationID: String?
  var focusPath: FirstRunFocusPath?
  var focusRequestedAt: Date?
  var distractionSite: String?
  var reminderPresented = false
  var transitionPending = false
  var pendingEffect: FirstRunPendingEffect?
  var reminderDismissals = 0
  var dwell: FirstRunDwell?
  var instructionChipDays: [String: Int] = [:]
  /// The step whose guide chip the user closed with ✕. The chip stays down for that step: the
  /// five-second presentation heartbeat used to put it straight back, which made ✕ a snooze nobody
  /// asked for. It returns on the next step, the next launch, or a snooze ending.
  var guideSuppressedStep: FirstRunStep?
  var log: [FirstRunLogEntry] = []

  static let inactive = FirstRunState()
}

enum FirstRunReducerEvent: Equatable, Sendable {
  case start
  case launch
  case resume
  case context(FirstRunObservedContext)
  case dwellElapsed(FirstRunObservedContext)
  case voiceTurn(String)
  case reminderCreated(reminderID: String, actionItemID: String?)
  case advance(expected: FirstRunStep)
  case focusProbeResult(delivered: Bool)
  case focusFallbackElapsed
  case reminderResolved(id: String, snoozed: Bool)
  case conversationCreated(String)
  case conversationCreationFailed
  case presentationOpportunity
  case focusReturnSelected
  case focusSnoozed(until: Date)
  case focusSnoozeElapsed
  case notificationDismissed(assistantID: String)
  case dismiss
}

enum FirstRunReducerEffect: Equatable, Sendable {
  case showInstruction
  case showTransient(title: String, message: String)
  case showLoopCompletion
  case hideGuide
  case scheduleDwell(context: FirstRunObservedContext, seconds: TimeInterval)
  case scheduleAdvance(expected: FirstRunStep, seconds: TimeInterval)
  case createReminder(text: String, context: ContextReminderKey)
  case requestFocus(site: String)
  case scheduleFocusFallback(seconds: TimeInterval)
  case scheduleFocusSnooze(seconds: TimeInterval)
  case deliverFallback(site: String, projectTitle: String)
  case deliverReminder(id: String)
  case createConversation
  case showSummary(conversationID: String)
  case scheduleConversationRetry(seconds: TimeInterval)
  case clearPending
  case stepAnalytics(step: FirstRunStep, elapsedMilliseconds: Int, path: String)
  case focusPathAnalytics(FirstRunFocusPath)
  case completedAnalytics(stepsCompleted: Int, totalMilliseconds: Int)
}

enum FirstRunReducer {
  static let abandonmentInterval: TimeInterval = 24 * 60 * 60
  static let maximumLaunches = 3

  static func reduce(
    _ current: FirstRunState,
    event: FirstRunReducerEvent,
    now: Date,
    calendar: Calendar = .current
  ) -> (state: FirstRunState, effects: [FirstRunReducerEffect]) {
    var state = current
    var effects: [FirstRunReducerEffect] = []

    func elapsed(from start: Date?) -> Int {
      Int(max(0, now.timeIntervalSince(start ?? now)) * 1_000)
    }

    func completeStep(_ step: FirstRunStep, path: String = "observed") {
      state.stepsCompleted += 1
      effects.append(
        .stepAnalytics(
          step: step,
          elapsedMilliseconds: elapsed(from: state.stepStartedAt),
          path: path))
    }

    func dismiss(path: String = "dismissed") {
      if state.step.isActive {
        effects.append(
          .stepAnalytics(
            step: state.step,
            elapsedMilliseconds: elapsed(from: state.stepStartedAt),
            path: path))
      }
      state.step = .dismissed
      state.dwell = nil
      state.transitionPending = false
      effects.append(.hideGuide)
      effects.append(.clearPending)
    }

    switch event {
    case .start:
      guard state.step == .inactive else { break }
      state.step = .openWork
      state.startedAt = now
      state.stepStartedAt = now
      state.launches = 1
      effects.append(.showInstruction)

    case .launch:
      guard state.step.isActive else { break }
      state.launches += 1
      if state.launches >= maximumLaunches
        || now.timeIntervalSince(state.startedAt ?? now) >= abandonmentInterval
      {
        dismiss()
      } else {
        state.guideSuppressedStep = nil
        effects.append(.showInstruction)
      }

    case .resume:
      guard state.step.isActive, let pending = state.pendingEffect else { break }
      switch pending {
      case .advance(let step, let deadline):
        effects.append(.scheduleAdvance(expected: step, seconds: max(0, deadline.timeIntervalSince(now))))
      case .focus(let site, let deadline):
        effects.append(.requestFocus(site: site))
        effects.append(.scheduleFocusFallback(seconds: max(0, deadline.timeIntervalSince(now))))
      case .focusSnooze(let deadline):
        effects.append(.scheduleFocusSnooze(seconds: max(0, deadline.timeIntervalSince(now))))
      case .reminder(let id):
        effects.append(.deliverReminder(id: id))
      case .conversation:
        effects.append(.createConversation)
      }

    case .context(let context):
      switch state.step {
      case .openWork where !state.transitionPending:
        guard context.isEligibleProject else {
          state.dwell = nil
          break
        }
        if state.dwell?.context != context {
          state.dwell = FirstRunDwell(context: context, startedAt: now)
          effects.append(.scheduleDwell(context: context, seconds: 8))
        }

      case .drift where state.focusRequestedAt == nil:
        guard context.distractionSite != nil else {
          state.dwell = nil
          break
        }
        if state.dwell?.context != context {
          state.dwell = FirstRunDwell(context: context, startedAt: now)
          effects.append(.scheduleDwell(context: context, seconds: 45))
        }

      case .backToWork where !state.reminderPresented:
        guard let project = state.projectContext, project.matches(context), let reminderID = state.reminderID else {
          break
        }
        state.reminderPresented = true
        state.pendingEffect = .reminder(id: reminderID)
        state.log.append(
          FirstRunLogEntry(
            t: now,
            text: "Returned to \(project.normalizedTitle).",
            isUser: false))
        effects.append(.deliverReminder(id: reminderID))

      default:
        break
      }

    case .dwellElapsed(let context):
      guard let dwell = state.dwell, dwell.context == context else { break }
      switch state.step {
      case .openWork where !state.transitionPending && context.isEligibleProject:
        guard now.timeIntervalSince(dwell.startedAt) >= 8 else { break }
        let project = context.reminderKey
        state.projectContext = project
        state.dwell = nil
        state.transitionPending = true
        state.pendingEffect = .advance(step: .openWork, deadline: now.addingTimeInterval(3))
        state.log.append(
          FirstRunLogEntry(
            t: now,
            text: "Opened \(project.normalizedTitle) in \(context.appName).",
            isUser: false))
        completeStep(.openWork)
        effects.append(
          .showTransient(
            title: "✓ \(project.normalizedTitle). I'll know this place when you come back.",
            message: ""))
        effects.append(.scheduleAdvance(expected: .openWork, seconds: 3))

      case .drift where state.focusRequestedAt == nil:
        guard now.timeIntervalSince(dwell.startedAt) >= 45,
          let site = context.distractionSite,
          let projectTitle = state.projectContext?.normalizedTitle
        else { break }
        state.dwell = nil
        state.focusRequestedAt = now
        state.distractionSite = site
        state.log.append(
          FirstRunLogEntry(t: now, text: "Drifted to \(site), away from \(projectTitle).", isUser: false))
        effects.append(.hideGuide)
        state.pendingEffect = .focus(site: site, deadline: now.addingTimeInterval(60))
        effects.append(.requestFocus(site: site))
        effects.append(.scheduleFocusFallback(seconds: 60))

      default:
        break
      }

    case .voiceTurn(let rawText):
      guard state.step == .setReminder, !state.transitionPending, let project = state.projectContext else { break }
      let text = rawText.trimmingCharacters(in: .whitespacesAndNewlines)
      guard !text.isEmpty else { break }
      state.reminderText = text
      state.transitionPending = true
      state.log.append(FirstRunLogEntry(t: now, text: text, isUser: true))
      effects.append(.createReminder(text: text, context: project))

    case .reminderCreated(let reminderID, let actionItemID):
      guard state.step == .setReminder, state.transitionPending,
        let projectTitle = state.projectContext?.normalizedTitle
      else { break }
      state.reminderID = reminderID
      state.actionItemID = actionItemID
      completeStep(.setReminder)
      state.pendingEffect = .advance(step: .setReminder, deadline: now.addingTimeInterval(3))
      effects.append(
        .showTransient(
          title: "✓ Got it. Next time you're back in \(projectTitle), I'll bring that up.",
          message: ""))
      effects.append(.scheduleAdvance(expected: .setReminder, seconds: 3))

    case .advance(let expected):
      guard state.step == expected, state.transitionPending else { break }
      state.transitionPending = false
      state.pendingEffect = nil
      state.stepStartedAt = now
      state.guideSuppressedStep = nil
      switch expected {
      case .openWork:
        state.step = .setReminder
        effects.append(.showInstruction)
      case .setReminder:
        state.step = .drift
        effects.append(.showInstruction)
      case .backToWork:
        state.step = .summary
        state.pendingEffect = .conversation(idempotencyKey: "first-run-\(state.reminderID ?? "session")")
        effects.append(.createConversation)
      default:
        break
      }

    case .focusProbeResult(let delivered):
      guard state.step == .drift, state.focusRequestedAt != nil, state.focusPath == nil, delivered else { break }
      state.focusPath = .assistant
      state.pendingEffect = nil
      state.step = .backToWork
      state.stepStartedAt = now
      completeStep(.drift)
      effects.append(.focusPathAnalytics(.assistant))

    case .focusFallbackElapsed:
      guard state.step == .drift, let requestedAt = state.focusRequestedAt,
        now.timeIntervalSince(requestedAt) >= 60,
        state.focusPath == nil,
        let site = state.distractionSite,
        let projectTitle = state.projectContext?.normalizedTitle
      else { break }
      state.focusPath = .fallback
      state.pendingEffect = nil
      state.step = .backToWork
      state.stepStartedAt = now
      completeStep(.drift, path: "fallback")
      effects.append(.deliverFallback(site: site, projectTitle: projectTitle))
      effects.append(.focusPathAnalytics(.fallback))

    case .reminderResolved(let id, let snoozed):
      guard state.step == .backToWork, state.reminderPresented, state.reminderID == id else { break }
      state.transitionPending = true
      state.pendingEffect = .advance(step: .backToWork, deadline: now.addingTimeInterval(3))
      state.log.append(
        FirstRunLogEntry(
          t: now,
          text: snoozed ? "Snoozed the reminder until tomorrow." : "Completed the reminder.",
          isUser: false))
      completeStep(.backToWork)
      effects.append(.showLoopCompletion)
      effects.append(.scheduleAdvance(expected: .backToWork, seconds: 3))

    case .conversationCreated(let conversationID):
      guard state.step == .summary else { break }
      state.conversationID = conversationID
      state.pendingEffect = nil
      completeStep(.summary)
      state.step = .done
      effects.append(.showSummary(conversationID: conversationID))
      effects.append(.clearPending)
      effects.append(
        .completedAnalytics(
          stepsCompleted: state.stepsCompleted,
          totalMilliseconds: elapsed(from: state.startedAt)))

    case .conversationCreationFailed:
      guard state.step == .summary else { break }
      effects.append(.scheduleConversationRetry(seconds: 30))

    case .presentationOpportunity:
      guard state.step.isActive, !state.transitionPending else { break }
      if now.timeIntervalSince(state.startedAt ?? now) >= abandonmentInterval {
        dismiss()
      } else if state.step == .openWork || state.step == .setReminder || state.step == .drift,
        state.guideSuppressedStep != state.step
      {
        effects.append(.showInstruction)
      }

    case .focusReturnSelected:
      guard state.step == .backToWork else { break }
      state.pendingEffect = nil
      state.log.append(FirstRunLogEntry(t: now, text: "Chose to return to work.", isUser: false))

    case .focusSnoozed(let deadline):
      guard state.step == .backToWork else { break }
      state.step = .drift
      state.stepStartedAt = deadline
      state.focusPath = nil
      state.focusRequestedAt = nil
      state.dwell = nil
      state.pendingEffect = .focusSnooze(deadline: deadline)
      effects.append(.scheduleFocusSnooze(seconds: max(0, deadline.timeIntervalSince(now))))

    case .focusSnoozeElapsed:
      guard state.step == .drift, case .focusSnooze = state.pendingEffect else { break }
      state.pendingEffect = nil
      state.stepStartedAt = now
      state.guideSuppressedStep = nil
      effects.append(.showInstruction)

    case .notificationDismissed(let assistantID):
      if assistantID == "first_run_guide", state.step.isActive {
        state.guideSuppressedStep = state.step
        break
      }
      guard assistantID == "first_run_card", state.step == .backToWork, state.reminderPresented else { break }
      state.reminderDismissals += 1
      state.reminderPresented = false
      state.pendingEffect = nil
      if state.reminderDismissals >= 2 {
        state.transitionPending = true
        completeStep(.backToWork, path: "abandoned")
        state.pendingEffect = .advance(step: .backToWork, deadline: now.addingTimeInterval(3))
        effects.append(.scheduleAdvance(expected: .backToWork, seconds: 3))
      }

    case .dismiss:
      guard state.step.isActive else { break }
      dismiss()
    }

    state.instructionChipDays = state.instructionChipDays.filter { key, _ in
      guard let date = Self.dayFormatter.date(from: key) else { return false }
      return calendar.dateComponents([.day], from: date, to: now).day.map { $0 < 7 } ?? false
    }
    return (state, effects)
  }

  static func dayKey(for date: Date, calendar: Calendar = .current) -> String {
    let formatter = dayFormatter
    formatter.calendar = calendar
    formatter.timeZone = calendar.timeZone
    return formatter.string(from: date)
  }

  private static var dayFormatter: DateFormatter {
    let formatter = DateFormatter()
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.timeZone = .current
    formatter.dateFormat = "yyyy-MM-dd"
    return formatter
  }
}

enum FirstRunChipPresentationPolicy {
  static func shouldPresent(
    isMeetingActive: Bool,
    hasAnotherCard: Bool,
    instructionCountToday: Int,
    countsAgainstDailyCap: Bool
  ) -> Bool {
    guard !isMeetingActive, !hasAnotherCard else { return false }
    return !countsAgainstDailyCap || instructionCountToday < 3
  }
}

@MainActor
protocol FirstRunScheduledCancellation {
  func cancel()
}

@MainActor
private final class FirstRunTaskCancellation: FirstRunScheduledCancellation {
  private var task: Task<Void, Never>?

  init(task: Task<Void, Never>) { self.task = task }

  func cancel() {
    task?.cancel()
    task = nil
  }
}

@MainActor
final class FirstRunCoordinator {
  static let shared = FirstRunCoordinator()

  nonisolated static let pendingKey = "omiFirstRunPending"
  nonisolated static let stateKey = "omiFirstRunState"
  static let scenarioJournalKey = "sbOnboardingScenarioJournal"
  nonisolated static let persistedKeys: Set<String> = [pendingKey, stateKey]

  /// The push-to-talk chord the user actually chose, for chip copy. Never a hard-coded ⌥: the
  /// scenario lets them pick fn or ⌃, and a chip that names the wrong key is a dead end.
  static func talkChordLabel() -> String {
    let tokens = ShortcutSettings.shared.pttShortcut.displayTokens
    return tokens.isEmpty ? "fn" : tokens.joined(separator: " ")
  }

  private let defaults: UserDefaults
  private let now: () -> Date
  private let calendar: Calendar
  private let executesEffects: Bool
  private let ownerID: () -> String?
  private var meetingIsActive: () -> Bool = { false }
  private var state: FirstRunState
  private var events: [FirstRunReducerEvent] = []
  private var isDraining = false
  private var scheduled: [String: FirstRunScheduledCancellation] = [:]
  private var handoffObserver: NSObjectProtocol?
  private var ownerObserver: NSObjectProtocol?
  private var boundOwnerID: String?
  private var didCountLaunch = false
  private var didResume = false
  private var effectObserverForTests: ((FirstRunReducerEffect) -> Void)?
  private var stateObserverForTests: ((FirstRunState) -> Void)?

  init(
    defaults: UserDefaults = .standard,
    now: @escaping () -> Date = { Date() },
    calendar: Calendar = .current,
    executesEffects: Bool = true,
    ownerID: @escaping () -> String? = { RuntimeOwnerIdentity.currentOwnerId() }
  ) {
    self.defaults = defaults
    self.now = now
    self.calendar = calendar
    self.executesEffects = executesEffects
    self.ownerID = ownerID
    boundOwnerID = ownerID()
    let persistedKey = boundOwnerID.map { Self.stateKey + "." + $0 } ?? Self.stateKey
    if let data = defaults.data(forKey: persistedKey) ?? defaults.data(forKey: Self.stateKey),
      let decoded = try? JSONDecoder().decode(FirstRunState.self, from: data),
      decoded.version == FirstRunState.currentVersion
    {
      state = decoded
    } else {
      state = .inactive
    }
    ownerObserver = NotificationCenter.default.addObserver(
      forName: .runtimeOwnerDidChange, object: nil, queue: .main
    ) { [weak self] _ in
      MainActor.assumeIsolated { self?.resetForOwnerChange() }
    }
  }

  func configure(meetingIsActive: @escaping () -> Bool) {
    self.meetingIsActive = meetingIsActive
  }

  func startIfNeeded(hasCompletedOnboarding: Bool) {
    reloadForCurrentOwner()
    installHandoffObserver()
    FirstRunContextObserver.shared.start()
    guard hasCompletedOnboarding else { return }

    if state.step.isActive {
      if !didCountLaunch {
        didCountLaunch = true
        send(.launch)
      }
      if !didResume {
        didResume = true
        send(.resume)
      }
    } else if defaults.bool(forKey: Self.pendingKey) {
      didCountLaunch = true
      send(.start)
    }
    armPresentationHeartbeatIfNeeded()
  }

  func observeContext(_ context: FirstRunObservedContext) {
    send(.context(context))
  }

  func observeVoiceTurn(_ transcript: String) {
    send(.voiceTurn(transcript))
  }

  func dismissByUser() {
    send(.dismiss)
  }

  func ownsReminderDelivery(_ reminderID: String) -> Bool {
    state.step == .backToWork && state.reminderID == reminderID
  }

  func handleCardAction(_ action: String, id: String?) {
    guard let id else {
      if action == "first_run_focus_return" || action == "first_run_focus_snooze" { return }
      return
    }
    switch action {
    case "context_reminder_done":
      resolveReminder(id: id, snoozed: false)
    case "context_reminder_snooze":
      resolveReminder(id: id, snoozed: true)
    case "first_run_open_summary":
      MeetingSummaryShareActions.openSummary(conversationID: id)
    case "first_run_focus_return":
      send(.focusReturnSelected)
    case "first_run_focus_snooze":
      send(.focusSnoozed(until: now().addingTimeInterval(5 * 60)))
    default:
      break
    }
  }

  func snapshotForTesting() -> FirstRunState { state }

  func setObserversForTesting(
    effect: ((FirstRunReducerEffect) -> Void)?,
    state: ((FirstRunState) -> Void)?
  ) {
    effectObserverForTests = effect
    stateObserverForTests = state
  }

  func sendForTesting(_ event: FirstRunReducerEvent) {
    send(event)
  }

  func notificationDismissed(assistantID: String) {
    send(.notificationDismissed(assistantID: assistantID))
  }

  private func installHandoffObserver() {
    guard handoffObserver == nil else { return }
    handoffObserver = NotificationCenter.default.addObserver(
      forName: Notification.Name("omi.onboarding.scenarioCompleted"),
      object: nil,
      queue: .main
    ) { [weak self] notification in
      let skipped = notification.userInfo?["skipped"] as? Bool ?? false
      Task { @MainActor in
        guard let self else { return }
        log("FirstRunCoordinator: received onboarding handoff skipped=\(skipped)")
        self.defaults.set(true, forKey: Self.pendingKey)
        if self.state.step == .inactive {
          self.didCountLaunch = true
          self.send(.start)
        }
      }
    }
  }

  private func send(_ event: FirstRunReducerEvent) {
    events.append(event)
    guard !isDraining else { return }
    isDraining = true
    defer {
      events.removeAll(keepingCapacity: true)
      isDraining = false
    }

    var index = 0
    while index < events.count {
      let event = events[index]
      index += 1
      let reduction = FirstRunReducer.reduce(state, event: event, now: now(), calendar: calendar)
      state = reduction.state
      persistState()
      for effect in reduction.effects {
        if executesEffects { execute(effect) }
        effectObserverForTests?(effect)
      }
      stateObserverForTests?(state)
    }
    if executesEffects { syncHubNote() }
  }

  /// While the guide is asking for a spoken reminder, the voice hub hears the same sentence the
  /// reducer does. Without this it answers as a general assistant, and can write its own task for
  /// "remind me to ping Priya" on top of the one the first run records. The note tells it whose
  /// turn it is. Owned here so it never clobbers the onboarding talk beat's note, which is torn
  /// down before the first run can start.
  private var ownsHubNote: Bool {
    get { Self.hubNoteOwned }
    set { Self.hubNoteOwned = newValue }
  }
  private static var hubNoteOwned = false

  private func syncHubNote() {
    if state.step == .setReminder, let project = state.projectContext?.normalizedTitle {
      OnboardingDemoNote.active = OnboardingDemoNote.firstRunReminder(project: project)
      ownsHubNote = true
    } else if ownsHubNote {
      OnboardingDemoNote.active = nil
      ownsHubNote = false
    }
  }

  private func execute(_ effect: FirstRunReducerEffect) {
    switch effect {
    case .showInstruction:
      showCurrentInstruction()
    case .showTransient(let title, let message):
      presentGuideChip(title: title, message: message, countAgainstDailyCap: false)
    case .showLoopCompletion:
      presentLoopCompletion()
    case .hideGuide:
      FloatingControlBarManager.shared.dismissNotifications(assistantID: "first_run_guide", kind: .replaced)
    case .scheduleDwell(let context, let seconds):
      schedule(key: "dwell", after: seconds) { [weak self] in self?.send(.dwellElapsed(context)) }
    case .scheduleAdvance(let expected, let seconds):
      schedule(key: "advance", after: seconds) { [weak self] in self?.send(.advance(expected: expected)) }
    case .createReminder(let text, let context):
      createReminder(text: text, context: context)
    case .requestFocus(let site):
      requestSuggestionProbe(site: site)
    case .scheduleFocusFallback(let seconds):
      schedule(key: "focus-fallback", after: seconds) { [weak self] in self?.send(.focusFallbackElapsed) }
    case .scheduleFocusSnooze(let seconds):
      schedule(key: "focus-snooze", after: seconds) { [weak self] in self?.send(.focusSnoozeElapsed) }
    case .deliverFallback(let site, let projectTitle):
      deliverFocusFallback(site: site, projectTitle: projectTitle)
    case .deliverReminder(let id):
      deliverReminder(id: id)
    case .createConversation:
      createConversation()
    case .showSummary(let conversationID):
      presentGuideChip(
        title: "Here's what we did",
        message: "I wrote it up like a meeting. Open Omi.",
        countAgainstDailyCap: false,
        action: FirstRunCardActions.make(.openSummary(conversationID: conversationID)))
    case .scheduleConversationRetry(let seconds):
      schedule(key: "conversation-retry", after: seconds) { [weak self] in self?.createConversation() }
    case .clearPending:
      defaults.set(false, forKey: Self.pendingKey)
      cancelScheduledWork()
    case .stepAnalytics(let step, let elapsedMilliseconds, let path):
      PostHogManager.shared.track(
        "First Run Step Completed",
        properties: ["step": step.rawValue, "elapsed_ms": elapsedMilliseconds, "path": path])
    case .focusPathAnalytics(let path):
      PostHogManager.shared.track("Focus Card Path", properties: ["path": path.rawValue])
    case .completedAnalytics(let stepsCompleted, let totalMilliseconds):
      PostHogManager.shared.track(
        "First Run Completed",
        properties: ["steps_completed": stepsCompleted, "total_ms": totalMilliseconds])
    }
  }

  private func showCurrentInstruction() {
    let copy: (String, String)?
    switch state.step {
    case .openWork:
      copy = ("Open something you're working on", "a doc, a repo, a design, a deck. Anything real.")
    case .setReminder:
      copy = (
        "Hold \(Self.talkChordLabel()) and tell me something to bring up next time you open this",
        "e.g. 'remind me to ping Priya about the pricing table'"
      )
    case .drift:
      copy = (
        "Now go scroll something for a bit",
        "news, Reddit, anything you'd normally drift to. I'll be watching."
      )
    default:
      copy = nil
    }
    guard let copy else { return }
    presentGuideChip(title: copy.0, message: copy.1, countAgainstDailyCap: true)
  }

  private func presentGuideChip(
    title: String,
    message: String,
    countAgainstDailyCap: Bool,
    action: FloatingBarNotificationAction? = nil
  ) {
    let manager = FloatingControlBarManager.shared
    if manager.hasNotification(assistantID: "first_run_guide") {
      if manager.currentNotificationAssistantID == "first_run_guide",
        manager.currentNotificationTitle == title
      {
        return
      }
      manager.dismissNotifications(assistantID: "first_run_guide", kind: .replaced)
    }
    let instructionCountToday: Int
    let dayKey = FirstRunReducer.dayKey(for: now(), calendar: calendar)
    if countAgainstDailyCap {
      instructionCountToday = state.instructionChipDays[dayKey, default: 0]
    } else {
      instructionCountToday = 0
    }
    let hasAnotherCard = manager.currentNotificationAssistantID != nil
    guard
      FirstRunChipPresentationPolicy.shouldPresent(
        isMeetingActive: meetingIsActive(),
        hasAnotherCard: hasAnotherCard,
        instructionCountToday: instructionCountToday,
        countsAgainstDailyCap: countAgainstDailyCap)
    else {
      FloatingControlBarManager.shared.dismissNotifications(assistantID: "first_run_guide", kind: .replaced)
      armPresentationHeartbeatIfNeeded()
      return
    }
    if countAgainstDailyCap {
      state.instructionChipDays[dayKey] = instructionCountToday + 1
      persistState()
    }
    guard let ownerID = RuntimeOwnerIdentity.currentOwnerId() else {
      armPresentationHeartbeatIfNeeded()
      return
    }
    NotificationService.shared.sendNotification(
      ownerID: ownerID,
      title: title,
      message: message,
      assistantId: "first_run_guide",
      action: action,
      respectFrequency: false,
      isPersistent: true)
    armPresentationHeartbeatIfNeeded()
  }

  private func presentLoopCompletion() {
    guard canPresentFirstRunCard() else {
      schedule(key: "loop-completion-retry", after: 5) { [weak self] in self?.presentLoopCompletion() }
      return
    }
    guard let ownerID = RuntimeOwnerIdentity.currentOwnerId() else { return }
    NotificationService.shared.sendNotification(
      ownerID: ownerID,
      title: "✓ That's the loop: I notice where you are, and I bring back what you told me.",
      message: "",
      assistantId: "first_run_card",
      respectFrequency: false,
      isPersistent: false)
  }

  private func armPresentationHeartbeatIfNeeded() {
    guard state.step.isActive else {
      scheduled.removeValue(forKey: "presentation-heartbeat")?.cancel()
      return
    }
    schedule(key: "presentation-heartbeat", after: 5) { [weak self] in
      guard let self else { return }
      if self.meetingIsActive() {
        FloatingControlBarManager.shared.dismissNotifications(assistantID: "first_run_guide", kind: .replaced)
      }
      self.send(.presentationOpportunity)
      self.armPresentationHeartbeatIfNeeded()
    }
  }

  private func createReminder(text: String, context: ContextReminderKey) {
    Task { [weak self] in
      guard let self, let ownerID = RuntimeOwnerIdentity.currentOwnerId(),
        let authorization = RuntimeOwnerIdentity.captureAuthorizationSnapshot(expectedOwnerID: ownerID)
      else { return }
      var actionItemID: String?
      do {
        let actionItem = try await APIClient.shared.createActionItem(
          description: "In \(context.normalizedTitle): \(text)",
          source: "onboarding",
          expectedOwnerId: ownerID,
          authorizationSnapshot: authorization)
        actionItemID = actionItem.id
        guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else {
          log("FirstRunCoordinator: owner changed after action-item write; aborting reminder")
          return
        }
        await TasksStore.shared.refreshDashboardTasksFromServer(
          expectedOwnerID: ownerID,
          authorizationSnapshot: authorization)
      } catch {
        logError("FirstRunCoordinator: failed to create action item", error: error)
        await MainActor.run {
          self.schedule(key: "reminder-create-retry", after: 30) { [weak self] in
            self?.createReminder(text: text, context: context)
          }
        }
        return
      }
      do {
        let reminder = try await ContextReminderStore.shared.create(
          text: text,
          for: context,
          actionItemID: actionItemID,
          now: self.now(),
          expectedOwnerID: ownerID,
          authorizationSnapshot: authorization)
        guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else {
          log("FirstRunCoordinator: owner changed before reminder publication")
          return
        }
        await MainActor.run {
          self.send(.reminderCreated(reminderID: reminder.id, actionItemID: actionItemID))
        }
      } catch {
        logError("FirstRunCoordinator: failed to persist context reminder", error: error)
      }
    }
  }

  private func requestSuggestionProbe(site: String) {
    let projectTitle = state.projectContext?.normalizedTitle
    Task { [weak self] in
      let result = await ProactiveAssistantsPlugin.shared.probeSuggestionNudge(
        appOverride: nil,
        windowTitleOverride: site,
        deliveryAssistantID: "first_run_card")
      let delivered = result["delivered"] == "true" || result["outcome"] == "delivered"
      await MainActor.run {
        guard let self else { return }
        if delivered {
          self.scheduled.removeValue(forKey: "focus-fallback")?.cancel()
        }
        self.send(.focusProbeResult(delivered: delivered))
        if delivered, let projectTitle {
          log("FirstRunCoordinator: suggestion assistant delivered focus return for \(projectTitle)")
        }
      }
    }
  }

  private func deliverFocusFallback(site: String, projectTitle: String) {
    guard canPresentFirstRunCard() else {
      schedule(key: "focus-card-retry", after: 5) { [weak self] in
        self?.deliverFocusFallback(site: site, projectTitle: projectTitle)
      }
      return
    }
    guard let ownerID = RuntimeOwnerIdentity.currentOwnerId() else { return }
    NotificationService.shared.sendNotification(
      ownerID: ownerID,
      title: "Focus",
      message: "Two minutes on \(site). \(projectTitle) is still open. Back to it?",
      assistantId: "first_run_card",
      action: FirstRunCardActions.make(.focusReturn(projectTitle: projectTitle)),
      respectFrequency: false,
      isPersistent: true)
  }

  private func deliverReminder(id: String) {
    guard canPresentFirstRunCard() else {
      schedule(key: "reminder-card-retry", after: 5) { [weak self] in self?.deliverReminder(id: id) }
      return
    }
    FloatingControlBarManager.shared.dismissNotifications(assistantID: "first_run_card", kind: .replaced)
    Task {
      do {
        guard let reminder = try await ContextReminderStore.shared.allReminders().first(where: { $0.id == id })
        else { return }
        _ = ContextReminderStore.shared.deliver(reminder)
      } catch {
        logError("FirstRunCoordinator: failed to deliver context reminder", error: error)
      }
    }
  }

  private func resolveReminder(id: String, snoozed: Bool) {
    Task { [weak self] in
      guard let self else { return }
      do {
        let reminder: ContextReminder?
        if snoozed {
          let tomorrow =
            self.calendar.date(
              byAdding: .day,
              value: 1,
              to: self.calendar.startOfDay(for: self.now())) ?? self.now().addingTimeInterval(24 * 60 * 60)
          reminder = try await ContextReminderStore.shared.snooze(id: id, until: tomorrow)
        } else {
          reminder = try await ContextReminderStore.shared.markDone(id: id, at: self.now())
          if let actionItemID = reminder?.actionItemID,
            let ownerID = RuntimeOwnerIdentity.currentOwnerId(),
            let authorization = RuntimeOwnerIdentity.captureAuthorizationSnapshot(expectedOwnerID: ownerID)
          {
            _ = try? await APIClient.shared.updateActionItem(
              id: actionItemID,
              completed: true,
              expectedOwnerId: ownerID,
              authorizationSnapshot: authorization)
            await TasksStore.shared.refreshDashboardTasksFromServer(
              expectedOwnerID: ownerID,
              authorizationSnapshot: authorization)
          }
        }
        guard reminder != nil else { return }
        await MainActor.run {
          FloatingControlBarManager.shared.dismissNotifications(assistantID: "first_run_card", kind: .replaced)
          self.send(.reminderResolved(id: id, snoozed: snoozed))
        }
      } catch {
        logError("FirstRunCoordinator: failed to resolve context reminder", error: error)
      }
    }
  }

  private func createConversation() {
    guard state.step == .summary, let startedAt = state.startedAt, let reminderID = state.reminderID,
      let ownerID = RuntimeOwnerIdentity.currentOwnerId(),
      let authorization = RuntimeOwnerIdentity.captureAuthorizationSnapshot(expectedOwnerID: ownerID)
    else { return }
    let end = now()
    let journal = FirstRunSummaryComposer.decodeJournal(defaults.data(forKey: Self.scenarioJournalKey))
    let segments = FirstRunSummaryComposer.compose(
      journal: journal,
      firstRunLog: state.log,
      sessionStart: min(journal.map(\.t).min() ?? startedAt, startedAt),
      sessionEnd: end)
    guard !segments.isEmpty else {
      send(.conversationCreationFailed)
      return
    }
    let uploadSegments = segments.map {
      APIClient.UploadSegment(
        text: $0.text,
        speaker: $0.speaker,
        speaker_id: $0.speakerID,
        is_user: $0.isUser,
        person_id: nil,
        start: $0.start,
        end: $0.end)
    }
    let formatter = ISO8601DateFormatter()
    let start = min(journal.map(\.t).min() ?? startedAt, startedAt)
    let language = AssistantSettings.shared.voiceLanguages.first ?? "en"
    let clientConversationID = "first-run-\(reminderID)"

    Task { [weak self] in
      guard let self else { return }
      func request(source: String) -> APIClient.CreateConversationFromSegmentsRequest {
        APIClient.CreateConversationFromSegmentsRequest(
          transcript_segments: uploadSegments,
          source: source,
          started_at: formatter.string(from: start),
          finished_at: formatter.string(from: end),
          language: language,
          client_conversation_id: clientConversationID,
          client_session_id: clientConversationID,
          conversation_role: TranscriptionConversationRole.ambient.rawValue,
          conversation_finalization_reason: TranscriptionFinalizationReason.userStop.rawValue)
      }
      do {
        guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else {
          log("FirstRunCoordinator: owner changed before conversation write")
          return
        }
        let response: APIClient.CreateConversationFromSegmentsResponse
        do {
          response = try await APIClient.shared.createConversationFromSegments(request(source: "onboarding"))
        } catch APIError.httpError(let statusCode, _) where (400..<500).contains(statusCode) {
          guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else {
            log("FirstRunCoordinator: owner changed before conversation fallback")
            return
          }
          DesktopDiagnosticsManager.shared.recordFallback(
            area: "conversation",
            from: "onboarding_source",
            to: "desktop_source",
            reason: "unsupported",
            outcome: .recovered)
          response = try await APIClient.shared.createConversationFromSegments(request(source: "desktop"))
        }
        guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else {
          log("FirstRunCoordinator: owner changed before conversation result publication")
          return
        }
        await MainActor.run { self.send(.conversationCreated(response.id)) }
      } catch {
        logError("FirstRunCoordinator: failed to create first-run conversation", error: error)
        await MainActor.run { self.send(.conversationCreationFailed) }
      }
    }
  }

  private func schedule(key: String, after seconds: TimeInterval, action: @escaping @MainActor () -> Void) {
    scheduled.removeValue(forKey: key)?.cancel()
    let task = Task { @MainActor in
      do {
        try await Task.sleep(for: .seconds(seconds))
      } catch {
        return
      }
      action()
    }
    scheduled[key] = FirstRunTaskCancellation(task: task)
  }

  private func cancelScheduledWork() {
    for cancellation in scheduled.values { cancellation.cancel() }
    scheduled.removeAll()
  }

  private func canPresentFirstRunCard() -> Bool {
    let current = FloatingControlBarManager.shared.currentNotificationAssistantID
    return !meetingIsActive() && (current == nil || current == "first_run_card")
  }

  private func persistState() {
    guard let boundOwnerID, ownerID() == boundOwnerID,
      let data = try? JSONEncoder().encode(state)
    else { return }
    defaults.set(data, forKey: Self.stateKey + "." + boundOwnerID)
  }

  private func resetForOwnerChange() {
    cancelScheduledWork()
    events.removeAll()
    state = .inactive
    boundOwnerID = nil
    didCountLaunch = false
    didResume = false
    FloatingControlBarManager.shared.dismissNotifications(assistantID: "first_run_guide", kind: .replaced)
    FloatingControlBarManager.shared.dismissNotifications(assistantID: "first_run_card", kind: .replaced)
  }

  private func reloadForCurrentOwner() {
    let currentOwner = ownerID()
    guard currentOwner != boundOwnerID else { return }
    boundOwnerID = currentOwner
    didCountLaunch = false
    didResume = false
    guard let currentOwner,
      let data = defaults.data(forKey: Self.stateKey + "." + currentOwner),
      let decoded = try? JSONDecoder().decode(FirstRunState.self, from: data),
      decoded.version == FirstRunState.currentVersion
    else {
      state = .inactive
      return
    }
    state = decoded
  }
}
