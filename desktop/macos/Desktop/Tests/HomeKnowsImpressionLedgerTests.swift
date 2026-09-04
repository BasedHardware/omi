import XCTest

@testable import Omi_Computer

// MARK: - Rules

final class HomeKnowsRotationPolicyTests: XCTestCase {
  private let now = HomeKnowsLedgerFixture.noon
  private let calendar = Calendar.current

  private func facts(
    _ key: String = "task:t1",
    text: String = "Meet with Priya",
    updatedAt: Date? = nil,
    dueAt: Date? = nil,
    isActive: Bool = true
  ) -> HomeKnowsCandidateFacts {
    HomeKnowsCandidateFacts(
      key: key,
      contentHash: HomeKnowsRotationPolicy.contentHash(text: text, updatedAt: updatedAt),
      updatedAt: updatedAt,
      dueAt: dueAt,
      isActive: isActive)
  }

  private func suppression(
    _ facts: HomeKnowsCandidateFacts,
    _ entry: HomeKnowsImpression?,
    at instant: Date? = nil,
    allowSameDayRepeat: Bool = false
  ) -> HomeKnowsRotationReason? {
    HomeKnowsRotationPolicy.suppression(
      facts: facts,
      entry: entry,
      now: instant ?? now,
      calendar: calendar,
      allowSameDayRepeat: allowSameDayRepeat)
  }

  func testNeverShownRowQualifies() {
    XCTAssertNil(suppression(facts(), nil))
  }

  func testThreeShowsWithoutAnOpenRotateOutForSevenDays() {
    let subject = facts()
    let lastShown = HomeKnowsLedgerFixture.previousDay(before: now)
    let entry = HomeKnowsImpression(
      shows: 3, firstShownAt: lastShown, lastShownAt: lastShown, contentHash: subject.contentHash)

    XCTAssertEqual(suppression(subject, entry), .showCap)
    // Still out one day before the cooldown ends…
    XCTAssertEqual(
      suppression(subject, entry, at: lastShown.addingTimeInterval(6 * 86_400)), .showCap)
    // …and back once it has passed.
    XCTAssertNil(suppression(subject, entry, at: lastShown.addingTimeInterval(7 * 86_400 + 1)))
  }

  func testTwoShowsDoNotHitTheCap() {
    let subject = facts()
    let lastShown = HomeKnowsLedgerFixture.previousDay(before: now)
    let entry = HomeKnowsImpression(shows: 2, lastShownAt: lastShown, contentHash: subject.contentHash)

    XCTAssertNil(suppression(subject, entry))
  }

  func testAnOpenedRowIsNeverCapped() {
    let subject = facts()
    let lastShown = HomeKnowsLedgerFixture.previousDay(before: now)
    let entry = HomeKnowsImpression(
      shows: 12, lastShownAt: lastShown, lastOpenedAt: lastShown, contentHash: subject.contentHash)

    XCTAssertNil(suppression(subject, entry))
  }

  func testDismissedRowNeverReturnsWhileItsObjectIsUnchanged() {
    let subject = facts()
    let entry = HomeKnowsImpression(
      shows: 1, dismissedAt: HomeKnowsLedgerFixture.previousDay(before: now),
      contentHash: subject.contentHash)

    XCTAssertEqual(suppression(subject, entry), .dismissed)
    // Even a year later, and even when nothing else qualifies for the slot.
    XCTAssertEqual(suppression(subject, entry, at: now.addingTimeInterval(365 * 86_400)), .dismissed)
    XCTAssertEqual(suppression(subject, entry, allowSameDayRepeat: true), .dismissed)
  }

  func testDismissedRowReturnsOnceItsUnderlyingObjectChanges() {
    let dismissed = facts(text: "Meet with Priya")
    let entry = HomeKnowsImpression(
      shows: 1, dismissedAt: HomeKnowsLedgerFixture.previousDay(before: now),
      contentHash: dismissed.contentHash)

    // Same row id, new content hash — a real edit to the task.
    let edited = facts(text: "Meet with Priya about the Q3 plan")
    XCTAssertNil(suppression(edited, entry))

    // A new updated_at alone is enough, even with identical text.
    let touched = facts(text: "Meet with Priya", updatedAt: now)
    XCTAssertNil(suppression(touched, entry))
  }

