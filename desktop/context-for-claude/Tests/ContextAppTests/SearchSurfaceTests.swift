import AppKit
import ContextCore
import SwiftUI
import XCTest

@testable import ContextApp

/// The search surface: two panels, a gap, and everything the second one draws.
///
/// The claims here are the ones a screenshot cannot make and a refactor can quietly break — that the
/// two panels are still two, that the grid is still four across at a width its cards survive, that
/// the whole surface still fits the smallest display it opens on, that a long title truncates instead
/// of making its row taller, and that the type on the glass is still legible over the worst desktop
/// that can be behind it.
final class SearchSurfaceTests: XCTestCase {

    override func setUp() {
        super.setUp()
        // The query chip is measured in the bundled face; without this every width assertion below
        // would silently be measuring SF Pro.
        _ = InkTestFonts.registered
    }

    // MARK: - Two panels, and the air between them

    /// **The panels are separate.** The whole design is that the bar and the panel under it are two
    /// floating objects, and the one way that can be lost is a gap quietly going to zero — at which
    /// point the surface is the single slab it used to be, with a rule where the gap was.
    func testTheTwoPanelsAreSeparatedByRealAir() {
        XCTAssertGreaterThan(
            SearchLayout.panelGap, 0,
            "a zero gap welds the bar and the results into one slab, which is the design this replaces")
        // Big enough to read as separation at a glance, not as a rendering seam.
        XCTAssertGreaterThanOrEqual(SearchLayout.panelGap, 10)
        XCTAssertLessThanOrEqual(SearchLayout.panelGap, 14)
    }

    /// …and the surface's height really contains the gap and both panels, so the window cannot be
    /// sized as if the two were touching.
    func testTheSurfaceHeightAccountsForBothPanelsAndTheGap() {
        let height = SearchLayout.surfaceHeight(showingNote: false)
        XCTAssertEqual(
            height,
            SearchLayout.shadowMargin * 2 + SearchLayout.barHeight + SearchLayout.panelGap
                + SearchLayout.initialFilterPanelHeight)
        // The bar grows by a line when it has something to say about where the question went, and
        // the window has to grow with it or the sentence is drawn outside the panel.
        XCTAssertEqual(
            SearchLayout.surfaceHeight(showingNote: true) - height, SearchLayout.noteHeight)
        // A taller panel is a taller window, one for one — this is the whole of the resize path.
        XCTAssertEqual(
            SearchLayout.surfaceHeight(showingNote: false, panelHeight: 600)
                - SearchLayout.surfaceHeight(showingNote: false, panelHeight: 400),
            200)
    }

    /// The panel's scroll body is clamped at both ends, and both ends are defects it prevents: a
    /// sliver below the floor, and above the ceiling a panel taller than a 13" display.
    func testThePanelBodyIsClampedAtBothEnds() {
        XCTAssertEqual(
            SearchLayout.resultsBodyHeight(contentHeight: 0), SearchLayout.minimumResultsBodyHeight)
        XCTAssertEqual(
            SearchLayout.resultsBodyHeight(contentHeight: 5_000),
            SearchLayout.maximumResultsBodyHeight)
        // Inside the clamp the panel is exactly as tall as what is in it, so nothing scrolls that
        // did not need to.
        XCTAssertEqual(SearchLayout.resultsBodyHeight(contentHeight: 260), 260)
        XCTAssertLessThan(SearchLayout.minimumResultsBodyHeight, SearchLayout.maximumResultsBodyHeight)
    }

    /// The panels wear the **shared** glass rather than a second one mixed here.
    ///
    /// Stated as the two values a private copy would have to diverge on. It is a tripwire and not a
    /// behavioural test — but the failure it catches (a search surface rounded and shadowed unlike
    /// every other panel in the app) is a visual one that no behavioural test sees.
    func testThePanelsTakeTheirCornerAndShadowFromTheSharedGlass() {
        XCTAssertEqual(SearchLayout.panelCornerRadius, InkGlass.cornerRadius)
        XCTAssertEqual(SearchLayout.shadowMargin, InkGlassShadow.ambient.padding)
        XCTAssertGreaterThan(
            SearchLayout.shadowMargin, 0,
            "with no margin the window clips the ambient shadow and the panels look stamped on")
    }

    /// The window is the surface, including the margin the shadow falls into.
    @MainActor
    func testTheWindowIsSizedFromTheSurfaceAndGrowsWithTheNote() {
        let resting = SearchBarWindow.surfaceSize()
        XCTAssertEqual(resting.width, SearchLayout.surfaceWidth)
        XCTAssertEqual(resting.height, SearchLayout.surfaceHeight(showingNote: false))
        XCTAssertGreaterThan(SearchBarWindow.surfaceSize(showingNote: true).height, resting.height)
    }

    /// The surface is a tall two-panel object, so the placement rule has to be clamped: the naive
    /// "upper third" arithmetic put its bottom edge under the dock on a 13" display.
    @MainActor
    func testThePanelIsPlacedInsideTheScreenEvenWhenItIsTallerThanTheOpeningOffset() {
        // A 13" MacBook's usable area, stated rather than read, so the claim does not depend on the
        // display the suite happens to run on.
        let visible = NSRect(x: 0, y: 0, width: 1470, height: 931)
        let frame = SearchBarWindow.defaultFrame(in: visible)
        XCTAssertGreaterThanOrEqual(frame.minY, visible.minY - 0.5)
        XCTAssertLessThanOrEqual(frame.maxY, visible.maxY + 0.5)
        XCTAssertEqual(frame.midX, visible.midX, accuracy: 1)
    }

    // MARK: - The two ways out of the panel

    /// **The bar can reach the timeline and Settings.**
    ///
    /// The regression this holds. While this surface was a titled main window it had a prompt bar, a
    /// spine of everything the Mac had done, and no route to either of the app's other windows: the
    /// timeline could only be reached by activating a moment, and Settings not at all. The timeline's
    /// own header has carried a "Search All" pill and a gear since it shipped, for exactly this
    /// reason, and these two are that pair pointing the other way.
    ///
    /// Three claims, because three things break separately: that the surface still carries both
    /// hand-offs (an initialiser that silently drops a parameter), that pressing each control really
    /// calls the one it belongs to (the classic swap), and that the pair fits in the room the bar
    /// reserves for it — controls wider than `trailingControlsWidth` push the query chip, which is the
    /// one thing on this surface that may not be squeezed.
    ///
    /// The surface is built with a query in it on purpose: that opens it on `.results` rather than on
    /// the activity spine, so nothing here constructs the account feed.
    @MainActor
    func testTheBarCanReachTheTimelineAndSettings() {
        var view = SearchBarView(query: "invoice", results: SearchResultsModel(moments: []))
        var reached: [String] = []
        view.onOpenTimeline = { reached.append("timeline") }
        view.onOpenSettings = { reached.append("settings") }
        view.onOpenTimeline()
        view.onOpenSettings()
        XCTAssertEqual(
            reached, ["timeline", "settings"],
            "the surface dropped one of the two hand-offs it was given")

        // The controls themselves, pressed. `SearchBarExits` is what the prompt bar mounts, so this
        // is the real pill and the real gear rather than a description of them.
        var pressed: [String] = []
        let exits = SearchBarExits(
            onOpenTimeline: { pressed.append("timeline") },
            onOpenSettings: { pressed.append("settings") })
        exits.onOpenTimeline()
        exits.onOpenSettings()
        XCTAssertEqual(pressed, ["timeline", "settings"])

        let host = NSHostingView(rootView: exits)
        host.layoutSubtreeIfNeeded()
        let width = host.fittingSize.width
        XCTAssertGreaterThan(width, 60, "the pill and the gear drew nothing")
        XCTAssertLessThan(
            width, SearchLayout.trailingControlsWidth,
            "the pill and the gear are \(width) pt wide, past the "
                + "\(SearchLayout.trailingControlsWidth) pt the bar reserves — they take the room out "
                + "of the query chip")
    }

    // MARK: - Clicking away from the panel

    /// **Click anywhere else and the panel goes.**
    ///
    /// The plain case, and the only one where the panel closes itself: it lost the keyboard, a
    /// runloop turn later nothing of ours has it back, nothing is modal, and no system prompt is up.
    /// The user clicked into another application.
    func testAClickOutsideThePanelClosesIt() {
        XCTAssertTrue(Self.clickedAway.closesThePanel)
    }

    /// **A click inside the panel is not a click away from it — and focus churn is neither.**
    ///
    /// This is the one the suite could not see and a real launch found in 375 ms. The trigger used to
    /// be `didResignKey`, which cannot tell the two apart: a `.nonactivatingPanel` is ordered in under
    /// whatever application is frontmost, takes key, and has it taken straight back. The log read
    /// `search bar presented (key: true)` and then `dismissed by a click outside it`, with nobody
    /// having touched anything — the app opened and shut itself, and every test here still passed,
    /// because a headless suite has no key window to lose.
    ///
    /// The trigger is now the gesture: a global mouse-down, tested against the panel's own rectangle.
    /// This covers the half of that decision that is expressible without a window on screen.
    func testAClickInsideThePanelIsNotAClickAway() {
        let panel = NSRect(x: 100, y: 200, width: 800, height: 600)

        XCTAssertFalse(
            SearchBarWindow.clickLandedOutside(NSPoint(x: 500, y: 500), panel: panel),
            "a press on the panel's own surface must never close it")
        XCTAssertFalse(
            SearchBarWindow.clickLandedOutside(NSPoint(x: 101, y: 201), panel: panel),
            "the window rectangle includes the shadow margin, and its edge belongs to the panel")
        XCTAssertTrue(
            SearchBarWindow.clickLandedOutside(NSPoint(x: 50, y: 500), panel: panel),
            "a press beside the panel is the gesture this feature is named after")
        XCTAssertTrue(
            SearchBarWindow.clickLandedOutside(NSPoint(x: 500, y: 1_000), panel: panel))
    }

