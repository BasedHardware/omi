import XCTest

@testable import Omi_Computer

final class HomeKnowsComposerTests: XCTestCase {
  private let tasks = [
    HomeKnowsTaskCandidate(id: "t1", text: "Submit the Design PR by 7pm"),
    HomeKnowsTaskCandidate(id: "t2", text: "Reply to Sarah"),
  ]
  private let insights = [
    HomeKnowsInsightCandidate(id: "i1", text: "Deepgram spend is pacing 18% over last week"),
    HomeKnowsInsightCandidate(id: "i2", text: "Two meetings overlap on Thursday"),
  ]
  private let questions = ["What should I do today?", "What did I spend my time on this week?"]

  func testComposePicksTaskInsightTaskQuestionWhenAllAvailable() {
    let rows = HomeKnowsListComposer.compose(tasks: tasks, insights: insights, questions: questions).rows

    // Diverse 4-slot brief: pressing task, one insight, a second task, then a prefilled ask.
    XCTAssertEqual(rows.count, 4)
    XCTAssertEqual(rows[0].kind, .task(id: "t1"))
    XCTAssertEqual(rows[0].text, "Submit the Design PR by 7pm")
    XCTAssertEqual(rows[1].kind, .insight(id: "i1"))
    XCTAssertEqual(rows[2].kind, .task(id: "t2"))
    XCTAssertEqual(rows[3].kind, .question)
    XCTAssertEqual(rows[3].text, "What should I do today?")
  }

  func testDismissedTaskFallsThroughToNextTask() {
    let ledger = HomeKnowsLedgerFixture.dismissing(taskID: "t1", text: "Submit the Design PR by 7pm")
    let rows = HomeKnowsListComposer.compose(
      tasks: tasks, insights: insights, questions: questions, ledger: ledger
    ).rows

    XCTAssertEqual(rows[0].kind, .task(id: "t2"))
  }

  func testAllTasksDismissedFillsWithOneInsightAndQuestion() {
    var ledger = HomeKnowsLedgerFixture.dismissing(taskID: "t1", text: "Submit the Design PR by 7pm")
    ledger.entries.merge(
      HomeKnowsLedgerFixture.dismissing(taskID: "t2", text: "Reply to Sarah").entries
    ) { _, new in new }

    let composition = HomeKnowsListComposer.compose(
      tasks: tasks, insights: insights, questions: questions, ledger: ledger)

    // At most one insight (the tip slot); the ask fills the remaining slot.
    XCTAssertEqual(composition.rows.count, 2)
    XCTAssertEqual(composition.rows[0].kind, .insight(id: "i1"))
    XCTAssertEqual(composition.rows[1].kind, .question)
    // Both task slots report why they stayed empty rather than repeating.
    XCTAssertEqual(
      composition.emptySlots,
      [
        HomeKnowsEmptySlot(slot: .pressingTask, reason: .dismissed),
        HomeKnowsEmptySlot(slot: .secondTask, reason: .dismissed),
      ])
  }

  func testSingleAskWhenNoTasksOrInsights() {
    let rows = HomeKnowsListComposer.compose(
      tasks: [], insights: [], questions: questions + ["Third question?"]
    ).rows

    // Only one prefilled ask is ever surfaced — the list never collapses into all-questions.
    XCTAssertEqual(rows.count, 1)
    XCTAssertEqual(rows[0].kind, .question)
    XCTAssertEqual(rows[0].text, "What should I do today?")
  }

  func testSecondTaskFillsLastSlotWhenNoQuestionExists() {
    let rows = HomeKnowsListComposer.compose(tasks: tasks, insights: insights, questions: []).rows

    // With no ask, the last slot goes to a second task — never a second insight.
    XCTAssertEqual(rows.count, 3)
    XCTAssertEqual(rows[0].kind, .task(id: "t1"))
    XCTAssertEqual(rows[1].kind, .insight(id: "i1"))
    XCTAssertEqual(rows[2].kind, .task(id: "t2"))
  }