  func testTaskMoreThanFourteenDaysPastDueIsExcluded() {
    XCTAssertNil(suppression(facts(dueAt: now.addingTimeInterval(-13 * 86_400)), nil))
    XCTAssertEqual(
      suppression(facts(dueAt: now.addingTimeInterval(-15 * 86_400)), nil), .staleDueDate)
    // A future due date is never stale.
    XCTAssertNil(suppression(facts(dueAt: now.addingTimeInterval(86_400)), nil))
  }

  func testCompletedOrDeletedTaskIsExcluded() {
    XCTAssertEqual(suppression(facts(isActive: false), nil), .inactive)
  }

  func testSameDayRepeatNeedsBothRelaxationAndAPriorOpen() {
    let subject = facts()
    let today = HomeKnowsLedgerFixture.sameDay(as: now)
    let unopened = HomeKnowsImpression(shows: 1, lastShownAt: today, contentHash: subject.contentHash)
    var opened = unopened
    opened.lastOpenedAt = today

    XCTAssertEqual(suppression(subject, unopened), .sameDay)
    XCTAssertEqual(suppression(subject, unopened, allowSameDayRepeat: true), .sameDay)
    XCTAssertEqual(suppression(subject, opened), .sameDay)
    XCTAssertNil(suppression(subject, opened, allowSameDayRepeat: true))
  }

  func testFreshnessRankPrefersNeverShownThenFewestShowsThenNewestUpdate() {
    var ledger = HomeKnowsImpressionLedger.empty
    ledger.entries["task:seen"] = HomeKnowsImpression(shows: 2)
    let never = facts("task:never")
    let seen = facts("task:seen")

    XCTAssertTrue(
      HomeKnowsRotationPolicy.freshnessRank(never, ledger: ledger)
        < HomeKnowsRotationPolicy.freshnessRank(seen, ledger: ledger))

    let older = facts("task:a", updatedAt: now.addingTimeInterval(-3600))
    let newer = facts("task:b", updatedAt: now)
    XCTAssertTrue(
      HomeKnowsRotationPolicy.freshnessRank(newer, ledger: .empty)
        < HomeKnowsRotationPolicy.freshnessRank(older, ledger: .empty))

    // Two equally fresh rows must tie, so the caller's own priority order — not
    // the row key — decides between them.
    XCTAssertTrue(
      HomeKnowsRotationPolicy.freshnessRank(facts("task:zzz"), ledger: .empty)
        == HomeKnowsRotationPolicy.freshnessRank(facts("task:aaa"), ledger: .empty))
  }

  func testDominantReasonUsesAFixedPriorityRatherThanInputOrder() {
    XCTAssertEqual(HomeKnowsRotationPolicy.dominantReason([.sameDay, .dismissed]), .dismissed)
    XCTAssertEqual(HomeKnowsRotationPolicy.dominantReason([.staleDueDate, .showCap]), .showCap)
    XCTAssertEqual(HomeKnowsRotationPolicy.dominantReason([]), .noCandidate)
  }

  func testContentHashMovesWithTextAndUpdatedAt() {
    let base = HomeKnowsRotationPolicy.contentHash(text: "Meet with Priya")
    XCTAssertEqual(base, HomeKnowsRotationPolicy.contentHash(text: "Meet with Priya"))
    XCTAssertNotEqual(base, HomeKnowsRotationPolicy.contentHash(text: "Meet with Ravi"))
    XCTAssertNotEqual(base, HomeKnowsRotationPolicy.contentHash(text: "Meet with Priya", updatedAt: now))
  }

  func testQuestionKeyHashesTheTextRatherThanStoringIt() {
    let key = HomeKnowsRotationPolicy.questionKey("What did I commit to this week?")
    XCTAssertTrue(key.hasPrefix("question:"))
    XCTAssertFalse(key.contains("commit"))
    XCTAssertEqual(key, HomeKnowsRotationPolicy.questionKey("What did I commit to this week?"))
  }
}

// MARK: - Store

/// Not `@MainActor` at the class level: `XCTestCase.setUp` is a nonisolated
/// override and cannot build main-actor state. Each test makes its own harness.
final class HomeKnowsImpressionStoreTests: XCTestCase {
  /// In-memory persistence plus a movable clock, so the rules are asserted
  /// without UserDefaults and without waiting on the wall clock.
  @MainActor
  private final class Harness {
    final class FakePersistence: HomeKnowsImpressionPersisting {
      var ledger = HomeKnowsImpressionLedger.empty

