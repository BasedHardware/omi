import XCTest

@testable import Omi_Computer

final class FirstRunEngineTests: XCTestCase {
  private let start = Date(timeIntervalSince1970: 1_788_230_400)

  func testReducerCompletesEveryObservedStepAndCreatesSummary() {
    var state = FirstRunState.inactive
    let project = context(app: "Xcode", bundle: "com.apple.dt.Xcode", title: "Pricing Engine")
    let distraction = context(app: "Safari", bundle: "com.apple.Safari", title: "Reddit — Safari")

    var effects = apply(&state, .start, offset: 0)
    XCTAssertEqual(state.step, .openWork)
    XCTAssertTrue(effects.contains(.showInstruction))

    effects = apply(&state, .context(project), offset: 1)
    XCTAssertTrue(effects.contains(.scheduleDwell(context: project, seconds: 8)))
    XCTAssertEqual(state.step, .openWork)
    _ = apply(&state, .dwellElapsed(project), offset: 9)
    XCTAssertEqual(state.projectContext, project.reminderKey)
    XCTAssertEqual(state.stepsCompleted, 1)

    _ = apply(&state, .advance(expected: .openWork), offset: 12)
    XCTAssertEqual(state.step, .setReminder)
    _ = apply(&state, .voiceTurn("remind me to ping Priya"), offset: 13)
    effects = apply(
      &state,
      .reminderCreated(reminderID: "reminder-1", actionItemID: "task-1"),
      offset: 14)
    XCTAssertEqual(state.stepsCompleted, 2)
    XCTAssertTrue(
      effects.contains(
        .showTransient(
          title: "✓ Got it. Next time you're back in Pricing Engine, I'll bring that up.",
          message: "")))

    _ = apply(&state, .advance(expected: .setReminder), offset: 17)
    XCTAssertEqual(state.step, .drift)
    _ = apply(&state, .context(distraction), offset: 18)
    effects = apply(&state, .dwellElapsed(distraction), offset: 63)
    XCTAssertTrue(effects.contains(.requestFocus(site: "Reddit")))
    _ = apply(&state, .focusProbeResult(delivered: true), offset: 64)
    XCTAssertEqual(state.step, .backToWork)
    XCTAssertEqual(state.focusPath, .assistant)
    XCTAssertEqual(state.stepsCompleted, 3)

    effects = apply(&state, .context(project), offset: 65)
    XCTAssertTrue(effects.contains(.deliverReminder(id: "reminder-1")))
    _ = apply(&state, .reminderResolved(id: "reminder-1", snoozed: false), offset: 66)
    XCTAssertEqual(state.stepsCompleted, 4)
    _ = apply(&state, .advance(expected: .backToWork), offset: 69)
    XCTAssertEqual(state.step, .summary)

    effects = apply(&state, .conversationCreated("conversation-1"), offset: 70)
    XCTAssertEqual(state.step, .done)
    XCTAssertEqual(state.stepsCompleted, 5)
    XCTAssertEqual(state.conversationID, "conversation-1")
    XCTAssertTrue(effects.contains(.showSummary(conversationID: "conversation-1")))
  }

  func testReducerRequiresFullDwellAndFallbackDelay() {
    var state = FirstRunState.inactive
    let project = context(app: "Figma", bundle: "com.figma.Desktop", title: "Launch Design")
    let distraction = context(app: "Safari", bundle: "com.apple.Safari", title: "YouTube")

    _ = apply(&state, .start, offset: 0)
    _ = apply(&state, .context(project), offset: 1)
    _ = apply(&state, .dwellElapsed(project), offset: 8)
    XCTAssertEqual(state.step, .openWork, "the full eight-second dwell is required")
    _ = apply(&state, .dwellElapsed(project), offset: 9)
    _ = apply(&state, .advance(expected: .openWork), offset: 12)
    _ = apply(&state, .voiceTurn("review the launch copy"), offset: 13)
    _ = apply(&state, .reminderCreated(reminderID: "r", actionItemID: "a"), offset: 14)
    _ = apply(&state, .advance(expected: .setReminder), offset: 17)
    _ = apply(&state, .context(distraction), offset: 18)
    _ = apply(&state, .dwellElapsed(distraction), offset: 62)
    XCTAssertNil(state.focusRequestedAt, "the full forty-five-second dwell is required")
    _ = apply(&state, .dwellElapsed(distraction), offset: 63)

    var effects = apply(&state, .focusFallbackElapsed, offset: 122)
    XCTAssertEqual(state.step, .drift, "the fallback cannot beat the assistant's sixty-second window")
    XCTAssertTrue(effects.isEmpty)
    effects = apply(&state, .focusFallbackElapsed, offset: 123)
    XCTAssertEqual(state.step, .backToWork)
    XCTAssertEqual(state.focusPath, .fallback)
    XCTAssertTrue(effects.contains(.deliverFallback(site: "YouTube", projectTitle: "Launch Design")))
  }

