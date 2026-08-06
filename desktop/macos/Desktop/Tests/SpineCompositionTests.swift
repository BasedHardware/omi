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

  func testTheDayHeaderCountsTheWholeDayNotTheFilteredView() {
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
    XCTAssertEqual(composed[0].subtitle, "1,204 moments · 1 conversation")

    let soloed = SpineComposer.filter(composed, kind: .memories, query: "")
    XCTAssertEqual(
      soloed[0].momentCount, 1204, "a filtered spine still says how big the day really was")
    XCTAssertEqual(soloed[0].conversationCount, 1)
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
      momentCount: 6
    )
    XCTAssertEqual(summary.subtitle, "8m 0s · 2 memories · 6 screen moments")

    let bare = SpineConversation(
      conversation: conversation(id: "c2", start: date(6, 20), minutes: 3),
      memoryCount: 0,
      momentCount: 0
    )
    XCTAssertEqual(bare.subtitle, "3m 0s")
  }

  func testDurationReadsAsAClockNotASecondsCount() {
    XCTAssertEqual(SpineFormat.duration(489), "8m 9s")
    XCTAssertEqual(SpineFormat.duration(42), "42s")
    XCTAssertEqual(SpineFormat.duration(3_855), "1h 04m")
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

  func testHourLabelsAreTwelveHourAndNeverZero() {
    XCTAssertEqual(SpineFormat.hourLabel(0), "12 AM")
    XCTAssertEqual(SpineFormat.hourLabel(6), "6 AM")
    XCTAssertEqual(SpineFormat.hourLabel(12), "12 PM")
    XCTAssertEqual(SpineFormat.hourLabel(18), "6 PM")
  }
}