      func load() -> HomeKnowsImpressionLedger { ledger }
      func save(_ ledger: HomeKnowsImpressionLedger) { self.ledger = ledger }
    }

    let persistence = FakePersistence()
    var clock = HomeKnowsLedgerFixture.noon
    /// Injected so an account switch is a value in the test rather than a
    /// mutation of the process-wide defaults.
    var owner: String? = "owner-a"
    lazy var store = HomeKnowsImpressionStore(
      persistence: persistence, now: { self.clock }, ownerID: { self.owner })
    let hash = HomeKnowsRotationPolicy.contentHash(text: "Meet with Priya")
  }

  @MainActor
  func testShowIsRecordedOncePerVisitNotOncePerRender() {
    let harness = Harness()
    harness.store.beginVisit()
    XCTAssertEqual(harness.store.recordShown(key: "task:t1", contentHash: harness.hash)?.shows, 1)
    // The in-visit rotation timer re-renders the same row every few seconds.
    XCTAssertNil(harness.store.recordShown(key: "task:t1", contentHash: harness.hash))
    XCTAssertNil(harness.store.recordShown(key: "task:t1", contentHash: harness.hash))
    XCTAssertEqual(harness.persistence.ledger.entry("task:t1")?.shows, 1)

    harness.store.beginVisit()
    XCTAssertEqual(harness.store.recordShown(key: "task:t1", contentHash: harness.hash)?.shows, 2)
  }

  @MainActor
  func testEmptySlotIsReportedOncePerVisit() {
    let harness = Harness()
    harness.store.beginVisit()
    XCTAssertTrue(harness.store.shouldReportEmptySlot("tip"))
    XCTAssertFalse(harness.store.shouldReportEmptySlot("tip"))
    harness.store.beginVisit()
    XCTAssertTrue(harness.store.shouldReportEmptySlot("tip"))
  }

  @MainActor
  func testFirstAndLastShownTrackSeparately() {
    let harness = Harness()
    harness.store.beginVisit()
    harness.store.recordShown(key: "task:t1", contentHash: harness.hash)
    let first = harness.clock
    harness.clock = harness.clock.addingTimeInterval(2 * 86_400)
    harness.store.beginVisit()
    harness.store.recordShown(key: "task:t1", contentHash: harness.hash)

    let entry = harness.store.snapshot().entry("task:t1")
    XCTAssertEqual(entry?.firstShownAt, first)
    XCTAssertEqual(entry?.lastShownAt, harness.clock)
    XCTAssertEqual(entry?.shows, 2)
  }

  @MainActor
  func testShowCountResetsAfterTheCooldownSoTheCapIsThreeShowsPerWindow() {
    let harness = Harness()
    for _ in 0..<HomeKnowsRotationPolicy.showCapCount {
      harness.store.beginVisit()
      harness.store.recordShown(key: "task:t1", contentHash: harness.hash)
      harness.clock = harness.clock.addingTimeInterval(86_400)
    }
    XCTAssertEqual(harness.store.snapshot().entry("task:t1")?.shows, 3)

    harness.clock = harness.clock.addingTimeInterval(HomeKnowsRotationPolicy.showCapCooldown)
    harness.store.beginVisit()
    XCTAssertEqual(harness.store.recordShown(key: "task:t1", contentHash: harness.hash)?.shows, 1)
  }

  @MainActor
  func testChangedContentResetsTheCountAndClearsADismissal() {
    let harness = Harness()
    harness.store.beginVisit()
    harness.store.recordShown(key: "task:t1", contentHash: harness.hash)
    harness.store.recordDismissed(key: "task:t1", contentHash: harness.hash)
    XCTAssertNotNil(harness.store.snapshot().entry("task:t1")?.dismissedAt)

    let edited = HomeKnowsRotationPolicy.contentHash(text: "Meet with Priya about Q3")
    harness.store.beginVisit()
    let entry = harness.store.recordShown(key: "task:t1", contentHash: edited)
    XCTAssertEqual(entry?.shows, 1)
    XCTAssertNil(entry?.dismissedAt)
    XCTAssertEqual(entry?.contentHash, edited)
  }

