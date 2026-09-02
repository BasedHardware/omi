import Foundation
import XCTest

@testable import Omi_Computer

private final class CardActionPayloadBox: @unchecked Sendable {
  private let lock = NSLock()
  private var payload: [String: String] = [:]

  func set(_ userInfo: [AnyHashable: Any]?) {
    lock.lock()
    payload = [
      "action": userInfo?["action"] as? String ?? "",
      "id": userInfo?["id"] as? String ?? "",
    ]
    lock.unlock()
  }

  func value(for key: String) -> String? {
    lock.lock()
    defer { lock.unlock() }
    return payload[key]
  }
}

@MainActor
final class OnboardingScenarioTests: XCTestCase {
  func testStepOrderAndSchemaThreeRestartRule() {
    XCTAssertEqual(SBOnboardingModel.Step.allCases, [.hello, .see, .card, .talk, .write, .ready])
    XCTAssertEqual(SBOnboardingModel.migratedResumeStepRaw(savedRaw: 17, storedSchema: 2), 0)
    XCTAssertEqual(
      SBOnboardingModel.migratedResumeStepRaw(
        savedRaw: SBOnboardingModel.Step.write.rawValue,
        storedSchema: 3),
      SBOnboardingModel.Step.write.rawValue)
  }

  func testSkipGateAndFirstUnaskedStepUseScenarioLayout() {
    XCTAssertFalse(SBOnboardingModel.canSkipOnboarding(step: .talk, shortcutsCompleted: true))
    XCTAssertFalse(SBOnboardingModel.canSkipOnboarding(step: .write, shortcutsCompleted: false))
    XCTAssertTrue(SBOnboardingModel.canSkipOnboarding(step: .write, shortcutsCompleted: true))
    for step in SBOnboardingModel.Step.allCases {
      XCTAssertEqual(SBOnboardingModel.firstUnaskedStep(from: step), step)
    }
  }

  func testPageRenderingSubstitutesPlaceholdersAndPreservesDetectionTokens() throws {
    let dates = OnboardingScenarioDates(
      deliveryDate: Date(timeIntervalSince1970: 1_757_030_400),
      returnDate: Date(timeIntervalSince1970: 1_757_116_800),
      saleEndDate: Date(timeIntervalSince1970: 1_757_289_600))
    let context = OnboardingScenarioPageContext(name: "David & Co", dates: dates)
    let buildDirectory = Bundle(for: OnboardingScenarioTests.self).bundleURL.deletingLastPathComponent()
    let siblingBundles =
      (try? FileManager.default.contentsOfDirectory(at: buildDirectory, includingPropertiesForKeys: nil)) ?? []
    let locator = OnboardingScenarioPageLocator(
      roots: siblingBundles.filter { $0.pathExtension == "bundle" })
    for (fileName, token) in [
      ("order.html", OnboardingScenarioTitleTransport.orderToken),
      ("compose.html", "Omi Welcome · Note to Sam"),
    ] {
      let source = try XCTUnwrap(locator.url(for: fileName))
      let rendered = OnboardingScenarioPageRenderer.render(
        template: try String(contentsOf: source, encoding: .utf8),
        context: context)
      XCTAssertTrue(rendered.contains(token))
      XCTAssertFalse(rendered.contains("{{"))
      XCTAssertTrue(rendered.contains("David &amp; Co") || fileName == "compose.html")
    }
  }

  func testSentSignalIsShortEnoughToSurviveTitleTruncationAndBoundToTheNonce() {
    let nonce = "8c1d2cfa-b9c9-4eb1-9115-7f0389d681a6"
    let title = OnboardingScenarioTitleTransport.sentTitle(nonce: nonce)
    XCTAssertEqual(title, "Omi Welcome · Sent · 8c1d2cfa")
    XCTAssertLessThan(title.count, 40, "the window server truncates long window names")
    XCTAssertTrue(OnboardingScenarioTitleTransport.isSentSignal(title, nonce: nonce))
    XCTAssertTrue(OnboardingScenarioTitleTransport.isSentSignal(title + " - Google Chrome", nonce: nonce))
    XCTAssertFalse(OnboardingScenarioTitleTransport.isSentSignal(title, nonce: "ffffffff-0000"))
    XCTAssertFalse(OnboardingScenarioTitleTransport.isSentSignal("Omi Welcome · Note to Sam", nonce: nonce))
    let context = OnboardingScenarioPageContext(
      name: "D", dates: OnboardingScenarioDates.make(), nonce: nonce, notePort: 4_242)
    XCTAssertEqual(context.replacements["{{nonceShort}}"], "8c1d2cfa")
    XCTAssertEqual(context.replacements["{{notePort}}"], "4242")
  }

