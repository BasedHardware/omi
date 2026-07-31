import AppKit
import SwiftUI
import XCTest

@testable import ContextApp

/// The search surface: two panels, a gap, and everything the second one draws.
///
/// The claims here are the ones a screenshot cannot make and a refactor can quietly break — that the
/// two panels are still two, that the grid is still three across at a width its cards survive, that a
/// long title truncates instead of making its row taller, and that the type on the glass is still
/// legible over the worst desktop that can be behind it.
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

    /// The surface is a tall two-panel object now, so the placement rule has to be clamped: the old
    /// "upper third" arithmetic put its bottom edge under the dock on a 13" display.
    @MainActor
    func testTheSurfaceIsPlacedInsideTheScreenEvenWhenItIsTallerThanTheOpeningOffset() throws {
        let screen = try XCTUnwrap(NSScreen.screens.first)
        let frame = SearchBarWindow.barFrame(on: screen, showingNote: true)
        XCTAssertGreaterThanOrEqual(frame.minY, screen.visibleFrame.minY - 0.5)
        XCTAssertLessThanOrEqual(frame.maxY, screen.visibleFrame.maxY + 0.5)
    }

    // MARK: - The grid

    /// **Three across, at a width the cards survive.**
    func testTheResultsGridIsThreeAcrossWithCardsWideEnoughToRead() {
        XCTAssertEqual(SearchLayout.resultColumns, 3)
        XCTAssertEqual(SearchResultsView.columns.count, SearchLayout.resultColumns)

        let card = SearchLayout.cardWidth()
        XCTAssertGreaterThanOrEqual(
            card, SearchLayout.minimumCardWidth,
            "a \(card) pt card has no room for a title before it truncates")
        // The columns and their gutters really do fill the panel's content width — a grid that
        // overflows is a grid whose last column is clipped at the panel's edge.
        let used = card * 3 + SearchLayout.cardGutter * 2
        XCTAssertEqual(used, SearchLayout.contentWidth(), accuracy: 0.001)
    }

    /// …and it reflows: at every panel width the surface could plausibly be given, three columns
    /// either still fit or the arithmetic says how much narrower they got. Nothing here may produce a
    /// negative or zero card, which is what clipping looks like from the layout's side.
    func testTheGridReflowsWithoutProducingAClippedColumn() {
        for width in stride(from: 520.0, through: 1200.0, by: 40.0) {
            let card = SearchLayout.cardWidth(panelWidth: width)
            XCTAssertGreaterThan(card, 0, "panel width \(width) produced a \(card) pt card")
            let used = card * 3 + SearchLayout.cardGutter * 2
            XCTAssertLessThanOrEqual(
                used, SearchLayout.contentWidth(panelWidth: width) + 0.001,
                "the grid overflows its panel at \(width) pt")
        }
        // The shipped width is comfortably above the point where three columns stop being readable.
        XCTAssertGreaterThan(
            SearchLayout.cardWidth(panelWidth: SearchLayout.panelWidth),
            SearchLayout.minimumCardWidth * 1.2)
    }

    /// **The panel is tall enough for a whole card.**
    ///
    /// This is the clipped-card defect stated as arithmetic. The body's ceiling has to clear the
    /// filter block plus one complete card — picture, title *and* source line — or the very first
    /// row the user sees is sliced through the middle at the panel's edge, which is what the first
    /// two passes of this design did.
    @MainActor
    func testTheCeilingLeavesRoomForAWholeCard() {
        let filterBlock = NSHostingView(
            rootView: SearchFilterContent(
                model: SearchResultsModel(
                    moments: [], websites: ["arc.net"],
                    apps: [SearchAppFacet(name: "Arc", bundleId: nil)])))
        filterBlock.layoutSubtreeIfNeeded()
        // The empty content, less the one-line "no results" note the grid replaces.
        let filters = filterBlock.fittingSize.height - SearchLayout.chipHeight

        XCTAssertGreaterThanOrEqual(
            SearchLayout.maximumResultsBodyHeight, filters + SearchLayout.cardHeight(),
            "the panel tops out at \(SearchLayout.maximumResultsBodyHeight) pt, which cuts the first "
                + "row of cards — it needs \(filters + SearchLayout.cardHeight())")
    }

    /// …and the card-height arithmetic the line above depends on really matches the card.
    @MainActor
    func testACardIsAsTallAsTheLayoutSays() {
        let host = NSHostingView(
            rootView: SearchResultCard(
                moment: SearchMoment(
                    id: 1, title: "Docs", source: "arc.net", appName: "Arc", bundleId: nil,
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
                    id: 1, title: title, source: "arc.net", appName: "Arc", bundleId: nil,
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
        for note in [SearchCopy.noWebsites, SearchCopy.noApps, SearchCopy.noResults] {
            XCTAssertFalse(note.isEmpty)
            XCTAssertGreaterThan(note.split(separator: " ").count, 2, "\"\(note)\" is a label, not an answer")
        }
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
                id: 7, title: "Retention pruned this one", source: "Finder", appName: "Finder",
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

            for (name, colour, floor) in [
                ("primary", Ink.primary, 4.5),
                ("secondary", Ink.secondary, 4.5),
                ("tertiary", Ink.tertiary, 4.5),
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
            id: id,
            title: title,
            source: SearchSource.source(appName: app, windowTitle: title),
            appName: app,
            bundleId: nil,
            capturedAt: 1_700_000_000 + Double(id),
            frame: nil)
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
