import AppKit
import Foundation

extension SBOnboardingModel {
  var scenarioPageContext: OnboardingScenarioPageContext {
    OnboardingScenarioPageContext(name: displayName, dates: scenarioDates, nonce: scenarioPageNonce)
  }

  func recordBeatExit(
    skipped: Bool,
    permission: String? = nil,
    granted: Bool? = nil,
    detection: String? = nil
  ) {
    guard !beatExitRecorded else { return }
    beatExitRecorded = true
    if let permission, let granted {
      OnboardingScenarioJournal().append(
        who: "system",
        text: "Permission \(permission): \(granted ? "granted" : "not granted")")
    }
    AnalyticsManager.shared.onboardingBeatCompleted(
      beat: String(describing: step),
      index: step.rawValue,
      elapsedMs: Int(Date().timeIntervalSince(beatStartedAt) * 1_000),
      skipped: skipped,
      permission: permission,
      granted: granted,
      detection: detection
    )
  }

  /// The Screen Recording answer ends the permission phase and nothing else. Leaving Omi is the
  /// user's own click on "Open the order page", so the browser never appears over a sentence they
  /// were still reading, and the thread says what will happen there before it happens.
  func answerSeePermission() {
    guard step == .see, seePhase == .permission else { return }
    let granted = scrState == .on
    let answer = granted ? "Allowed" : "Skip for now"
    thread.append(Msg(isOmi: false, text: answer))
    OnboardingScenarioJournal().append(who: "user", text: answer)
    seePhase = .openPage
    persistScenarioProgress()
    appendScenarioOmiLine(
      "When you open it, watch the top of your screen: a card will show up there. Answer it, and I'll bring you back here."
    )
  }

  /// The click that leaves Omi. Also the retry when the browser never came up.
  func openOrderPage() {
    guard step == .see, seePhase == .openPage || seePhase == .waitingForPage else { return }
    if seePhase == .openPage {
      thread.append(Msg(isOmi: false, text: "Open the order page"))
      OnboardingScenarioJournal().append(who: "user", text: "Open the order page")
    }
    do {
      _ = try OnboardingScenarioPageRenderer.writeAndOpen(
        fileName: "order.html",
        context: scenarioPageContext,
        directory: scenarioPageDirectory,
        locator: scenarioPageLocator,
        open: scenarioPageOpener
      )
      OnboardingScenarioJournal().append(who: "system", text: "Opened the local order page")
    } catch {
      log("Scenario onboarding could not open order page: \(error.localizedDescription)")
      OnboardingScenarioJournal().append(who: "system", text: "The local order page could not be opened")
    }
    seePhase = .waitingForPage
    persistScenarioProgress()
    startOrderPageDetection()
  }

  /// Watch for the page to become frontmost, then move to the card beat and fire the card at once.
  /// The card must not wait for the card beat's sentence to finish streaming into a window the
  /// browser is now covering; the page's own cue says "watch the top of your screen", so the top of
  /// the screen has to answer within a poll, not a paragraph.
  func startOrderPageDetection() {
    let granted = scrState == .on
    scenarioDetectionTask?.cancel()
    scenarioDetectionTask = Task { [weak self] in
      guard let self else { return }
      let result = await OnboardingScenarioDetector.waitForTitle(
        token: OnboardingScenarioTitleTransport.orderToken,
        maximumPolls: granted ? 40 : 6,
        useTimedFallback: !granted,
        undetectableAfterPolls: 6,
        poll: {
          let info = await WindowMonitor.getActiveWindowInfoAsync()
          return OnboardingScenarioWindowObservation(
            title: info.windowTitle,
            bundleID: NSWorkspace.shared.frontmostApplication?.bundleIdentifier)
        },
        wait: { try? await Task.sleep(nanoseconds: 500_000_000) }
      )
      guard !Task.isCancelled, self.step == .see, self.seePhase == .waitingForPage else { return }
      if result == .timedFallback {
        DesktopDiagnosticsManager.shared.recordFallback(
          area: "onboarding_detection",
          from: "window_title",
          to: "timed_advance",
          reason: "title_unavailable",
          outcome: .degraded)
      }
      OnboardingScenarioJournal().append(
        who: "system",
        text: result == .timedFallback ? "Order page detection used the timed fallback" : "Order page became frontmost"
      )
      self.advance(
        userAnswer: nil,
        to: .card,
        skipped: !granted,
        permission: "screen_recording",
        granted: granted,
        detection: result.analyticsValue
      )
      self.presentScenarioCard()
    }
  }