  func testDeterministicNoteEffects() {
    let prefilled = "Hey Sam — intact commitment"
    let intact = OnboardingScenarioNotePlanner.effects(note: prefilled, prefilledNote: prefilled)
    XCTAssertEqual(intact.memories, ["Note to Sam: \(prefilled)", OnboardingScenarioNotePlanner.personMemory])
    XCTAssertEqual(intact.taskTitle, "Send Sam the lamp link")
    XCTAssertEqual(intact.personMemory, OnboardingScenarioNotePlanner.personMemory)

    // A rewrite that keeps the promise keeps the task; a rewrite that drops it gets no task, honestly.
    let rewritten = OnboardingScenarioNotePlanner.effects(
      note: "sam!! lamp arrived, will shoot you the LINK tmrw", prefilledNote: prefilled)
    XCTAssertEqual(rewritten.taskTitle, "Send Sam the lamp link")
    XCTAssertEqual(rewritten.personMemory, OnboardingScenarioNotePlanner.personMemory)
    let edited = OnboardingScenarioNotePlanner.effects(note: "Changed note", prefilledNote: prefilled)
    XCTAssertEqual(edited.memories, ["Note to Sam: Changed note"])
    XCTAssertNil(edited.taskTitle)
    XCTAssertNil(edited.personMemory)
    XCTAssertEqual(OnboardingScenarioNotePlanner.effects(note: "  ", prefilledNote: prefilled), .none)
  }

  func testJournalAppendsAndCapsAtTwoHundredEntries() throws {
    let suite = "OnboardingScenarioJournalTests-\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
    defer { defaults.removePersistentDomain(forName: suite) }
    var tick: TimeInterval = 0
    let journal = OnboardingScenarioJournal(defaults: defaults) {
      defer { tick += 1 }
      return Date(timeIntervalSince1970: tick)
    }
    for index in 0..<205 { journal.append(who: "system", text: "entry-\(index)") }
    let entries = journal.entries()
    XCTAssertEqual(entries.count, 200)
    XCTAssertEqual(entries.first?.text, "entry-5")
    XCTAssertEqual(entries.last?.text, "entry-204")
    XCTAssertEqual(entries.last?.who, "system")
    XCTAssertFalse(entries.last?.t.isEmpty ?? true)
  }

  func testEveryScenarioCardActionPostsStablePayloadAndDismisses() throws {
    let center = NotificationCenter()
    let cases: [(FloatingBarNotificationAction, FloatingBarCardActionDispatcher.Selection, String, String)] = [
      (.onboardingRemindMe(taskTitle: "Return lamp", dueDate: Date()), .primary, "onboarding_remind_me", ""),
      (.onboardingRemindMe(taskTitle: "Return lamp", dueDate: Date()), .secondary, "onboarding_not_now", ""),
      (.firstRunFocusReturn(projectTitle: "Launch"), .primary, "first_run_focus_return", ""),
      (.firstRunFocusReturn(projectTitle: "Launch"), .secondary, "first_run_focus_snooze", ""),
      (.contextReminder(reminderID: "rem-7"), .primary, "context_reminder_done", "rem-7"),
      (.contextReminder(reminderID: "rem-7"), .secondary, "context_reminder_snooze", "rem-7"),
      (.firstRunOpenSummary(conversationID: "conv-9"), .primary, "first_run_open_summary", "conv-9"),
    ]
    for (action, selection, expectedAction, expectedID) in cases {
      let descriptor = try XCTUnwrap(action.scenarioDescriptor)
      let payload = CardActionPayloadBox()
      var dismissed = false
      let token = center.addObserver(forName: .omiFloatingBarCardAction, object: nil, queue: nil) {
        payload.set($0.userInfo)
      }
      FloatingBarCardActionDispatcher.dispatch(
        descriptor: descriptor,
        selection: selection,
        center: center,
        dismiss: { dismissed = true })
      center.removeObserver(token)
      XCTAssertEqual(payload.value(for: "action"), expectedAction)
      XCTAssertEqual(payload.value(for: "id"), expectedID)
      XCTAssertTrue(dismissed)
    }
  }

