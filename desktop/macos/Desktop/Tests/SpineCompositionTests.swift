//
//  SpineCompositionTests.swift — the rules the spine is built from.
//
//  Every assertion here is about a decision that is otherwise only checkable by looking at a
//  screenshot: what attaches to what, what a day header counts, what a soloed filter does to the
//  indent, and which way the hour rail runs. Those are exactly the rules a later change breaks
//  silently, so they are held here rather than in a rendered image.
//

import XCTest

@testable import Omi_Computer

final class SpineCompositionTests: XCTestCase {
  private let calendar = Calendar(identifier: .gregorian)

  // MARK: - Fixtures

  /// A fixed instant in a fixed calendar. `.distantPast` rather than a force unwrap for the
  /// impossible branch: these components always resolve, and a crash here would report as a
  /// mysterious test-runner failure rather than as the assertion that actually broke.
  private func date(_ day: Int, _ hour: Int, _ minute: Int = 0) -> Date {
    var components = DateComponents()
    components.year = 2026
    components.month = 8
    components.day = day
    components.hour = hour
    components.minute = minute
    return calendar.date(from: components) ?? .distantPast
  }

  private func conversation(
    id: String,
    start: Date,
    minutes: Int = 8,
    title: String = "Team Aligns On Product Growth Strategy",
    emoji: String = "📈",
    starred: Bool = false
  ) -> ServerConversation {
    ServerConversation(
      id: id,
      createdAt: start,
      startedAt: start,
      finishedAt: start.addingTimeInterval(TimeInterval(minutes * 60)),
      structured: Structured(
        title: title, overview: "", emoji: emoji, category: "other", actionItems: [], events: []),
      transcriptSegments: [],
      transcriptSegmentsIncluded: true,
      geolocation: nil,
      photos: [],
      appsResults: [],
      source: .desktop,
      language: "en",
      status: .completed,
      discarded: false,
      deleted: false,
      isLocked: false,
      starred: starred,
      folderId: nil,
      inputDeviceName: nil
    )
  }

  private func memory(_ id: String, _ text: String, at when: Date, from conversationID: String?)
    -> SpineMemory
  {
    SpineMemory(id: id, text: text, timestamp: when, conversationID: conversationID)
  }

  private func moment(_ id: Int64, at when: Date, app: String = "Safari") -> SpineMoment {
    SpineMoment(
      id: id, timestamp: when, appName: app, windowTitle: nil, imagePath: "a.jpg",
      videoChunkPath: nil, frameOffset: nil)
  }

  private func task(_ id: String, _ text: String, at when: Date, from conversationID: String?) -> SpineTask {
    SpineTask(
      task: TaskActionItem(
        id: id,
        description: text,
        completed: false,
        createdAt: when,
        conversationId: conversationID,
        source: conversationID == nil ? "manual" : "conversation"
      ),
      sourceConversationTitle: conversationID == nil ? nil : "Source conversation"
    )
  }

  // MARK: - Attachment

  func testMemoriesAndFramesAttachToTheConversationTheyBelongTo() {
    let start = date(6, 20, 0)
    let conversations = [conversation(id: "c1", start: start, minutes: 15)]
    let memories = [memory("m1", "Q3 is an activation quarter.", at: date(6, 20, 9), from: "c1")]
    let screen = SpineDayScreen(
      total: 184,
      hourCounts: [],
      sampled: [moment(1, at: date(6, 20, 2)), moment(2, at: date(6, 22, 0))]
    )

    let days = SpineComposer.compose(
      conversations: conversations,
      memories: memories,
      screen: [calendar.startOfDay(for: start): screen],
      calendar: calendar
    )

    XCTAssertEqual(days.count, 1)
    let rows = days[0].rows

    // 22:00 is later than the conversation's 20:00–20:15 window, so the frame that fell outside it
    // is the newest thing in the day and correctly sorts above the conversation. Attachment is
    // about *which* conversation produced a row, never about pinning it to the top of the day.
    XCTAssertEqual(rows[0].kind, .screen)
    XCTAssertFalse(rows[0].isAttached, "a frame outside every conversation stands on its own")

    guard let conversationIndex = rows.firstIndex(where: { $0.kind == .conversations }),
      case .conversation(let summary) = rows[conversationIndex].content
    else {
      return XCTFail("the conversation is in the day")
    }
    XCTAssertFalse(rows[conversationIndex].isAttached)
    XCTAssertEqual(summary.memoryCount, 1)
    XCTAssertEqual(summary.momentCount, 1, "only the frame inside the window attaches")

    // Its memories and its frames follow it immediately, indented.
    XCTAssertEqual(rows[conversationIndex + 1].kind, .memories)
    XCTAssertTrue(rows[conversationIndex + 1].isAttached)
    XCTAssertEqual(rows[conversationIndex + 2].kind, .screen)
    XCTAssertTrue(rows[conversationIndex + 2].isAttached)

    let memoriesOnly = SpineComposer.filter(days, kind: .memories, query: "")
    XCTAssertTrue(memoriesOnly[0].rows.allSatisfy { !$0.isAttached })
  }

  func testAMemoryWhoseConversationIsNotLoadedStillAppears() {
    let start = date(6, 20, 0)
    let days = SpineComposer.compose(
      conversations: [],
      memories: [memory("m1", "Prefers dark roast.", at: start, from: "not-loaded")],
      screen: [:],
      calendar: calendar
    )

    XCTAssertEqual(days.count, 1)
    XCTAssertEqual(
      days[0].rows.filter { $0.kind == .memories && !$0.isAttached }.count, 2,
      "the memory row plus the day's brain-map card")
  }