    /// **…and nothing the panel itself put on screen counts as clicking away.**
    ///
    /// Every exemption, one at a time, from the same otherwise-dismissing state — so a `&&` dropped
    /// out of `closesThePanel` fails here rather than in somebody's session. These are the states
    /// that make the difference between a Spotlight and a panel that cannot be used:
    ///
    /// - **Settings and the timeline.** Both are opened *from* this panel, and both come forward and
    ///   activate the app, which is precisely the panel doing its job. A gear that closes the surface
    ///   it is attached to is a gear that does nothing.
    /// - **The tutorial's coach card**, which takes key on entry for the beats the user is meant to
    ///   press — the same exemption, because it is another window of ours. A panel that vanished
    ///   there would take the coached surface away mid-beat.
    /// - **A sheet or a modal**, whose parent window is not key while it is up.
    /// - **The login-Keychain password sheet**, which is another process's window and therefore looks
    ///   exactly like clicking into another application — the one case where that reading is wrong,
    ///   because this app raised the prompt without being asked to.
    /// - **Focus bouncing straight back**, which is a popover closing and not a gesture at all.
    func testThePanelSurvivesEverythingItOpenedForItself() {
        let exemptions: [(String, (inout SearchResignation) -> Void)] = [
            ("Settings, the timeline, a popover, or a coach card took key", {
                $0.anotherWindowOfOursHasFocus = true
            }),
            ("a sheet or a modal session is up", { $0.aSheetOrModalIsUp = true }),
            ("the system keychain prompt is up", { $0.aSystemSecurityPromptIsUp = true }),
            ("the keyboard came straight back to the panel", { $0.panelTookKeyBack = true }),
        ]
        for (what, apply) in exemptions {
            var resignation = Self.clickedAway
            apply(&resignation)
            XCTAssertFalse(
                resignation.closesThePanel,
                "the panel closed itself while \(what) — that is not the user clicking away from it")
        }
    }

    /// **A panel some other route already closed is never closed a second time.**
    ///
    /// The guard that keeps `SearchPanelWatch.report(.closed)` at exactly one per real dismissal.
    /// `SearchBarWindow.travel(to:)` is the shape it is for: it presents the timeline — which takes
    /// key away from this panel and so schedules this very check — and *then* dismisses the panel
    /// itself, announcing `.closed` on the way. A second announcement is not cosmetic:
    /// `TutorialModel` clears `searchPanelIsOurs` on `.closed`, so a spurious one hands the tutorial
    /// a panel it believes it no longer owns.
    ///
    /// Asserted against the announcement rather than only against the flag, so the claim is about
    /// what observers hear.
    @MainActor
    func testAPanelAlreadyDismissedIsNotClosedAgainByTheClickOutsideRule() {
        var already = Self.clickedAway
        already.panelIsStillTheOpenOne = false
        XCTAssertFalse(
            already.closesThePanel,
            "the click-outside rule would dismiss a panel another route already closed, announcing "
                + "a second `.closed` for one dismissal")

        // One dismissal, one announcement — including the second `dismiss()` that finds nothing to
        // close, which is the shape `travel(to:)` and this rule can produce together.
        var heard: [SearchPanelEvent] = []
        let token = SearchPanelWatch.addObserver { heard.append($0) }
        defer { SearchPanelWatch.removeObserver(token) }
        SearchBarWindow.dismiss()
        XCTAssertEqual(heard, [.closed])
    }

    /// The state a click into another application leaves behind: the panel had the keyboard, is still
    /// the open one, has lost it, and nothing of ours or of the system's took it.
    private static let clickedAway = SearchResignation(
        panelIsStillTheOpenOne: true,
        panelTookKeyBack: false,
        anotherWindowOfOursHasFocus: false,
        aSheetOrModalIsUp: false,
        aSystemSecurityPromptIsUp: false)

    // MARK: - The grid

    /// **Four across, at a width the cards survive.**
    ///
    /// It was three across at a 760 pt panel. The claim that moved with the panel is only the count;
    /// the one that did not move is the one worth having — a card at or under `minimumCardWidth` is a
    /// card whose title truncates before it says anything, and the widening is only worth doing if
    /// the cards come through it unchanged. They do: 229.5 pt now against 230.7 pt at three columns.
    func testTheResultsGridIsFourAcrossWithCardsWideEnoughToRead() {
        XCTAssertEqual(SearchLayout.resultColumns, 4)
        XCTAssertEqual(SearchResultsView.columns.count, SearchLayout.resultColumns)

        let card = SearchLayout.cardWidth()
        XCTAssertGreaterThanOrEqual(
            card, SearchLayout.minimumCardWidth,
            "a \(card) pt card has no room for a title before it truncates")
        // The fourth column was paid for out of the panel's new width and not out of the cards. The
        // three-across card at the old 760 pt panel is the number to beat, and it is restated here
        // rather than derived because the whole point is that it is the *old* geometry.
        let threeAcrossAtTheOldWidth = (760 - SearchLayout.panelPaddingHorizontal * 2 - 14 * 2) / 3
        XCTAssertEqual(
            card, threeAcrossAtTheOldWidth, accuracy: 4,
            "the extra width went into fatter cards rather than into another column of answers")

        // The columns and their gutters really do fill the panel's content width — a grid that
        // overflows is a grid whose last column is clipped at the panel's edge.
        let used =
            card * CGFloat(SearchLayout.resultColumns)
            + SearchLayout.cardGutter * CGFloat(SearchLayout.resultColumns - 1)
        XCTAssertEqual(used, SearchLayout.contentWidth(), accuracy: 0.001)
    }

    /// …and it reflows: at every panel width the surface could plausibly be given, the columns either
    /// still fit or the arithmetic says how much narrower they got. Nothing here may produce a
    /// negative or zero card, which is what clipping looks like from the layout's side.
    func testTheGridReflowsWithoutProducingAClippedColumn() {
        let columns = CGFloat(SearchLayout.resultColumns)
        for width in stride(from: 520.0, through: 1400.0, by: 40.0) {
            let card = SearchLayout.cardWidth(panelWidth: width)
            XCTAssertGreaterThan(card, 0, "panel width \(width) produced a \(card) pt card")
            let used = card * columns + SearchLayout.cardGutter * (columns - 1)
            XCTAssertLessThanOrEqual(
                used, SearchLayout.contentWidth(panelWidth: width) + 0.001,
                "the grid overflows its panel at \(width) pt")
        }
        // The shipped width is comfortably above the point where the columns stop being readable.
        XCTAssertGreaterThan(
            SearchLayout.cardWidth(panelWidth: SearchLayout.panelWidth),
            SearchLayout.minimumCardWidth * 1.2)
    }

    /// **The whole surface still fits the smallest display it opens on, at its widest and at its
    /// tallest.**
    ///
    /// The constraint the panel's new size was chosen against, stated so the next person to widen it
    /// finds out from a failing test rather than from a laptop. Both ends are real:
    ///
    /// - **Across.** The window is `panelWidth` plus the clear margin the shadows fall into. A
    ///   surface that reached the edges of a 13" display would stop reading as a floating panel and
    ///   start reading as a sheet stretched over the desktop, which is the shape this design exists
    ///   to not be.
    /// - **Down.** The tallest the surface can ever be is the body at its ceiling, the panel's own
    ///   header above it, the bar grown by its note line, the gap and both shadow margins. Past the
    ///   display it is not clipped — `defaultFrame` clamps it — it is simply pinned to the bottom
    ///   edge with its head off the top of the usable area, which is worse than clipping because it
    ///   takes the prompt bar with it.
    @MainActor
    func testTheSurfaceFitsAThirteenInchDisplayAtItsWidestAndTallest() {
        // A 13" MacBook at 1440 × 900, less the 25 pt menu bar. Stated rather than read from
        // `NSScreen` so the claim does not depend on the display the suite happens to run on.
        let visible = NSRect(x: 0, y: 0, width: 1440, height: 875)

        XCTAssertLessThanOrEqual(
            SearchLayout.surfaceWidth, visible.width - 240,
            "the surface is \(SearchLayout.surfaceWidth) pt wide, which leaves a 13\" display too "
                + "little desktop either side for this to read as a panel floating over one")

        let tallest = SearchLayout.surfaceHeight(
            showingNote: true,
            panelHeight: SearchLayout.panelHeaderHeight + SearchLayout.maximumResultsBodyHeight)
        XCTAssertLessThanOrEqual(
            tallest, visible.height,
            "at its tallest the surface is \(tallest) pt, past the \(visible.height) pt a 13\" "
                + "display has under its menu bar — the prompt bar goes off the top of the screen")

        // …and the placement really does put a whole panel inside that rectangle, rather than the
        // arithmetic above being true of a shape the app never opens at.
        let opening = SearchBarWindow.defaultFrame(in: visible)
        XCTAssertTrue(visible.contains(opening), "the opening panel does not fit a 13\" display")
    }

    /// **The panel is tall enough for a whole card, even with the filter block open.**
    ///
    /// This is the clipped-card defect stated as arithmetic. The body's ceiling has to clear the
    /// filter block plus one complete card — picture, title *and* source line — or the very first
    /// row the user sees is sliced through the middle at the panel's edge, which is what the first
    /// two passes of this design did.
    ///
    /// Measured with the block **open**, because that is the state the claim is now about: the
    /// block is closed at rest (`SearchResultsModel.isShowingFilters`), and measuring it closed
    /// would leave this asserting that a header plus one card fits in 545 pt — true, and not the
    /// defect. What the ceiling has to survive is the state where the filters really are above the
    /// grid, which is the state this opens.
    @MainActor
    func testTheCeilingLeavesRoomForAWholeCard() {
        let model = SearchResultsModel(
            moments: [], websites: ["arc.net"],
            apps: [SearchAppFacet(name: "Arc", bundleId: nil)])
        model.toggleFilters()
        let filterBlock = NSHostingView(rootView: SearchFilterContent(model: model))
        filterBlock.layoutSubtreeIfNeeded()
        // The empty content, less the one-line "no results" note the grid replaces.
        let filters = filterBlock.fittingSize.height - SearchLayout.chipHeight

        XCTAssertGreaterThanOrEqual(
            SearchLayout.maximumResultsBodyHeight, filters + SearchLayout.cardHeight(),
            "the panel tops out at \(SearchLayout.maximumResultsBodyHeight) pt, which cuts the first "
                + "row of cards — it needs \(filters + SearchLayout.cardHeight())")
    }

    // MARK: - The results lead, and the filters are one press behind them