  /// How long the scripted card waits at the notch. Long, because the user is reading a page in
  /// another app and the card is the only piece of Omi they can see; a card that leaves while they
  /// are still looking for it is the lesson taught backwards.
  static let scenarioCardTimeout: UInt64 = 90_000_000_000

  func presentScenarioCard() {
    guard step == .card, cardPhase == .waitingForAction, !scenarioCardPresented else { return }
    let manager = FloatingControlBarManager.shared
    let hasAnotherCard = manager.currentNotificationAssistantID.map { $0 != "onboarding_scenario" } ?? false
    guard appState.meetingDetector?.isMeetingActive != true, !hasAnotherCard else {
      scenarioCardTimeoutTask?.cancel()
      scenarioCardTimeoutTask = Task { [weak self] in
        try? await Task.sleep(nanoseconds: 5_000_000_000)
        guard !Task.isCancelled else { return }
        self?.presentScenarioCard()
      }
      return
    }
    let dueDate = scenarioDates.atNineAM(scenarioDates.returnDate)
    guard
      let ownerID = RuntimeOwnerIdentity.currentOwnerId(),
      let authorization = RuntimeOwnerIdentity.captureAuthorizationSnapshot(expectedOwnerID: ownerID)
    else {
      showScenarioNotificationsPrompt(
        userAnswer: nil, preface: "I couldn't show the card just now; the next one will land.")
      return
    }
    scenarioCardPresented = true
    NotificationService.shared.sendNotification(
      ownerID: ownerID,
      title: "Aurora desk lamp",
      message: "Return window closes \(scenarioPageContext.returnDateText)",
      assistantId: "onboarding_scenario",
      action: .onboardingRemindMe(
        taskTitle: "Return the desk lamp if it's not right",
        dueDate: dueDate),
      respectFrequency: false,
      isPersistent: true,
      authorizationSnapshot: authorization
    )
    OnboardingScenarioJournal().append(who: "system", text: "Presented the scripted notch card")
    scenarioCardTimeoutTask?.cancel()
    scenarioCardTimeoutTask = Task { [weak self] in
      try? await Task.sleep(nanoseconds: Self.scenarioCardTimeout)
      guard let self, !Task.isCancelled, self.step == .card, self.cardPhase == .waitingForAction else { return }
      FloatingControlBarManager.shared.dismissNotifications(assistantID: "onboarding_scenario", kind: .timeout)
      OnboardingScenarioJournal().append(who: "system", text: "The scripted card timed out")
      // The user is still somewhere else. Bring them back with the thread explaining what happened,
      // rather than advancing silently in a window they cannot see.
      self.scenarioReturnToOmi()
      self.showScenarioNotificationsPrompt(
        userAnswer: nil,
        preface: "That one got out of the way on its own; cards do that. There'll be more.")
    }
  }

  func handleScenarioCardAction(_ action: String) {
    guard step == .card,
      cardPhase == .waitingForAction,
      ["onboarding_remind_me", "onboarding_not_now"].contains(action)
    else { return }
    scenarioCardTimeoutTask?.cancel()
    if action == "onboarding_remind_me" {
      let title = "Return the desk lamp if it's not right"
      let dueDate = scenarioDates.atNineAM(scenarioDates.returnDate)
      Task { [weak self] in
        guard let self, let ownerID = RuntimeOwnerIdentity.currentOwnerId(),
          let authorization = RuntimeOwnerIdentity.captureAuthorizationSnapshot(expectedOwnerID: ownerID)
        else { return }
        if await OnboardingScenarioWrites.createActionItem(
          title: title, dueDate: dueDate, ownerID: ownerID, authorization: authorization)
        {
          guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else {
            OnboardingScenarioJournal().append(who: "system", text: "Owner changed; aborted reminder result")
            return
          }
          self.scenarioTaskChips.append(title)
          OnboardingScenarioJournal().append(who: "system", text: "Created task: \(title)")
          self.presentReminderConfirmationCard()
        } else {
          OnboardingScenarioJournal().append(who: "system", text: "The reminder task could not be saved")
        }
      }
      showScenarioNotificationsPrompt(userAnswer: "Remind me", preface: nil)
    } else {
      showScenarioNotificationsPrompt(userAnswer: "Not now", preface: nil)
    }
    // The tap was on Omi's own card, so the user's attention is already here. Coming back to the
    // thread is the promise the card beat made ("Answer it, and I'll bring you back").
    scenarioReturnToOmi()
  }