  func testReducerDismissesAfterThreeLaunchesOrTwentyFourHours() {
    var launchState = FirstRunState.inactive
    _ = apply(&launchState, .start, offset: 0)
    _ = apply(&launchState, .launch, offset: 10)
    XCTAssertEqual(launchState.step, .openWork)
    _ = apply(&launchState, .launch, offset: 20)
    XCTAssertEqual(launchState.step, .dismissed)

    var ageState = FirstRunState.inactive
    _ = apply(&ageState, .start, offset: 0)
    let effects = apply(&ageState, .presentationOpportunity, offset: FirstRunReducer.abandonmentInterval)
    XCTAssertEqual(ageState.step, .dismissed)
    XCTAssertTrue(effects.contains(.clearPending))
  }

  func testResumeReconstructsExactlyOnePersistedEffect() {
    var state = FirstRunState.inactive
    state.step = .openWork
    state.startedAt = start
    state.stepStartedAt = start
    state.transitionPending = true
    state.pendingEffect = .advance(step: .openWork, deadline: start.addingTimeInterval(3))

    let effects = apply(&state, .resume, offset: 1)

    XCTAssertEqual(effects, [.scheduleAdvance(expected: .openWork, seconds: 2)])
  }

  func testFocusControlsAndReminderDismissalsAreReducerEvents() {
    var state = FirstRunState.inactive
    state.step = .backToWork
    state.startedAt = start
    state.stepStartedAt = start
    state.reminderID = "reminder-1"
    state.reminderPresented = true
    state.pendingEffect = .reminder(id: "reminder-1")

    _ = apply(&state, .notificationDismissed(assistantID: "first_run_card"), offset: 1)
    XCTAssertFalse(state.reminderPresented)
    XCTAssertEqual(state.reminderDismissals, 1)

    state.reminderPresented = true
    let effects = apply(&state, .notificationDismissed(assistantID: "first_run_card"), offset: 2)
    XCTAssertTrue(state.transitionPending)
    XCTAssertTrue(effects.contains(.scheduleAdvance(expected: .backToWork, seconds: 3)))

    var focus = FirstRunState.inactive
    focus.step = .backToWork
    _ = apply(&focus, .focusSnoozed(until: start.addingTimeInterval(300)), offset: 0)
    XCTAssertEqual(focus.step, .drift)
    XCTAssertEqual(focus.pendingEffect, .focusSnooze(deadline: start.addingTimeInterval(300)))
  }

