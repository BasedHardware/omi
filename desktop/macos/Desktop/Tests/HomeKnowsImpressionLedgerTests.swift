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

@MainActor
final class HomeKnowsImpressionStoreTests: XCTestCase {
  /// In-memory persistence so the rules are asserted without UserDefaults.
  private final class FakePersistence: HomeKnowsImpressionPersisting {
    var ledger = HomeKnowsImpressionLedger.empty
    var saves = 0

    func load() -> HomeKnowsImpressionLedger { ledger }
    func save(_ ledger: HomeKnowsImpressionLedger) {
      self.ledger = ledger
      saves += 1
    }
  }

  private var persistence = FakePersistence()
  private var clock = HomeKnowsLedgerFixture.noon
  private var store = HomeKnowsImpressionStore()
  private let hash = HomeKnowsRotationPolicy.contentHash(text: "Meet with Priya")

  override func setUp() {
    super.setUp()
    persistence = FakePersistence()
    clock = HomeKnowsLedgerFixture.noon
    store = HomeKnowsImpressionStore(persistence: persistence, now: { self.clock })
  }

  func testShowIsRecordedOncePerVisitNotOncePerRender() {
    store.beginVisit()
    XCTAssertEqual(store.recordShown(key: "task:t1", contentHash: hash)?.shows, 1)
    // The in-visit rotation timer re-renders the same row every few seconds.
    XCTAssertNil(store.recordShown(key: "task:t1", contentHash: hash))
    XCTAssertNil(store.recordShown(key: "task:t1", contentHash: hash))
    XCTAssertEqual(persistence.ledger.entry("task:t1")?.shows, 1)

    store.beginVisit()
    XCTAssertEqual(store.recordShown(key: "task:t1", contentHash: hash)?.shows, 2)
  }

  func testEmptySlotIsReportedOncePerVisit() {
    store.beginVisit()
    XCTAssertTrue(store.shouldReportEmptySlot("tip"))
    XCTAssertFalse(store.shouldReportEmptySlot("tip"))
    store.beginVisit()
    XCTAssertTrue(store.shouldReportEmptySlot("tip"))
  }

  func testFirstAndLastShownTrackSeparately() {
    store.beginVisit()
    store.recordShown(key: "task:t1", contentHash: hash)
    let first = clock
    clock = clock.addingTimeInterval(2 * 86_400)
    store.beginVisit()
    store.recordShown(key: "task:t1", contentHash: hash)

    let entry = store.snapshot().entry("task:t1")
    XCTAssertEqual(entry?.firstShownAt, first)
    XCTAssertEqual(entry?.lastShownAt, clock)
    XCTAssertEqual(entry?.shows, 2)
  }

  func testShowCountResetsAfterTheCooldownSoTheCapIsThreeShowsPerWindow() {
    for _ in 0..<HomeKnowsRotationPolicy.showCapCount {
      store.beginVisit()
      store.recordShown(key: "task:t1", contentHash: hash)
      clock = clock.addingTimeInterval(86_400)
    }
    XCTAssertEqual(store.snapshot().entry("task:t1")?.shows, 3)

    clock = clock.addingTimeInterval(HomeKnowsRotationPolicy.showCapCooldown)
    store.beginVisit()
    XCTAssertEqual(store.recordShown(key: "task:t1", contentHash: hash)?.shows, 1)
  }

  func testChangedContentResetsTheCountAndClearsADismissal() {
    store.beginVisit()
    store.recordShown(key: "task:t1", contentHash: hash)
    store.recordDismissed(key: "task:t1", contentHash: hash)
    XCTAssertNotNil(store.snapshot().entry("task:t1")?.dismissedAt)

    let edited = HomeKnowsRotationPolicy.contentHash(text: "Meet with Priya about Q3")
    store.beginVisit()
    let entry = store.recordShown(key: "task:t1", contentHash: edited)
    XCTAssertEqual(entry?.shows, 1)
    XCTAssertNil(entry?.dismissedAt)
    XCTAssertEqual(entry?.contentHash, edited)
  }

  func testOpeningARowClearsAnEarlierDismissal() {
    store.beginVisit()
    store.recordDismissed(key: "insight:i1", contentHash: hash)
    let entry = store.recordOpened(key: "insight:i1", contentHash: hash)

    XCTAssertNil(entry.dismissedAt)
    XCTAssertEqual(entry.lastOpenedAt, clock)
  }

  /// The composer reads the store's snapshot, so the two must agree: a row the
  /// store has recorded three times is one the policy holds back.
  func testStoreAndPolicyAgreeOnTheShowCap() {
    for _ in 0..<HomeKnowsRotationPolicy.showCapCount {
      store.beginVisit()
      store.recordShown(key: "task:t1", contentHash: hash)
      clock = clock.addingTimeInterval(86_400)
    }

    let composition = HomeKnowsListComposer.compose(
      tasks: [HomeKnowsTaskCandidate(id: "t1", text: "Meet with Priya")],
      insights: [], questions: [],
      ledger: store.snapshot(), now: clock)

    XCTAssertTrue(composition.rows.isEmpty)
    XCTAssertEqual(
      composition.emptySlots.first, HomeKnowsEmptySlot(slot: .pressingTask, reason: .showCap))
  }
}

// MARK: - Persistence

@MainActor
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

  func testLedgerRoundTrips() {
    let store = HomeKnowsImpressionDefaults(defaults: defaults, ownerID: "owner-a")
    var ledger = HomeKnowsImpressionLedger.empty
    ledger.entries["task:t1"] = HomeKnowsImpression(
      shows: 2, lastShownAt: HomeKnowsLedgerFixture.noon, contentHash: "abc")
    store.save(ledger)

    XCTAssertEqual(HomeKnowsImpressionDefaults(defaults: defaults, ownerID: "owner-a").load(), ledger)
  }

  func testOneOwnersDismissalsDoNotSilenceAnother() {
    let owner = HomeKnowsImpressionDefaults(defaults: defaults, ownerID: "owner-a")
    var ledger = HomeKnowsImpressionLedger.empty
    ledger.entries["task:t1"] = HomeKnowsImpression(
      dismissedAt: HomeKnowsLedgerFixture.noon, contentHash: "abc")
    owner.save(ledger)

    let other = HomeKnowsImpressionDefaults(defaults: defaults, ownerID: "owner-b")
    XCTAssertEqual(other.load(), .empty)
  }

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

  func testCorruptPayloadLoadsAsAnEmptyLedgerRatherThanTrapping() {
    let store = HomeKnowsImpressionDefaults(defaults: defaults, ownerID: "owner-a")
    var ledger = HomeKnowsImpressionLedger.empty
    ledger.entries["task:t1"] = HomeKnowsImpression(shows: 1, contentHash: "abc")
    store.save(ledger)

    // Overwrite whatever key the store chose with something undecodable; a bad
    // payload must degrade to "no history", never trap the process.
    let storageKey = defaults.dictionaryRepresentation().keys.first { $0.hasPrefix("homeKnows.") }
    XCTAssertNotNil(storageKey)
    defaults.set(Data("not json".utf8), forKey: storageKey ?? "")

    XCTAssertEqual(store.load(), .empty)
  }
}