  private func presentReminderConfirmationCard() {
    guard
      let ownerID = RuntimeOwnerIdentity.currentOwnerId(),
      let authorization = RuntimeOwnerIdentity.captureAuthorizationSnapshot(expectedOwnerID: ownerID)
    else { return }
    let formatter = DateFormatter()
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.dateFormat = "EEEE, h:mm a"
    let dueDate = scenarioDates.atNineAM(scenarioDates.returnDate)
    NotificationService.shared.sendNotification(
      ownerID: ownerID,
      title: "✓ Reminder set",
      message: formatter.string(from: dueDate),
      assistantId: "onboarding_scenario",
      respectFrequency: false,
      isPersistent: false,
      authorizationSnapshot: authorization
    )
  }

  private func showScenarioNotificationsPrompt(userAnswer: String?, preface: String?) {
    guard step == .card, cardPhase == .waitingForAction else { return }
    if let userAnswer {
      thread.append(Msg(isOmi: false, text: userAnswer))
      OnboardingScenarioJournal().append(who: "user", text: userAnswer)
    }
    cardPhase = .notifications
    persistScenarioProgress()
    let ask =
      "To reach you when I'm not in front, I'll ask for notifications. The notch works without it; the lock screen doesn't."
    appendScenarioOmiLine(preface.map { "\($0) \(ask)" } ?? ask)
    precheckPerm("notifications")
  }

  func answerCardNotifications() {
    let granted = notifState == .on
    advance(
      userAnswer: granted ? "Allowed" : "Not now",
      to: .talk,
      skipped: !granted,
      permission: "notifications",
      granted: granted
    )
  }

  func answerTalkMicrophone() {
    guard step == .talk, talkPhase == .microphone else { return }
    let answer = micState == .on ? "Allowed" : "Skip for now"
    thread.append(Msg(isOmi: false, text: answer))
    OnboardingScenarioJournal().append(who: "user", text: answer)
    talkPhase = .shortcut
    persistScenarioProgress()
    appendScenarioOmiLine("And to talk to me hands-free? Choose one, or pick Custom to hold your own modifier key.")
    armShortcutSummon()
  }

  func finishTalkShortcut() {
    guard step == .talk, talkPhase == .shortcut, shortcutPicked, shortcutPressed else { return }
    UserDefaults.standard.set(true, forKey: Self.shortcutsCompletedKey)
    disarmShortcutSummon()
    talkPhase = .demo
    persistScenarioProgress()
    OnboardingScenarioJournal().append(who: "user", text: "Talk shortcut selected")
    appendScenarioOmiLine(
      "Hold \(voiceChordTokens.joined(separator: " ")) and say: 'when does this arrive?' Let go when you're done.")
    startScreenDemo()
  }

  func finishTalkDemo() {
    guard step == .talk, talkPhase == .demo else { return }
    advance(
      userAnswer: "Continue",
      to: .write,
      skipped: micState != .on,
      permission: "microphone",
      granted: micState == .on
    )
  }

  /// The click that leaves Omi for the note. Also the retry when the browser never came up.
  func openComposePage() {
    guard step == .write, writePhase == .intro || writePhase == .waitingForSend else { return }
    if writePhase == .intro {
      thread.append(Msg(isOmi: false, text: "Open the note"))
      OnboardingScenarioJournal().append(who: "user", text: "Open the note")
    }
    scenarioWriteDetectionTimedOut = false
    do {
      _ = try OnboardingScenarioPageRenderer.writeAndOpen(
        fileName: "compose.html",
        context: scenarioPageContext,
        directory: scenarioPageDirectory,
        locator: scenarioPageLocator,
        open: scenarioPageOpener
      )
      OnboardingScenarioJournal().append(who: "system", text: "Opened the local note to Sam")
    } catch {
      log("Scenario onboarding could not open compose page: \(error.localizedDescription)")
      scenarioWriteDetectionTimedOut = true
      return
    }
    writePhase = .waitingForSend
    persistScenarioProgress()
    startComposeDetection()
  }

  /// Five minutes of polling: a note takes as long as the user wants it to, and the escape hatches
  /// ("Open it again", "Skip for now") are on screen the whole time, so the timeout only changes a
  /// caption. When Send lands, Omi comes back on its own; the page says so.
  static let composeDetectionMaximumPolls = 600