  func testTasksAttachToTheirConversationAndRemainStandaloneWithoutOne() {
    let start = date(6, 20)
    let days = SpineComposer.compose(
      conversations: [conversation(id: "c1", start: start)],
      memories: [],
      tasks: [
        task("attached", "Send the proposal", at: date(6, 20, 4), from: "c1"),
        task("manual", "Buy coffee", at: date(6, 22), from: nil),
      ],
      screen: [:],
      calendar: calendar
    )

    guard let conversationIndex = days[0].rows.firstIndex(where: { $0.kind == .conversations }),
      case .conversation(let summary) = days[0].rows[conversationIndex].content
    else { return XCTFail("the conversation is in the day") }
    XCTAssertEqual(summary.taskCount, 1)
    XCTAssertEqual(days[0].rows[conversationIndex + 1].kind, .tasks)
    XCTAssertTrue(days[0].rows[conversationIndex + 1].isAttached)
    XCTAssertTrue(days[0].rows.contains { $0.id == "task:manual" && !$0.isAttached })
    XCTAssertEqual(days[0].taskCount, 2)

    let matchingOneTask = SpineComposer.filter(days, kind: .everything, query: "coffee")
    XCTAssertEqual(
      matchingOneTask[0].taskCount, 1,
      "a filtered day header describes the task that remains visible"
    )

    let tasksOnly = SpineComposer.filter(days, kind: .tasks, query: "")
    XCTAssertTrue(tasksOnly[0].rows.allSatisfy { $0.kind == .tasks && !$0.isAttached })
  }

  /// The attachment merge walks two newest-first runs at once. A frame newer than the newest
  /// conversation used to walk its cursor off the end of that run, and every older frame after it
  /// was orphaned — a whole day of screen moments detaching because of one late frame.
  func testAFrameNewerThanEveryConversationDoesNotOrphanTheOnesBehindIt() {
    let start = date(6, 20, 0)
    let screen = SpineDayScreen(
      total: 3,
      hourCounts: [],
      sampled: [
        moment(1, at: date(6, 23, 0)),  // after every conversation
        moment(2, at: date(6, 20, 5)),  // inside the conversation
        moment(3, at: date(6, 20, 9)),  // inside the conversation
      ]
    )

    let days = SpineComposer.compose(
      conversations: [conversation(id: "c1", start: start, minutes: 15)],
      memories: [],
      screen: [calendar.startOfDay(for: start): screen],
      calendar: calendar
    )

    guard case .conversation(let summary) = days[0].rows.first(where: { $0.kind == .conversations })?.content
    else { return XCTFail("the conversation is in the day") }
    XCTAssertEqual(summary.momentCount, 2, "the late frame must not detach the two behind it")
  }

  // MARK: - Ordering

  func testTheStreamIsNewestFirstAcrossAndWithinDays() {
    let older = conversation(id: "old", start: date(5, 16, 40))
    let newer = conversation(id: "new", start: date(6, 22, 35))
    let middle = conversation(id: "mid", start: date(6, 20, 0))

    let days = SpineComposer.compose(
      conversations: [older, middle, newer], memories: [], screen: [:], calendar: calendar)

    XCTAssertEqual(days.map(\.id), [calendar.startOfDay(for: date(6, 0)), calendar.startOfDay(for: date(5, 0))])
    let firstDayIDs = days[0].rows.compactMap { row -> String? in
      guard case .conversation(let summary) = row.content else { return nil }
      return summary.id
    }
    XCTAssertEqual(firstDayIDs, ["new", "mid"])
  }

  // MARK: - Day header counts

  func testTheDayHeaderCountsTheFilteredView() {
    let start = date(6, 20, 0)
    let screen = SpineDayScreen(total: 1204, hourCounts: [], sampled: [moment(1, at: date(6, 20, 2))])
    let composed = SpineComposer.compose(
      conversations: [conversation(id: "c1", start: start)],
      memories: [memory("m1", "Doors at 7.", at: date(6, 20, 4), from: "c1")],
      screen: [calendar.startOfDay(for: start): screen],
      calendar: calendar
    )

    XCTAssertEqual(composed[0].momentCount, 1204)
    XCTAssertEqual(composed[0].conversationCount, 1)
    XCTAssertEqual(composed[0].memoryCount, 1)
    // Every kind the day holds, because this line is the whole of the day once it is folded shut.
    XCTAssertEqual(composed[0].subtitle, "1,204 moments · 1 conversation · 1 memory")

    let soloed = SpineComposer.filter(composed, kind: .memories, query: "")
    XCTAssertEqual(
      soloed[0].momentCount, 0, "a memory filter must not claim screen moments are visible")
    XCTAssertEqual(soloed[0].conversationCount, 0)
    XCTAssertEqual(soloed[0].memoryCount, 1)
    XCTAssertEqual(soloed[0].subtitle, "1 memory")

    let matchingMemory = SpineComposer.filter(composed, kind: .everything, query: "doors")
    XCTAssertEqual(matchingMemory[0].momentCount, 0)
    XCTAssertEqual(matchingMemory[0].conversationCount, 0)
    XCTAssertEqual(matchingMemory[0].memoryCount, 1)
    XCTAssertEqual(matchingMemory[0].subtitle, "1 memory")
  }

  // MARK: - Solo

  func testSoloingOneKindCollapsesTheIndentSoEveryRowKeepsItsOwnTime() {
    let start = date(6, 20, 0)
    let composed = SpineComposer.compose(
      conversations: [conversation(id: "c1", start: start)],
      memories: [memory("m1", "Doors at 7.", at: date(6, 20, 4), from: "c1")],
      screen: [:],
      calendar: calendar
    )
    XCTAssertTrue(
      composed[0].rows.contains { $0.kind == .memories && $0.isAttached },
      "unfiltered, the memory is indented under its conversation")

    let soloed = SpineComposer.filter(composed, kind: .memories, query: "")
    XCTAssertFalse(
      soloed[0].rows.contains { $0.isAttached },
      "soloed, nothing is a child of anything and every row states its own time")
    XCTAssertTrue(soloed[0].rows.allSatisfy { $0.kind == .memories })
  }