  /// A prior open belongs to the text that was open. Carrying it onto changed
  /// content left the row exempt from the show cap and the same-day rule for
  /// good — the one entry that could repeat itself indefinitely.
  @MainActor
  func testChangedContentAlsoClearsAnEarlierOpen() {
    let harness = Harness()
    harness.store.beginVisit()
    harness.store.recordOpened(key: "task:t1", contentHash: harness.hash)
    XCTAssertNotNil(harness.store.snapshot().entry("task:t1")?.lastOpenedAt)

    let edited = HomeKnowsRotationPolicy.contentHash(text: "Meet with Priya about Q3")
    harness.store.beginVisit()
    XCTAssertNil(harness.store.recordShown(key: "task:t1", contentHash: edited)?.lastOpenedAt)
  }

  /// The ledger is owner-scoped at every read and write, but the once-per-visit
  /// de-duplication set is not: a question row is keyed by its text, so the
  /// previous owner's key would silence the new owner's first impression.
  @MainActor
  func testAnAccountSwitchStartsAFreshVisit() {
    let harness = Harness()
    harness.store.beginVisit()
    XCTAssertEqual(harness.store.recordShown(key: "question:q1", contentHash: harness.hash)?.shows, 1)
    XCTAssertNil(harness.store.recordShown(key: "question:q1", contentHash: harness.hash))
    XCTAssertTrue(harness.store.shouldReportEmptySlot("tip"))
    XCTAssertFalse(harness.store.shouldReportEmptySlot("tip"))

    harness.owner = "owner-b"
    XCTAssertEqual(harness.store.recordShown(key: "question:q1", contentHash: harness.hash)?.shows, 2)
    XCTAssertTrue(harness.store.shouldReportEmptySlot("tip"))
  }

  @MainActor
  func testOpeningARowClearsAnEarlierDismissal() {
    let harness = Harness()
    harness.store.beginVisit()
    harness.store.recordDismissed(key: "insight:i1", contentHash: harness.hash)
    let entry = harness.store.recordOpened(key: "insight:i1", contentHash: harness.hash)

    XCTAssertNil(entry.dismissedAt)
    XCTAssertEqual(entry.lastOpenedAt, harness.clock)
  }

  /// The composer reads the store's snapshot, so the two must agree: a row the
  /// store has recorded three times is one the policy holds back.
  @MainActor
  func testStoreAndPolicyAgreeOnTheShowCap() {
    let harness = Harness()
    for _ in 0..<HomeKnowsRotationPolicy.showCapCount {
      harness.store.beginVisit()
      harness.store.recordShown(key: "task:t1", contentHash: harness.hash)
      harness.clock = harness.clock.addingTimeInterval(86_400)
    }

    let composition = HomeKnowsListComposer.compose(
      tasks: [HomeKnowsTaskCandidate(id: "t1", text: "Meet with Priya")],
      insights: [], questions: [],
      ledger: harness.store.snapshot(), now: harness.clock)

    XCTAssertTrue(composition.rows.isEmpty)
    XCTAssertEqual(
      composition.emptySlots.first, HomeKnowsEmptySlot(slot: .pressingTask, reason: .showCap))
  }
}

// MARK: - Persistence

/// Not `@MainActor` at the class level: `XCTestCase.setUp`/`tearDown` are
/// nonisolated overrides and cannot touch main-actor state. The individual
/// tests carry the isolation the store requires.
final class HomeKnowsImpressionDefaultsTests: XCTestCase {
  private var suiteName = ""
  private var defaults = UserDefaults.standard

  override func setUp() {
    super.setUp()
    suiteName = "HomeKnowsImpressionDefaultsTests.\(UUID().uuidString)"
    defaults = UserDefaults(suiteName: suiteName) ?? .standard
  }

  override func tearDown() {
    UserDefaults.standard.removePersistentDomain(forName: suiteName)
    super.tearDown()
  }

  @MainActor
  func testLedgerRoundTrips() {
    let now = HomeKnowsLedgerFixture.noon
    let store = HomeKnowsImpressionDefaults(defaults: defaults, ownerID: "owner-a", now: { now })
    var ledger = HomeKnowsImpressionLedger.empty
    ledger.entries["task:t1"] = HomeKnowsImpression(shows: 2, lastShownAt: now, contentHash: "abc")
    store.save(ledger)

    let reader = HomeKnowsImpressionDefaults(defaults: defaults, ownerID: "owner-a", now: { now })
    XCTAssertEqual(reader.load(), ledger)
  }

