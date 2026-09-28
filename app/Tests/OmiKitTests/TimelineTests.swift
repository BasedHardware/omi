import XCTest

@testable import OmiKit

// Ports of `react-native/src/desktop/rewindTimeline.test.ts` plus coverage
// for the merged-timeline grouping/filter logic of UnifiedTimeline.tsx and
// the desktopChrome filter labels.

func rewindFrame(_ id: String, _ capturedAtMs: Int64) -> RewindFrame {
    RewindFrame(id: id, capturedAtMs: capturedAtMs, appName: "Browser", windowTitle: id)
}

final class Counter: @unchecked Sendable {
    var count = 0
    func inc() { count += 1 }
}

func conversation(
    _ id: String, startedAt: String, title: String = "Standup", summary: String = "sync"
) -> ConversationProjection {
    ConversationProjection(
        id: id, title: title, summary: summary, searchableText: "\(title) \(summary)",
        createdAt: startedAt, starred: false, status: "finished", source: "omi",
        visibility: .priv
    )
}

final class TimelineTests: XCTestCase {
    // MARK: - createRewindTimeline (rewindTimeline.test.ts ports)

    func testMergesInterleavedSourcePagesWithoutOmissions() throws {
        let captured = (0..<127).map { rewindFrame("captured:\($0)", 1000 - $0 * 2) }
        let shipping = (0..<117).map { rewindFrame("shipping:\($0)", 999 - $0 * 2) }
        let counter = Counter()
        let bridge = RewindTimelineBridge { source, query, cursor, limit in
            counter.inc()
            XCTAssertEqual(query, "work")
            XCTAssertEqual(limit, 50)
            let data = source == .captured ? captured : shipping
            let start = Int(cursor ?? "0")!
            return RewindFramePage(
                frames: Array(data[start..<min(start + limit, data.count)]),
                nextCursor: start + limit < data.count ? String(start + limit) : nil
            )
        }
        let timeline = RewindTimeline(bridge: bridge, query: "work")
        var result: [RewindFrame] = []
        var more = true
        while more {
            let page = try timeline.next()
            XCTAssertLessThanOrEqual(page.frames.count, 50)
            result.append(contentsOf: page.frames)
            more = page.next
        }
        let expected = (captured + shipping).sorted { $0.capturedAtMs > $1.capturedAtMs }
        XCTAssertEqual(result, expected)
        XCTAssertEqual(counter.count, 6)
    }

    func testKeepsDeterministicTiesAcrossSourcePageBoundary() throws {
        let captured = (0..<51).map { rewindFrame("captured:\($0)", 10) }
        let bridge = RewindTimelineBridge { source, _, cursor, _ in
            if source == .shipping {
                return RewindFramePage(frames: [rewindFrame("shipping:1", 10)], nextCursor: nil)
            }
            if cursor != nil {
                return RewindFramePage(frames: [captured[50]], nextCursor: nil)
            }
            let page = Array(captured[0..<50])
            return RewindFramePage(frames: page, nextCursor: "next")
        }
        let timeline = RewindTimeline(bridge: bridge, query: "")
        XCTAssertEqual(try timeline.next().frames, Array(captured[0..<50]))
        XCTAssertEqual(
            try timeline.next().frames.map(\.id), ["captured:50", "shipping:1"])
    }

    func testMissingHistoryIsNormalButFailedReadableSourceIsReported() throws {
        for (code, expectWarning) in [
            (RewindTimelineFailure.unavailable, false),
            (RewindTimelineFailure.storage, true),
        ] {
            let failure = code
            let bridge = RewindTimelineBridge { source, _, _, _ in
                if source == .shipping { throw failure }
                return RewindFramePage(frames: [rewindFrame("captured:1", 10)], nextCursor: nil)
            }
            let timeline = RewindTimeline(bridge: bridge, query: "")
            let page = try timeline.next()
            XCTAssertEqual(page.frames.count, 1)
            XCTAssertEqual(page.next, false)
            XCTAssertEqual(page.warning != nil, expectWarning)
            if expectWarning {
                XCTAssertEqual(page.warning, rewindHistoryWarning)
            }
        }
    }