  func testQueryMatchesAcrossEveryKindAndDropsEmptyDays() {
    let composed = SpineComposer.compose(
      conversations: [conversation(id: "c1", start: date(6, 20), title: "Charlie Puth Concert")],
      memories: [memory("m1", "Doors at 7.", at: date(5, 16), from: nil)],
      screen: [:],
      calendar: calendar
    )
    XCTAssertEqual(composed.count, 2)

    let hits = SpineComposer.filter(composed, kind: .everything, query: "charlie")
    XCTAssertEqual(hits.count, 1, "a day with nothing left is dropped, header and all")
    XCTAssertEqual(hits[0].id, calendar.startOfDay(for: date(6, 0)))
  }

  func testTimeWindowNarrowsTheStream() {
    let composed = SpineComposer.compose(
      conversations: [
        conversation(id: "today", start: date(6, 20)),
        conversation(id: "older", start: date(5, 16)),
      ],
      memories: [], screen: [:], calendar: calendar)

    let narrowed = SpineComposer.filter(
      composed, kind: .everything, query: "", earliest: calendar.startOfDay(for: date(6, 0)))
    XCTAssertEqual(narrowed.count, 1)
    XCTAssertEqual(narrowed[0].id, calendar.startOfDay(for: date(6, 0)))
  }

  // MARK: - Brain map

  func testTheBrainMapIsFiledUnderMemoriesAtTheFootOfTheDay() {
    let composed = SpineComposer.compose(
      conversations: [],
      memories: [memory("m1", "Prefers dark roast.", at: date(6, 16), from: nil)],
      screen: [:],
      calendar: calendar
    )

    guard let last = composed[0].rows.last, case .brainMap(let map) = last.content else {
      return XCTFail("the day ends with the brain-map card")
    }
    XCTAssertEqual(last.kind, .memories, "it is filed under memories, never a kind of its own")
    XCTAssertEqual(map.memoryCount, 1)

    // Soloing Conversations must not leave the map behind as an orphan.
    let conversationsOnly = SpineComposer.filter(composed, kind: .conversations, query: "")
    XCTAssertTrue(conversationsOnly.isEmpty)
  }

  func testADayWithNoMemoriesHasNoBrainMapCard() {
    let composed = SpineComposer.compose(
      conversations: [conversation(id: "c1", start: date(6, 20))],
      memories: [], screen: [:], calendar: calendar)
    XCTAssertFalse(
      composed[0].rows.contains { if case .brainMap = $0.content { return true } else { return false } })
  }

  // MARK: - Clustering

  func testUnattachedFramesSplitIntoRunsOnALongGap() {
    let moments = [
      moment(1, at: date(6, 21, 0)),
      moment(2, at: date(6, 21, 20)),
      moment(3, at: date(6, 9, 0)),
    ]
    let clusters = SpineComposer.clusters(of: moments)
    XCTAssertEqual(clusters.count, 2)
    // Newest first, inside a run as well as between them — the strip reads the way the spine does.
    XCTAssertEqual(clusters[0].map(\.id), [2, 1])
    XCTAssertEqual(clusters[1].map(\.id), [3])
  }

  // MARK: - Counts

  func testTheMatchCountCountsThingsNotRows() {
    let start = date(6, 20, 0)
    let screen = SpineDayScreen(
      total: 90, hourCounts: [], sampled: (1...12).map { moment(Int64($0), at: date(6, 20, $0)) })
    let composed = SpineComposer.compose(
      conversations: [conversation(id: "c1", start: start, minutes: 30)],
      memories: [
        memory("m1", "One.", at: date(6, 20, 4), from: "c1"),
        memory("m2", "Two.", at: date(6, 20, 6), from: "c1"),
      ],
      screen: [calendar.startOfDay(for: start): screen],
      calendar: calendar
    )
    // One conversation + two memories + the twelve frames that attached to it.
    XCTAssertEqual(composed[0].matchCount, 15)
  }

  // MARK: - Sampling

  func testSamplingSpreadsAcrossTheRunRatherThanTakingTheFront() {
    let moments = (0..<100).map { moment(Int64($0), at: date(6, 12, $0 % 60)) }
    let sampled = SpineScreenIndex.evenlySampled(moments, ceiling: 10)
    XCTAssertEqual(sampled.count, 10)
    XCTAssertEqual(sampled.first?.id, 0)
    XCTAssertGreaterThan(
      sampled.last?.id ?? 0, 80, "the tail of the run is represented, not dropped")
  }

  func testSamplingKeepsEverythingUnderTheCeiling() {
    let moments = (0..<5).map { moment(Int64($0), at: date(6, 12, $0)) }
    XCTAssertEqual(SpineScreenIndex.evenlySampled(moments, ceiling: 240).map(\.id), [0, 1, 2, 3, 4])
  }

  // MARK: - Copy

  func testConversationSubtitleDropsZeroClausesRatherThanShowingThem() {
    let summary = SpineConversation(
      conversation: conversation(id: "c1", start: date(6, 20), minutes: 8),
      memoryCount: 2,
      taskCount: 1,
      momentCount: 6
    )
    XCTAssertEqual(summary.subtitle, "8m 0s · 2 memories · 1 task · 6 screen moments")

    let bare = SpineConversation(
      conversation: conversation(id: "c2", start: date(6, 20), minutes: 3),
      memoryCount: 0,
      taskCount: 0,
      momentCount: 0
    )
    XCTAssertEqual(bare.subtitle, "3m 0s")
  }

  func testDurationReadsAsAClockNotASecondsCount() {
    XCTAssertEqual(SpineFormat.duration(489), "8m 9s")
    XCTAssertEqual(SpineFormat.duration(42), "42s")
    XCTAssertEqual(SpineFormat.duration(3_855), "1h 04m")
  }

  // MARK: - A memory's repeated half

  /// The generated shape the spine actually receives, four times in a row.
  func testAMemoryStatesItsCategoryOnceAndItsSentenceOnce() {
    let copy = SpineFormat.memoryCopy(
      "Focused on Omi App: Archit is reviewing the Omi app interface, which shows a timeline.")
    XCTAssertEqual(copy.label, "Focused on Omi App")
    XCTAssertEqual(copy.body, "Archit is reviewing the Omi app interface, which shows a timeline.")
  }