  @MainActor
  func testOneOwnersDismissalsDoNotSilenceAnother() {
    let owner = HomeKnowsImpressionDefaults(defaults: defaults, ownerID: "owner-a")
    // Owner-b must see nothing regardless of retention, so both readers share a clock.
    var ledger = HomeKnowsImpressionLedger.empty
    ledger.entries["task:t1"] = HomeKnowsImpression(
      dismissedAt: HomeKnowsLedgerFixture.noon, contentHash: "abc")
    owner.save(ledger)

    let other = HomeKnowsImpressionDefaults(
      defaults: defaults, ownerID: "owner-b", now: { HomeKnowsLedgerFixture.noon })
    XCTAssertEqual(other.load(), .empty)
  }

  @MainActor
  func testUntouchedEntriesArePrunedOnLoad() {
    let now = HomeKnowsLedgerFixture.noon
    let writer = HomeKnowsImpressionDefaults(defaults: defaults, ownerID: "owner-a")
    var ledger = HomeKnowsImpressionLedger.empty
    ledger.entries["task:recent"] = HomeKnowsImpression(
      shows: 1, lastShownAt: now.addingTimeInterval(-30 * 86_400), contentHash: "a")
    ledger.entries["task:ancient"] = HomeKnowsImpression(
      shows: 1, lastShownAt: now.addingTimeInterval(-200 * 86_400), contentHash: "b")
    writer.save(ledger)

    let loaded = HomeKnowsImpressionDefaults(
      defaults: defaults, ownerID: "owner-a", now: { now }
    ).load()

    XCTAssertEqual(Set(loaded.entries.keys), ["task:recent"])
  }

  @MainActor
  func testCorruptPayloadLoadsAsAnEmptyLedgerRatherThanTrapping() {
    let store = HomeKnowsImpressionDefaults(
      defaults: defaults, ownerID: "owner-a", now: { HomeKnowsLedgerFixture.noon })
    var ledger = HomeKnowsImpressionLedger.empty
    ledger.entries["task:t1"] = HomeKnowsImpression(
      shows: 1, lastShownAt: HomeKnowsLedgerFixture.noon, contentHash: "abc")
    store.save(ledger)

    // Overwrite whatever key the store chose with something undecodable; a bad
    // payload must degrade to "no history", never trap the process.
    let storageKey = defaults.dictionaryRepresentation().keys.first { $0.hasPrefix("homeKnows.") }
    XCTAssertNotNil(storageKey)
    defaults.set(Data("not json".utf8), forKey: storageKey ?? "")

    XCTAssertEqual(store.load(), .empty)
  }
}

// MARK: - Harness seams

/// The two non-production seams `home-knows-rotation.yaml` reaches the list through.
///
/// Both are gated, and the gate is the thing worth pinning: a registry that stayed live on a
/// shipped bundle would hold a strong-enough reference to a dismissed card's rows and would put a
/// drive path for the reader's own list behind a name anything in-process could call.
@MainActor
final class HomeKnowsAutomationSeamTests: XCTestCase {
  private func handle(token: UUID) -> HomeKnowsAutomationRegistry.Handle {
    HomeKnowsAutomationRegistry.Handle(
      token: token,
      snapshot: {
        HomeKnowsAutomationRegistry.Snapshot(
          rows: [], emptySlots: [], canRotate: false, openTaskCount: 0, ledger: .empty)
      },
      beginVisit: {},
      recordImpressions: {},
      open: { _ in false },
      dismiss: { _ in false })
  }

  override func tearDown() async throws {
    if let mounted = HomeKnowsAutomationRegistry.mounted {
      HomeKnowsAutomationRegistry.unregister(token: mounted.token)
    }
  }

  /// On a production bundle the page registers and nothing happens.
  func testRegistrationIsANoOpWhenDisabled() {
    HomeKnowsAutomationRegistry.register(handle(token: UUID()), enabled: false)
    XCTAssertNil(HomeKnowsAutomationRegistry.mounted)
  }

  func testRegistrationPublishesTheMountedList() {
    let token = UUID()
    HomeKnowsAutomationRegistry.register(handle(token: token), enabled: true)
    XCTAssertEqual(HomeKnowsAutomationRegistry.mounted?.token, token)
  }