  func testClosingTheGuideChipKeepsItDownForThatStepOnly() {
    var state = FirstRunState.inactive
    let project = context(app: "Xcode", bundle: "com.apple.dt.Xcode", title: "Pricing Engine")
    _ = apply(&state, .start, offset: 0)

    _ = apply(&state, .notificationDismissed(assistantID: "first_run_guide"), offset: 1)
    XCTAssertEqual(state.step, .openWork, "closing the chip is not abandoning the first run")
    var effects = apply(&state, .presentationOpportunity, offset: 6)
    XCTAssertFalse(effects.contains(.showInstruction), "the heartbeat must not put a closed chip back")
    effects = apply(&state, .presentationOpportunity, offset: 11)
    XCTAssertFalse(effects.contains(.showInstruction))

    _ = apply(&state, .context(project), offset: 12)
    _ = apply(&state, .dwellElapsed(project), offset: 21)
    effects = apply(&state, .advance(expected: .openWork), offset: 24)
    XCTAssertEqual(state.step, .setReminder)
    XCTAssertTrue(effects.contains(.showInstruction), "the next step gets its own chip")
    effects = apply(&state, .presentationOpportunity, offset: 29)
    XCTAssertTrue(effects.contains(.showInstruction))

    var relaunched = FirstRunState.inactive
    _ = apply(&relaunched, .start, offset: 0)
    _ = apply(&relaunched, .notificationDismissed(assistantID: "first_run_guide"), offset: 1)
    effects = apply(&relaunched, .launch, offset: 600)
    XCTAssertTrue(effects.contains(.showInstruction), "a new launch is a new chance to show the step")
  }

  func testReducerHonorsExplicitDismissal() {
    var state = FirstRunState.inactive
    _ = apply(&state, .start, offset: 0)
    let effects = apply(&state, .dismiss, offset: 4)

    XCTAssertEqual(state.step, .dismissed)
    XCTAssertTrue(effects.contains(.hideGuide))
    XCTAssertTrue(effects.contains(.clearPending))
    XCTAssertTrue(
      effects.contains(
        .stepAnalytics(step: .openWork, elapsedMilliseconds: 4_000, path: "dismissed")))
  }

  func testChipPolicySuppressesMeetingsOtherCardsAndFourthDailyInstruction() {
    XCTAssertFalse(
      FirstRunChipPresentationPolicy.shouldPresent(
        isMeetingActive: true, hasAnotherCard: false, instructionCountToday: 0,
        countsAgainstDailyCap: true))
    XCTAssertFalse(
      FirstRunChipPresentationPolicy.shouldPresent(
        isMeetingActive: false, hasAnotherCard: true, instructionCountToday: 0,
        countsAgainstDailyCap: true))
    XCTAssertFalse(
      FirstRunChipPresentationPolicy.shouldPresent(
        isMeetingActive: false, hasAnotherCard: false, instructionCountToday: 3,
        countsAgainstDailyCap: true))
    XCTAssertTrue(
      FirstRunChipPresentationPolicy.shouldPresent(
        isMeetingActive: false, hasAnotherCard: false, instructionCountToday: 2,
        countsAgainstDailyCap: true))
    XCTAssertTrue(
      FirstRunChipPresentationPolicy.shouldPresent(
        isMeetingActive: false, hasAnotherCard: false, instructionCountToday: 3,
        countsAgainstDailyCap: false))
  }

  func testContextClassificationExcludesOmiWelcomeAndKnownDistractions() {
    XCTAssertFalse(
      context(app: "Omi", bundle: "com.omi.computer-macos", title: "Project").isEligibleProject)
    XCTAssertFalse(
      context(app: "Safari", bundle: "com.apple.Safari", title: "Omi Welcome — Safari").isEligibleProject)
    XCTAssertEqual(
      context(app: "Google Chrome", bundle: "com.google.Chrome", title: "Hacker News").distractionSite,
      "Hacker News")
  }

  @MainActor
  func testCoordinatorQueuesSynchronousCallbackEventsWithoutReenteringReducer() throws {
    let suite = "FirstRunEngineTests.\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
    defer { defaults.removePersistentDomain(forName: suite) }
    var persisted = FirstRunState.inactive
    persisted.step = .openWork
    persisted.startedAt = start
    persisted.stepStartedAt = start
    defaults.set(try JSONEncoder().encode(persisted), forKey: FirstRunCoordinator.stateKey)
    var clock = start
    let project = context(app: "Xcode", bundle: "com.apple.dt.Xcode", title: "Pricing Engine")
    let coordinator = FirstRunCoordinator(
      defaults: defaults,
      now: { clock },
      executesEffects: false)
    var observedSteps: [FirstRunStep] = []
    coordinator.setObserversForTesting(
      effect: { effect in
        guard case .scheduleDwell(let context, _) = effect else { return }
        clock = clock.addingTimeInterval(8)
        coordinator.sendForTesting(.dwellElapsed(context))
      },
      state: { observedSteps.append($0.step) })

    coordinator.sendForTesting(.context(project))

    XCTAssertEqual(observedSteps, [.openWork, .openWork])
    XCTAssertEqual(coordinator.snapshotForTesting().projectContext, project.reminderKey)
    XCTAssertTrue(coordinator.snapshotForTesting().transitionPending)
  }