    /// **A search shows the user their screenshots, not a screenful of filter controls.**
    ///
    /// The reported defect, as arithmetic on the real view. The panel's body is capped at
    /// `SearchLayout.maximumResultsBodyHeight`, and the filter block — four time chips, a row of
    /// site pills, a row of 46 pt app icons — used to sit inside that cap *above* the grid and take
    /// very nearly all of it. So a query with a hundred and nine answers showed three of them and
    /// sliced the fourth row, and what a person saw after searching their own machine was a stack
    /// of controls they had not asked for. That is the state this is a guard against.
    ///
    /// Two whole rows is the floor rather than the target: one row is indistinguishable from a
    /// list, and one row is exactly what the old arrangement managed. The comparison against the
    /// open block is what keeps this honest — it proves the closed state really is buying rows,
    /// rather than the numbers happening to satisfy a threshold.
    @MainActor
    func testTheOpenedPanelSpendsItsHeightOnResultsRatherThanOnFilters() {
        /// The panel's natural height for a page of `cards`, in whichever filter state.
        func naturalHeight(cards: Int, showingFilters: Bool) -> CGFloat {
            let model = SearchResultsModel(
                moments: (1...cards).map {
                    Self.moment(id: Int64($0), title: "Docs — arc.net", app: "Arc")
                },
                websites: ["arc.net", "duckduckgo.com"],
                apps: [SearchAppFacet(name: "Arc", bundleId: nil)])
            if showingFilters { model.toggleFilters() }
            let host = NSHostingView(rootView: SearchFilterContent(model: model))
            host.layoutSubtreeIfNeeded()
            return host.fittingSize.height
        }

        /// How many whole rows of cards the ceiling leaves for the grid, measured by growing the
        /// page by a row and seeing what that costs — so the row's height and the chrome around it
        /// are both the view's own numbers rather than constants restated here.
        func visibleRows(showingFilters: Bool) -> Int {
            let one = naturalHeight(cards: SearchLayout.resultColumns, showingFilters: showingFilters)
            let two = naturalHeight(cards: SearchLayout.resultColumns * 2, showingFilters: showingFilters)
            let row = two - one
            XCTAssertGreaterThan(row, 0, "a second row of cards cost the panel no height at all")
            let chrome = one - row
            return Int(((SearchLayout.maximumResultsBodyHeight - chrome) / row).rounded(.down))
        }

        let closed = visibleRows(showingFilters: false)
        let open = visibleRows(showingFilters: true)
        print("[search] whole rows of cards visible — filters closed: \(closed), open: \(open)")

        XCTAssertGreaterThanOrEqual(
            closed, 2,
            "a search shows \(closed) row(s) of results before the user has to scroll — the panel is "
                + "spending its height on something other than the answer")
        XCTAssertGreaterThan(
            open, 0, "with the filters open the grid is gone entirely, not merely pushed down")
        XCTAssertGreaterThan(
            closed, open,
            "closing the filter block bought the grid no rows, so it is not what is between the user "
                + "and their screenshots and this guard is measuring the wrong thing")
    }

    /// **The panel opens on the results, and a filter it is not showing is named in words.**
    ///
    /// Both halves are the same claim: closing the block may cost the user controls, never
    /// information. A count that fell from 109 to 4 with no visible cause is indistinguishable from
    /// a machine that captured almost nothing, and there would be nothing on screen to undo.
    @MainActor
    func testAFilterTheClosedBlockIsHidingIsStillNamedInTheHeader() throws {
        let model = SearchResultsModel(
            moments: [], websites: ["arc.net"], apps: [SearchAppFacet(name: "Arc", bundleId: nil)])

        XCTAssertFalse(
            model.isShowingFilters,
            "the panel opens on the filter block again — the results are back below the fold")
        XCTAssertNil(
            model.hiddenFilterSummary,
            "nothing is narrowing this answer, so the header is reporting a filter nobody set")

        model.select(time: .today)
        model.select(website: "arc.net")
        model.select(app: "Arc")
        let summary = try XCTUnwrap(
            model.hiddenFilterSummary,
            "three filters are narrowing the answer and the closed header says nothing about any of them")
        for lit in ["today", "arc.net", "Arc"] {
            XCTAssertTrue(
                summary.contains(lit), "the header does not name the lit `\(lit)` filter: \(summary)")
        }
        // …and the accessibility label carries it too, since the chevron says nothing to a reader.
        XCTAssertTrue(SearchResultsView.filterDisclosureLabel(summary: summary).contains(summary))

        // Open the block and the lit chips say it themselves — saying it twice is how the two get
        // to disagree.
        model.toggleFilters()
        XCTAssertNil(model.hiddenFilterSummary)
        XCTAssertEqual(SearchResultsView.filterDisclosureLabel(summary: nil), "Filter")
    }

    // MARK: - The arrow keys on a grid

    /// **↓ means the card below, not the card to the right.**
    ///
    /// The defect this fixes is a signature one for a list turned into a grid: the selection stepped
    /// ±1 through the ranking, so on a three-across grid pressing ↓ walked the highlight *sideways*
    /// along the first row. Pure arithmetic, so the cases that actually break are reachable — the
    /// ragged last row, a page shorter than one row, an empty page — none of which anybody opens by
    /// hand.
    func testTheArrowKeysMoveThroughTheResultsAsAGridRatherThanAsAList() {
        // Eight cards, three across: rows [0 1 2] [3 4 5] [6 7].
        func step(_ direction: SearchGridStep, from index: Int?, count: Int = 8) -> Int? {
            SearchResultsModel.destination(of: direction, from: index, count: count, columns: 3)
        }

        // Entering from the field is unchanged: ↓ at the best answer, ↑ at the last one.
        XCTAssertEqual(step(.down, from: nil), 0)
        XCTAssertEqual(step(.up, from: nil), 7)

        // The fix. Down is a row.
        XCTAssertEqual(step(.down, from: 0), 3, "↓ moved sideways instead of down")
        XCTAssertEqual(step(.down, from: 1), 4)
        XCTAssertEqual(step(.up, from: 4), 1)
        XCTAssertEqual(step(.up, from: 5), 2)

        // The ragged final row: ↓ from above it must still reach it, or the last results on the
        // page are only ever reachable sideways.
        XCTAssertEqual(step(.down, from: 5), 7)
        XCTAssertEqual(step(.down, from: 7), 7, "clamped at the end rather than wrapping to the top")

        // ↑ is held at the top row rather than stepping out, so that a second press cannot re-enter
        // at the far end and teleport the keyboard to the bottom of the page.
        XCTAssertEqual(step(.up, from: 0), 0)
        XCTAssertEqual(step(.up, from: 2), 2)

        // ← and → walk the ranking, which flows across a row boundary exactly as reading does.
        XCTAssertEqual(step(.right, from: 2), 3)
        XCTAssertEqual(step(.left, from: 3), 2)
        XCTAssertEqual(step(.right, from: 7), 7)

        // The one exit: ← off the best answer puts the keyboard back in the query.
        XCTAssertNil(step(.left, from: 0))

        // Every card on the page is reachable, which is what makes row-stepping safe: ↓ alone skips
        // two cards in three, and a result the keyboard cannot land on is a result Return cannot open.
        var reached: Set<Int> = [0]
        var cursor = 0
        while let next = step(.right, from: cursor), next != cursor {
            cursor = next
            reached.insert(next)
        }
        XCTAssertEqual(
            reached, Set(0..<8),
            "→ does not reach every card, so some results are unreachable from the keyboard")

        // A page shorter than one row is a whole grid with no second row to move to.
        XCTAssertEqual(step(.down, from: nil, count: 2), 0)
        XCTAssertEqual(step(.down, from: 0, count: 2), 1, "↓ on a short page must reach its last card")
        XCTAssertEqual(step(.up, from: 1, count: 2), 1)

        // An empty page, and a degenerate column count, are ordinary states rather than errors.
        for direction in [SearchGridStep.up, .down, .left, .right] {
            XCTAssertNil(SearchResultsModel.destination(of: direction, from: nil, count: 0, columns: 3))
            XCTAssertNil(SearchResultsModel.destination(of: direction, from: 0, count: 0, columns: 3))
            XCTAssertNil(SearchResultsModel.destination(of: direction, from: 0, count: 8, columns: 0))
        }

        // The grid the keys step over is the grid the panel draws — a column count restated there
        // would have left ↓ stepping by three when the panel went four across, which is the whole of
        // this claim and is exactly what happened to the width of this panel.
        XCTAssertEqual(SearchResultsModel.gridColumns, SearchLayout.resultColumns)
    }

    /// **← and → belong to the query until the keyboard is actually in the grid.**
    ///
    /// This is the whole reason those two keys were previously offered to nobody: they move the
    /// insertion point through what has been typed, and a bar where they sometimes do not is a bar
    /// that eats your editing. The borrow is announced by the return value, so the field can hand
    /// the key straight back — and this asserts both directions of that, plus the way out.
    ///
    /// **The page and every landing are stated in `SearchLayout.resultColumns`, not in cards.** This
    /// walked a six-card page and expected index 4 back, which was one whole row on a three-across
    /// grid and is not one on the four-across grid the panel draws now. A test that had to be
    /// re-typed for a column count is a test that can silently stop asserting "↓ is a row" the next
    /// time the panel is widened, so it asks the layout instead.
    @MainActor
    func testLeftAndRightStayWithTheQueryUntilTheKeyboardIsInTheGrid() {
        // Two full rows, so the second row is never ragged and "one row down" always lands on a card.
        let columns = SearchLayout.resultColumns
        let model = SearchResultsModel(
            moments: (1...(columns * 2)).map {
                Self.moment(id: Int64($0), title: "Docs — arc.net", app: "Arc")
            },
            query: "invoice")

        XCTAssertFalse(model.move(.left), "← was taken from the query with no card selected")
        XCTAssertFalse(model.move(.right), "→ was taken from the query with no card selected")
        XCTAssertNil(model.selection)

        XCTAssertTrue(model.move(.down))
        XCTAssertEqual(model.selectedMoment?.id, model.moments[0].id)
        XCTAssertTrue(model.move(.right), "→ is the grid's once a card is selected")
        XCTAssertEqual(model.selectedMoment?.id, model.moments[1].id)
        XCTAssertTrue(model.move(.down))
        XCTAssertEqual(
            model.selectedMoment?.id, model.moments[columns + 1].id,
            "↓ did not move a whole row on the model")

        // Back out along the ranking, and off the front of it: the last ← is consumed (it is what
        // drops the selection), and the one after it is the query's again.
        for _ in 0..<(columns + 1) { XCTAssertTrue(model.move(.left)) }
        XCTAssertEqual(model.selectedMoment?.id, model.moments[0].id)
        XCTAssertTrue(model.move(.left))
        XCTAssertNil(model.selection, "← off the best answer must put the keyboard back in the query")
        XCTAssertFalse(model.move(.left))

        // An empty answer never takes an arrow key at all, so every one of them still edits.
        let empty = SearchResultsModel(moments: [])
        for direction in [SearchGridStep.up, .down, .left, .right] {
            XCTAssertFalse(empty.move(direction), "\(direction) was consumed over an empty page")
            XCTAssertNil(empty.selection)
        }
    }

