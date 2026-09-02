import AppKit
import Foundation

extension SBOnboardingModel {
  var scenarioPageContext: OnboardingScenarioPageContext {
    OnboardingScenarioPageContext(
      name: displayName, dates: scenarioDates, nonce: scenarioPageNonce, notePort: scenarioNotePort)
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
      "Say you just bought a lamp. Open the receipt, then look up: I'll leave you a card. Answer it and I'll bring you back."
    )
  }

  /// The click that leaves Omi. Also the retry when the browser never came up.
  func openOrderPage() {
    guard step == .see, seePhase == .openPage || seePhase == .waitingForPage else { return }
    if seePhase == .openPage {
      thread.append(Msg(isOmi: false, text: "Open the page"))
      OnboardingScenarioJournal().append(who: "user", text: "Open the page")
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
        poll: self.scenarioWindowObservation,
        wait: self.scenarioDetectionWait
      )
      guard !Task.isCancelled, self.step == .see, self.seePhase == .waitingForPage else { return }
      // The card beat is canned, so it goes ahead whatever detection said; what detection said is
      // still recorded truthfully. A timeout with Screen Recording on is a real signal (a browser
      // that never came up, a title we cannot read), not a page becoming frontmost.
      let journalLine: String
      switch result {
      case .matched:
        journalLine = "Order page became frontmost"
      case .timedFallback:
        DesktopDiagnosticsManager.shared.recordFallback(
          area: "onboarding_detection",
          from: "window_title",
          to: "timed_advance",
          reason: "title_unavailable",
          outcome: .degraded)
        journalLine = "Order page detection used the timed fallback"
      case .timedOut:
        DesktopDiagnosticsManager.shared.recordFallback(
          area: "onboarding_detection",
          from: "window_title",
          to: "timed_advance",
          reason: "title_never_matched",
          outcome: .degraded)
        journalLine = "Order page was not seen within 20 s; continuing to the card"
      }
      OnboardingScenarioJournal().append(who: "system", text: journalLine)
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

  /// Retries while a meeting or another card holds the notch: twelve × 5 s, one minute, then the
  /// beat gives up on the card and brings the user back with an explanation.
  static let scenarioCardBlockedRetryLimit = 12

  func presentScenarioCard() {
    guard step == .card, cardPhase == .waitingForAction, !scenarioCardPresented else { return }
    let manager = FloatingControlBarManager.shared
    // The notch window is ordinarily created by the signed-in Home start-up, which runs after
    // onboarding, and by the talk beat, which comes after this one. Without this the card beat's
    // one card is dropped ("window is not set up") while the page says a card is on its way.
    // `setup` is idempotent, so the later callers are unaffected.
    manager.setup(appState: appState, chatProvider: chatProvider)
    let hasAnotherCard = manager.currentNotificationAssistantID.map { $0 != "onboarding_scenario" } ?? false
    guard appState.meetingDetector?.isMeetingActive != true, !hasAnotherCard else {
      scenarioCardBlockedRetries += 1
      guard scenarioCardBlockedRetries <= Self.scenarioCardBlockedRetryLimit else {
        OnboardingScenarioJournal().append(who: "system", text: "The scripted card stayed blocked; skipped it")
        scenarioReturnToOmi()
        showScenarioNotificationsPrompt(
          userAnswer: nil,
          preface: "The top of your screen was busy, so that card will wait.")
        return
      }
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
        userAnswer: nil, preface: "I couldn't show the card just now.")
      return
    }
    scenarioCardPresented = true
    NotificationService.shared.sendNotification(
      ownerID: ownerID,
      title: "Aurora desk lamp",
      message: "Return window closes \(scenarioPageContext.returnDateText)",
      assistantId: "onboarding_scenario",
      kind: .insight,
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
        preface: "That card left on its own. They do that.")
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
        if let taskID = await OnboardingScenarioWrites.createActionItem(
          title: title, dueDate: dueDate, ownerID: ownerID, authorization: authorization)
        {
          guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else {
            OnboardingScenarioJournal().append(who: "system", text: "Owner changed; aborted reminder result")
            return
          }
          self.scenarioTaskChips.append(title)
          self.appendReceipt(.task(title))
          OnboardingScenarioJournal().append(who: "system", text: "Created task: \(title)")
          self.presentReminderConfirmationCard()
          await OnboardingScenarioWrites.journalTaskCard(
            taskID: taskID, title: title, chatProvider: self.chatProvider, ownerID: ownerID)
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

  /// The confirmation where the user is looking when they press Send: a card at the top of the
  /// browser, a beat before the window comes back. Same shape as the card beat's "✓ Reminder set".
  private func presentNoteKeptCard(_ effects: OnboardingScenarioNoteEffects) {
    guard
      let ownerID = RuntimeOwnerIdentity.currentOwnerId(),
      let authorization = RuntimeOwnerIdentity.captureAuthorizationSnapshot(expectedOwnerID: ownerID)
    else { return }
    let title: String
    let message: String
    if let taskTitle = effects.taskTitle {
      title = "✓ Task: \(taskTitle)"
      message = effects.personMemory == nil ? "" : "And a memory about Sam."
    } else if effects.memories.isEmpty {
      return
    } else {
      title = "✓ Remembered"
      message = "What you told Sam."
    }
    NotificationService.shared.sendNotification(
      ownerID: ownerID,
      title: title,
      message: message,
      assistantId: "onboarding_scenario",
      kind: effects.taskTitle == nil ? .memory : .task,
      respectFrequency: false,
      isPersistent: false,
      authorizationSnapshot: authorization
    )
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
      kind: .task,
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
      "Want me to reach you when Omi isn't open? That takes notifications."
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
    appendScenarioOmiLine("Pick a key to hold while you talk.")
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
      "Hold \(voiceChordTokens.joined(separator: " ")) and ask: when does it arrive? Let go when you're done.")
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
    guard scenarioNoteReceiver == nil else {
      renderAndOpenComposePage()
      return
    }
    Task { [weak self] in
      guard let self else { return }
      await self.startScenarioNoteReceiverIfNeeded()
      guard self.step == .write, self.writePhase == .intro || self.writePhase == .waitingForSend else { return }
      self.renderAndOpenComposePage()
    }
  }

  /// The note comes back over loopback. The receiver is bound to this model's nonce, lives only
  /// while the note page is open, and fires at most once; the page gets its port at render time.
  func startScenarioNoteReceiverIfNeeded() async {
    guard scenarioNoteReceiver == nil else { return }
    let receiver = OnboardingNoteReceiver(nonce: scenarioPageNonce)
    receiver.onNote = { [weak self] note in
      self?.receiveScenarioNote(note)
    }
    do {
      scenarioNotePort = try await receiver.start()
      scenarioNoteReceiver = receiver
    } catch {
      log("Scenario onboarding could not start the note receiver: \(error.localizedDescription)")
      OnboardingScenarioJournal().append(who: "system", text: "The note receiver could not start")
      scenarioNotePort = 0
    }
  }

  func stopScenarioNoteReceiver() {
    scenarioNoteReceiver?.stop()
    scenarioNoteReceiver = nil
    scenarioNotePort = 0
  }

  private func renderAndOpenComposePage() {
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
    scenarioWriteGuideChip(true)
    startComposeDetection()
  }

  func dismissWriteGuideChip() {
    scenarioWriteGuideChip(false)
  }

  /// The one piece of Omi the user can see from the browser. It says what to do and promises the
  /// return; the page's own banner says what Omi will keep. Persistent until Send, Skip, or Back.
  func presentWriteGuideChipOnNotch() {
    let manager = FloatingControlBarManager.shared
    manager.setup(appState: appState, chatProvider: chatProvider)
    guard let ownerID = RuntimeOwnerIdentity.currentOwnerId(),
      let authorization = RuntimeOwnerIdentity.captureAuthorizationSnapshot(expectedOwnerID: ownerID)
    else { return }
    manager.dismissNotifications(assistantID: FirstRunNotchCardIdentity.scenarioGuide, kind: .replaced)
    NotificationService.shared.sendNotification(
      ownerID: ownerID,
      title: "Send the note to Sam",
      message: "As is, or in your words. I'll bring you back.",
      assistantId: FirstRunNotchCardIdentity.scenarioGuide,
      respectFrequency: false,
      isPersistent: true,
      authorizationSnapshot: authorization
    )
  }

  func dismissWriteGuideChipOnNotch() {
    FloatingControlBarManager.shared.dismissNotifications(
      assistantID: FirstRunNotchCardIdentity.scenarioGuide, kind: .replaced)
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
        poll: self.scenarioWindowObservation,
        wait: self.scenarioDetectionWait
      )
      guard !Task.isCancelled, self.step == .write, self.writePhase == .waitingForSend else { return }
      guard case .matched = result else {
        self.scenarioWriteDetectionTimedOut = true
        return
      }
      OnboardingScenarioJournal().append(who: "system", text: "Saw the sent signal in the window title")
      // The beacon and the title change happen in the same click handler; give the beacon a
      // moment, then complete honestly without the note if it never arrived.
      await self.scenarioNoteGrace()
      guard !Task.isCancelled, self.step == .write, self.writePhase == .waitingForSend else { return }
      self.completeWriteBeatUnreadable()
    }
  }

  /// The note arrived over loopback: the one path that shows what Omi kept.
  func receiveScenarioNote(_ note: String) {
    guard step == .write, writePhase == .waitingForSend else { return }
    scenarioDetectionTask?.cancel()
    OnboardingScenarioJournal().append(who: "system", text: "Received the sent local note")
    stopScenarioNoteReceiver()
    // The kept card presented by `applyScenarioNote` replaces the guide chip in place; a separate
    // retraction first left the new card fighting the chip's collapse for the island's size.
    applyScenarioNote(note)
    if FloatingControlBarManager.shared.currentNotificationAssistantID == FirstRunNotchCardIdentity.scenarioGuide {
      dismissWriteGuideChip()
    }
    scenarioReturnToOmi()
  }

  /// Sent, but unreadable on this Mac. Nothing is written; the thread says so and offers Continue.
  private func completeWriteBeatUnreadable() {
    OnboardingScenarioJournal().append(who: "system", text: "The sent note never reached the receiver")
    stopScenarioNoteReceiver()
    dismissWriteGuideChip()
    scenarioWriteUnreadable = true
    scenarioMemoryChips = []
    scenarioTaskChips = []
    scenarioProposedTaskTitle = nil
    writePhase = .review
    persistScenarioProgress()
    thread.append(Msg(isOmi: false, text: "Sent"))
    OnboardingScenarioJournal().append(who: "user", text: "Sent")
    appendScenarioOmiLine(
      "I saw it go out, but the note didn't reach me. Nothing kept this time. My fault, not yours.")
    scenarioReturnToOmi()
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
    thread.append(Msg(isOmi: false, text: "Sent"))
    OnboardingScenarioJournal().append(who: "user", text: "Sent")
    appendScenarioOmiLine(
      effects.taskTitle == nil
        ? "Got it. Here's what I kept."
        : "Got it. You promised Sam a link, so that's a task. The rest I'll remember.")
    if let taskTitle = effects.taskTitle { appendReceipt(.task(taskTitle)) }
    presentNoteKeptCard(effects)
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
          self.appendReceipt(.memory(memory))
          OnboardingScenarioJournal().append(who: "system", text: "Created memory: \(memory)")
        }
      }
    }
  }

  /// "Looks right" is the explicit gesture that turns the note's commitment into a task
  /// (INV-TASK-2: capture proposes; only a user gesture writes a task). The memories were written on
  /// detection because they are the user's own words; the task waits for this tap. There is no
  /// second button: "Fix something" did nothing but skip the task, and a control that does nothing
  /// visible is a lie. Anything kept here can be edited in Tasks and Memories like everything else.
  func confirmScenarioWrites() {
    guard step == .write, writePhase == .review else { return }
    if let taskTitle = scenarioProposedTaskTitle, !scenarioWriteReceipts.contains("task:\(taskTitle)"),
      let ownerID = RuntimeOwnerIdentity.currentOwnerId(),
      let authorization = RuntimeOwnerIdentity.captureAuthorizationSnapshot(expectedOwnerID: ownerID)
    {
      let dueDate = scenarioDates.atNineAM(scenarioDates.deliveryDate)
      Task { [weak self] in
        guard let self, RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else { return }
        if let taskID = await OnboardingScenarioWrites.createActionItem(
          title: taskTitle, dueDate: dueDate, ownerID: ownerID, authorization: authorization)
        {
          guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else { return }
          self.scenarioWriteReceipts.insert("task:\(taskTitle)")
          self.persistScenarioProgress()
          OnboardingScenarioJournal().append(who: "system", text: "Created task: \(taskTitle)")
          await OnboardingScenarioWrites.journalTaskCard(
            taskID: taskID, title: taskTitle, chatProvider: self.chatProvider, ownerID: ownerID)
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
    // The chip comes down in `teardownStep(.write)`, which every exit from the beat runs.
    OnboardingScenarioJournal().append(who: "user", text: "Skip for now")
    advance(userAnswer: "Skip for now", to: .ready, skipped: true, detection: "timeout")
  }

  private func appendScenarioOmiLine(_ text: String) {
    thread.append(Msg(isOmi: true, text: text))
    OnboardingScenarioJournal().append(who: "omi", text: text)
    showWidget = true
  }
}