    func testAllUnreadableFailuresRejectAndAccountFailuresRetireTheReader() {
        for failure in [
            RewindTimelineFailure.storage,
            RewindTimelineFailure.rewindAuth,
            RewindTimelineFailure.ownerChanged,
        ] {
            let thrown = failure
            let bridge = RewindTimelineBridge { source, _, _, _ in
                if source == .shipping || thrown == .storage { throw thrown }
                return RewindFramePage(frames: [rewindFrame("captured:1", 10)], nextCursor: nil)
            }
            let timeline = RewindTimeline(bridge: bridge, query: "")
            XCTAssertThrowsError(try timeline.next()) { error in
                XCTAssertEqual(error as? RewindTimelineFailure, thrown)
            }
            // Retired (or persistently failing) readers keep failing.
            XCTAssertThrowsError(try timeline.next())
        }
    }

    func testLaterSourceFailureRetainsReadableHistoryWithPersistentWarning() throws {
        let captured = (0..<50).map { rewindFrame("captured:\($0)", 100 - $0) }
        let bridge = RewindTimelineBridge { source, _, cursor, _ in
            if source == .shipping {
                return RewindFramePage(frames: [rewindFrame("shipping:1", 0)], nextCursor: nil)
            }
            if cursor != nil { throw RewindTimelineFailure.storage }
            return RewindFramePage(frames: captured, nextCursor: "next")
        }
        let timeline = RewindTimeline(bridge: bridge, query: "")
        XCTAssertEqual(try timeline.next().frames, captured)
        let page = try timeline.next()
        XCTAssertEqual(page.frames.map(\.id), ["shipping:1"])
        XCTAssertEqual(page.warning, "Some screen history could not be loaded.")
        XCTAssertEqual(page.next, false)
    }

    // MARK: - groupRewindFrames (12-minute same-window bound)

    func testGroupRewindFramesEmptyInput() {
        XCTAssertEqual(groupRewindFrames([]), [])
    }

    func testGroupRewindFramesMergesSameWindowWithinTwelveMinutes() {
        func doc(_ id: String, _ at: Int64) -> RewindFrame {
            RewindFrame(id: id, capturedAtMs: at, appName: "Browser", windowTitle: "Docs")
        }
        let frames = [
            doc("a", 2_000_000),
            doc("b", 2_000_000 - 720_000),  // exactly the 12-minute bound — merges
            doc("c", 1_280_000 - 720_001),  // past the bound from the NEW head (280k... 559999)
        ]
        let groups = groupRewindFrames(frames)
        XCTAssertEqual(groups.count, 2)
        XCTAssertEqual(groups[0].id, "a")
        XCTAssertEqual(groups[0].count, 2)
        XCTAssertEqual(groups[0].firstCapturedAtMs, 1_280_000)
        XCTAssertEqual(groups[0].capturedAtMs, 2_000_000)
        XCTAssertEqual(groups[1].id, "c")
        XCTAssertEqual(groups[1].count, 1)
    }

    func testGroupRewindFramesSplitsOnAppOrTitleChange() {
        var frame = rewindFrame("a", 500)
        let sameTime = RewindFrame(
            id: "b", capturedAtMs: 400, appName: "Editor", windowTitle: "a")
        let renamed = RewindFrame(
            id: "c", capturedAtMs: 300, appName: "Browser", windowTitle: "other")
        let groups = groupRewindFrames([frame, sameTime, renamed])
        XCTAssertEqual(groups.map(\.id), ["a", "b", "c"])
        frame.capturedAtMs = 0
        XCTAssertEqual(groups[0].frame.capturedAtMs, 500)
    }