  func testContextReminderStoreMatchesSnoozesAndCompletes() async throws {
    let directory = FileManager.default.temporaryDirectory
      .appendingPathComponent("first-run-reminders-\(UUID().uuidString)", isDirectory: true)
    let fileURL = directory.appendingPathComponent("reminders.json")
    defer { try? FileManager.default.removeItem(at: directory) }
    let store = ContextReminderStore(fileURLProvider: { fileURL })
    let createdAt = start
    let key = ContextReminderKey(
      bundleID: "com.apple.dt.Xcode", normalizedTitle: "Pricing Engine", bucketID: "bucket-1")
    let reminder = try await store.create(
      text: "ping Priya", for: key, actionItemID: "task-1", now: createdAt, id: "reminder-1")

    let sameTitle = context(app: "Xcode", bundle: key.bundleID, title: key.normalizedTitle)
    let sameBucket = context(
      app: "Code", bundle: "com.microsoft.VSCode", title: "Renamed", bucketID: "bucket-1")
    let titleMatches = try await store.dueReminders(for: sameTitle, now: createdAt)
    let bucketMatches = try await store.dueReminders(for: sameBucket, now: createdAt)
    XCTAssertEqual(titleMatches.map(\.id), [reminder.id])
    XCTAssertEqual(bucketMatches.map(\.id), [reminder.id])

    let tomorrow = createdAt.addingTimeInterval(86_400)
    _ = try await store.snooze(id: reminder.id, until: tomorrow)
    let beforeSnooze = try await store.dueReminders(for: sameTitle, now: tomorrow.addingTimeInterval(-1))
    let atSnooze = try await store.dueReminders(for: sameTitle, now: tomorrow)
    XCTAssertTrue(beforeSnooze.isEmpty)
    XCTAssertEqual(atSnooze.map(\.id), [reminder.id])

    let completed = try await store.markDone(id: reminder.id, at: tomorrow)
    XCTAssertEqual(completed?.actionItemID, "task-1")
    let afterDone = try await store.dueReminders(for: sameTitle, now: tomorrow)
    XCTAssertTrue(afterDone.isEmpty)
  }

  func testContextReminderStoreRefusesWriteWhenOwnerChangesAfterLoad() async throws {
    let directory = FileManager.default.temporaryDirectory
      .appendingPathComponent("first-run-owner-fence-\(UUID().uuidString)", isDirectory: true)
    let fileURL = directory.appendingPathComponent("reminders.json")
    defer { try? FileManager.default.removeItem(at: directory) }
    final class OwnerBox: @unchecked Sendable { var value = "owner-a" }
    let owner = OwnerBox()
    let store = ContextReminderStore(
      fileURLProvider: { fileURL },
      ownerIDProvider: { owner.value },
      beforeMutationSave: { owner.value = "owner-b" })
    let key = ContextReminderKey(bundleID: "com.apple.dt.Xcode", normalizedTitle: "Project", bucketID: nil)

    do {
      _ = try await store.create(text: "secret", for: key)
      XCTFail("owner change must reject the write")
    } catch {
      // Expected: the owner observed at load no longer owns the save boundary.
    }
    XCTAssertFalse(FileManager.default.fileExists(atPath: fileURL.path))
  }