  /// The hub list and the chat strip render the same rows and overlap for a frame while the stage
  /// animates: the one leaving must not clear the handle the one arriving just took.
  func testUnregisteringAnOlderListLeavesTheCurrentOne() {
    let outgoing = UUID()
    let incoming = UUID()
    HomeKnowsAutomationRegistry.register(handle(token: outgoing), enabled: true)
    HomeKnowsAutomationRegistry.register(handle(token: incoming), enabled: true)

    HomeKnowsAutomationRegistry.unregister(token: outgoing)
    XCTAssertEqual(HomeKnowsAutomationRegistry.mounted?.token, incoming)

    HomeKnowsAutomationRegistry.unregister(token: incoming)
    XCTAssertNil(HomeKnowsAutomationRegistry.mounted)
  }

  /// What `home_knows_reset` buys the flow: the ledger outlives the app, so without a cleared
  /// starting state the second run of the flow opens on rows the first run already suppressed.
  func testResetForAutomationClearsTheLedgerAndStartsAFreshVisit() {
    let persistence = HomeKnowsAutomationSeamTests.FakePersistence()
    let store = HomeKnowsImpressionStore(
      persistence: persistence, now: { HomeKnowsLedgerFixture.noon }, ownerID: { "owner-a" })
    let hash = HomeKnowsRotationPolicy.contentHash(text: "Meet with Priya")
    store.beginVisit()
    XCTAssertEqual(store.recordShown(key: "task:t1", contentHash: hash)?.shows, 1)
    XCTAssertNil(store.recordShown(key: "task:t1", contentHash: hash), "same visit")

    store.resetForAutomation()

    XCTAssertTrue(store.snapshot().entries.isEmpty)
    // The de-duplication set is reset too, or the first visit after a reset would report nothing
    // and the flow would read a silent list as a composer that had stopped producing rows.
    XCTAssertEqual(store.recordShown(key: "task:t1", contentHash: hash)?.shows, 1)
  }

  private final class FakePersistence: HomeKnowsImpressionPersisting {
    var ledger = HomeKnowsImpressionLedger.empty
    func load() -> HomeKnowsImpressionLedger { ledger }
    func save(_ ledger: HomeKnowsImpressionLedger) { self.ledger = ledger }
  }
}

// MARK: - Telemetry seam

/// `rotated_out_reason` is the rotation policy's verdict and is readable nowhere after the emit
/// consumes it. The capture seam is how both a test and the automation bridge observe it at the
/// boundary production writes it, rather than recomputing the reason and asserting their own work.
@MainActor
final class HomeKnowsTelemetrySeamTests: XCTestCase {
  override func tearDown() async throws {
    AnalyticsManager.homeKnowsTelemetryCaptureForTests = nil
  }

  func testRowShownCarriesItsKindSlotAndPriorShowCount() {
    var captured: [(String, [String: Any])] = []
    AnalyticsManager.homeKnowsTelemetryCaptureForTests = { name, props in captured.append((name, props)) }

    AnalyticsManager.shared.trackHomeKnowsRowShown(kind: "task", slot: .pressingTask, showsBefore: 2)

    XCTAssertEqual(captured.count, 1)
    XCTAssertEqual(captured.first?.0, AnalyticsManager.homeKnowsRowEvent)
    XCTAssertEqual(captured.first?.1["kind"] as? String, "task")
    XCTAssertEqual(captured.first?.1["slot"] as? String, "pressing_task")
    XCTAssertEqual(captured.first?.1["shows_before"] as? Int, 2)
    XCTAssertNil(captured.first?.1["rotated_out_reason"], "a rendered row rotated nothing out")
  }

  func testEmptySlotCarriesTheRotationReason() {
    var captured: [String: Any] = [:]
    AnalyticsManager.homeKnowsTelemetryCaptureForTests = { _, props in captured = props }

    AnalyticsManager.shared.trackHomeKnowsSlotEmpty(slot: .secondTask, reason: .dismissed)

    XCTAssertEqual(captured["kind"] as? String, "empty")
    XCTAssertEqual(captured["slot"] as? String, "second_task")
    XCTAssertEqual(captured["rotated_out_reason"] as? String, "dismissed")
    XCTAssertEqual(captured["shows_before"] as? Int, 0)
  }

  /// The property is a closed set because it is a PostHog dimension: an unbounded one would make
  /// the breakdown unreadable and is the failure this enum exists to prevent.
  func testEveryRotationReasonIsASnakeCaseRawValue() {
    for reason in HomeKnowsRotationReason.allCases {
      XCTAssertFalse(reason.rawValue.isEmpty)
      XCTAssertEqual(reason.rawValue, reason.rawValue.lowercased())
    }
  }
}