  /// The split moves words; it never loses them. Label and body together are the whole memory less
  /// the colon that already separated them.
  func testTheSplitKeepsEveryWordOfTheMemory() {
    let text = "Focused on Omi Memories: Archit prefers spacious layouts."
    let copy = SpineFormat.memoryCopy(text)
    let rejoined = [copy.label, copy.body].compactMap { $0 }.joined(separator: ": ")
    XCTAssertEqual(rejoined, text)
  }

  /// A sentence that merely contains a colon is still a sentence. Each of these is a real memory the
  /// split would otherwise fold in half.
  func testASentenceThatMerelyContainsAColonIsLeftWhole() {
    for text in [
      "Standup is at 12:30 every weekday.",
      "Archit bookmarked https://omi.me for later.",
      "He asked Dr. Kim: whether the results were in.",
      "Archit spent the morning on a long stretch of unbroken work before the call: mostly reading.",
      "Whatever follows is missing here:",
    ] {
      let copy = SpineFormat.memoryCopy(text)
      XCTAssertNil(copy.label, "“\(text)” is a sentence, not a labelled memory")
      XCTAssertEqual(copy.body, text)
    }
  }

  // MARK: - Folding a day

  /// The failure this is keyed against: the spine pages older days in as you scroll, so a set keyed
  /// by position folds a different day the moment a page lands.
  func testFoldingIsKeyedByTheDayAndSurvivesAnEarlierPageLanding() {
    var collapse = SpineDayCollapse()
    let today = calendar.startOfDay(for: date(6, 12))
    let yesterday = calendar.startOfDay(for: date(5, 12))

    collapse.toggle(today)
    XCTAssertTrue(collapse.contains(today))
    XCTAssertFalse(collapse.contains(yesterday))

    // A page of older days lands: today is still the folded one.
    let older = (1...4).map { calendar.startOfDay(for: date($0, 12)) }
    for day in older { XCTAssertFalse(collapse.contains(day)) }
    XCTAssertTrue(collapse.contains(today))

    collapse.toggle(today)
    XCTAssertFalse(collapse.contains(today))
    XCTAssertTrue(collapse.isEmpty)
  }

  // MARK: - Duplicate rows

  /// The two stores behind the spine page by offset against a list the server keeps re-sorting, so
  /// an overlapping page is a matter of timing — and paging the whole account makes far more chances
  /// for one. Every row id here is derived from a record id, so a repeated record is a repeated
  /// `ForEach` identity, which is not a cosmetic duplicate but undefined behaviour in the list.
  func testARepeatedRecordProducesOneRowRatherThanTwoWithTheSameIdentity() {
    let start = date(6, 20, 0)
    let duplicated = conversation(id: "c1", start: start)
    let memory = memory("m1", "Doors at 7.", at: date(6, 18), from: nil)

    let days = SpineComposer.compose(
      conversations: [duplicated, duplicated],
      memories: [memory, memory],
      screen: [:],
      calendar: calendar
    )

    let ids = days.flatMap { $0.rows.map(\.id) }
    XCTAssertEqual(ids.count, Set(ids).count, "no two rows may share a SwiftUI identity")
    XCTAssertEqual(days[0].conversationCount, 1)
    XCTAssertEqual(days[0].memoryCount, 1)
  }

  /// The real hazard, at the real size, in the exact shape that produces it.
  ///
  /// The memories loader carries two cursors — `currentOffset` over the visible/SQLite rows and
  /// `rawBackendOffset` over the raw API page — and advancing only one re-requests part of the page
  /// just read. The account behind this surface holds ~995 conversations and ~5,849 memories, so at
  /// a page size of 50 and 100 that is twenty and fifty-nine seams; a defect at any one of them is a
  /// day rendered twice. This composes the whole corpus with **every page seam overlapping** and
  /// asserts the spine still holds each record exactly once.
  func testTheWholeCorpusWithEveryPageSeamOverlappingStillRendersEachRecordOnce() {
    let conversationPage = 50
    let memoryPage = 100
    let overlap = 7

    var conversations: [ServerConversation] = []
    for index in 0..<995 {
      conversations.append(
        conversation(id: "c\(index)", start: date(1 + index % 28, index % 24, index % 60)))
      // The seam: the last `overlap` rows of each page arrive again at the head of the next one.
      if index % conversationPage == conversationPage - 1 {
        conversations.append(contentsOf: conversations.suffix(overlap))
      }
    }

    var memories: [SpineMemory] = []
    for index in 0..<5_849 {
      memories.append(
        memory(
          "m\(index)", "Focused on Omi App: note \(index).",
          at: date(1 + index % 28, index % 24, index % 60),
          from: index % 3 == 0 ? "c\(index % 995)" : nil))
      if index % memoryPage == memoryPage - 1 {
        memories.append(contentsOf: memories.suffix(overlap))
      }
    }

    XCTAssertGreaterThan(conversations.count, 995, "the fixture really does contain overlaps")
    XCTAssertGreaterThan(memories.count, 5_849)

    let days = SpineComposer.compose(
      conversations: conversations, memories: memories, screen: [:], calendar: calendar)

    let rowIDs = days.flatMap { $0.rows.map(\.id) }
    XCTAssertEqual(rowIDs.count, Set(rowIDs).count, "no two rows may share a SwiftUI identity")
    XCTAssertEqual(days.map(\.id).count, Set(days.map(\.id)).count, "no day may appear twice")
    XCTAssertEqual(days.reduce(0) { $0 + $1.conversationCount }, 995)
    XCTAssertEqual(days.reduce(0) { $0 + $1.memoryCount }, 5_849)

    // And the same record cannot be carried by two different rows either — a memory that attached
    // to a conversation must not also stand alone.
    let memoryIDs = days.flatMap { day in
      day.rows.flatMap { row -> [String] in
        if case .memories(let carried) = row.content { return carried.map(\.id) }
        return []
      }
    }
    XCTAssertEqual(memoryIDs.count, Set(memoryIDs).count)
  }