  func testEmptyAndWhitespaceEntriesAreSkipped() {
    let rows = HomeKnowsListComposer.compose(
      tasks: [HomeKnowsTaskCandidate(id: "t0", text: "   ")],
      insights: [HomeKnowsInsightCandidate(id: "i0", text: "")],
      questions: ["  ", "Real question?"]
    ).rows

    XCTAssertEqual(rows.count, 1)
    XCTAssertEqual(rows[0].kind, .question)
    XCTAssertEqual(rows[0].text, "Real question?")
  }

  func testEverythingEmptyProducesNoRows() {
    XCTAssertTrue(HomeKnowsListComposer.compose(tasks: [], insights: [], questions: []).rows.isEmpty)
  }

  func testDuplicateQuestionsDoNotCollideAcrossQuestionRows() {
    // Question rows derive their ForEach ID from the text, so a repeated
    // suggestion must never surface twice. The redesign surfaces at most two
    // question-kind rows (a composed tip in the second slot and a distinct ask
    // in the last), so use a tip to exercise both and assert the repeat is
    // dropped and the two IDs stay unique.
    let rows = HomeKnowsListComposer.compose(
      tasks: [], insights: [],
      tip: "What should I do today?",
      questions: ["What should I do today?", " What should I do today? ", "Second question?"]
    ).rows

    XCTAssertEqual(rows.count, 2)
    XCTAssertEqual(rows.map(\.kind), [.question, .question])
    XCTAssertEqual(rows.map(\.text), ["What should I do today?", "Second question?"])
    XCTAssertEqual(Set(rows.map(\.id)).count, rows.count)
  }

  func testDuplicateTaskIDsAcrossBucketsSurfaceOnce() {
    // The hub concatenates overdue + today + no-due-date, which can repeat a row.
    let rows = HomeKnowsListComposer.compose(
      tasks: tasks + [HomeKnowsTaskCandidate(id: "t1", text: "Submit the Design PR by 7pm")],
      insights: [], questions: []
    ).rows

    XCTAssertEqual(rows.map(\.kind), [.task(id: "t1"), .task(id: "t2")])
  }

  // MARK: Rotation — the list gets shorter rather than repeating

  /// The reported defect: a thin source re-showed the same four rows on every
  /// visit. With the ledger, the second visit that same day is short, not a repeat.
  func testAlreadyShownRowsLeaveSlotsEmptyInsteadOfRepeating() {
    let now = HomeKnowsLedgerFixture.noon
    var ledger = HomeKnowsImpressionLedger.empty
    for task in tasks {
      ledger.entries[HomeKnowsRotationPolicy.taskKey(task.id)] =
        HomeKnowsLedgerFixture.shownToday(text: task.text, now: now)
    }
    ledger.entries[HomeKnowsRotationPolicy.insightKey("i1")] =
      HomeKnowsLedgerFixture.shownToday(text: insights[0].text, now: now)

    let composition = HomeKnowsListComposer.compose(
      tasks: tasks, insights: insights, questions: questions, ledger: ledger, now: now)

    // Both tasks and the first insight were shown today; only the untouched
    // insight and the ask still qualify. The list is shorter, never repeated.
    XCTAssertEqual(composition.rows.map(\.kind), [.insight(id: "i2"), .question])
    XCTAssertEqual(
      composition.emptySlots,
      [
        HomeKnowsEmptySlot(slot: .pressingTask, reason: .sameDay),
        HomeKnowsEmptySlot(slot: .secondTask, reason: .sameDay),
      ])
  }

  func testEverySourceExhaustedProducesAnEmptyListNotAFallbackRepeat() {
    let now = HomeKnowsLedgerFixture.noon
    let tip = "Recap what I got done today"
    var ledger = HomeKnowsImpressionLedger.empty
    ledger.entries[HomeKnowsRotationPolicy.taskKey("t1")] = HomeKnowsLedgerFixture.shownToday(
      text: tasks[0].text, now: now)
    ledger.entries[HomeKnowsRotationPolicy.questionKey(questions[0])] =
      HomeKnowsLedgerFixture.shownToday(text: questions[0], now: now)
    ledger.entries[HomeKnowsRotationPolicy.questionKey(tip)] =
      HomeKnowsLedgerFixture.shownToday(text: tip, now: now)

    let composition = HomeKnowsListComposer.compose(
      tasks: [tasks[0]], insights: [], tip: tip, questions: [questions[0]], ledger: ledger, now: now)

    XCTAssertTrue(composition.rows.isEmpty)
    XCTAssertEqual(composition.emptySlots.map(\.slot), [.pressingTask, .tip, .secondTask, .ask])
    XCTAssertTrue(composition.emptySlots.allSatisfy { $0.reason == .sameDay })
  }