  func startComposeDetection() {
    guard step == .write, writePhase == .waitingForSend else { return }
    scenarioDetectionTask?.cancel()
    scenarioDetectionTask = Task { [weak self] in
      guard let self else { return }
      let result = await OnboardingScenarioDetector.waitForTitle(
        token: OnboardingScenarioTitleTransport.sentToken,
        nonce: self.scenarioPageNonce,
        requireBrowser: true,
        maximumPolls: Self.composeDetectionMaximumPolls,
        useTimedFallback: false,
        poll: {
          let info = await WindowMonitor.getActiveWindowInfoAsync()
          return OnboardingScenarioWindowObservation(
            title: info.windowTitle,
            bundleID: NSWorkspace.shared.frontmostApplication?.bundleIdentifier)
        },
        wait: { try? await Task.sleep(nanoseconds: 500_000_000) }
      )
      guard !Task.isCancelled, self.step == .write, self.writePhase == .waitingForSend else { return }
      guard case .matched(let title) = result,
        let note = OnboardingScenarioTitleTransport.note(from: title, nonce: self.scenarioPageNonce)
      else {
        self.scenarioWriteDetectionTimedOut = true
        return
      }
      OnboardingScenarioJournal().append(who: "system", text: "Detected the sent local note")
      self.applyScenarioNote(note)
      self.scenarioReturnToOmi()
    }
  }

  func retryWriteDetection() {
    openComposePage()
  }

  func applyScenarioNote(_ note: String) {
    guard step == .write else { return }
    scenarioWriteNote = note
    let effects = OnboardingScenarioNotePlanner.effects(note: note, prefilledNote: scenarioPageContext.prefilledNote)
    scenarioMemoryChips = []
    scenarioTaskChips = []
    writePhase = .review
    scenarioProposedTaskTitle = effects.taskTitle
    if let proposed = effects.taskTitle { scenarioTaskChips = [proposed] }
    persistScenarioProgress()
    scenarioWritesPending = true
    OnboardingScenarioJournal().append(who: "user", text: note)
    Task { [weak self] in
      guard let self, let ownerID = RuntimeOwnerIdentity.currentOwnerId(),
        let authorization = RuntimeOwnerIdentity.captureAuthorizationSnapshot(expectedOwnerID: ownerID)
      else { return }
      defer { self.scenarioWritesPending = false }
      for memory in effects.memories {
        let receipt = "memory:\(memory)"
        if self.scenarioWriteReceipts.contains(receipt) { continue }
        guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else {
          OnboardingScenarioJournal().append(who: "system", text: "Owner changed; aborted note writes")
          return
        }
        if await OnboardingScenarioWrites.createMemory(
          memory, ownerID: ownerID, authorization: authorization)
        {
          guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else { return }
          self.scenarioWriteReceipts.insert(receipt)
          self.persistScenarioProgress()
          self.scenarioMemoryChips.append(memory)
          OnboardingScenarioJournal().append(who: "system", text: "Created memory: \(memory)")
        }
      }
    }
  }

  /// "Looks right" is the explicit gesture that turns the note's commitment into a task
  /// (INV-TASK-2: capture proposes; only a user gesture writes a task). The memories were written on
  /// detection because they are the user's own words; the task waits for this tap.
  func confirmScenarioWrites() {
    guard step == .write, writePhase == .review else { return }
    if let taskTitle = scenarioProposedTaskTitle, !scenarioWriteReceipts.contains("task:\(taskTitle)"),
      let ownerID = RuntimeOwnerIdentity.currentOwnerId(),
      let authorization = RuntimeOwnerIdentity.captureAuthorizationSnapshot(expectedOwnerID: ownerID)
    {
      let dueDate = scenarioDates.atNineAM(scenarioDates.deliveryDate)
      Task { [weak self] in
        guard let self, RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else { return }
        if await OnboardingScenarioWrites.createActionItem(
          title: taskTitle, dueDate: dueDate, ownerID: ownerID, authorization: authorization)
        {
          guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else { return }
          self.scenarioWriteReceipts.insert("task:\(taskTitle)")
          self.persistScenarioProgress()
          OnboardingScenarioJournal().append(who: "system", text: "Created task: \(taskTitle)")
        }
      }
    }
    advance(userAnswer: "Looks right", to: .ready, detection: "title_match")
  }

  /// The escape when the browser hand-off never comes back (no default browser, a closed tab).
  /// Never gate a beat on something the app cannot observe.
  func skipWriteBeat() {
    guard step == .write, writePhase != .review else { return }
    scenarioDetectionTask?.cancel()
    OnboardingScenarioJournal().append(who: "user", text: "Skip for now")
    advance(userAnswer: "Skip for now", to: .ready, skipped: true, detection: "timeout")
  }

  func requestScenarioWriteFix() {
    guard step == .write, writePhase == .review else { return }
    OnboardingScenarioJournal().append(who: "user", text: "fix_requested")
    advance(userAnswer: "Fix something", to: .ready, detection: "title_match")
  }

  private func appendScenarioOmiLine(_ text: String) {
    thread.append(Msg(isOmi: true, text: text))
    OnboardingScenarioJournal().append(who: "omi", text: text)
    showWidget = true
  }
}