  func testDetectorMatchesAndTimesOutWithoutWallClockWaiting() async {
    var titles: [String?] = ["Other", "Omi Welcome · Order confirmed · Norrland Goods"]
    var waits = 0
    let matched = await OnboardingScenarioDetector.waitForTitle(
      token: OnboardingScenarioTitleTransport.orderToken,
      maximumPolls: 4,
      useTimedFallback: false,
      poll: { OnboardingScenarioWindowObservation(title: titles.removeFirst(), bundleID: "com.apple.Safari") },
      wait: { waits += 1 })
    XCTAssertEqual(matched, .matched(title: "Omi Welcome · Order confirmed · Norrland Goods"))
    XCTAssertEqual(waits, 1)

    let timeout = await OnboardingScenarioDetector.waitForTitle(
      token: OnboardingScenarioTitleTransport.sentToken,
      maximumPolls: 3,
      useTimedFallback: false,
      poll: { OnboardingScenarioWindowObservation(title: "Other", bundleID: "com.apple.Safari") },
      wait: {})
    XCTAssertEqual(timeout, .timedOut)

    let fallback = await OnboardingScenarioDetector.waitForTitle(
      token: OnboardingScenarioTitleTransport.orderToken,
      maximumPolls: 40,
      useTimedFallback: false,
      undetectableAfterPolls: 3,
      poll: { OnboardingScenarioWindowObservation(title: nil, bundleID: nil) },
      wait: {})
    XCTAssertEqual(fallback, .timedFallback)

    let nonce = "nonce-123"
    let sentTitle = "Omi Welcome · Sent · \(nonce) · hello"
    let nonBrowser = await OnboardingScenarioDetector.waitForTitle(
      token: OnboardingScenarioTitleTransport.sentToken,
      nonce: nonce,
      requireBrowser: true,
      maximumPolls: 1,
      useTimedFallback: false,
      poll: { OnboardingScenarioWindowObservation(title: sentTitle, bundleID: "com.apple.TextEdit") },
      wait: {})
    XCTAssertEqual(nonBrowser, .timedOut)
  }

  // MARK: - Hand-offs out of Omi and back

  @MainActor
  private func scenarioModel(opened: OpenedBox, returned: ReturnedBox) -> SBOnboardingModel {
    let model = SBOnboardingModel(appState: AppState(), chatProvider: ChatProvider(), onComplete: nil)
    let buildDirectory = Bundle(for: OnboardingScenarioTests.self).bundleURL.deletingLastPathComponent()
    let siblingBundles =
      (try? FileManager.default.contentsOfDirectory(at: buildDirectory, includingPropertiesForKeys: nil)) ?? []
    model.scenarioPageLocator = OnboardingScenarioPageLocator(
      roots: siblingBundles.filter { $0.pathExtension == "bundle" })
    model.scenarioPageDirectory = FileManager.default.temporaryDirectory
      .appendingPathComponent("omi-scenario-tests-\(UUID().uuidString)", isDirectory: true)
    model.scenarioPageOpener = { url in
      opened.urls.append(url)
      return true
    }
    model.scenarioReturnToOmi = { returned.count += 1 }
    model.scenarioWriteGuideChip = { present in if present { returned.chips += 1 } else { returned.chipsDown += 1 } }
    return model
  }

  @MainActor
  func testScreenRecordingAnswerNeverOpensTheBrowser() {
    let opened = OpenedBox()
    let returned = ReturnedBox()
    let model = scenarioModel(opened: opened, returned: returned)
    model.step = .see
    model.seePhase = .permission
    model.scrState = .on

    model.answerSeePermission()

    XCTAssertEqual(model.seePhase, .openPage, "the permission answer ends at the offer, not in the browser")
    XCTAssertTrue(opened.urls.isEmpty, "nothing may leave Omi on a permission answer")
    XCTAssertEqual(model.step, .see)
    XCTAssertEqual(model.thread.last?.isOmi, true)
    XCTAssertTrue(model.thread.last?.text.contains("bring you back") == true)
    XCTAssertEqual(
      model.permissionKey(for: .see), nil,
      "once answered, a late Screen Recording grant must not re-answer the beat")
  }