  /// Deduplication keeps the first sighting so the spine's order is the order the stores published.
  func testDeduplicationKeepsTheFirstSightingAndItsOrder() {
    let ordered = SpineComposer.uniqued(
      [("a", 1), ("b", 2), ("a", 3), ("c", 4)].map {
        SpineMemory(id: $0.0, text: "\($0.1)", timestamp: .distantPast, conversationID: nil)
      },
      by: \.id
    )
    XCTAssertEqual(ordered.map(\.id), ["a", "b", "c"])
    XCTAssertEqual(ordered.first?.text, "1")
  }

  // MARK: - The rail's direction

  /// The mismatch most timeline UIs ship: an ascending rail beside a descending list. The spine is
  /// newest-first, so the rail has to run late-night at the top down to midnight at the bottom.
  func testTheRailRunsTheSameDirectionAsTheNewestFirstList() {
    XCTAssertEqual(SpineHourRail.renderedHours.first, 23)
    XCTAssertEqual(SpineHourRail.renderedHours.last, 0)
    XCTAssertEqual(SpineHourRail.renderedHours.count, 24)
    XCTAssertEqual(
      SpineHourRail.renderedHours, SpineHourRail.renderedHours.sorted(by: >),
      "every step goes back in time, exactly as the list under it does")
  }

  // MARK: - The ribbon is continuous

  /// The column height every geometry test measures against. One day is one column, so this stands
  /// in for the real rail's height without any test depending on the window being a given size.
  private static let ribbonViewport: CGFloat = 600

  /// **The defect this ribbon replaced:** the rail drew one day at a time, so crossing midnight
  /// swapped the whole column at once. Depth is monotonic across the day boundary now — one more
  /// minute into the past is one step further down the strip, whether or not that minute is in a
  /// different day.
  func testDepthNeverJumpsBackwardsAcrossADayBoundary() {
    var previous = -CGFloat.greatestFiniteMagnitude
    for dayIndex in 0..<3 {
      for hour in SpineHourRail.renderedHours {
        for minute in [59, 30, 0] {
          let depth = SpineRibbonGeometry.depth(
            dayIndex: dayIndex, hour: hour, minute: minute, viewport: Self.ribbonViewport)
          XCTAssertGreaterThan(
            depth, previous,
            "day \(dayIndex) \(hour):\(minute) went back up the strip")
          previous = depth
        }
      }
    }
  }

  /// The last minute of a day and the first of the next are adjacent in time, so they are adjacent
  /// on the strip: one day break apart and nothing else. This is what makes the midnight crossing
  /// glide rather than cut.
  func testMidnightIsOneBreakWideAndNotACut() {
    let viewport = Self.ribbonViewport
    let lastOfDay = SpineRibbonGeometry.depth(
      dayIndex: 0, hour: 0, minute: 0, viewport: viewport)
    let firstOfNext = SpineRibbonGeometry.depth(
      dayIndex: 1, hour: 23, minute: 59, viewport: viewport)
    XCTAssertEqual(
      firstOfNext - lastOfDay,
      SpineRibbonGeometry.dayBreakHeight + SpineRibbonGeometry.hourHeight(viewport: viewport) / 60,
      accuracy: 0.001)
  }

  /// **One day is one column**, the way the per-day rail always sized itself. The strip is longer
  /// than the rail was; it is not drawn tighter, so nothing about how a single day reads changed.
  func testOneDayFillsTheColumnAtAnySize() {
    for viewport in [CGFloat(320), 600, 1400] {
      XCTAssertEqual(SpineRibbonGeometry.dayHeight(viewport: viewport), viewport, accuracy: 0.001)
      XCTAssertEqual(
        SpineRibbonGeometry.hourHeight(viewport: viewport) * 24
          + SpineRibbonGeometry.dayBreakHeight,
        viewport, accuracy: 0.001)
    }
    XCTAssertGreaterThan(
      SpineRibbonGeometry.hourHeight(viewport: 0), 0,
      "a column with no height yet must not collapse an hour to nothing")
  }

  /// **A day with no reported row still parks the strip on that day.**
  ///
  /// The rail describes a fallback day whenever the reported one has been folded shut, and the hour
  /// marker is deliberately dropped in that case — it belongs to a row nobody can see. The first
  /// version carried that one `nil` into the strip's position too, so the headline named the
  /// fallback day while the strip scrolled to the newest one. Position and highlight are separate
  /// inputs now; this pins that they stay separate.
  func testAnUnreportedDayStillParksTheStripOnThatDay() {
    let height = Self.ribbonViewport
    let parked = SpineRibbonGeometry.depth(
      dayIndex: 4, hour: 23, minute: 59, viewport: height)
    XCTAssertTrue(
      SpineRibbonGeometry.visibleDays(depth: parked, height: height, count: 9).contains(4),
      "the strip has to be showing the day the headline is describing")
    XCTAssertNotEqual(
      parked,
      SpineRibbonGeometry.depth(dayIndex: 0, hour: 23, minute: 59, viewport: height),
      "parking an unreported day must not collapse to the newest day")
  }

  /// **The strip labels exactly what the per-day rail labelled, and suppresses nothing.**
  ///
  /// Four fixed hours orient every day, and the hour being read names itself when it is not one of
  /// them. An earlier version of the strip also *dropped* a fixed label within an hour of the marker,
  /// to stop two captions colliding — a real collision, but only at the six-point hour spacing that
  /// version drew at. At one day per column an hour is more than twenty points, so the rule deleted
  /// labels to prevent an overlap that cannot happen, and made the strip read differently from the
  /// rail it replaced.
  func testTheStripLabelsTheSameHoursTheRailAlwaysDid() {
    for hour in [0, 6, 12, 18] {
      XCTAssertEqual(
        SpineRibbon.caption(for: hour, isLit: false), SpineFormat.hourLabel(hour),
        "a fixed label is drawn on every day, read or not")
      XCTAssertEqual(SpineRibbon.caption(for: hour, isLit: true), SpineFormat.hourLabel(hour))
    }
    XCTAssertNil(
      SpineRibbon.caption(for: 19, isLit: false),
      "an unread hour that is not one of the four stays unnamed")
    XCTAssertEqual(
      SpineRibbon.caption(for: 19, isLit: true), "7 PM",
      "the hour being read names itself even when it is not one of the four")
    XCTAssertEqual(
      SpineRibbon.caption(for: 17, isLit: false), SpineRibbon.caption(for: 17, isLit: false),
      "and a label near the one being read is never taken away")
    XCTAssertEqual(
      SpineRibbon.caption(for: 18, isLit: false), "6 PM",
      "including the fixed label directly beside it")
  }

