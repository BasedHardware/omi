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

  func testNoteTitleTransportRoundTripsBrowserEncoding() throws {
    let note = "Hey Sam — lamp is great & arrives Friday."
    let encoded = try XCTUnwrap(note.addingPercentEncoding(withAllowedCharacters: .alphanumerics))
    let nonce = "nonce-123"
    let title = "Omi Welcome · Sent · \(nonce) · \(encoded)"
    XCTAssertEqual(OnboardingScenarioTitleTransport.note(from: title, nonce: nonce), note)
    XCTAssertNil(OnboardingScenarioTitleTransport.note(from: title, nonce: "wrong"))
  }

  func testDeterministicNoteEffects() {
    let prefilled = "Hey Sam — intact commitment"
    let intact = OnboardingScenarioNotePlanner.effects(note: prefilled, prefilledNote: prefilled)
    XCTAssertEqual(intact.memories, ["Note to Sam: \(prefilled)", OnboardingScenarioNotePlanner.personMemory])
    XCTAssertEqual(intact.taskTitle, "Send Sam the lamp link")
    XCTAssertEqual(intact.personMemory, OnboardingScenarioNotePlanner.personMemory)

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
    XCTAssertEqual(model.thread.last?.text, "Open the order page")
    XCTAssertNotNil(model.scenarioDetectionTask, "the click starts the watch for the page")
    model.scenarioDetectionTask?.cancel()

    // A retry from the waiting phase opens again without a second user bubble.
    model.openOrderPage()
    XCTAssertEqual(opened.urls.count, 2)
    XCTAssertEqual(model.thread.filter { $0.text == "Open the order page" }.count, 1)
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
  func testWriteBeatWaitsForTheClickAndReturnsAfterSend() {
    let opened = OpenedBox()
    let returned = ReturnedBox()
    let model = scenarioModel(opened: opened, returned: returned)
    model.step = .write
    model.writePhase = .intro

    XCTAssertTrue(opened.urls.isEmpty, "the write beat's message opens nothing")
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
}