  func testSameDayRepeatIsAllowedOnlyForAPreviouslyOpenedRow() {
    let now = HomeKnowsLedgerFixture.noon
    var ledger = HomeKnowsImpressionLedger.empty
    var opened = HomeKnowsLedgerFixture.shownToday(text: tasks[0].text, now: now)
    opened.lastOpenedAt = HomeKnowsLedgerFixture.sameDay(as: now)
    ledger.entries[HomeKnowsRotationPolicy.taskKey("t1")] = opened

    // Nothing else qualifies for the task slot, and this row has been opened
    // before, so the same-day rule relaxes for it.
    let composition = HomeKnowsListComposer.compose(
      tasks: [tasks[0]], insights: [], questions: [], ledger: ledger, now: now)

    XCTAssertEqual(composition.rows.map(\.kind), [.task(id: "t1")])
  }

  func testAnotherQualifyingTaskWinsOverASameDayRepeat() {
    let now = HomeKnowsLedgerFixture.noon
    var ledger = HomeKnowsImpressionLedger.empty
    var opened = HomeKnowsLedgerFixture.shownToday(text: tasks[0].text, now: now)
    opened.lastOpenedAt = HomeKnowsLedgerFixture.sameDay(as: now)
    ledger.entries[HomeKnowsRotationPolicy.taskKey("t1")] = opened

    let composition = HomeKnowsListComposer.compose(
      tasks: tasks, insights: [], questions: [], ledger: ledger, now: now)

    // t2 has never been shown, so the strict pass succeeds and t1 stays out.
    XCTAssertEqual(composition.rows.map(\.kind), [.task(id: "t2")])
  }

  func testStaleAndCompletedTasksAreExcluded() {
    let now = HomeKnowsLedgerFixture.noon
    let candidates = [
      HomeKnowsTaskCandidate(id: "old", text: "Long-dead commitment", dueAt: now.addingTimeInterval(-20 * 86_400)),
      HomeKnowsTaskCandidate(id: "done", text: "Finished thing", isActive: false),
      HomeKnowsTaskCandidate(id: "live", text: "Still open", dueAt: now.addingTimeInterval(-3 * 86_400)),
    ]

    let composition = HomeKnowsListComposer.compose(
      tasks: candidates, insights: [], questions: [], now: now)

    XCTAssertEqual(composition.rows.map(\.kind), [.task(id: "live")])
  }

  func testFreshnessOrderPrefersNeverShownThenFewestShows() {
    let now = HomeKnowsLedgerFixture.noon
    let yesterday = HomeKnowsLedgerFixture.previousDay(before: now)
    let candidates = [
      HomeKnowsTaskCandidate(id: "seenTwice", text: "Seen twice"),
      HomeKnowsTaskCandidate(id: "seenOnce", text: "Seen once"),
      HomeKnowsTaskCandidate(id: "neverSeen", text: "Never seen"),
    ]
    var ledger = HomeKnowsImpressionLedger.empty
    ledger.entries[HomeKnowsRotationPolicy.taskKey("seenTwice")] = HomeKnowsImpression(
      shows: 2, lastShownAt: yesterday,
      contentHash: HomeKnowsRotationPolicy.contentHash(text: "Seen twice"))
    ledger.entries[HomeKnowsRotationPolicy.taskKey("seenOnce")] = HomeKnowsImpression(
      shows: 1, lastShownAt: yesterday,
      contentHash: HomeKnowsRotationPolicy.contentHash(text: "Seen once"))

    let composition = HomeKnowsListComposer.compose(
      tasks: candidates, insights: [], questions: [], ledger: ledger, now: now)

    XCTAssertEqual(composition.rows.map(\.kind), [.task(id: "neverSeen"), .task(id: "seenOnce")])
    XCTAssertEqual(composition.rows.map(\.showsBefore), [0, 1])
  }