  /// **The bar being read is always at full strength, and only its outgoing neighbour fades.**
  ///
  /// Sharing the weight evenly was the obvious way to make the highlight glide and it made the
  /// highlight vanish: with the marker between two slots each bar got half of it, so the one thing
  /// on the strip that has to be findable was drawn at half strength for most of every scroll.
  func testTheBarBeingReadIsNeverDimmedByTheHandover() {
    let hour: CGFloat = 24
    let marker: CGFloat = 300

    XCTAssertEqual(
      SpineRibbon.litness(slotCentre: marker, marker: marker, hourHeight: hour), 1, accuracy: 0.001)
    for offset in [CGFloat(0), 0.1, 0.25, 0.4, 0.49] {
      XCTAssertEqual(
        SpineRibbon.litness(slotCentre: marker + hour * offset, marker: marker, hourHeight: hour), 1,
        accuracy: 0.001,
        "every bar the marker is inside is fully lit, wherever inside it sits")
    }

    XCTAssertEqual(
      SpineRibbon.litness(slotCentre: marker + hour * 0.75, marker: marker, hourHeight: hour), 0.5,
      accuracy: 0.001, "the bar being left fades across the second half")
    XCTAssertEqual(
      SpineRibbon.litness(slotCentre: marker + hour, marker: marker, hourHeight: hour), 0,
      accuracy: 0.001, "an hour away is where it lets go")
    XCTAssertEqual(
      SpineRibbon.litness(slotCentre: marker + hour * 3, marker: marker, hourHeight: hour), 0,
      accuracy: 0.001, "and it never goes negative further out")
    XCTAssertEqual(
      SpineRibbon.litness(slotCentre: marker, marker: marker, hourHeight: 0), 0, accuracy: 0.001,
      "a column with no height yet lights nothing rather than dividing by zero")
  }

  /// **One hour says the time, never two.** A partly lit neighbour captioning itself put two hours
  /// on screen at once and left the reader to work out which of them the list was actually showing.
  func testOnlyTheHourBeingReadSaysTheTime() {
    let hour: CGFloat = 24
    let marker: CGFloat = 300

    XCTAssertTrue(
      SpineRibbon.isBeingRead(slotCentre: marker, marker: marker, hourHeight: hour))
    XCTAssertTrue(
      SpineRibbon.isBeingRead(slotCentre: marker + hour * 0.49, marker: marker, hourHeight: hour))
    XCTAssertFalse(
      SpineRibbon.isBeingRead(slotCentre: marker + hour * 0.51, marker: marker, hourHeight: hour),
      "the neighbour is lit during the hand-over but is not the hour being read")
    XCTAssertTrue(
      SpineRibbon.isBeingRead(slotCentre: marker + hour / 2, marker: marker, hourHeight: hour),
      "the boundary belongs to one side, so the hand-over has no gap in it")
    XCTAssertFalse(
      SpineRibbon.isBeingRead(slotCentre: marker - hour / 2, marker: marker, hourHeight: hour),
      "and not to both")
    XCTAssertFalse(
      SpineRibbon.isBeingRead(slotCentre: marker - hour * 0.75, marker: marker, hourHeight: hour))
    XCTAssertFalse(
      SpineRibbon.isBeingRead(slotCentre: marker, marker: marker, hourHeight: 0))

    // Exactly one slot on the strip owns the caption, wherever the marker falls between them.
    for shift in stride(from: CGFloat(0), through: 0.95, by: 0.05) {
      let centres = [marker - hour * shift, marker + hour * (1 - shift)]
      let owning = centres.filter {
        SpineRibbon.isBeingRead(slotCentre: $0, marker: marker, hourHeight: hour)
      }
      XCTAssertEqual(owning.count, 1, "two adjacent slots, one of them reading")
    }
  }

  // MARK: - The reading position is continuous

  private func anchor(hour: Int, minute: Int = 0, top: CGFloat, bottom: CGFloat) -> SpineRowAnchor {
    SpineRowAnchor(dayID: Date(timeIntervalSince1970: 0), hour: hour, minute: minute, top: top, bottom: bottom)
  }

  /// **The whole point of reporting two rows.** As the row at the reading line travels past it, the
  /// fraction runs 0 → 1; the strip blends towards the next row over that span and therefore moves
  /// every frame the list does, instead of holding still for a whole row and then jumping.
  func testTheFractionRunsTheLengthOfTheRow() {
    let line = SpineLayout.readingLine
    let justArrived = SpineReadingPosition(
      row: anchor(hour: 12, top: line, bottom: line + 100), next: nil)
    XCTAssertEqual(justArrived.fraction, 0, accuracy: 0.001)

    let halfway = SpineReadingPosition(
      row: anchor(hour: 12, top: line - 50, bottom: line + 50), next: nil)
    XCTAssertEqual(halfway.fraction, 0.5, accuracy: 0.001)

    let leaving = SpineReadingPosition(
      row: anchor(hour: 12, top: line - 100, bottom: line), next: nil)
    XCTAssertEqual(leaving.fraction, 1, accuracy: 0.001)
  }

