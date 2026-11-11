import ContextCore
import Foundation
import XCTest

@testable import ContextMCPKit

/// The ceiling on how much of the frame table one `activity` call may read — and, just as much,
/// its absence on the ranges the tool is actually for.
///
/// `activity` is the one tool with no `limit`: its window came straight from the model, over a
/// store the default retention never prunes, and every frame between the ends is read. Folding the
/// rows through a cursor fixed what a huge range *holds*; it does not change what a huge range
/// *reads*. So half of this file is the bound, and half is the promise that a day, a week or a
/// month still comes back exactly as it did — a ceiling nobody notices on ordinary questions is
/// the only kind worth having here.
final class ActivityRangeBoundTests: XCTestCase {
    private var root: URL!

    override func setUpWithError() throws {
        root = FileManager.default.temporaryDirectory
            .appendingPathComponent("activity-bound-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        addTeardownBlock { [root] in try? FileManager.default.removeItem(at: root!) }
    }

    private func makeStore() throws -> ContextStore {
        try ContextStore(url: root.appendingPathComponent("context.db"))
    }

    /// One collapsible stretch: three frames a minute apart, which clears both the 120-second gap
    /// that would split a run and the 15-second floor a block must reach to be rendered at all.
    private func stretch(_ store: ContextStore, app: String, at start: Double) throws {
        for offset in stride(from: 0.0, through: 120.0, by: 60.0) {
            _ = try store.insertFrame(
                Frame(capturedAt: start + offset, appName: app, windowTitle: "\(app) window"))
        }
    }

    private func activity(_ store: ContextStore, since: Double, until: Double) throws -> String {
        try Tools.call(
            name: "activity",
            arguments: .object(["since": .number(since), "until": .number(until)]),
            store: store
        ).text
    }

    // MARK: - Ordinary ranges are untouched

    /// The regression that matters most in the other direction. "What did I do today" must read the
    /// whole day, including its first minutes, and must say nothing about a limit — a bound that
    /// leaks into the answer to a normal question has cost more than it saved.
    func testADayIsReadEndToEndAndSaysNothingAboutABound() throws {
        let store = try makeStore()
        let until = ContextTime.now
        let since = until - 86_400
        try stretch(store, app: "Figma", at: since + 60)
        try stretch(store, app: "Xcode", at: until - 3_600)

        let text = try activity(store, since: since, until: until)

        XCTAssertTrue(text.contains("Figma"), "the start of the day was dropped: \(text)")
        XCTAssertTrue(text.contains("Xcode"), "the end of the day was dropped: \(text)")
        XCTAssertFalse(
            text.contains(Tools.clampedRangeMarker), "a one-day range was reported as clamped: \(text)")
    }

    /// A week — the other range the tool's own description names — and the boundary itself. A cap
    /// that fires one second early would make "the last month" a different answer than it was.
    func testAWeekAndTheCeilingItselfAreReadWhole() throws {
        let store = try makeStore()
        let until = ContextTime.now

        for span in [7 * 86_400.0, Tools.activityMaxRangeSeconds] {
            let since = until - span
            try stretch(store, app: "Slack", at: since + 60)

            let text = try activity(store, since: since, until: until)

            XCTAssertTrue(text.contains("Slack"), "the oldest end of a \(span)s range was dropped: \(text)")
            XCTAssertFalse(
                text.contains(Tools.clampedRangeMarker),
                "a \(span)s range is inside the ceiling and must not be clamped: \(text)")
        }
    }

    // MARK: - The pathological range

    /// A year is a range no honest reader asked for and every model can name. The proof that the
    /// bound is a bound on the *read* is the frame that is missing from the answer: it sits inside
    /// the window that was asked for and outside the window that was walked.
    func testAYearReadsTheMostRecentMonthAndSaysWhatItSkipped() throws {
        let store = try makeStore()
        let until = ContextTime.now
        try stretch(store, app: "MailFromLastSpring", at: until - 200 * 86_400)
        try stretch(store, app: "SlackYesterday", at: until - 86_400)

        let text = try activity(store, since: until - 365 * 86_400, until: until)

        XCTAssertTrue(text.contains("SlackYesterday"), "the recent end was not read: \(text)")
        XCTAssertFalse(
            text.contains("MailFromLastSpring"),
            "a frame 200 days back was still read, so nothing was bounded: \(text)")
        XCTAssertTrue(text.contains(Tools.clampedRangeMarker), "the clamp was silent: \(text)")
        XCTAssertTrue(
            text.contains("nothing before that was read"),
            "the answer does not say the earlier stretch is a gap rather than an idle Mac: \(text)")
    }

    /// The dangerous case, and the reason the note is appended to the empty branch too: a clamped
    /// read that finds nothing prints "no screen activity between X and Y" over a window the
    /// caller never named. Alone, that sentence is how "not read" becomes "never happened".
    func testAnEmptyClampedReadStillSaysTheRangeWasCut() throws {
        let store = try makeStore()
        let until = ContextTime.now
        try stretch(store, app: "MailFromLastSpring", at: until - 200 * 86_400)

        let text = try activity(store, since: until - 365 * 86_400, until: until)

        XCTAssertFalse(text.contains("MailFromLastSpring"), "the old frame was read after all: \(text)")
        XCTAssertTrue(text.contains(Tools.clampedRangeMarker), "an empty clamped answer said nothing: \(text)")
    }

    /// Both corrections at once. The swap has to happen before the clamp — clamping a backwards
    /// range would cut the wrong end — and each has to be admitted separately, since a caller who
    /// learns only that the range was reversed will read the shortened window as their own.
    func testAReversedYearIsSwappedFirstAndThenClamped() throws {
        let store = try makeStore()
        let now = ContextTime.now
        try stretch(store, app: "MailFromLastSpring", at: now - 200 * 86_400)
        try stretch(store, app: "SlackYesterday", at: now - 86_400)

        let text = try activity(store, since: now, until: now - 365 * 86_400)

        XCTAssertTrue(text.contains("SlackYesterday"), "the swap did not happen: \(text)")
        XCTAssertFalse(text.contains("MailFromLastSpring"), "the clamp did not happen after the swap: \(text)")
        XCTAssertTrue(text.contains("the other way round"), "the swap was silent: \(text)")
        XCTAssertTrue(text.contains(Tools.clampedRangeMarker), "the clamp was silent: \(text)")
    }

    /// The two clamps meet here. A month of blocks can outrun the one-reply character budget, and
    /// that budget cuts the tail — so a range disclosure printed after the last block is precisely
    /// the text a long answer drops, leaving a shortened window reading as the one that was asked
    /// for. Both cuts have to be visible in the same answer.
    func testTheRangeDisclosureSurvivesTheOneReplyClamp() throws {
        let store = try makeStore()
        let until = ContextTime.now
        // Alternating apps so each stretch closes into its own block, with titles long enough that
        // 400 rendered lines pass the character budget.
        let title = String(repeating: "a long window title ", count: 5)
        for index in 0..<400 {
            let start = until - 20 * 86_400 + Double(index) * 200
            for offset in stride(from: 0.0, through: 120.0, by: 60.0) {
                _ = try store.insertFrame(
                    Frame(
                        capturedAt: start + offset, appName: index.isMultiple(of: 2) ? "Arc" : "Xcode",
                        windowTitle: "\(index) \(title)"))
            }
        }

        let text = try activity(store, since: until - 365 * 86_400, until: until)

        XCTAssertTrue(
            text.contains(Tools.clampedResultMarker),
            "the fixture is too small to reach the reply budget, so this proves nothing")
        XCTAssertTrue(
            text.contains(Tools.clampedRangeMarker),
            "the range disclosure was cut off by the reply clamp: \(text.suffix(400))")
    }

    /// The model has to be able to act on the bound, and it can only act on what the schema tells
    /// it. A ceiling discoverable only by tripping it costs a wasted call every time.
    func testTheSchemaTellsTheModelAboutTheCeiling() throws {
        let activity = try XCTUnwrap(Tools.all.first { $0.name == "activity" })
        let since = try XCTUnwrap(activity.inputSchema["properties"]?["since"]?["description"]?.stringValue)

        XCTAssertTrue(
            since.contains("\(Tools.activityMaxRangeDays) days"),
            "`since` does not mention the ceiling: \(since)")
    }
}