    /// **A body with more below it says so; one that contains everything does not.**
    ///
    /// The regression: the grid's second row was sliced by the panel's bottom edge with no fade, no
    /// scroller and nothing else to say the panel continued — `.scrollIndicators(.never)` on a view
    /// that really did scroll. A half a card cut off by a hard edge reads as a broken layout, not as
    /// "there is more below", and it was the state every populated query landed in.
    func testTheBottomEdgeOnlyPromisesMoreBelowWhenThereIsMoreBelow() {
        // Inside the clamp the panel contains everything it has, so nothing may be faded: a fade
        // over a panel that cannot scroll is a promise of content that does not exist.
        XCTAssertFalse(SearchLayout.bodyScrolls(contentHeight: 0))
        XCTAssertFalse(SearchLayout.bodyScrolls(contentHeight: SearchLayout.minimumResultsBodyHeight / 2))
        XCTAssertFalse(SearchLayout.bodyScrolls(contentHeight: 300))
        XCTAssertFalse(
            SearchLayout.bodyScrolls(contentHeight: SearchLayout.maximumResultsBodyHeight),
            "content that lands exactly on the ceiling fits — it has nothing below it")

        // Past the ceiling the content is cut, and that is precisely when the edge has to say so.
        XCTAssertTrue(SearchLayout.bodyScrolls(contentHeight: SearchLayout.maximumResultsBodyHeight + 1))
        XCTAssertTrue(SearchLayout.bodyScrolls(contentHeight: 5_000))

        // The fade is a signal, not a curtain: readable as a dissolve, and never deep enough to
        // swallow a card's title-and-source block, which would fix the next row by ruining the last.
        XCTAssertGreaterThan(SearchLayout.scrollFadeHeight, 8)
        XCTAssertLessThan(SearchLayout.scrollFadeHeight, SearchLayout.cardCaptionHeight)

        // …and the depth the panel actually draws, which is the whole of the view's decision: the
        // fade only exists where the content is cut, and the content's own bottom inset is the same
        // number, so the reader who scrolls to the end has the fade falling on spare glass rather
        // than on the last card's source line.
        XCTAssertEqual(SearchLayout.scrollFade(contentHeight: 300), 0)
        XCTAssertEqual(SearchLayout.scrollFade(contentHeight: SearchLayout.maximumResultsBodyHeight), 0)
        XCTAssertEqual(
            SearchLayout.scrollFade(contentHeight: SearchLayout.maximumResultsBodyHeight + 1),
            SearchLayout.scrollFadeHeight)
        XCTAssertEqual(SearchLayout.scrollFade(contentHeight: 5_000), SearchLayout.scrollFadeHeight)
    }

    /// …and the fade really is a fade: the bottom edge of a scrolling body dissolves, and the same
    /// body with nothing below it is untouched.
    ///
    /// Rendered rather than asserted about the source, because the defect is a visual one — a
    /// gradient whose stops were built the wrong way round would still type-check, still be applied,
    /// and still cut the cards with a knife.
    @MainActor
    func testTheFadeDissolvesTheBottomEdgeAndLeavesAPanelThatFitsAlone() throws {
        func alpha(fade: CGFloat, atBottom: Bool) throws -> CGFloat {
            let height: CGFloat = 100
            let renderer = ImageRenderer(
                content: Color.black
                    .frame(width: 20, height: height)
                    .mask(SearchScrollFade(fade: fade)))
            renderer.scale = 1
            let image = try XCTUnwrap(renderer.cgImage)
            let rep = NSBitmapImageRep(cgImage: image)
            let colour = try XCTUnwrap(rep.colorAt(x: 10, y: atBottom ? rep.pixelsHigh - 1 : 0))
            return colour.alphaComponent
        }

        // Scrolling: opaque at the top, gone at the very bottom.
        XCTAssertEqual(try alpha(fade: SearchLayout.scrollFadeHeight, atBottom: false), 1, accuracy: 0.02)
        XCTAssertLessThan(
            try alpha(fade: SearchLayout.scrollFadeHeight, atBottom: true), 0.15,
            "the bottom edge is still a hard cut — the sliced row does not dissolve into the glass")

        // Not scrolling: no fade anywhere, because there is nothing below to point at.
        XCTAssertEqual(try alpha(fade: 0, atBottom: true), 1, accuracy: 0.02)
        XCTAssertEqual(try alpha(fade: 0, atBottom: false), 1, accuracy: 0.02)
    }

    /// **At every result count the panel really shows, the bottom edge agrees with the content.**
    ///
    /// Measured on the real filter block and the real grid at the shipped panel width, so the inputs
    /// are the heights the app actually produces rather than numbers chosen to make the predicate
    /// true. One row fits inside the ceiling and must not be faded; four rows and thirty-four rows do
    /// not fit and must be. The sweep asserts both directions occur, so it cannot pass by never
    /// exercising the branch.
    @MainActor
    func testEveryResultCountEitherFitsOrSaysItDoesNot() {
        var scrolled: [Int] = []
        var fitted: [Int] = []
        for count in [1, 2, 3, 12, 100] {
            let model = SearchResultsModel(
                moments: (1...count).map { Self.moment(id: Int64($0), title: "Docs — arc.net", app: "Arc") },
                websites: ["arc.net", "duckduckgo.com"],
                apps: [SearchAppFacet(name: "Arc", bundleId: nil)])
            let host = NSHostingView(rootView: SearchFilterContent(model: model))
            host.layoutSubtreeIfNeeded()
            let content = host.fittingSize.height
            let body = SearchLayout.resultsBodyHeight(contentHeight: content)

            XCTAssertLessThanOrEqual(
                body, SearchLayout.maximumResultsBodyHeight,
                "\(count) results made the panel taller than a 13\" display can hold")
            XCTAssertEqual(
                SearchLayout.bodyScrolls(contentHeight: content), content > body + 0.5,
                "at \(count) results the panel's bottom edge disagrees with whether it is cut: "
                    + "content \(content) pt in a \(body) pt body")

            if SearchLayout.bodyScrolls(contentHeight: content) {
                scrolled.append(count)
                XCTAssertEqual(
                    SearchLayout.scrollFade(contentHeight: content), SearchLayout.scrollFadeHeight,
                    "\(count) results are cut by the panel's edge with no fade on it")
                // The fade is drawn inside the body, so it can only ever be a signal at the edge —
                // never a curtain over a panel that is mostly fade.
                XCTAssertLessThan(SearchLayout.scrollFadeHeight, body / 4)
            } else {
                fitted.append(count)
                XCTAssertEqual(
                    SearchLayout.scrollFade(contentHeight: content), 0,
                    "\(count) results fit, and a fade over them promises a row that is not there")
                // A panel that fits is exactly as tall as what is in it, and shows all of it.
                XCTAssertEqual(body, content, accuracy: 0.5)
            }
        }
        XCTAssertFalse(scrolled.isEmpty, "no count in the sweep overflowed — the sweep proves nothing")
        XCTAssertFalse(fitted.isEmpty, "every count overflowed — the fade would be permanent")
        print("[search] result counts that scroll: \(scrolled); counts that fit: \(fitted)")
    }

    /// …and the card-height arithmetic the line above depends on really matches the card.
    @MainActor
    func testACardIsAsTallAsTheLayoutSays() {
        let host = NSHostingView(
            rootView: SearchResultCard(
                moment: SearchMoment(
                    rowId: 1, title: "Docs", source: "arc.net", appName: "Arc", bundleId: nil,
                    capturedAt: 1_700_000_000, frame: nil),
                loader: FrameLoader()))
        host.layoutSubtreeIfNeeded()
        XCTAssertEqual(
            host.fittingSize.height, SearchLayout.cardHeight(), accuracy: 6,
            "SearchLayout.cardHeight no longer describes the card, so every height derived from it is wrong")
    }

    /// **A long title truncates; it does not wrap.**
    ///
    /// Measured on the real card through `NSHostingView`, because the defect is a layout one: a card
    /// whose title wraps to two lines is taller than the cards beside it, and a grid row of unequal
    /// cards is what made the old surface look unconsidered. Asserting `.lineLimit(1)` is in the
    /// source would not catch a `.fixedSize` added three lines below it.
    @MainActor
    func testALongTitleTruncatesRatherThanMakingItsCardTaller() {
        let loader = FrameLoader()
        func height(of title: String) -> CGFloat {
            let card = SearchResultCard(
                moment: SearchMoment(
                    rowId: 1, title: title, source: "arc.net", appName: "Arc", bundleId: nil,
                    capturedAt: 1_700_000_000, frame: nil),
                loader: loader)
            let host = NSHostingView(rootView: card)
            host.layoutSubtreeIfNeeded()
            return host.fittingSize.height
        }

        let short = height(of: "Inbox")
        let long = height(
            of: String(
                repeating: "an extremely long window title that would wrap several times over ",
                count: 4))
        XCTAssertEqual(
            long, short, accuracy: 0.5,
            "a long title made its card \(long - short) pt taller — it is wrapping, not truncating")
        XCTAssertGreaterThan(short, 0)
    }

    // MARK: - The query chip

    /// The chip hugs what has been typed, and stops at the bar's edge instead of running past it.
    func testTheQueryChipHugsTheTextAndClampsToTheBar() {
        let available = SearchLayout.queryFieldWidth
        XCTAssertGreaterThan(available, SearchMetrics.minimumChipWidth)

        XCTAssertEqual(
            SearchMetrics.chipWidth(for: "", available: available), 0,
            "with nothing typed there is no chip at all — the bar shows the placeholder and a cursor")

        let short = SearchMetrics.chipWidth(for: "gpu", available: available)
        let longer = SearchMetrics.chipWidth(for: "gpu benchmarks", available: available)
        XCTAssertGreaterThan(longer, short, "the chip has to grow with the query")
        XCTAssertGreaterThanOrEqual(short, SearchMetrics.minimumChipWidth)

        let huge = SearchMetrics.chipWidth(
            for: String(repeating: "unreasonably long query ", count: 20), available: available)
        XCTAssertLessThanOrEqual(
            huge, available,
            "the chip ran past the bar rather than letting the field truncate inside it")
    }

    // MARK: - What a card says

    /// The friendly timestamp, on a fixed clock so the ladder is assertable rather than
    /// day-of-the-week dependent.
    func testTheRelativeTimestampReadsTheWayAPersonWould() {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "UTC")!
        calendar.locale = Locale(identifier: "en_US_POSIX")
        let locale = Locale(identifier: "en_US_POSIX")
        // Wednesday 29 July 2026, 18:00 UTC.
        let now = calendar.date(from: DateComponents(year: 2026, month: 7, day: 29, hour: 18))!

        // macOS 15 sets the AM/PM separator as a narrow no-break space (U+202F). Normalised rather
        // than expected literally, because the separator is the system's business and this test is
        // about which *words* the ladder picks.
        func describe(_ date: Date) -> String {
            SearchTime.describe(
                date.timeIntervalSince1970, now: now, calendar: calendar, locale: locale)
                .replacingOccurrences(of: "\u{202F}", with: " ")
                .replacingOccurrences(of: "\u{00A0}", with: " ")
        }

