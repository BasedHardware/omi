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
    let title = "Omi Welcome · Sent · \(encoded)"
    XCTAssertEqual(OnboardingScenarioTitleTransport.note(from: title), note)
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
      poll: { titles.removeFirst() },
      wait: { waits += 1 })
    XCTAssertEqual(matched, .matched(title: "Omi Welcome · Order confirmed · Norrland Goods"))
    XCTAssertEqual(waits, 1)

    let timeout = await OnboardingScenarioDetector.waitForTitle(
      token: OnboardingScenarioTitleTransport.sentToken,
      maximumPolls: 3,
      useTimedFallback: false,
      poll: { "Other" },
      wait: {})
    XCTAssertEqual(timeout, .timedOut)

    let fallback = await OnboardingScenarioDetector.waitForTitle(
      token: OnboardingScenarioTitleTransport.orderToken,
      maximumPolls: 40,
      useTimedFallback: false,
      undetectableAfterPolls: 3,
      poll: { nil },
      wait: {})
    XCTAssertEqual(fallback, .timedFallback)
  }
}