  @MainActor
  func testOpenOrderPageIsTheOnlyThingThatOpensTheBrowser() {
    let opened = OpenedBox()
    let returned = ReturnedBox()
    let model = scenarioModel(opened: opened, returned: returned)
    model.step = .see
    model.seePhase = .openPage

    model.openOrderPage()

    XCTAssertEqual(opened.urls.map(\.lastPathComponent), ["order.html"])
    XCTAssertEqual(model.seePhase, .waitingForPage)
    XCTAssertEqual(model.thread.last?.text, "Open the page")
    XCTAssertNotNil(model.scenarioDetectionTask, "the click starts the watch for the page")
    model.scenarioDetectionTask?.cancel()

    // A retry from the waiting phase opens again without a second user bubble.
    model.openOrderPage()
    XCTAssertEqual(opened.urls.count, 2)
    XCTAssertEqual(model.thread.filter { $0.text == "Open the page" }.count, 1)
    model.scenarioDetectionTask?.cancel()
  }

  @MainActor
  func testCardAnswerBringsOmiBackAndKeepsTheReceiptThroughTheNotificationsAsk() {
    let opened = OpenedBox()
    let returned = ReturnedBox()
    let model = scenarioModel(opened: opened, returned: returned)
    model.step = .card
    model.cardPhase = .waitingForAction

    model.handleScenarioCardAction("onboarding_not_now")

    XCTAssertEqual(returned.count, 1, "answering Omi's own card is the moment Omi comes back")
    XCTAssertEqual(model.cardPhase, .notifications)
    XCTAssertTrue(model.thread.contains { !$0.isOmi && $0.text == "Not now" })
    XCTAssertTrue(model.thread.last?.text.contains("notifications") == true)
    XCTAssertTrue(opened.urls.isEmpty)

    // A second answer is inert: the card is gone and the ask is already on screen.
    model.handleScenarioCardAction("onboarding_remind_me")
    XCTAssertEqual(returned.count, 1)
  }

  @MainActor
  func testWriteBeatWaitsForTheClickAndReturnsAfterSend() async {
    let opened = OpenedBox()
    let returned = ReturnedBox()
    let model = scenarioModel(opened: opened, returned: returned)
    model.step = .write
    model.writePhase = .intro

    XCTAssertTrue(opened.urls.isEmpty, "the write beat's message opens nothing")
    await model.startScenarioNoteReceiverIfNeeded()
    XCTAssertNotEqual(model.scenarioNotePort, 0, "the page needs a port to beacon to")
    model.openComposePage()
    XCTAssertEqual(opened.urls.map(\.lastPathComponent), ["compose.html"])
    XCTAssertEqual(model.writePhase, .waitingForSend)
    XCTAssertEqual(model.thread.last?.text, "Open the note")
    model.scenarioDetectionTask?.cancel()

    // Skip is available from the offer and from the wait, never from the review.
    model.writePhase = .review
    model.skipWriteBeat()
    XCTAssertEqual(model.step, .write)
    XCTAssertEqual(returned.count, 0, "nothing summons Omi until Send is seen")
  }

  @MainActor
  func testSendSeenInTheBrowserWritesTheNoteAndBringsOmiBackExactlyOnce() async throws {
    let opened = OpenedBox()
    let returned = ReturnedBox()
    let model = scenarioModel(opened: opened, returned: returned)
    model.step = .write
    model.writePhase = .intro
    model.scenarioWindowObservation = {
      OnboardingScenarioWindowObservation(title: "Omi Welcome · Note to Sam", bundleID: "com.google.Chrome")
    }
    model.scenarioDetectionWait = {}
    await model.startScenarioNoteReceiverIfNeeded()
    model.openComposePage()
    XCTAssertEqual(model.writePhase, .waitingForSend)

    // The note arrives over loopback, not through the title.
    model.receiveScenarioNote("Hey Sam — lamp is great")

    XCTAssertEqual(model.writePhase, .review)
    XCTAssertEqual(model.scenarioWriteNote, "Hey Sam — lamp is great")
    XCTAssertEqual(returned.count, 1, "the note arriving is the one moment the write beat summons Omi")
    XCTAssertTrue(model.thread.contains { !$0.isOmi && $0.text == "Sent" })
    XCTAssertTrue(
      model.thread.last?.isOmi == true && model.thread.last?.text.contains("kept") == true,
      "the window comes back with Omi already explaining what it kept")
    XCTAssertFalse(model.scenarioWriteUnreadable)
    XCTAssertEqual(
      returned.chipsDown, 0,
      "the kept card replaces the guide chip in place; no separate retraction races the new card's size")

    // A second delivery is inert.
    model.receiveScenarioNote("again")
    XCTAssertEqual(returned.count, 1)
    model.streamTask?.cancel()
  }