        XCTAssertEqual(
            describe(calendar.date(from: DateComponents(year: 2026, month: 7, day: 29, hour: 14, minute: 5))!),
            "Today, 2:05 PM")
        XCTAssertEqual(
            describe(calendar.date(from: DateComponents(year: 2026, month: 7, day: 28, hour: 11, minute: 53))!),
            "Yesterday, 11:53 AM")
        // Inside the week, a weekday name locates it; past the week it becomes a riddle, so it
        // becomes a date instead.
        XCTAssertEqual(
            describe(calendar.date(from: DateComponents(year: 2026, month: 7, day: 26, hour: 9, minute: 2))!),
            "Sunday, 9:02 AM")
        XCTAssertEqual(
            describe(calendar.date(from: DateComponents(year: 2026, month: 7, day: 12, hour: 15, minute: 40))!),
            "Jul 12, 3:40 PM")
        // A different year has to say so, or "Jul 12" is a lie by omission.
        XCTAssertEqual(
            describe(calendar.date(from: DateComponents(year: 2025, month: 7, day: 12, hour: 15, minute: 40))!),
            "Jul 12, 2025, 3:40 PM")
    }

    /// The count on the filter row, including the two forms a fresh install actually shows.
    func testTheResultCountIsWrittenTheWayItIsRead() {
        XCTAssertEqual(SearchCopy.resultCount(109), "109 results")
        XCTAssertEqual(SearchCopy.resultCount(1), "1 result", "\"1 results\" is the tell that nobody looked")
        XCTAssertEqual(SearchCopy.resultCount(0), "No results")
        XCTAssertEqual(SearchCopy.resultCount(-3), "No results", "a negative count is still nothing")
    }

    /// The source line: a domain when the window carried one, the app when it did not, and never a
    /// version number or a filename mistaken for a website.
    func testTheSourceIsTheSiteWhenThereIsOneAndTheAppWhenThereIsNot() {
        XCTAssertEqual(SearchSource.source(appName: "Arc", windowTitle: "Pricing — arc.net"), "arc.net")
        XCTAssertEqual(
            SearchSource.source(appName: "Arc", windowTitle: "Home | www.shop.flixbus.com"),
            "shop.flixbus.com", "a leading www. is noise on a chip twelve characters wide")
        XCTAssertEqual(SearchSource.source(appName: "Cursor", windowTitle: "Engine.swift"), "Cursor")
        XCTAssertEqual(SearchSource.source(appName: "Finder", windowTitle: nil), "Finder")
        XCTAssertNil(SearchSource.domain(in: "shipping v1.2 of the thing"))
        XCTAssertNil(SearchSource.domain(in: "notes.txt"), "a filename is not a website")

        // A capture with no title falls back to the app rather than to a blank card.
        XCTAssertEqual(SearchSource.title(appName: "Finder", windowTitle: "   "), "Finder")
    }

    /// Website chips truncate with an ellipsis — the expected state, not the failure one.
    func testDomainChipsTruncateWithAnEllipsis() {
        XCTAssertEqual(SearchSource.truncated("arc.net"), "arc.net", "short domains are left alone")
        XCTAssertEqual(SearchSource.truncated("shop.flixbus.com"), "shop.flixbu…")
        XCTAssertEqual(SearchSource.truncated("shop.flixbus.com").count, 12)
        XCTAssertTrue(SearchSource.truncated("now.hdfcbank.example").hasSuffix("…"))
    }

    // MARK: - The empty and sparse cases

    /// **Every section says something when it is empty.**
    ///
    /// A Mac that has captured for ten minutes has no websites and two apps, so a bare header over a
    /// void is the first thing a new user sees. This is the guard against a section being added later
    /// with no empty state — the copy has to exist and it has to be a sentence.
    func testEverySectionHasCopyForTheStateANewInstallIsIn() {
        for note in [
            SearchCopy.noWebsites, SearchCopy.noApps, SearchCopy.noResults,
            SearchCopy.results(intent: .browsing), SearchCopy.results(intent: .filtering),
            SearchCopy.results(intent: .searching),
        ] {
            XCTAssertFalse(note.isEmpty)
            XCTAssertGreaterThan(note.split(separator: " ").count, 2, "\"\(note)\" is a label, not an answer")
        }
    }

    /// **An untouched search bar is not a failed search.**
    ///
    /// The regression this exists for shipped: on a fresh install, with an empty query and nothing
    /// captured, the panel said `No results` in its header and `Nothing captured matches that yet`
    /// under `RESULTS`. Both are verdicts on a search nobody ran, and they were the first two
    /// sentences the app showed a brand-new user. `SearchCopy` had no empty-query state at all — it
    /// only knew "has results" from "no results" — so an untouched bar was reported as a failure.
    func testAnUntouchedSearchBarIsNotReportedAsAFailedSearch() {
        // The results section: browsing must not borrow the sentence written for a failed search.
        XCTAssertNotEqual(
            SearchCopy.results(intent: .browsing), SearchCopy.noResults,
            "an empty query is answered with the no-results copy — the false negative is back")
        XCTAssertFalse(
            SearchCopy.results(intent: .browsing).lowercased().contains("match"),
            "\"\(SearchCopy.results(intent: .browsing))\" claims a match failed; nothing was searched for")

        // …and a search that really ran and really found nothing still says so, in both the forms
        // that count as having asked.
        XCTAssertEqual(SearchCopy.results(intent: .searching), SearchCopy.noResults)
        XCTAssertEqual(
            SearchCopy.results(intent: .filtering), SearchCopy.noResults,
            "a lit filter chip is a question, so an empty answer to it is an answer")

        // The header, which is the other half of the same defect.
        XCTAssertNil(
            SearchCopy.countLabel(0, intent: .browsing),
            "the filter row reported \"No results\" for a search that was never run")
        XCTAssertEqual(SearchCopy.countLabel(0, intent: .searching), "No results")
        XCTAssertEqual(SearchCopy.countLabel(0, intent: .filtering), "No results")
        // A browsing panel that does have captures says how much there is, which is a fact about
        // what is on screen rather than a verdict on a query.
        XCTAssertEqual(SearchCopy.countLabel(1, intent: .browsing), "1 moment captured")
        XCTAssertEqual(SearchCopy.countLabel(109, intent: .browsing), "109 moments captured")
        XCTAssertEqual(SearchCopy.countLabel(109, intent: .searching), "109 results")
    }

    /// **Opening the bar reads the capture, even though nothing was typed.**
    ///
    /// The other half of the empty-query defect, and the one that made the copy a lie rather than
    /// merely a false negative: `onAppear` called `search("")`, whose "identical text is a no-op"
    /// guard matched the query's initial `""` and returned before touching the database. Every open
    /// therefore drew the no-captures state — on a Mac with a hundred thousand of them. Measured
    /// against a real `ContextStore` on disk, because the bug was in the read that never happened.
    @MainActor
    func testOpeningTheBarWithNothingTypedStillReadsWhatWasCaptured() throws {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("search-open-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let store = try ContextStore(url: root.appendingPathComponent("context.db"))
        for offset in 0..<3 {
            _ = try store.insertFrame(
                Frame(
                    capturedAt: 1_760_000_000 + Double(offset),
                    appName: "Cursor", bundleId: nil, windowTitle: "Docs — arc.net",
                    imagePath: "/tmp/frame-\(offset).heic"))
        }

        let model = SearchResultsModel(store: { store })
        model.ask("")

        XCTAssertEqual(
            model.moments.count, 3,
            "the surface opened without reading anything — an empty bar is not a reason to skip the read")
        XCTAssertEqual(model.totalCount, 3)
        XCTAssertEqual(model.intent, .browsing)
        // …so the sentence the panel would have shown is about what is there, not about a failure.
        XCTAssertEqual(SearchCopy.countLabel(model.totalCount, intent: model.intent), "3 moments captured")
        XCTAssertFalse(model.moments.isEmpty, "the browsing empty-state copy would be a lie here")

        // And a store with nothing in it is the only way the browsing empty state is reached, which
        // is what makes its sentence true wherever it appears.
        let bare = try ContextStore(url: root.appendingPathComponent("empty.db"))
        let fresh = SearchResultsModel(store: { bare })
        fresh.ask("")
        XCTAssertTrue(fresh.moments.isEmpty)
        XCTAssertNil(SearchCopy.countLabel(fresh.totalCount, intent: fresh.intent))
        XCTAssertEqual(SearchCopy.results(intent: fresh.intent), SearchCopy.nothingCapturedYet)
    }

    /// …and the intent really follows what the user did, so the copy above is reached in the states
    /// it was written for. Whitespace is not a question, and a lit chip is.
    @MainActor
    func testTheIntentFollowsWhatTheUserActuallyDid() {
        let model = SearchResultsModel(moments: [])
        XCTAssertEqual(model.intent, .browsing, "a fresh install has been asked nothing")

        model.search("gpu benchmarks")
        XCTAssertEqual(model.intent, .searching)

        model.search("   ")
        XCTAssertEqual(model.intent, .browsing, "a bar holding one space is an untouched bar")

        model.select(time: .today)
        XCTAssertEqual(model.intent, .filtering, "a lit chip narrows the answer, so it is a question")
        model.select(time: .anytime)
        XCTAssertEqual(model.intent, .browsing, "\"anytime\" is the resting state, not a filter")

        // And the model a preview or the render harness builds carries its query with it, rather
        // than depending on a view's `onAppear` to put it there.
        XCTAssertEqual(SearchResultsModel(moments: [], query: "invoice").intent, .searching)
        XCTAssertEqual(SearchResultsModel(moments: []).intent, .browsing)
    }

    /// **An empty panel is short, and a full one is not.**
    ///
    /// The defect on either side of this is one the user sees the first time they open the surface:
    /// a fresh install showing three empty sections over 200 pt of blank glass, or a page of results
    /// whose last row of cards is sliced through the middle at the panel's edge. Measured on the real
    /// content view, whose height is its own rather than the panel's clamp.
    @MainActor
    func testAnEmptyPanelIsShortAndAFullOneIsNot() {
        func naturalHeight(_ model: SearchResultsModel) -> CGFloat {
            let host = NSHostingView(rootView: SearchFilterContent(model: model))
            host.layoutSubtreeIfNeeded()
            return host.fittingSize.height
        }

        let empty = naturalHeight(SearchResultsModel(moments: []))
        let full = naturalHeight(
            SearchResultsModel(
                moments: (1...9).map { Self.moment(id: Int64($0), title: "Docs — arc.net", app: "Arc") },
                websites: ["arc.net", "duckduckgo.com"],
                apps: [SearchAppFacet(name: "Arc", bundleId: nil)]))

        XCTAssertGreaterThan(
            full, empty + 200,
            "an empty panel is nearly as tall as a full one — the empty state is a slab of glass")
        XCTAssertLessThanOrEqual(
            SearchLayout.resultsBodyHeight(contentHeight: empty),
            SearchLayout.maximumResultsBodyHeight)
        // …and the empty panel really is short enough that the window is not mostly nothing.
        XCTAssertLessThan(empty, 300, "the empty panel is \(empty) pt of mostly blank glass")
        XCTAssertGreaterThan(empty, 0)
    }

    /// A moment whose picture is gone renders the neutral well rather than a broken image — and a
    /// card with no frame at all is an ordinary state, not a crash.
    @MainActor
    func testAMomentWithNoPictureStillDrawsACard() {
        let card = SearchResultCard(
            moment: SearchMoment(
                rowId: 7, title: "Retention pruned this one", source: "Finder", appName: "Finder",
                bundleId: nil, capturedAt: 1_700_000_000, frame: nil),
            loader: FrameLoader())
        let host = NSHostingView(rootView: card)
        host.layoutSubtreeIfNeeded()
        XCTAssertGreaterThan(host.fittingSize.height, 0)
        XCTAssertEqual(host.fittingSize.width, SearchLayout.cardWidth(), accuracy: 1)
    }

    // MARK: - Facets

    /// The chip rows offer what is actually in the answer, most frequent first, and are bounded.
    func testFacetsAreRankedByHowMuchOfTheAnswerTheyAccountFor() {
        let moments = [
            Self.moment(id: 1, title: "Docs — arc.net", app: "Arc"),
            Self.moment(id: 2, title: "Engine.swift", app: "Cursor"),
            Self.moment(id: 3, title: "Pricing — arc.net", app: "Arc"),
            Self.moment(id: 4, title: "Search — duckduckgo.com", app: "Arc"),
        ]
        XCTAssertEqual(SearchResultsModel.facetWebsites(moments), ["arc.net", "duckduckgo.com"])
        XCTAssertEqual(SearchResultsModel.facetApps(moments).map(\.name), ["Arc", "Cursor"])
        XCTAssertEqual(
            SearchResultsModel.facetWebsites(moments, limit: 1), ["arc.net"],
            "a facet row that lists everything the user ever opened is not a filter")
        XCTAssertTrue(
            SearchResultsModel.facetWebsites([Self.moment(id: 9, title: "Engine.swift", app: "Cursor")]).isEmpty,
            "a Mac with no browsing captured has no website chips, and that is the empty state")
    }

    /// The time chips select the days they name, and `anytime` really means no bound.
    func testTheTimeChipsSelectTheDaysTheyName() {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "UTC")!
        let now = calendar.date(from: DateComponents(year: 2026, month: 7, day: 29, hour: 18))!

        let today = SearchTimeFilter.today.range(now: now, calendar: calendar)
        XCTAssertEqual(today.since, calendar.startOfDay(for: now).timeIntervalSince1970)
        XCTAssertEqual(today.until!, today.since! + 86_400, accuracy: 0.01)

        let yesterday = SearchTimeFilter.yesterday.range(now: now, calendar: calendar)
        XCTAssertEqual(yesterday.until!, today.since!, accuracy: 0.01, "the two days must not overlap")

        let week = SearchTimeFilter.lastWeek.range(now: now, calendar: calendar)
        XCTAssertEqual(week.since!, today.since! - 7 * 86_400, accuracy: 0.01)
        XCTAssertNil(week.until, "\"last week\" means since, not a window that excludes today")

        XCTAssertNil(SearchTimeFilter.anytime.range(now: now, calendar: calendar).since)
        // `anytime` is a state and not a chip: a row where one pill is always lit is a segmented
        // control, and this row's pills each toggle.
        XCTAssertFalse(SearchTimeFilter.chips.contains(.anytime))
        XCTAssertEqual(SearchTimeFilter.chips, [.today, .yesterday, .lastWeek, .pickADate])
    }

    // MARK: - The bar answers for itself

    /// **Return searches; it does not hand the question to another application.**
    ///
    /// The bar used to be a delivery mechanism — whatever was typed went to `claude://code/new` on
    /// Return and the panel below was only a filter over what had been captured. What a user gets
    /// instead is stated in the two places they can actually read it (the placeholder on an untouched
    /// bar, and the label the hint button and the field carry for VoiceOver and the tooltip), so this
    /// asserts those rather than an internal flag.
    func testTheBarSaysItSearchesThisMacRatherThanOfferingToSendTheQuestionAway() {
        for sentence in [SearchMetrics.placeholder, SearchBarView.searchActionName] {
            XCTAssertFalse(
                sentence.lowercased().contains("claude"),
                "\"\(sentence)\" still offers to hand the question to Claude")
            XCTAssertFalse(
                sentence.lowercased().contains("ask "),
                "\"\(sentence)\" describes asking somebody else, not searching this Mac")
        }
        // …and it names both halves, because a user who has only seen this bar route to Claude has
        // no reason to expect it to know what was said out loud.
        XCTAssertTrue(SearchBarView.searchActionName.lowercased().contains("conversation"))
        XCTAssertTrue(SearchBarView.searchActionName.lowercased().contains("screen"))
    }

    /// A **static tripwire**, not behavioural coverage: the behaviour is covered by
    /// `testSearchingReadsBothTheScreensAndTheConversations` below, which runs the real read.
    ///
    /// **This used to list `SearchBarView.swift` too, and no longer does.** The rule it was written
    /// for was "the search bar answers for itself", enforced by forbidding the whole surface from
    /// naming `ClaudeRouter` — and that over-shot the thing worth protecting. What made routing a
    /// defect was that it was on the way to *a result*: every recall became a round trip through
    /// another application when this app owns two full-text indexes over the same machine. Return is
    /// not on the way to a result. It is the one key that says the user has a **question** rather
    /// than a lookup, and `SearchBarView.askClaude` is where it leaves — see that file's own note on
    /// why typing and Return are now different acts.
    ///
    /// So the tripwire keeps the half that is still true, and it is the half that was always doing
    /// the work: **the read-and-render path must not reach for Claude.** A keystroke that costs a
    /// window switch, or a "send this to Claude" button grown beside the results, is the regression —
    /// and neither of those can happen without one of these two files naming the router.
    func testNoFileOnTheResultsPathRoutesToClaude() throws {
        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()  // ContextAppTests
            .deletingLastPathComponent()  // Tests
            .deletingLastPathComponent()  // package root
        for file in ["SearchResultsModel.swift", "SearchResultsView.swift"] {
            let source = try String(
                contentsOf: root.appendingPathComponent("Sources/ContextApp/Search/\(file)"),
                encoding: .utf8)
            XCTAssertFalse(
                source.contains("ClaudeRouter"),
                "\(file) reaches for ClaudeRouter — searching and rendering answer from this Mac")
        }
    }

    // MARK: - Screens and conversations, ranked together

    /// **Coverage first, recency second.**
    ///
    /// The rule has to be primary-relevance rather than pure time, and this is the case that shows
    /// why: the spoken line that answers the question is twenty minutes older than three screen
    /// frames that share one incidental word with it. Ordered by time it is fourth and below the
    /// fold on a narrow panel; ordered by how much of the question it actually contains, it leads.
    func testTheMergedOrderPutsWhatCoversTheQuestionAboveWhatIsMerelyRecent() {
        let merged = SearchRanking.merge(
            screens: [
                Self.screenMoment(id: 1, title: "Invoice viewer", app: "Preview", at: 3_000),
                Self.screenMoment(id: 2, title: "Invoice viewer", app: "Preview", at: 2_900),
                Self.screenMoment(id: 3, title: "Invoice viewer", app: "Preview", at: 2_800),
            ],
            conversations: [
                Self.spokenMoment(id: 10, text: "we should send Priya the invoice on Friday", at: 1_700)
            ],
            query: "priya invoice friday",
            limit: 20)

        XCTAssertEqual(
            merged.first?.kind, .conversation,
            "the line that contains three of the three words typed is below three screens that "
                + "contain one — the merge is ordering on time, not on the question")
        XCTAssertEqual(merged.count, 4, "nothing may be dropped by the merge, only ordered")
        // …and inside the screens, which all cover the query equally, time decides.
        XCTAssertEqual(merged.dropFirst().map(\.capturedAt), [3_000, 2_900, 2_800])
    }

    /// **With nothing typed, the order is pure recency** — the state the panel opens in.
    ///
    /// There is no question to cover, so coverage is 1 everywhere and must not silently become a
    /// tie-break of its own. A browsing panel whose newest capture is not first is a panel that looks
    /// stale on a machine that is capturing right now.
    func testWithNothingTypedTheMergedOrderIsPureRecency() {
        let merged = SearchRanking.merge(
            screens: [
                Self.screenMoment(id: 1, title: "Docs — arc.net", app: "Arc", at: 500),
                Self.screenMoment(id: 2, title: "Docs — arc.net", app: "Arc", at: 300),
            ],
            conversations: [
                Self.spokenMoment(id: 10, text: "morning", at: 400),
                Self.spokenMoment(id: 11, text: "later", at: 200),
            ],
            query: "",
            limit: 20)

        XCTAssertEqual(merged.map(\.capturedAt), [500, 400, 300, 200])
        XCTAssertEqual(merged.map(\.kind), [.screen, .conversation, .screen, .conversation])
    }

    /// **Neither half can crowd the other out of the page.**
    ///
    /// This is the whole reason a plain time merge is not enough. Screen capture writes a frame every
    /// three seconds and speech writes a line a sentence, so on any real machine the newest sixty
    /// rows are sixty screenshots — and the conversation the user was searching for is on a page they
    /// will never scroll to. The cap is expressed in grid rows, so the claim is the visible one: a
    /// reader who has not scrolled has seen both kinds.
    func testNeitherHalfOfTheCaptureCanFillThePageWhileTheOtherHasAnswers() {
        // Fifty screens, all newer than every spoken line, all equally relevant — the shape a real
        // corpus has.
        let screens = (0..<50).map {
            Self.screenMoment(id: Int64($0), title: "Invoice — arc.net", app: "Arc", at: Double(10_000 - $0))
        }
        let conversations = (0..<5).map {
            Self.spokenMoment(id: Int64(100 + $0), text: "the invoice went out", at: Double(500 - $0))
        }
        // 35 is five full runs of `maximumRun` screens with a spoken line after each, which is what
        // the cap promises for this corpus — stated as arithmetic so a change to the cap fails here
        // with the number rather than silently altering what the page contains.
        let page = (SearchRanking.maximumRun + 1) * 5
        let merged = SearchRanking.merge(
            screens: screens, conversations: conversations, query: "invoice", limit: page)

        XCTAssertEqual(merged.count, page)
        let spoken = merged.filter { $0.kind == .conversation }
        XCTAssertEqual(
            spoken.count, 5,
            "every spoken line was pushed off the page by newer screenshots — the run cap is not "
                + "holding, which is the defect a pure time merge has on any real machine")

        // …and the cap really is a cap: nowhere in the page is there a longer unbroken run of one
        // kind than the rule allows, in either direction.
        var run = 0
        var previous: SearchMoment.Kind?
        for moment in merged {
            run = moment.kind == previous ? run + 1 : 1
            previous = moment.kind
            XCTAssertLessThanOrEqual(
                run, SearchRanking.maximumRun,
                "\(run) \(moment.kind.rawValue) cards in a row, past a cap of \(SearchRanking.maximumRun)")
        }
        // The cap is two grid rows: a reader who has not scrolled has seen both kinds.
        XCTAssertEqual(SearchRanking.maximumRun, SearchLayout.resultColumns * 2)
    }

    /// …and the cap never invents work: with only one kind present it must not stall, drop rows, or
    /// pad the page with anything.
    func testTheRunCapDoesNothingWhenOnlyOneKindHasAnswers() {
        let screens = (0..<20).map {
            Self.screenMoment(id: Int64($0), title: "Docs", app: "Arc", at: Double(1_000 - $0))
        }
        let merged = SearchRanking.merge(
            screens: screens, conversations: [], query: "docs", limit: 12)
        XCTAssertEqual(merged.count, 12)
        XCTAssertEqual(merged.map(\.capturedAt), (0..<12).map { Double(1_000 - $0) })

        let spokenOnly = SearchRanking.merge(
            screens: [], conversations: [Self.spokenMoment(id: 1, text: "hello", at: 5)],
            query: "hello", limit: 12)
        XCTAssertEqual(spokenOnly.map(\.kind), [.conversation])

        XCTAssertTrue(SearchRanking.merge(screens: [], conversations: [], query: "x", limit: 5).isEmpty)
        XCTAssertTrue(
            SearchRanking.merge(
                screens: screens, conversations: [], query: "docs", limit: 0
            ).isEmpty,
            "a zero page is empty, not the whole corpus")
    }

    /// **Coverage is never zero**, so a hit the index matched by a stem this ranking cannot see keeps
    /// its place rather than sinking below everything.
    ///
    /// FTS is porter-stemmed and this tokenizer is not, so "decided" in the query genuinely does
    /// match "decide" in the row while a literal comparison does not. Under-crediting is the
    /// direction that costs a true match its place, which is exactly what `Queries.coverage` floors
    /// for on the MCP side.
    func testCoverageIsNeverZeroAndCreditsOnlyRealInflections() {
        XCTAssertEqual(SearchRanking.coverage(of: "nothing in common", terms: ["invoice"]), 1)
        XCTAssertEqual(SearchRanking.coverage(of: "anything", terms: []), 1, "no question, full credit")

        // Whole words, in either order, case-folded.
        XCTAssertEqual(
            SearchRanking.coverage(of: "The INVOICE went out", terms: ["invoice", "friday"]), 0.5)
        XCTAssertEqual(
            SearchRanking.coverage(of: "invoice on friday", terms: ["invoice", "friday"]), 1)

        // An inflection counts. Two terms, one of which only matches through the plural, so the
        // answer distinguishes a real inflection credit from the floor above (which would be 0.5).
        XCTAssertEqual(
            SearchRanking.coverage(of: "the invoices went out on friday", terms: ["invoice", "friday"]),
            1,
            "\"invoices\" did not pay for \"invoice\" — the porter-stemmed index matched it and this "
                + "ranking did not, which is how a true hit sinks")
        // …and an incidental prefix does not, which is the rule that stopped a bookmark bar
        // outranking a real match in `Queries`. One term does match here, so 0.5 is a real half
        // rather than the never-zero floor.
        XCTAssertEqual(
            SearchRanking.coverage(of: "the package arrived on friday", terms: ["pack", "friday"]), 0.5,
            "\"package\" was credited for \"pack\" — incidental prefixes are how ranking rots")
    }

    /// The words a query splits into, which is the denominator of every coverage number above.
    func testTheRankingTokenizerSplitsTheWayAReaderWould() {
        XCTAssertEqual(SearchRanking.words(in: "Invoice, on Friday!"), ["invoice", "on", "friday"])
        XCTAssertEqual(
            SearchRanking.words(in: "SCA-219"), ["sca", "219"],
            "a hyphenated identifier is two words, as the index holds it")
        XCTAssertEqual(
            SearchRanking.words(in: "invoice invoice"), ["invoice"],
            "typing a word twice must not make a row that contains it look twice as relevant")
        XCTAssertTrue(SearchRanking.words(in: "   ").isEmpty)
    }

    // MARK: - What a conversation card looks like

    /// **A conversation card is the same size as a screen card**, or the grid rows go ragged and
    /// every height derived from `SearchLayout.cardHeight` is wrong for half the page.
    @MainActor
    func testAConversationCardIsTheSameShapeAsAScreenCard() {
        func height(_ moment: SearchMoment) -> CGFloat {
            let host = NSHostingView(rootView: SearchResultCard(moment: moment, loader: FrameLoader()))
            host.layoutSubtreeIfNeeded()
            return host.fittingSize.height
        }

        let screen = height(Self.moment(id: 1, title: "Docs — arc.net", app: "Arc"))
        let short = height(Self.spokenMoment(id: 2, text: "yes", at: 1_700_000_000))
        let long = height(
            Self.spokenMoment(
                id: 3,
                text: String(repeating: "a sentence that runs on well past four lines of a card ", count: 6),
                at: 1_700_000_000))

        XCTAssertEqual(short, screen, accuracy: 1, "a spoken card is \(short) pt against a screen's \(screen)")
        XCTAssertEqual(
            long, short, accuracy: 0.5,
            "a long line made its card \(long - short) pt taller — it is growing the well, not truncating in it")
        XCTAssertEqual(long, SearchLayout.cardHeight(), accuracy: 6)
    }

    /// …and it says which side of the microphone it came from, without inventing a name for anybody.
    func testASpokenCardSaysWhichSideOfTheMicrophoneItCameFrom() {
        XCTAssertEqual(SearchSpeech.title(for: .mic), "You said")
        XCTAssertEqual(
            SearchSpeech.title(for: .system), "Heard",
            "the system tap is everyone and everything else — naming a speaker would be a confident "
                + "wrong answer for a video, a call, or a stranger")

        let placed = SearchMoment(
            line: ScreenSearchQueries.SpokenLine(
                id: 1, sessionId: 7, startedAt: 1_700_000_000, source: .mic,
                text: "we should send the invoice", appHint: "zoom.us"))
        XCTAssertEqual(placed.source, "zoom.us")
        XCTAssertEqual(placed.sessionId, 7)
        XCTAssertEqual(placed.snippet, "we should send the invoice")
        XCTAssertEqual(
            placed.appName, "",
            "a spoken line was not in a window, so it must never claim an app the facet row filters on")

        let unplaced = SearchMoment(
            line: ScreenSearchQueries.SpokenLine(
                id: 2, sessionId: 8, startedAt: 1_700_000_000, source: .system, text: "sounds good"))
        XCTAssertEqual(unplaced.source, SearchSpeech.unplacedSource)
    }

    /// A card's identity has to survive both halves being on the same page: the two tables number
    /// their rows independently, so frame 41 and segment 41 both exist and would collide.
    func testAScreenAndASpokenLineWithTheSameRowNumberAreDifferentCards() {
        let screen = Self.moment(id: 41, title: "Docs", app: "Arc")
        let spoken = Self.spokenMoment(id: 41, text: "docs", at: 1_700_000_041)
        XCTAssertEqual(screen.rowId, spoken.rowId)
        XCTAssertNotEqual(
            screen.id, spoken.id,
            "the list would reuse one card's state for the other's row")
    }

    // MARK: - Reading both halves for real

    /// **The panel answers over what was said as well as what was seen.**
    ///
    /// Measured against a real `ContextStore` on disk, through both FTS indexes, because the claim is
    /// about the read: the surface used to search `frames` and nothing else, so "what did we say
    /// about the invoice" found the window somebody had it open in and never the sentence.
    @MainActor
    func testSearchingReadsBothTheScreensAndTheConversations() throws {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("search-both-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let store = try ContextStore(url: root.appendingPathComponent("context.db"))

        let base: Double = 1_760_000_000
        _ = try store.insertFrame(
            Frame(
                capturedAt: base, appName: "Preview", bundleId: nil,
                windowTitle: "Invoice 2026-07 — now.hdfcbank.example.com",
                ocrText: "amount due 412.00", imagePath: "/tmp/frame-invoice.heic"))
        // A frame that matches nothing, so a passing test cannot be "everything came back".
        _ = try store.insertFrame(
            Frame(
                capturedAt: base + 1, appName: "Finder", bundleId: nil, windowTitle: "Downloads",
                ocrText: "screenshots", imagePath: "/tmp/frame-downloads.heic"))

        let session = try store.openSession(at: base - 60, appHint: "zoom.us")
        _ = try store.insertSegment(
            Segment(
                sessionId: session, startedAt: base - 50, endedAt: base - 47, source: .mic,
                text: "I will send the invoice before Friday"))
        _ = try store.insertSegment(
            Segment(
                sessionId: session, startedAt: base - 40, endedAt: base - 38, source: .system,
                text: "the weather is fine"))

        let model = SearchResultsModel(store: { store })
        model.ask("invoice")

        XCTAssertNil(model.loadError)
        let kinds = Set(model.moments.map(\.kind))
        XCTAssertTrue(
            kinds.contains(.conversation),
            "the search found no spoken line — the panel is still screen-only")
        XCTAssertTrue(kinds.contains(.screen))
        XCTAssertEqual(
            model.totalCount, 2,
            "the count is one answer over both halves, not one half's count")

        // The frame carries the text it matched on, so a card can say why it came back.
        let screen = try XCTUnwrap(model.moments.first { $0.kind == .screen })
        XCTAssertEqual(screen.snippet, "amount due 412.00")

        // The spoken line carries its words and its conversation.
        let spoken = try XCTUnwrap(model.moments.first { $0.kind == .conversation })
        XCTAssertEqual(spoken.snippet, "I will send the invoice before Friday")
        XCTAssertEqual(spoken.sessionId, session)
        XCTAssertEqual(spoken.title, "You said")
        XCTAssertEqual(spoken.source, "zoom.us")

        // …and an empty bar still browses both halves rather than only one.
        model.ask("")
        XCTAssertEqual(model.totalCount, 4)
        XCTAssertEqual(Set(model.moments.map(\.kind)), [.screen, .conversation])
    }

    /// **A site or app chip narrows to screens**, because both are claims about a window and a spoken
    /// line was not in one.
    ///
    /// The alternative — keeping speech visible under a lit app chip — would mean a filter that says
    /// "Preview" over a grid containing rows that were never in Preview, which is the same class of
    /// untruth as the facet row offering an app none of the results belong to.
    @MainActor
    func testAnAppChipNarrowsToScreensBecauseSpeechWasNotInAWindow() throws {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("search-facet-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let store = try ContextStore(url: root.appendingPathComponent("context.db"))

        let base: Double = 1_760_000_000
        _ = try store.insertFrame(
            Frame(
                capturedAt: base, appName: "Preview", bundleId: nil, windowTitle: "Invoice",
                ocrText: "invoice", imagePath: "/tmp/frame.heic"))
        let session = try store.openSession(at: base, appHint: "zoom.us")
        _ = try store.insertSegment(
            Segment(
                sessionId: session, startedAt: base, endedAt: base + 2, source: .mic,
                text: "sending the invoice now"))

        let model = SearchResultsModel(store: { store })
        model.ask("invoice")
        XCTAssertEqual(Set(model.moments.map(\.kind)), [.screen, .conversation])
        XCTAssertEqual(
            model.apps.map(\.name), ["Preview"],
            "the app row offered something no screen result belongs to")

        model.select(app: "Preview")
        XCTAssertEqual(model.moments.map(\.kind), [.screen])
        XCTAssertEqual(model.totalCount, 1)

        model.select(app: nil)
        XCTAssertEqual(Set(model.moments.map(\.kind)), [.screen, .conversation])
    }

    // MARK: - Contrast

    /// **The type on the glass clears WCAG AA over the worst desktop that can be behind it.**
    ///
    /// The ground is the real one: `InkGlass`'s measured material over the desktop, then its scrim,
    /// resolved in the appearance the panel is pinned to. The desktops are the two extremes — solid
    /// black and solid white — because those bound everything in between.
    ///
    /// The chip is measured too, and separately, because it is the one element that puts type on
    /// something other than the panel: `Ink.primary` over `SearchInk.queryChipFill` over the glass.
    @MainActor
    func testEveryStepAndTheQueryChipClearWCAGAAOnTheRealGlass() {
        for (label, desktop) in [("black desktop", Color.black), ("white desktop", Color.white)] {
            let ground = SearchContrastProbe.glassGround(over: desktop)
            // Printed as well as asserted: the table is what a person reviewing this reads, and a
            // number nobody can see is a number that drifts.
            print(
                "[contrast] \(label): "
                    + "primary \(SearchContrastProbe.ratio(of: Ink.primary, over: ground).rounded(2)):1, "
                    + "secondary \(SearchContrastProbe.ratio(of: Ink.secondary, over: ground).rounded(2)):1, "
                    + "tertiary \(SearchContrastProbe.ratio(of: Ink.tertiary, over: ground).rounded(2)):1, "
                    + "query-in-chip \(SearchContrastProbe.ratio(of: Ink.primary, over: SearchContrastProbe.composite(SearchInk.queryChipFill, over: ground)).rounded(2)):1")

            // Two rungs, not three. This panel is glass, and glass carries `primary` and `secondary`
            // only — the ground is tuned to whatever the faintest rung on it is, so a third rung here
            // would cost the surface half its transparency. `Ink.tertiary` states the rule and
            // `InkGlassTests.testTheBottomRungIsWhatPaysForTheGlass` holds the arithmetic; what is
            // checked *here* is that this panel's own dense small copy really does clear AA on the
            // real ground, which is the case the rule was written for.
            for (name, colour, floor) in [
                ("primary", Ink.primary, 4.5),
                ("secondary", Ink.secondary, 4.5),
            ] {
                let ratio = SearchContrastProbe.ratio(of: colour, over: ground)
                XCTAssertGreaterThanOrEqual(
                    ratio, floor,
                    "\(name) is \(String(format: "%.2f", ratio)):1 on the glass over a \(desktop) desktop")
            }

            // Inside the chip, which is a tint over the same glass.
            let chip = SearchContrastProbe.composite(SearchInk.queryChipFill, over: ground)
            let query = SearchContrastProbe.ratio(of: Ink.primary, over: chip)
            XCTAssertGreaterThanOrEqual(
                query, 4.5,
                "the query inside its chip is \(String(format: "%.2f", query)):1 over a \(desktop) desktop")

            // …and the chip still reads *as* a chip: it has to differ from the panel it sits on, or
            // it is a tint nobody can see.
            XCTAssertGreaterThan(
                SearchContrastProbe.ratio(of: SearchInk.queryChipFill, over: ground), 1.02,
                "the query chip is invisible against the panel")
        }
    }

    /// The chip's tint is `systemBlue` and never the user's accent, which is purple on any Mac whose
    /// owner chose purple (INV-UI-1). Stated as an identity, because "it looked blue on my machine"
    /// is exactly the reasoning this guards against.
    @MainActor
    func testTheQueryChipIsNeverTheUsersAccentColour() {
        InkGlass.appearance.performAsCurrentDrawingAppearance {
            let chip = NSColor(SearchInk.queryChipGlyph).usingColorSpace(.sRGB)!
            let blue = NSColor.systemBlue.usingColorSpace(.sRGB)!
            XCTAssertEqual(chip.redComponent, blue.redComponent, accuracy: 0.001)
            XCTAssertEqual(chip.greenComponent, blue.greenComponent, accuracy: 0.001)
            XCTAssertEqual(chip.blueComponent, blue.blueComponent, accuracy: 0.001)
            // Blue, not purple: blue is the dominant channel and red is not close behind it.
            XCTAssertGreaterThan(chip.blueComponent, chip.redComponent + 0.3)
        }
    }

    // MARK: - Fixtures

    private static func moment(id: Int64, title: String, app: String) -> SearchMoment {
        SearchMoment(
            rowId: id,
            title: title,
            source: SearchSource.source(appName: app, windowTitle: title),
            appName: app,
            bundleId: nil,
            capturedAt: 1_700_000_000 + Double(id),
            frame: nil)
    }

    /// A screen hit at a chosen instant. Separate from `moment` because every ranking claim is about
    /// the order two hits end up in, which needs the time to be an argument rather than the row id.
    private static func screenMoment(
        id: Int64, title: String, app: String, at: Double, snippet: String? = nil
    ) -> SearchMoment {
        SearchMoment(
            rowId: id,
            title: title,
            source: SearchSource.source(appName: app, windowTitle: title),
            appName: app,
            bundleId: nil,
            capturedAt: at,
            frame: nil,
            kind: .screen,
            snippet: snippet)
    }

    /// A spoken hit, built through the real conversion from a query row rather than by filling the
    /// fields in by hand — so a test cannot assert an arrangement the app never produces.
    private static func spokenMoment(
        id: Int64, text: String, at: Double, source: SegmentSource = .mic, appHint: String? = nil
    ) -> SearchMoment {
        SearchMoment(
            line: ScreenSearchQueries.SpokenLine(
                id: id, sessionId: 1, startedAt: at, source: source, text: text, appHint: appHint))
    }
}

// MARK: - Measuring type on the glass

/// WCAG 2.1 contrast against the ground `InkGlass` actually produces.
///
/// Separate from `InkContrastProbe`, which measures the fixed three-step ladder against
/// `Ink.surface`. This one takes an arbitrary stack, because the thing being asserted here is not the
/// ladder — it is a tinted chip over a scrim over a material over a desktop, which is four layers the
/// ladder probe has no shape for.
///
/// Every colour is resolved *inside* `InkGlass.appearance` and only then converted to sRGB: the
/// palette is dynamic, and a colour read outside an appearance is whatever the test host happened to
/// be running in. The panel is pinned to that appearance, so this measures what actually ships in
/// both system appearances rather than one of them.
@MainActor
enum SearchContrastProbe {

    struct RGBA {
        var r: Double, g: Double, b: Double, a: Double
    }

    /// The real ground: `InkGlass`'s material (pure white at its measured opacity) over the desktop,
    /// then `Ink.surface` at the scrim.
    static func glassGround(over desktop: Color) -> RGBA {
        var ground = RGBA(r: 0, g: 0, b: 0, a: 1)
        InkGlass.appearance.performAsCurrentDrawingAppearance {
            let tint = InkGlass.measuredMaterialTint
            let material = RGBA(
                r: Double(tint), g: Double(tint), b: Double(tint),
                a: Double(InkGlass.measuredMaterialOpacity))
            let frosted = composite(material, over: components(desktop))
            ground = composite(
                components(Ink.surface, alpha: InkGlass.groundAlpha(reduceTransparency: false)),
                over: frosted)
        }
        return ground
    }

    static func composite(_ colour: Color, over ground: RGBA) -> RGBA {
        var result = ground
        InkGlass.appearance.performAsCurrentDrawingAppearance {
            result = composite(components(colour), over: ground)
        }
        return result
    }

    static func ratio(of colour: Color, over ground: RGBA) -> Double {
        var ratio = 0.0
        InkGlass.appearance.performAsCurrentDrawingAppearance {
            let front = luminance(composite(components(colour), over: ground))
            let back = luminance(ground)
            ratio = (max(front, back) + 0.05) / (min(front, back) + 0.05)
        }
        return ratio
    }

    private static func components(_ colour: Color, alpha: CGFloat = 1) -> RGBA {
        let resolved = NSColor(colour).usingColorSpace(.sRGB)!
        return RGBA(
            r: Double(resolved.redComponent),
            g: Double(resolved.greenComponent),
            b: Double(resolved.blueComponent),
            a: Double(resolved.alphaComponent) * Double(alpha))
    }

    /// Source-over, in the premultiplied form the compositor uses.
    private static func composite(_ fg: RGBA, over bg: RGBA) -> RGBA {
        RGBA(
            r: fg.r * fg.a + bg.r * (1 - fg.a),
            g: fg.g * fg.a + bg.g * (1 - fg.a),
            b: fg.b * fg.a + bg.b * (1 - fg.a),
            a: 1)
    }

    /// Relative luminance, WCAG 2.1 §Relative luminance.
    private static func luminance(_ c: RGBA) -> Double {
        func linear(_ channel: Double) -> Double {
            channel <= 0.04045 ? channel / 12.92 : pow((channel + 0.055) / 1.055, 2.4)
        }
        return 0.2126 * linear(c.r) + 0.7152 * linear(c.g) + 0.0722 * linear(c.b)
    }
}

extension Double {
    /// Two decimals, for a printed contrast table.
    fileprivate func rounded(_ places: Int) -> String { String(format: "%.\(places)f", self) }
}