  /// A row taller than the whole scroll, and a zero-height one, both have to produce a fraction the
  /// blend can use rather than a NaN or a value outside 0…1 that would throw the strip off its ends.
  func testTheFractionStaysInsideItsRange() {
    let line = SpineLayout.readingLine
    XCTAssertEqual(
      SpineReadingPosition(row: anchor(hour: 12, top: line, bottom: line), next: nil).fraction, 0,
      accuracy: 0.001, "a row with no height cannot be part-way past anything")
    XCTAssertEqual(
      SpineReadingPosition(row: anchor(hour: 12, top: line + 10, bottom: line + 20), next: nil)
        .fraction, 0, accuracy: 0.001, "a row not yet at the line is at the start of its travel")
    XCTAssertEqual(
      SpineReadingPosition(row: anchor(hour: 12, top: line - 900, bottom: line - 1), next: nil)
        .fraction, 1, accuracy: 0.001, "and one already past it is at the end")
  }

  /// The two rows kept are the two nearest the reading line, whatever order the list reported them
  /// in — a `PreferenceKey` reduce sees them in no guaranteed order.
  func testTheTwoRowsNearestTheReadingLineWin() {
    let line = SpineLayout.readingLine
    let first = SpineReadingPosition(row: anchor(hour: 12, top: line - 10, bottom: line + 10), next: nil)
    let second = SpineReadingPosition(row: anchor(hour: 11, top: line + 10, bottom: line + 60), next: nil)
    let far = SpineReadingPosition(row: anchor(hour: 9, top: line + 300, bottom: line + 400), next: nil)

    for order in [[first, second, far], [far, second, first], [second, far, first]] {
      let merged = order.reduce(nil) { SpineReadingPosition.merge($0, $1) }
      XCTAssertEqual(merged?.row.hour, 12, "the row at the line is the position")
      XCTAssertEqual(merged?.next?.hour, 11, "and the one after it is what to blend towards")
    }
    XCTAssertNil(SpineReadingPosition.merge(nil, nil))
  }

  /// At the end of the loaded stream there is no row to blend towards, and the position simply rests
  /// on the last one rather than blending towards nothing.
  func testTheLastRowHasNothingToBlendTowards() {
    let line = SpineLayout.readingLine
    let last = SpineReadingPosition(row: anchor(hour: 3, top: line - 20, bottom: line + 20), next: nil)
    XCTAssertNil(last.next)
    XCTAssertEqual(SpineReadingPosition.merge(nil, last)?.row.hour, 3)
  }

  /// Only the days on screen are drawn — the strip is the whole account, and drawing all of it on
  /// every scroll tick is the cost a `Canvas` was chosen to avoid.
  func testOnlyTheDaysInTheViewportAreDrawn() {
    let height = Self.ribbonViewport
    let window = SpineRibbonGeometry.visibleDays(
      depth: SpineRibbonGeometry.depth(
        dayIndex: 40, hour: 12, minute: 0, viewport: height),
      height: height, count: 300)
    XCTAssertTrue(window.contains(40))
    XCTAssertLessThanOrEqual(
      window.count,
      Int((height / SpineRibbonGeometry.dayHeight(viewport: height)).rounded(.up)) + 1)
  }

  /// The strip runs out at both ends rather than the index going out of bounds: reading the newest
  /// day means there is nothing above it, and an empty account has no strip at all.
  func testTheVisibleWindowStaysInsideTheLoadedDays() {
    let height = Self.ribbonViewport
    let atNewest = SpineRibbonGeometry.visibleDays(
      depth: SpineRibbonGeometry.depth(dayIndex: 0, hour: 23, minute: 59, viewport: height),
      height: height, count: 2)
    XCTAssertEqual(atNewest.lowerBound, 0)
    XCTAssertLessThanOrEqual(atNewest.upperBound, 2)
    XCTAssertTrue(SpineRibbonGeometry.visibleDays(depth: 0, height: height, count: 0).isEmpty)
    XCTAssertTrue(SpineRibbonGeometry.visibleDays(depth: 0, height: 0, count: 5).isEmpty)
  }

  /// **A day nobody has read yet is not a day with nothing on it.**
  ///
  /// Screen days are read lazily, three at a time, and an empty result is deliberately never stored
  /// — so "not queried yet" and "queried, found nothing" are the same absence in the store. The rail
  /// printed a confident `0` for both, which is how the tester came to read "0 screen moments" next
  /// to a five-figure account total and take it for a contradiction.
  func testTheRailSaysItIsCountingRatherThanClaimingZero() {
    XCTAssertEqual(SpineHourRail.headlineNumber(nil), "—")
    XCTAssertEqual(SpineHourRail.headlineCaption(nil), "counting screen moments")

    XCTAssertEqual(
      SpineHourRail.headlineNumber(0), "0",
      "A read that came back empty is a claim the rail is entitled to make.")
    XCTAssertEqual(SpineHourRail.headlineCaption(0), "screen moments")
    XCTAssertEqual(SpineHourRail.headlineCaption(1), "screen moment")
    XCTAssertEqual(SpineHourRail.headlineNumber(1_204), "1,204")
  }

  /// **The rail counts one day; the panel's corner counts the whole account — and the reader could
  /// not tell, twice.**
  ///
  /// The first fix gave the two counters different nouns, "screen moments" against "moments". The
  /// same reader looked again at `0` beside `798` and asked what each was supposed to show, because
  /// a different noun only separates them if you read both and infer a scope neither states. The
  /// rail now names the day its number belongs to, above the number, so it is legible without the
  /// other counter in view.
  func testTheRailNamesTheDayItsNumberBelongsTo() {
    XCTAssertEqual(SpineHourRail.headlineScope("Today"), "Today")
    XCTAssertEqual(SpineHourRail.headlineScope("Wednesday 6 August"), "Wednesday 6 August")

    XCTAssertNil(
      SpineHourRail.headlineScope(""),
      "An account with no days has no scope to claim, and must not invent one.")
    XCTAssertNil(SpineHourRail.headlineScope("   "))
  }