  @MainActor
  func testSentSignalWithoutTheNoteCompletesHonestlyWithNothingKept() async throws {
    let opened = OpenedBox()
    let returned = ReturnedBox()
    let model = scenarioModel(opened: opened, returned: returned)
    model.step = .write
    model.writePhase = .waitingForSend
    let polls = PollBox()
    let sent = OnboardingScenarioTitleTransport.sentTitle(nonce: model.scenarioPageNonce)
    model.scenarioWindowObservation = {
      polls.count += 1
      return OnboardingScenarioWindowObservation(
        title: polls.count < 3 ? "Omi Welcome · Note to Sam" : sent, bundleID: "com.google.Chrome")
    }
    model.scenarioDetectionWait = {}
    model.scenarioNoteGrace = {}

    model.startComposeDetection()
    let detection = try XCTUnwrap(model.scenarioDetectionTask)
    await detection.value

    XCTAssertEqual(polls.count, 3)
    XCTAssertEqual(model.writePhase, .review)
    XCTAssertTrue(model.scenarioWriteUnreadable)
    XCTAssertTrue(model.scenarioMemoryChips.isEmpty && model.scenarioTaskChips.isEmpty)
    XCTAssertEqual(returned.count, 1, "the user still comes back to Omi, with the truth")
    XCTAssertTrue(model.thread.last?.text.contains("Nothing kept") == true)
  }

  @MainActor
  func testSendNeverSeenLeavesTheEscapesAndNeverSummonsOmi() async throws {
    let opened = OpenedBox()
    let returned = ReturnedBox()
    let model = scenarioModel(opened: opened, returned: returned)
    model.step = .write
    model.writePhase = .intro
    model.scenarioWindowObservation = {
      OnboardingScenarioWindowObservation(title: "Omi Welcome · Note to Sam", bundleID: "com.google.Chrome")
    }
    model.scenarioDetectionWait = {}

    await model.startScenarioNoteReceiverIfNeeded()
    model.openComposePage()
    let detection = try XCTUnwrap(model.scenarioDetectionTask)
    await detection.value

    XCTAssertEqual(model.writePhase, .waitingForSend)
    XCTAssertTrue(model.scenarioWriteDetectionTimedOut)
    XCTAssertEqual(returned.count, 0)
    XCTAssertEqual(returned.chips, 1, "the notch chip goes up with the page")
    XCTAssertEqual(returned.chipsDown, 0, "and stays until Send, Skip, or Back")
    model.skipWriteBeat()
    XCTAssertEqual(returned.chipsDown, 1)
    model.streamTask?.cancel()
  }

  @MainActor
  func testScreenRecordingRelaunchResumesOnTheOfferNotTheCard() {
    let opened = OpenedBox()
    let returned = ReturnedBox()
    let model = scenarioModel(opened: opened, returned: returned)
    model.step = .see
    model.seePhase = .permission
    var restarted = false

    XCTAssertTrue(model.acceptPermissionRelaunch("screen_recording", needsRelaunch: true) { restarted = true })

    XCTAssertTrue(restarted)
    XCTAssertEqual(
      UserDefaults.standard.integer(forKey: SBOnboardingModel.resumeStepKey), SBOnboardingModel.Step.see.rawValue,
      "the relaunch must come back to the see beat, not skip to a card about a page nobody opened")
    XCTAssertEqual(model.seePhase, .openPage)
    XCTAssertEqual(UserDefaults.standard.string(forKey: SBOnboardingModel.seePhaseKey), "openPage")
    UserDefaults.standard.removeObject(forKey: SBOnboardingModel.resumeStepKey)
    UserDefaults.standard.removeObject(forKey: SBOnboardingModel.seePhaseKey)
  }

  @MainActor
  func testSkipFromTheWriteOfferLeavesWithoutOpeningAnything() {
    let opened = OpenedBox()
    let returned = ReturnedBox()
    let model = scenarioModel(opened: opened, returned: returned)
    model.step = .write
    model.writePhase = .intro

    model.skipWriteBeat()

    XCTAssertEqual(model.step, .ready)
    XCTAssertTrue(opened.urls.isEmpty)
    model.streamTask?.cancel()
  }
}

private final class OpenedBox: @unchecked Sendable {
  var urls: [URL] = []
}

private final class ReturnedBox: @unchecked Sendable {
  var count = 0
  var chips = 0
  var chipsDown = 0
}

private final class PollBox: @unchecked Sendable {
  var count = 0
}