    func testGroupRewindFramesGapBoundUsesGroupFirstFrameNotPreviousFrame() {
        // The contiguous check compares against firstCapturedAtMs, so a slow
        // trickle that never gaps more than 12 minutes from the group head
        // keeps merging even across many frames.
        var frames = [RewindFrame(
            id: "head", capturedAtMs: 10_000_000, appName: "Browser", windowTitle: "chain")]
        for index in 0..<5 {
            frames.append(RewindFrame(
                id: "t\(index)", capturedAtMs: 10_000_000 - 600_000 * Int64(index + 1),
                appName: "Browser", windowTitle: "chain"))
        }
        let groups = groupRewindFrames(frames)
        XCTAssertEqual(groups.count, 1)
        XCTAssertEqual(groups[0].count, 6)
        XCTAssertEqual(groups[0].firstCapturedAtMs, 10_000_000 - 600_000 * 5)
    }

    // MARK: - mergeTimeline

    func testMergeTimelineEmptyInputs() {
        XCTAssertEqual(mergeTimeline(nil).entries, [])
        XCTAssertEqual(mergeTimeline(nil).failures, [])
        let outcomes = DesktopReadOutcomes(
            conversations: .success(DomainRead(items: [], page: emptyPage)),
            memories: .success(DomainRead(items: [], page: emptyPage)),
            tasks: .success(TaskRead(items: [], page: emptyPage))
        )
        let merged = mergeTimeline(outcomes)
        XCTAssertEqual(merged.entries, [])
        XCTAssertEqual(merged.failures, [])
    }

    private var emptyPage: ReadPageState {
        ReadPageState(
            windowStatus: .complete, complete: true, hasMore: false, nextCursor: nil,
            completenessStatus: .complete, reasons: [])
    }

    func testMergeTimelineSortsNewestFirstAndReportsFailures() {
        let outcomes = DesktopReadOutcomes(
            conversations: .success(DomainRead(items: [
                conversation("c1", startedAt: "2026-09-28T10:00:00Z")
            ], page: emptyPage)),
            memories: .error("boom"),
            tasks: .error("boom")
        )
        let merged = mergeTimeline(outcomes)
        XCTAssertEqual(merged.entries.map(\.id), ["conversation-c1"])
        XCTAssertEqual(
            merged.failures, ["Memories are unavailable.", "Tasks are unavailable."])
    }

    func testMergeTimelineEntryShapesAndFallbackTitles() {
        let memory = MemoryProjection(
            id: "m1", title: "  ", summary: "likes tea", searchableText: "",
            citations: [], timestamp: 1_700_000_000,  // seconds epoch
            provenance: MemoryProvenance(
                label: nil, synthesisVersion: nil, inputDigest: nil, outputDigest: nil))
        let done = TaskProjection(
            id: "t1", title: "Ship", summary: "the port", searchableText: "",
            completed: true, completedAt: 1_700_000_100, source: "omi", provenance: [],
            sortOrder: 0, indentLevel: 0)
        let undated = TaskProjection(
            id: "t2", title: "Someday", summary: "", searchableText: "",
            completed: false, source: "omi", provenance: [], sortOrder: 1, indentLevel: 0)
        let outcomes = DesktopReadOutcomes(
            conversations: .success(DomainRead(items: [
                conversation("c1", startedAt: "not-a-date")
            ], page: emptyPage)),
            memories: .success(DomainRead(items: [memory], page: emptyPage)),
            tasks: .success(TaskRead(items: [done, undated], page: emptyPage))
        )
        let captures = [
            CaptureGroupSummary(
                id: "g1", title: "Docs", appName: "Browser", capturedAtMs: 5_000, count: 3),
            CaptureGroupSummary(
                id: "g2", title: "Solo", appName: "Editor", capturedAtMs: 4_000, count: 1),
        ]
        let merged = mergeTimeline(outcomes, captures: captures)
        let entries = merged.entries
        // Newest first; the two atMs == 0 entries keep insertion order.
        XCTAssertEqual(
            entries.map(\.id),
            ["task-t1", "memory-m1", "capture-g1", "capture-g2", "conversation-c1", "task-t2"])
        XCTAssertEqual(entries[0].atMs, 1_700_000_100_000)
        XCTAssertEqual(entries[0].detail, "Done · the port")
        XCTAssertEqual(entries[1].atMs, 1_700_000_000_000)
        XCTAssertEqual(entries[1].title, "Memory")
        XCTAssertEqual(entries[2].detail, "Browser · 3 captures")
        XCTAssertEqual(entries[3].detail, "Editor")
        XCTAssertEqual(entries[4].atMs, 0)
        XCTAssertEqual(entries[4].title, "Standup")
    }