  /// Equal freshness must fall back to the caller's own priority order. An
  /// earlier revision tie-broke on the ledger key, which is a hash, and silently
  /// reordered the suggested questions the caller had already ranked.
  func testEquallyFreshCandidatesKeepTheCallersOrder() {
    let composition = HomeKnowsListComposer.compose(
      tasks: [], insights: [], questions: questions, now: HomeKnowsLedgerFixture.noon)

    XCTAssertEqual(composition.rows.first?.text, questions[0])
  }

  func testFreshnessOrderBreaksTiesOnMostRecentUpdate() {
    let now = HomeKnowsLedgerFixture.noon
    let candidates = [
      HomeKnowsTaskCandidate(id: "stale", text: "Older update", updatedAt: now.addingTimeInterval(-7200)),
      HomeKnowsTaskCandidate(id: "fresh", text: "Newer update", updatedAt: now.addingTimeInterval(-60)),
    ]

    let composition = HomeKnowsListComposer.compose(
      tasks: candidates, insights: [], questions: [], now: now)

    XCTAssertEqual(composition.rows.first?.kind, .task(id: "fresh"))
  }

  func testCanRotateOnlyWhenMoreCandidatesStillQualify() {
    let now = HomeKnowsLedgerFixture.noon
    XCTAssertFalse(
      HomeKnowsListComposer.compose(tasks: tasks, insights: [], questions: [], now: now).canRotate)

    let three = tasks + [HomeKnowsTaskCandidate(id: "t3", text: "Third task")]
    XCTAssertTrue(
      HomeKnowsListComposer.compose(tasks: three, insights: [], questions: [], now: now).canRotate)

    // A third task that no longer qualifies does not make the list rotatable.
    var ledger = HomeKnowsImpressionLedger.empty
    ledger.entries[HomeKnowsRotationPolicy.taskKey("t3")] = HomeKnowsLedgerFixture.shownToday(
      text: "Third task", now: now)
    XCTAssertFalse(
      HomeKnowsListComposer.compose(tasks: three, insights: [], questions: [], ledger: ledger, now: now)
        .canRotate)
  }

  func testOpenTaskCountIgnoresDismissedAndCompletedTasks() {
    let ledger = HomeKnowsLedgerFixture.dismissing(taskID: "t1", text: "Submit the Design PR by 7pm")
    let candidates = tasks + [HomeKnowsTaskCandidate(id: "done", text: "Finished", isActive: false)]

    XCTAssertEqual(HomeKnowsListComposer.openTaskCount(candidates), 2)
    XCTAssertEqual(HomeKnowsListComposer.openTaskCount(candidates, ledger: ledger), 1)
  }
}

/// Shared ledger fixtures. A fixed instant keeps the calendar-day rules
/// deterministic regardless of when the suite runs.
enum HomeKnowsLedgerFixture {
  /// 2026-03-07 12:00:00 UTC — mid-day, so "same calendar day" is unambiguous.
  static let noon = Date(timeIntervalSince1970: 1_772_884_800)

  /// An instant guaranteed to be the same *local* calendar day as `now`, so the
  /// same-day rule is asserted the same way in every timezone the suite runs in.
  static func sameDay(as now: Date, calendar: Calendar = .current) -> Date {
    calendar.startOfDay(for: now)
  }

  static func previousDay(before now: Date, calendar: Calendar = .current) -> Date {
    calendar.startOfDay(for: now).addingTimeInterval(-1)
  }

  static func shownToday(text: String, now: Date, shows: Int = 1) -> HomeKnowsImpression {
    HomeKnowsImpression(
      shows: shows,
      firstShownAt: sameDay(as: now),
      lastShownAt: sameDay(as: now),
      contentHash: HomeKnowsRotationPolicy.contentHash(text: text))
  }

  static func dismissing(taskID: String, text: String, at date: Date = noon) -> HomeKnowsImpressionLedger {
    var ledger = HomeKnowsImpressionLedger.empty
    ledger.entries[HomeKnowsRotationPolicy.taskKey(taskID)] = HomeKnowsImpression(
      shows: 1,
      firstShownAt: date,
      lastShownAt: date,
      dismissedAt: date,
      contentHash: HomeKnowsRotationPolicy.contentHash(text: text))
    return ledger
  }
}
