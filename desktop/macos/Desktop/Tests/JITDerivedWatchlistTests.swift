import XCTest

@testable import Omi_Computer

final class JITDerivedWatchlistTests: XCTestCase {
  func testKeywordsAreBoundedLowercasedAndFreeOfStopwordsAndNumbers() {
    let keywords = JITDerivedWatchlistCompiler.keywords(
      from: "Follow up with Martin Lange about the Grafana dashboard before Thursday 2026, then update the runbook")
    XCTAssertEqual(keywords, ["martin", "lange", "grafana", "dashboard", "thursday", "runbook"])
    XCTAssertTrue(JITDerivedWatchlistCompiler.keywords(from: "Review the pull request and reply").isEmpty)
    XCTAssertEqual(keywords.count, JITDerivedWatchlistCompiler.maxKeywordsPerEntry)
    XCTAssertTrue(JITDerivedWatchlistCompiler.keywords(from: "call them back today").isEmpty)
  }

  func testCompileIsDeterministicDedupedAndBounded() {
    let tasks = (0..<100).map { (identity: "task-\($0)", description: "Review pull request \($0) for gateway routing") }
    let entries = JITDerivedWatchlistCompiler.compile(tasks: tasks, goals: [(identity: "g1", title: "Ship gateway v2")])
    XCTAssertEqual(entries.count, JITDerivedWatchlistCompiler.maxEntries)
    XCTAssertEqual(Set(entries.map(\.id)).count, entries.count)
    XCTAssertTrue(entries.allSatisfy { $0.source == .task })

    let again = JITDerivedWatchlistCompiler.compile(tasks: tasks, goals: [])
    XCTAssertEqual(entries, again)

    let duplicate = JITDerivedWatchlistCompiler.compile(
      tasks: [(identity: "", description: "Ship gateway v2"), (identity: "", description: "Ship gateway v2")],
      goals: [])
    XCTAssertEqual(duplicate.count, 1)
    XCTAssertTrue(JITProactivityReservation.isIdentifier(duplicate[0].id))
  }

  func testMatchRequiresTwoKeywordHitsAndIgnoresGenericOverlap() {
    let entries = JITDerivedWatchlistCompiler.compile(
      tasks: [
        (identity: "t1", description: "Review the Grafana dashboard alert rules"),
        (identity: "t2", description: "Book dentist appointment"),
      ],
      goals: [])
    let observation = KnowledgeLedgerTriggerObservation(
      text: "Grafana — Alert rules — omi-prod", windowTitle: "Grafana dashboard")

    let match = JITDerivedWatchlistMatcher.match(entries: entries, observation: observation)
    XCTAssertEqual(match.entries.map(\.label), ["Review the Grafana dashboard alert rules"])

    let oneHit = JITDerivedWatchlistMatcher.match(
      entries: entries, observation: KnowledgeLedgerTriggerObservation(text: "dentist reviews"))
    XCTAssertTrue(oneHit.isEmpty)
  }

  func testEntriesNeedTwoDiscriminatingKeywordsAndGenericTasksNeverMatchPRWindows() throws {
    XCTAssertNil(JITDerivedWatchlistCompiler.entry(source: .goal, identity: "g", text: "Learn"))
    XCTAssertNil(
      JITDerivedWatchlistCompiler.entry(source: .task, identity: "t", text: "Review pull request"),
      "generic workflow words are stopwords, so this task has no discriminating keyword")
    let short = try XCTUnwrap(
      JITDerivedWatchlistCompiler.entry(source: .goal, identity: "g2", text: "Meditate daily"))
    XCTAssertEqual(short.keywords, ["meditate", "daily"])
    let match = JITDerivedWatchlistMatcher.match(
      entries: [short], observation: KnowledgeLedgerTriggerObservation(text: "daily meditate timer"))
    XCTAssertEqual(match.entries, [short])

    let gateway = try XCTUnwrap(
      JITDerivedWatchlistCompiler.entry(
        source: .task, identity: "t2", text: "Review pull request for gateway routing"))
    XCTAssertEqual(gateway.keywords, ["gateway", "routing"])
    let unrelatedPR = KnowledgeLedgerTriggerObservation(
      text: "Fix typo in README · Pull Request #12 · BasedHardware/omi", windowTitle: "Pull Request #12")
    XCTAssertTrue(JITDerivedWatchlistMatcher.match(entries: [gateway], observation: unrelatedPR).isEmpty)
  }

  func testCalendarPresenceMatchesWithoutLeakingEventTitles() throws {
    let observation = KnowledgeLedgerTriggerObservation(
      text: "notes",
      calendarEvents: [KnowledgeLedgerTriggerCalendarEvent(title: "Board meeting with Acme", eventType: "meeting")])
    let match = JITDerivedWatchlistMatcher.match(entries: [], observation: observation)
    XCTAssertEqual(match.entries.count, 1)
    XCTAssertEqual(match.entries[0].source, .calendar)
    let section = try XCTUnwrap(match.promptSection())
    XCTAssertFalse(section.contains("Acme"))
    XCTAssertTrue(section.contains(JITDerivedWatchlistMatcher.calendarLabel))
  }

  func testPromptSectionIsStableAndBounded() throws {
    let entries = (0..<10).map {
      JITDerivedIntentEntry(id: "id-\($0)", source: .task, label: "task \($0)", keywords: ["alpha", "beta"])
    }
    let match = JITDerivedIntentMatch(entries: entries)
    let section = try XCTUnwrap(match.promptSection())
    XCTAssertEqual(section.components(separatedBy: "\n- ").count - 1, JITDerivedIntentMatch.maxPromptEntries)
    XCTAssertNil(JITDerivedIntentMatch.none.promptSection())
  }

  func testSourceCachesPerOwnerAndRefreshesAfterInterval() async {
    let loads = LoadCounter()
    let source = JITDerivedWatchlistSource(loader: {
      await loads.increment()
      return [JITDerivedIntentEntry(id: "x", source: .task, label: "x", keywords: ["alpha", "beta"])]
    })
    let start = Date(timeIntervalSince1970: 1_777_248_000)
    _ = await source.entries(ownerID: "a", now: start)
    _ = await source.entries(ownerID: "a", now: start.addingTimeInterval(60))
    var count = await loads.count
    XCTAssertEqual(count, 1)
    _ = await source.entries(ownerID: "b", now: start.addingTimeInterval(61))
    count = await loads.count
    XCTAssertEqual(count, 2, "an owner change never reuses another owner's intent")
    _ = await source.entries(
      ownerID: "b", now: start.addingTimeInterval(61 + JITDerivedWatchlistSource.refreshInterval))
    count = await loads.count
    XCTAssertEqual(count, 3)
  }
}

private actor LoadCounter {
  private(set) var count = 0
  func increment() { count += 1 }
}