    func testMergeTimelineFilters() {
        func outcomes() -> DesktopReadOutcomes {
            DesktopReadOutcomes(
                conversations: .success(DomainRead(items: [
                    conversation("c1", startedAt: "2026-09-28T10:00:00Z")
                ], page: emptyPage)),
                memories: .success(DomainRead(items: [
                    MemoryProjection(
                        id: "m1", title: "Memory one", summary: "s", searchableText: "",
                        citations: [], timestamp: 1_700_000_000,
                        provenance: MemoryProvenance(
                            label: nil, synthesisVersion: nil, inputDigest: nil,
                            outputDigest: nil))
                ], page: emptyPage)),
                tasks: .success(TaskRead(items: [
                    TaskProjection(
                        id: "t1", title: "Task one", summary: "", searchableText: "",
                        completed: false, dueAt: 1_700_000_200, source: "omi",
                        provenance: [], sortOrder: 0, indentLevel: 0)
                ], page: emptyPage))
            )
        }
        let captures = [
            CaptureGroupSummary(
                id: "g1", title: "Docs", appName: "Browser", capturedAtMs: 5_000, count: 2)
        ]
        XCTAssertEqual(
            mergeTimeline(outcomes(), captures: captures, filter: .all).entries.map(\.kind),
            [.conversation, .task, .memory, .capture])
        XCTAssertEqual(
            mergeTimeline(outcomes(), captures: captures, filter: .conversations).entries
                .map(\.id),
            ["conversation-c1", "memory-m1"])
        XCTAssertEqual(
            mergeTimeline(outcomes(), captures: captures, filter: .recall).entries.map(\.id),
            ["capture-g1"])
        XCTAssertEqual(
            mergeTimeline(outcomes(), captures: captures, filter: .tasks).entries.map(\.id),
            ["task-t1"])
    }

    func testMergeTimelineQueryMatching() {
        let outcomes = DesktopReadOutcomes(
            conversations: .success(DomainRead(items: [
                conversation(
                    "c1", startedAt: "2026-09-28T10:00:00Z", title: "Budget review",
                    summary: "q3 numbers")
            ], page: emptyPage)),
            memories: .success(DomainRead(items: [], page: emptyPage)),
            tasks: .success(TaskRead(items: [], page: emptyPage))
        )
        XCTAssertEqual(mergeTimeline(outcomes, query: "  BUDGET ").entries.count, 1)
        XCTAssertEqual(mergeTimeline(outcomes, query: "q3 numbers").entries.count, 1)
        XCTAssertEqual(mergeTimeline(outcomes, query: "nomatch").entries, [])
        XCTAssertEqual(mergeTimeline(outcomes).entries.count, 1)
    }

    // MARK: - Filter and grouping labels (desktopChrome.ts)

    func testFilterAndGroupingLabels() {
        XCTAssertEqual(TimelineFilter.allCases.map(\.rawValue),
                       ["all", "conversations", "recall", "tasks"])
        XCTAssertEqual(TimelineFilter.allCases.map(\.label),
                       ["All", "Conversations", "Recall", "Tasks"])
        XCTAssertEqual(TimelineGrouping.allCases.map(\.rawValue), ["date", "type", "topic"])
        XCTAssertEqual(TimelineGrouping.allCases.map(\.label), ["Date", "Type", "Topic"])
        XCTAssertEqual(TimelineEntryKind.capture.label, "Recall")
    }

    // MARK: - Grouping (Date / Type / Topic)

    private func utcCalendar() -> Calendar {
        var calendar = Calendar(identifier: Calendar.Identifier.gregorian)
        calendar.timeZone = TimeZone(identifier: "UTC")!
        return calendar
    }

    private func ms(_ iso: String) -> Int64 {
        parseEpochMilliseconds(iso)!
    }