  func testSummaryComposerMergesJournalAndObservedLogChronologically() throws {
    let journalData = try XCTUnwrap(
      """
      [{"t":"2026-09-01T12:00:00Z","who":"omi","text":"Welcome"},
       {"t":"2026-09-01T12:00:02Z","who":"user","text":"Let's go"}]
      """.data(using: .utf8))
    let journal = FirstRunSummaryComposer.decodeJournal(journalData)
    let sessionStart = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-09-01T12:00:00Z"))
    let segments = FirstRunSummaryComposer.compose(
      journal: journal,
      firstRunLog: [FirstRunLogEntry(t: sessionStart.addingTimeInterval(1), text: "Opened the repo.", isUser: false)],
      sessionStart: sessionStart,
      sessionEnd: sessionStart.addingTimeInterval(10))

    XCTAssertEqual(segments.map(\.text), ["Welcome", "Opened the repo.", "Let's go"])
    XCTAssertEqual(segments.map(\.speaker), ["Omi", "Omi", "You"])
    XCTAssertEqual(segments.map(\.isUser), [false, false, true])
    XCTAssertTrue(zip(segments, segments.dropFirst()).allSatisfy { pair in pair.0.end <= pair.1.start })
  }

  @MainActor
  func testUsageReporterAccumulatesAndRollsOverWithoutDroppingPriorDay() throws {
    let suite = "FirstRunEngineTests.\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
    defer { defaults.removePersistentDomain(forName: suite) }
    var calendar = Calendar(identifier: .gregorian)
    calendar.timeZone = try XCTUnwrap(TimeZone(identifier: "America/New_York"))
    let dayOne = Date(timeIntervalSince1970: 1_788_230_400)
    let dayTwo = try XCTUnwrap(calendar.date(byAdding: .day, value: 1, to: dayOne))
    let reporter = DesktopUsageDailyReporter(
      defaults: defaults,
      now: { dayOne },
      calendar: calendar,
      timezone: { calendar.timeZone },
      deviceID: { "device-1" })

    reporter.sampleForTesting(watching: true, listening: false, at: dayOne)
    reporter.recordProactiveCardShown()
    reporter.recordProactiveCardActed()
    reporter.recordCompletedPTTTurn(repliedToCard: true)
    reporter.sampleForTesting(watching: true, listening: true, at: dayTwo)

    let snapshot = reporter.snapshotForTesting()
    let keys = snapshot.records.keys.sorted()
    XCTAssertEqual(keys.count, 2)
    XCTAssertEqual(snapshot.records[keys[0]]?.watchingSeconds, 60)
    XCTAssertEqual(snapshot.records[keys[1]]?.watchingSeconds, 60)
    XCTAssertEqual(snapshot.records[keys[1]]?.listeningSeconds, 60)
    XCTAssertEqual(snapshot.records[keys[0]]?.proactiveCardsShown, 1)
    XCTAssertEqual(snapshot.records[keys[0]]?.proactiveCardsActed, 2)
    XCTAssertEqual(snapshot.records[keys[0]]?.pttTurns, 1)
  }

  @MainActor
  func testUsagePersistenceIsNamespacedByOwner() throws {
    let suite = "FirstRunEngineTests.\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
    defer { defaults.removePersistentDomain(forName: suite) }
    let ownerA = DesktopUsageDailyReporter(defaults: defaults, ownerID: { "owner-a" })
    ownerA.recordProactiveCardShown()
    let ownerB = DesktopUsageDailyReporter(defaults: defaults, ownerID: { "owner-b" })

    XCTAssertEqual(ownerA.snapshotForTesting().dirtyDates.count, 1)
    XCTAssertTrue(ownerB.snapshotForTesting().dirtyDates.isEmpty)
  }

  private func apply(
    _ state: inout FirstRunState,
    _ event: FirstRunReducerEvent,
    offset: TimeInterval
  ) -> [FirstRunReducerEffect] {
    let reduction = FirstRunReducer.reduce(state, event: event, now: start.addingTimeInterval(offset))
    state = reduction.state
    return reduction.effects
  }

  private func context(
    app: String,
    bundle: String,
    title: String,
    bucketID: String? = nil
  ) -> FirstRunObservedContext {
    FirstRunObservedContext(appName: app, bundleID: bundle, normalizedTitle: title, bucketID: bucketID)
  }
}