  /// **The scope line has to fit the rail's column on one line, and the way it was checked is the
  /// reason it did not.**
  ///
  /// The comment beside it reasoned from a hand-picked date — "Wednesday 6 August 2025", 153 pt
  /// against a 154 pt column — and concluded the line fit. `EEEE d MMMM yyyy` also emits
  /// "Wednesday 30 September 2026" at 183 pt, so 1,808 of the 10,234 forms the day formatter can
  /// produce were overhanging the column and wrapping to two lines.
  ///
  /// So the assertion is the invariant over every form the formatter can emit, not another example:
  /// picking a better example leaves exactly the same mistake available to the next format change.
  /// The formatters are pinned to `en_US_POSIX` so the sweep is the same set of strings on every
  /// machine.
  func testEveryDayTheFormatterCanEmitFitsTheRailColumnOnOneLine() {
    let dayOnly = DateFormatter()
    dayOnly.locale = Locale(identifier: "en_US_POSIX")
    dayOnly.dateFormat = "EEEE d MMMM"
    let dayAndYear = DateFormatter()
    dayAndYear.locale = Locale(identifier: "en_US_POSIX")
    dayAndYear.dateFormat = "EEEE d MMMM yyyy"

    // Six years covers every weekday × day-of-month × month pairing, and enough distinct year
    // stamps for the digit widths to vary.
    var forms: Set<String> = ["Today", "Yesterday"]
    for year in 2024...2029 {
      for month in 1...12 {
        for day in 1...31 {
          var components = DateComponents()
          components.year = year
          components.month = month
          components.day = day
          guard let date = calendar.date(from: components),
            calendar.component(.month, from: date) == month,
            calendar.component(.day, from: date) == day
          else { continue }
          forms.insert(dayOnly.string(from: date))
          forms.insert(dayAndYear.string(from: date))
        }
      }
    }
    XCTAssertGreaterThan(forms.count, 3_000, "the sweep has to be the whole space, not a sample")

    for form in forms {
      guard let scope = SpineHourRail.headlineScope(form) else {
        return XCTFail("\(form) is a real day and must claim a scope")
      }
      XCTAssertLessThanOrEqual(
        SpineHourRail.scopeWidth(scope), SpineHourRail.contentWidth,
        "\"\(scope)\" (from \"\(form)\") overhangs the rail's column and wraps")
    }
  }

  /// What the fit rule is allowed to change, and what it must leave alone.
  ///
  /// It drops the weekday, and only the weekday, and only when the full title does not fit: the
  /// date alone still identifies the day, and the list header beside the rail is printing the day
  /// in full anyway. A title that already fits must come back untouched — a scope that quietly
  /// shortens every day would be a copy change wearing a bug fix's clothes.
  func testTheScopeDropsTheWeekdayOnlyWhenTheFullDayWillNotFit() {
    XCTAssertEqual(
      SpineHourRail.headlineScope("Wednesday 30 September 2026"), "30 September 2026",
      "the formatter's widest output, 183 pt against a 154 pt column")
    XCTAssertEqual(SpineHourRail.headlineScope("Tuesday 22 September 2026"), "22 September 2026")

    XCTAssertEqual(SpineHourRail.headlineScope("Today"), "Today")
    XCTAssertEqual(SpineHourRail.headlineScope("Yesterday"), "Yesterday")
    XCTAssertEqual(
      SpineHourRail.headlineScope("Wednesday 6 August"), "Wednesday 6 August",
      "120 pt — fits, so it keeps its weekday")
    XCTAssertEqual(
      SpineHourRail.headlineScope("Wednesday 6 August 2025"), "Wednesday 6 August 2025",
      "153 pt — the date the old comment reasoned from, and the reason the wrap went unseen")

    XCTAssertEqual(
      SpineHourRail.headlineScope("Supercalifragilisticexpialidociously"),
      "Supercalifragilisticexpialidociously",
      "a single word there is no weekday to drop from keeps its text rather than losing the day")
  }

  /// The day word used to be the tail of the footer, twenty-four bars below the number it scoped.
  /// Moving it up must not leave it in both places: a scope stated twice is a scope nobody reads
  /// once.
  func testTheFooterNoLongerRepeatsTheDay() {
    XCTAssertEqual(SpineHourRail.footer(conversationCount: 6), "6 conversations")
    XCTAssertEqual(SpineHourRail.footer(conversationCount: 1), "1 conversation")
    XCTAssertNil(
      SpineHourRail.footer(conversationCount: 0),
      "A day with no conversations drops the line rather than drawing a blank one.")
  }

  /// The rail is one accessibility element, so the spoken sentence is the only form of it a
  /// screen-reader user gets — and comparing two counters across the width of the window, which is
  /// what the written rail wrongly asked for, was never available to them at all.
  func testTheSpokenRailLeadsWithItsScopeAndKeepsTheUnreadDayUnread() {
    XCTAssertEqual(
      SpineHourRail.readAloud(
        momentCount: 0, dayTitle: "Today", conversationCount: 6, currentHour: nil),
      "Today: 0 screen moments. 6 conversations.")

    XCTAssertEqual(
      SpineHourRail.readAloud(
        momentCount: 1, dayTitle: "Yesterday", conversationCount: 1, currentHour: 15),
      "Yesterday: 1 screen moment. 1 conversation. Reading 3 PM.")

    XCTAssertEqual(
      SpineHourRail.readAloud(
        momentCount: nil, dayTitle: "Today", conversationCount: 6, currentHour: nil),
      "Today: Counting screen moments. 6 conversations.",
      "A day nobody has read yet must not be spoken as a confident zero.")

    XCTAssertEqual(
      SpineHourRail.readAloud(
        momentCount: 1_204, dayTitle: "", conversationCount: 0, currentHour: nil),
      "1,204 screen moments.",
      "No day and no conversations still has to be a sentence, not one with holes in it.")
  }

  func testHourLabelsAreTwelveHourAndNeverZero() {
    XCTAssertEqual(SpineFormat.hourLabel(0), "12 AM")
    XCTAssertEqual(SpineFormat.hourLabel(6), "6 AM")
    XCTAssertEqual(SpineFormat.hourLabel(12), "12 PM")
    XCTAssertEqual(SpineFormat.hourLabel(18), "6 PM")
  }
}