    func testDateGroupingBoundaries() {
        let now = ms("2026-09-28T12:00:00Z")
        let calendar = utcCalendar()
        let entries = [
            TimelineEntry(id: "e1", kind: .conversation, atMs: ms("2026-09-28T01:00:00Z"),
                          title: "t", detail: ""),
            TimelineEntry(id: "e2", kind: .conversation, atMs: ms("2026-09-27T23:00:00Z"),
                          title: "t", detail: ""),
            TimelineEntry(id: "e3", kind: .conversation, atMs: ms("2026-09-26T10:00:00Z"),
                          title: "t", detail: ""),
            TimelineEntry(id: "e4", kind: .conversation, atMs: 0, title: "t", detail: ""),
        ]
        let sections = groupTimelineSections(entries, .date, nowMs: now, calendar: calendar)
        XCTAssertEqual(
            sections.map(\.label),
            ["Today", "Yesterday", "Saturday, September 26", "Undated"])
        XCTAssertEqual(
            sections.map(\.key),
            ["date-Today", "date-Yesterday", "date-Saturday, September 26", "date-Undated"])
        XCTAssertEqual(sections[0].entries.map(\.id), ["e1"])
        XCTAssertEqual(sections[3].entries.map(\.id), ["e4"])
    }

    func testTypeGroupingUsesKindLabelsInFirstAppearanceOrder() {
        let entries = [
            TimelineEntry(id: "c", kind: .conversation, atMs: 300, title: "t", detail: ""),
            TimelineEntry(id: "r", kind: .capture, atMs: 200, title: "t", detail: ""),
            TimelineEntry(id: "c2", kind: .conversation, atMs: 100, title: "t", detail: ""),
            TimelineEntry(id: "t", kind: .task, atMs: 50, title: "t", detail: ""),
            TimelineEntry(id: "m", kind: .memory, atMs: 10, title: "t", detail: ""),
        ]
        let sections = groupTimelineSections(entries, .type)
        XCTAssertEqual(
            sections.map(\.label), ["Conversation", "Recall", "Task", "Memory"])
        XCTAssertEqual(sections.map(\.key), ["type-Conversation", "type-Recall", "type-Task", "type-Memory"])
        XCTAssertEqual(sections[0].entries.map(\.id), ["c", "c2"])
    }

    func testTopicGroupingBucketsBySharedKeywordWithOtherLast() {
        let entries = [
            TimelineEntry(id: "a", kind: .conversation, atMs: 30, title: "kubernetes cluster",
                          detail: "rollout"),
            TimelineEntry(id: "b", kind: .capture, atMs: 20, title: "kubernetes dashboard",
                          detail: ""),
            TimelineEntry(id: "c", kind: .memory, atMs: 10, title: "unrelated words here",
                          detail: ""),
        ]
        let sections = groupTimelineSections(entries, .topic)
        XCTAssertEqual(sections.count, 2)
        XCTAssertEqual(sections[0].label, "Kubernetes")
        XCTAssertEqual(sections[0].key, "topic-Kubernetes")
        XCTAssertEqual(sections[0].entries.map(\.id), ["a", "b"])
        XCTAssertEqual(sections[1].key, "topic-other")
        XCTAssertEqual(sections[1].label, "Everything else")
        XCTAssertEqual(sections[1].entries.map(\.id), ["c"])
    }

    func testTopicGroupingIgnoresStopwordsShortTokensAndDuplicates() {
        // "the", "for", "with" are stopwords; "tea" is < 4 chars; the only
        // repeated token across entries is "garden".
        let entries = [
            TimelineEntry(id: "a", kind: .memory, atMs: 20, title: "The garden tea",
                          detail: "for the"),
            TimelineEntry(id: "b", kind: .memory, atMs: 10, title: "garden party",
                          detail: "garden"),
        ]
        let sections = groupTimelineSections(entries, .topic)
        XCTAssertEqual(sections.map(\.label), ["Garden"])
        XCTAssertEqual(sections[0].entries.map(\.id), ["a", "b"])
    }

    func testGroupTimelineSectionsEmptyInput() {
        XCTAssertEqual(groupTimelineSections([], .date), [])
        XCTAssertEqual(groupTimelineSections([], .topic), [])
    }
}
