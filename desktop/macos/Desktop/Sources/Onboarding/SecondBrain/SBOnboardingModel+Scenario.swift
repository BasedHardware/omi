import Foundation

extension SBOnboardingModel {
  var scenarioPageContext: OnboardingScenarioPageContext {
    OnboardingScenarioPageContext(name: displayName, dates: scenarioDates)
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

  func answerSee() {
    let granted = scrState == .on
    let defaults = UserDefaults.standard
    if !defaults.bool(forKey: OnboardingScenarioDefaults.pageAOpenedKey) {
      do {
        _ = try OnboardingScenarioPageRenderer.writeAndOpen(
          fileName: "order.html",
          context: scenarioPageContext,
          directory: scenarioPageDirectory
        )
        defaults.set(true, forKey: OnboardingScenarioDefaults.pageAOpenedKey)
        OnboardingScenarioJournal().append(who: "system", text: "Opened the local order page")
      } catch {
        log("Scenario onboarding could not open order page: \(error.localizedDescription)")
        OnboardingScenarioJournal().append(who: "system", text: "The local order page could not be opened")
      }
    }

    scenarioDetectionTask?.cancel()
    scenarioDetectionTask = Task { [weak self] in
      guard let self else { return }
      let result = await OnboardingScenarioDetector.waitForTitle(
        token: OnboardingScenarioTitleTransport.orderToken,
        maximumPolls: granted ? 40 : 6,
        useTimedFallback: !granted,
        undetectableAfterPolls: 6,
        poll: { await WindowMonitor.getActiveWindowInfoAsync().windowTitle },
        wait: { try? await Task.sleep(nanoseconds: 500_000_000) }
      )
      guard !Task.isCancelled, self.step == .see else { return }
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
        userAnswer: granted ? "Allowed" : "Skip for now",
        to: .card,
        skipped: !granted,
        permission: "screen_recording",
        granted: granted,
        detection: result.analyticsValue
      )
    }
  }

  func presentScenarioCard() {
    guard step == .card, cardPhase == .waitingForAction else { return }
    let dueDate = scenarioDates.atNineAM(scenarioDates.returnDate)
    guard
      let ownerID = RuntimeOwnerIdentity.currentOwnerId(),
      let authorization = RuntimeOwnerIdentity.captureAuthorizationSnapshot(expectedOwnerID: ownerID)
    else {
      showScenarioNotificationsPrompt(actionText: "Card unavailable")
      return
    }
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
      try? await Task.sleep(nanoseconds: 25_000_000_000)
      guard let self, !Task.isCancelled, self.step == .card, self.cardPhase == .waitingForAction else { return }
      FloatingControlBarManager.shared.dismissCurrentNotification()
      self.showScenarioNotificationsPrompt(actionText: "Card timed out")
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
      OnboardingScenarioJournal().append(who: "user", text: "Remind me")
      Task { [weak self] in
        guard let self else { return }
        if await OnboardingScenarioWrites.createActionItem(title: title, dueDate: dueDate) {
          self.scenarioTaskChips.append(title)
          OnboardingScenarioJournal().append(who: "system", text: "Created task: \(title)")
          self.presentReminderConfirmationCard()
        } else {
          OnboardingScenarioJournal().append(who: "system", text: "The reminder task could not be saved")
        }
      }
      showScenarioNotificationsPrompt(actionText: nil)
    } else {
      showScenarioNotificationsPrompt(actionText: "Not now")
    }
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

  private func showScenarioNotificationsPrompt(actionText: String?) {
    guard step == .card, cardPhase == .waitingForAction else { return }
    if let actionText {
      thread.append(Msg(isOmi: false, text: actionText))
      OnboardingScenarioJournal().append(who: "user", text: actionText)
    }
    cardPhase = .notifications
    appendScenarioOmiLine(
      "To reach you when I'm not in front, I'll ask for notifications. The notch works without it; the lock screen doesn't."
    )
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
    appendScenarioOmiLine("And to talk to me hands-free? Choose one, or pick Custom to hold your own modifier key.")
    armShortcutSummon()
  }

  func finishTalkShortcut() {
    guard step == .talk, talkPhase == .shortcut, shortcutPicked, shortcutPressed else { return }
    UserDefaults.standard.set(true, forKey: Self.shortcutsCompletedKey)
    disarmShortcutSummon()
    talkPhase = .demo
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

  func openComposePageAndWaitForSend() {
    guard step == .write, writePhase == .waitingForSend else { return }
    do {
      _ = try OnboardingScenarioPageRenderer.writeAndOpen(
        fileName: "compose.html",
        context: scenarioPageContext,
        directory: scenarioPageDirectory
      )
      OnboardingScenarioJournal().append(who: "system", text: "Opened the local note to Sam")
    } catch {
      log("Scenario onboarding could not open compose page: \(error.localizedDescription)")
      scenarioWriteDetectionTimedOut = true
      return
    }
    scenarioDetectionTask?.cancel()
    scenarioDetectionTask = Task { [weak self] in
      guard let self else { return }
      let result = await OnboardingScenarioDetector.waitForTitle(
        token: OnboardingScenarioTitleTransport.sentToken,
        maximumPolls: 120,
        useTimedFallback: false,
        poll: { await WindowMonitor.getActiveWindowInfoAsync().windowTitle },
        wait: { try? await Task.sleep(nanoseconds: 500_000_000) }
      )
      guard !Task.isCancelled, self.step == .write else { return }
      guard case .matched(let title) = result,
        let note = OnboardingScenarioTitleTransport.note(from: title)
      else {
        self.scenarioWriteDetectionTimedOut = true
        return
      }
      OnboardingScenarioJournal().append(who: "system", text: "Detected the sent local note")
      self.applyScenarioNote(note)
    }
  }

  func retryWriteDetection() {
    scenarioWriteDetectionTimedOut = false
    openComposePageAndWaitForSend()
  }

  func applyScenarioNote(_ note: String) {
    guard step == .write else { return }
    scenarioWriteNote = note
    let effects = OnboardingScenarioNotePlanner.effects(note: note, prefilledNote: scenarioPageContext.prefilledNote)
    scenarioMemoryChips = []
    scenarioTaskChips = []
    writePhase = .review
    scenarioWritesPending = true
    OnboardingScenarioJournal().append(who: "user", text: note)
    Task { [weak self] in
      guard let self else { return }
      defer { self.scenarioWritesPending = false }
      for memory in effects.memories {
        if await OnboardingScenarioWrites.createMemory(memory) {
          self.scenarioMemoryChips.append(memory)
          OnboardingScenarioJournal().append(who: "system", text: "Created memory: \(memory)")
        }
      }
      if let taskTitle = effects.taskTitle,
        await OnboardingScenarioWrites.createActionItem(
          title: taskTitle,
          dueDate: self.scenarioDates.atNineAM(self.scenarioDates.deliveryDate))
      {
        self.scenarioTaskChips.append(taskTitle)
        OnboardingScenarioJournal().append(who: "system", text: "Created task: \(taskTitle)")
      }
    }
  }

  func confirmScenarioWrites() {
    guard step == .write, writePhase == .review else { return }
    advance(userAnswer: "Looks right", to: .ready, detection: "title_match")
  }

  /// The escape when the browser hand-off never comes back (no default browser, a closed tab).
  /// Never gate a beat on something the app cannot observe.
  func skipWriteBeat() {
    guard step == .write, writePhase == .waitingForSend else { return }
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
