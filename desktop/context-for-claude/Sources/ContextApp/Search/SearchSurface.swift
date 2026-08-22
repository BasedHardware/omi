//
//  SearchSurface.swift — the two floating panels the search surface is made of, and the pure
//  values behind them.
//
//  The whole point of this file is that the search surface is **two objects, not one**. A prompt bar
//  and a panel of things to filter or look at are different in kind: one is a place you type, the
//  other is a place you look. Drawing them as one tall slab with a rule across it says they are the
//  same object, and that is exactly what the surface used to say. Here they are two panels with real
//  air between them, each with its own corner, its own glass and its own shadow — so the eye reads
//  two floating things over the desktop rather than one window pretending not to be a window.
//
//  Everything a test can hold is a value in here rather than a number inside a `body`: the gap, the
//  grid's column count and the card width it implies, the relative timestamp, the result count
//  sentence, the domain a window title carries. A view then has no arithmetic of its own to get
//  wrong.
//
//  Colour and type come from `Ink` / `InkType`. The two tokens this file adds (`SearchInk`) are the
//  query chip's tint, and they are here rather than in `Ink` because they are the only place in the
//  app that needs a hue at all — see the note there for why the hue is `systemBlue` and never
//  `controlAccentColor`.
//

import AppKit
import ContextCore
import SwiftUI

// MARK: - The glass

/// One floating panel of the app's **one** glass.
///
/// Everything about what the panel is made of — the `.headerView` material, the 0.10 scrim, the 22 pt
/// corner, the broad ambient shadow, the light-appearance pin that makes the type on it dark — comes
/// from `InkGlass`, which is the shared surface every window in this app now wears. Nothing about the
/// material is decided here, and a second `NSVisualEffectView` configured in this file would be the
/// defect that component exists to prevent.
///
/// What this type adds is only the *arrangement*: there are two of these, they are the same width,
/// and there is `SearchLayout.panelGap` of real air between them.
struct SearchGlassPanel<Content: View>: View {
    var cornerRadius: CGFloat = InkGlass.cornerRadius
    @ViewBuilder var content: Content

    var body: some View {
        content
            .inkGlassPanel(cornerRadius: cornerRadius, shadow: .ambient)
            // The hit shape is the panel, not its bounding box, so the rounded corners are really
            // corners: a click in the notch outside the curve belongs to whatever is behind.
            .contentShape(RoundedRectangle(cornerRadius: cornerRadius, style: .continuous))
    }
}

// MARK: - Metrics

/// Every number the search surface is laid out from.
///
/// Sizes that already exist elsewhere are taken from there — the vertical rhythm is
/// `InkLayout.rhythm`, the type is `InkType` — and only the values this surface genuinely
/// introduces are stated here, each with what set it.
enum SearchLayout {

    /// The width of both panels. Wide enough for a **four**-across grid of legible cards (see
    /// `cardWidth`) and no wider: past this the prompt bar stops reading as a bar.
    ///
    /// It was 760 for three columns. The extra 240 pt is spent on a *fourth* column rather than on
    /// four fatter cards — `cardWidth` lands at 229.5 pt against the 230.7 pt three columns used to
    /// get — so the widening costs the cards nothing and buys a third more answers per row, which is
    /// the only thing width is worth on this surface.
    ///
    /// The ceiling on it is the smallest display this panel opens on. The window is
    /// `panelWidth + shadowMargin * 2` = 1112 pt, which leaves 164 pt of desktop either side of a
    /// 13" MacBook's 1440 pt — still visibly a floating panel over a desktop rather than a sheet
    /// pinned across it. `testTheSurfaceFitsAThirteenInchDisplayAtItsWidestAndTallest` holds it.
    static let panelWidth: CGFloat = 1000

    /// **The gap.** The single most important number in this file.
    ///
    /// Two panels 12 pt apart read as two objects; the same two at 0 read as one slab with a rule
    /// through it, which is what the surface looked like before. It is a hair under the 14 pt rung of
    /// `InkLayout.rhythm` on purpose: the panels have their own shadows, and a shadow already reads
    /// as a few points of separation, so a rhythm gap on top of one measures as too much air.
    static let panelGap: CGFloat = 12

    /// The corner is the shared one. Not restated here as a number: a search bar and a timeline cut
    /// to two different radii read as two products, which is exactly why `InkGlass` owns it.
    static var panelCornerRadius: CGFloat { InkGlass.cornerRadius }

    /// The prompt bar's height. Roomy — the reference's bar is a place to type, not a control strip.
    static let barHeight: CGFloat = 60

    /// The second panel is **as tall as what is in it**, between these two bounds.
    ///
    /// A fixed height was the first attempt and it is wrong at both ends: on a fresh install the
    /// panel is three empty sections over 200 pt of nothing, and with a page of results the last row
    /// of cards is sliced through the middle at the panel's edge — which is precisely the "cards get
    /// clipped" failure this design is supposed to avoid. The panel measures its own content
    /// (`SearchPanelHeightKey`) and clamps it here instead, so a sparse panel is short and a full one
    /// stops at a height that still fits a 13" display.
    static let minimumResultsBodyHeight: CGFloat = 40
    /// The ceiling is **set by the cards at one end and by the display at the other.** Its floor is
    /// the filter block plus one whole card — thumbnail, title and source line — plus the panel's
    /// bottom padding; a ceiling under that is the clipped-card defect by another route, because the
    /// first row the user sees would be sliced through the middle.
    /// `testTheCeilingLeavesRoomForAWholeCard` holds that end.
    ///
    /// Its other end is a 13" MacBook. It was 545; 580 is as far as it can go and still leave the
    /// *tallest* the surface can be — this plus the panel's own header, the bar grown by its note
    /// line, the gap and both shadow margins, 842 pt in all — inside the 875 pt a 1440 × 900 display
    /// has under its menu bar. `testTheSurfaceFitsAThirteenInchDisplayAtItsWidestAndTallest` holds
    /// that end, and it is the reason this grew by 35 pt while the width grew by 240: there is room
    /// across a laptop display and there is almost none down it.
    ///
    /// It is also the height the activity spine takes, and takes flat rather than by measurement: a
    /// stream of everything this Mac has done is always longer than the panel, so there is no content
    /// height to hug — see the mounting point in `SearchBarView`.
    static let maximumResultsBodyHeight: CGFloat = 580

    /// What the window opens at, before the view has measured itself. A prediction, not the truth —
    /// the measured height arrives within a frame and the window resizes to it.
    ///
    /// It tracks the ceiling rather than standing still: it was 430 against a 545 pt ceiling, and it
    /// is 470 against 580, so the first frame is wrong by the same ~110 pt it always was and the
    /// opening resize is no more visible than it used to be.
    static let initialFilterPanelHeight: CGFloat = 470

    /// The scroll view's height for a given natural content height.
    ///
    /// The clamp, as a function, so both ends of it are a test rather than a screenshot: below the
    /// floor the panel is a sliver, above the ceiling it is taller than a 13" display, and inside it
    /// the panel is exactly as tall as what is in it and nothing scrolls that did not need to.
    static func resultsBodyHeight(contentHeight: CGFloat) -> CGFloat {
        min(max(contentHeight, minimumResultsBodyHeight), maximumResultsBodyHeight)
    }

    /// **Whether the body scrolls** — the content did not fit in the height the clamp gave it.
    ///
    /// The one question the bottom edge's appearance turns on. Above the ceiling the grid keeps
    /// going past the panel, which is fine and is what the scroll view is for; what is not fine is
    /// that state looking identical to the state where the panel really does contain everything. A
    /// row of cards sliced by the panel's edge with no fade, no scroller and no motion reads as a
    /// clipped view, not as "there is more below" — that is the defect this predicate exists to let
    /// the view answer.
    static func bodyScrolls(contentHeight: CGFloat) -> Bool {
        // Half a point of slack: a content height that lands exactly on the ceiling fits, and
        // floating-point measurement noise must not make a settled panel flicker its fade on.
        contentHeight > resultsBodyHeight(contentHeight: contentHeight) + 0.5
    }

    /// The soft edge at the bottom of a body that has more below it, and the room the content gains
    /// underneath itself so the fade always has something spare to fall on.
    ///
    /// Sized between two failures. Under about ten points a fade is a rendering artefact rather than
    /// a signal; at more than `cardCaptionHeight` it could swallow a card's whole title-and-source
    /// block, which would make the *last* row unreadable to fix the *next* row's slice. 26 pt is
    /// roughly a tenth of a card — enough that the sliced row visibly dissolves into the glass
    /// instead of being cut with a knife, and small enough that the row above it is untouched.
    ///
    /// Only the bottom edge fades. The top of the body is already bounded by the header's rule,
    /// which is a real edge and reads as one; the bottom is a free edge with nothing to say where
    /// the content stopped and the panel began.
    static let scrollFadeHeight: CGFloat = 26

    /// **How deep the bottom edge fades for a measured content height** — the whole of the view's
    /// decision, as a value.
    ///
    /// The view has no arithmetic of its own for the same reason nothing else in this file does: a
    /// fade the panel forgets to turn on, and a fade it leaves on over content that fits, are both
    /// invisible in a `body` and both obvious here. It also feeds the matching bottom inset, so the
    /// fade and the room it falls on cannot drift apart.
    static func scrollFade(contentHeight: CGFloat) -> CGFloat {
        bodyScrolls(contentHeight: contentHeight) ? scrollFadeHeight : 0
    }

    /// The filter panel's own header — the `Filter` row and the rule under it.
    static let panelHeaderHeight: CGFloat = 44

    static let panelPaddingHorizontal: CGFloat = 20
    static let panelPaddingVertical: CGFloat = 16

    /// Clear margin the window keeps around the panels so the shared ambient shadow has room to fall
    /// off instead of being clipped at the window's edge. Taken from the shadow itself
    /// (`InkGlassShadow.padding`), never guessed — a margin that stops tracking the shadow is a
    /// panel with a straight grey line down one side.
    static var shadowMargin: CGFloat { InkGlassShadow.ambient.padding }

    // The results grid.

    /// Four across. A count and not a `.adaptive` minimum: the panel is a fixed width, so an
    /// adaptive grid would silently become three or five across after any padding change and nothing
    /// would say so.
    ///
    /// It was three, at a 760 pt panel. What moved is the panel, not the taste: at 1000 pt a
    /// three-across grid would be 310 pt cards, which is a thumbnail bigger than the thing it is a
    /// picture of and a third fewer answers on the first row. Four keeps the card at the width it
    /// has always been (`cardWidth`, 229.5 pt against 230.7) and spends the whole widening on
    /// answers.
    ///
    /// Two other things read this rather than restating it, and both have to move with it:
    /// `SearchRanking.maximumRun` — no kind of result may take more than two grid rows in a row —
    /// and `SearchResultsModel.gridColumns`, which is what ↑/↓ step by.
    static let resultColumns = 4
    static let cardGutter: CGFloat = 14
    /// Cards are wider than they are tall by 4:3 — the shape of the screens they are pictures of.
    static let thumbnailAspect: CGFloat = 4.0 / 3.0
    static let cardCornerRadius: CGFloat = 10

    // Chips.

    static let chipHeight: CGFloat = 28
    static let chipCornerRadius: CGFloat = 14
    static let chipSpacing: CGFloat = 8
    /// The app tiles in `FILTER BY APP`, which are icons rather than pills.
    static let appTileIcon: CGFloat = 46
    static let appTileWidth: CGFloat = 74

    /// The content width inside a panel.
    static func contentWidth(panelWidth: CGFloat = panelWidth) -> CGFloat {
        max(0, panelWidth - panelPaddingHorizontal * 2)
    }

    /// One result card's width, from the panel width and the gutters between the columns.
    ///
    /// A function rather than a constant so the reflow claim is testable: the grid has to keep
    /// `resultColumns` legible columns at the width it is actually given, and a card that goes under
    /// `minimumCardWidth` is a clipped one.
    static func cardWidth(panelWidth: CGFloat = panelWidth, columns: Int = resultColumns) -> CGFloat {
        let columns = max(1, columns)
        let gutters = cardGutter * CGFloat(columns - 1)
        return max(0, (contentWidth(panelWidth: panelWidth) - gutters) / CGFloat(columns))
    }

    /// Below this a card's title has no room to say anything before it truncates, and the thumbnail
    /// stops being recognisable as a screen.
    static let minimumCardWidth: CGFloat = 150

    /// The gap between the thumbnail and the two lines under it, and the height those two lines take.
    /// Stated rather than measured so `cardHeight` is arithmetic; `testACardIsAsTallAsTheLayoutSays`
    /// checks it against the real card.
    static let cardCaptionHeight: CGFloat = 46

    /// One whole card: the picture, plus the title and source under it.
    static func cardHeight(panelWidth: CGFloat = panelWidth) -> CGFloat {
        cardWidth(panelWidth: panelWidth) / thumbnailAspect + cardCaptionHeight
    }

    // The bar's own furniture.

    /// The app glyph at the leading edge.
    static let glyphSize: CGFloat = 22
    /// The note that replaces the keyboard hint when there is something to say about the route.
    static let noteHeight: CGFloat = 34

    /// What the bar keeps for the controls at its trailing edge: the `↵ Ask Claude` hint, the
    /// Timeline pill and the gear.
    ///
    /// It used to be 190 pt for the hint alone. The two controls beside it are the surface's only
    /// routes to the timeline and to Settings — a Spotlight panel with no way out of itself is a
    /// place the user gets stuck — so the reservation grew with them rather than the chip being
    /// allowed to run underneath.
    static let trailingControlsWidth: CGFloat = 320

    /// Room the query chip may grow into before it stops. The bar's content width, less the glyph
    /// and the space the controls need on the other side.
    static let queryFieldWidth: CGFloat = contentWidth() - glyphSize - 12 - trailingControlsWidth

    // The window.

    /// The whole surface including the clear margin the shadows fall into.
    static var surfaceWidth: CGFloat { panelWidth + shadowMargin * 2 }

    /// The surface's height for a given panel height — what the window is sized to.
    ///
    /// The view measures its own content and hands the result back (`onHeightChange`), so this is
    /// the arithmetic that turns a panel height into a window height and nothing more. The default
    /// argument is the opening prediction.
    static func surfaceHeight(
        showingNote: Bool, panelHeight: CGFloat = initialFilterPanelHeight
    ) -> CGFloat {
        let bar = barHeight + (showingNote ? noteHeight : 0)
        return shadowMargin * 2 + bar + panelGap + panelHeight
    }
}

/// The second panel's measured height, on its way up to the window.
///
/// A preference and not a constant because the panel is content-sized: three empty sections and a
/// page of result cards are 300 pt apart, and a window sized for one of them is wrong for the other
/// in a way the user sees immediately — either a slab of empty glass or a row of cards sliced
/// through the middle.
struct SearchPanelHeightKey: PreferenceKey {
    static let defaultValue: CGFloat = 0
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) {
        value = max(value, nextValue())
    }
}

/// The whole surface's measured height, on its way to the window's frame.
///
/// A second key rather than the panel's, so the two measurements cannot be confused for each other:
/// one is what the scroll view may show, the other is what the window has to be.
struct SearchSurfaceHeightKey: PreferenceKey {
    static let defaultValue: CGFloat = 0
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) {
        value = max(value, nextValue())
    }
}

/// Reports the height of whatever it is placed behind. `Color.clear` so it draws nothing.
struct SearchHeightReader<Key: PreferenceKey>: View where Key.Value == CGFloat {
    var key: Key.Type

    var body: some View {
        GeometryReader { proxy in
            Color.clear.preference(key: key, value: proxy.size.height)
        }
    }
}

// MARK: - Measurement

/// The one place text is measured, so the chip and the text inside it cannot disagree.
enum SearchMetrics {

    /// What the empty bar says it is for.
    ///
    /// It used to read "Ask Claude Code…", because the bar's one action was to hand the sentence to
    /// Claude. It answers for itself now, over both halves of the capture, and the placeholder is the
    /// only thing on an untouched surface that says what typing will do — so it names the two halves
    /// rather than an app that is no longer involved.
    static let placeholder = "Search what you've seen and heard…"

    /// The size the query is set at.
    ///
    /// 19 and not `InkType.stepHeadline`'s 27, which is what this bar used before: at 27 the query
    /// is the loudest thing on the whole surface — louder than the results it produced — and it
    /// overflows the field's line box, which clipped the top of the placeholder's ascenders. 19 is
    /// still visibly larger than every other run of type here (the next is `rowCopy` at 15), which is
    /// the hierarchy the bar needs, and it stays under `Font.inkDisplayThreshold` so it is SF Pro
    /// rather than the display face — a search field is reading type.
    static let queryFontSize: CGFloat = 19

    /// The face the query is set in, resolved to the AppKit font the field is actually made of. Both
    /// the chip's width and the field's own text use this exact value; two different faces here is a
    /// capsule that is a few points too narrow and looks like a rendering bug.
    static var queryFace: NSFont {
        InkFonts.role(size: queryFontSize, weight: .semiBold).metrics
    }

    /// The line box the query needs, with room above the ascenders. The chip and the field row are
    /// both this tall — a field shorter than its own font is the clipped-placeholder defect.
    static var queryLineHeight: CGFloat {
        (InkFonts.naturalLineHeight(queryFace) + 10).rounded()
    }

    /// Padding inside the query chip, either end.
    static let chipPaddingHorizontal: CGFloat = 12
    /// The magnifier plus the gap after it.
    static let chipGlyphWidth: CGFloat = 13 + 6

    /// How wide the tinted capsule is for a given query.
    ///
    /// A pure function of the string and the room it has, which is what makes "the chip hugs the
    /// text" and "the chip stops at the bar's edge" two things a test can hold rather than two things
    /// that look right on the one query someone tried.
    static func chipWidth(for query: String, available: CGFloat) -> CGFloat {
        guard !query.isEmpty else { return 0 }
        let text = textWidth(query)
        let wanted = chipPaddingHorizontal * 2 + chipGlyphWidth + text
        return min(max(wanted, minimumChipWidth), max(minimumChipWidth, available))
    }

    /// A chip narrower than this is a coloured smudge rather than a chip.
    static let minimumChipWidth: CGFloat = 54

    /// The rendered width of a run of text in the query face.
    static func textWidth(_ text: String, font: NSFont? = nil) -> CGFloat {
        let face = font ?? queryFace
        return NSAttributedString(string: text, attributes: [.font: face]).size().width
    }
}

// MARK: - Colour

/// The two hues the search surface adds, and the reason each one is a system semantic colour.
///
/// `Ink` is the palette; this is not a second one. It exists because the query chip is the only
/// element in the app that has to read as *tinted* rather than as a neutral wash, and because a
/// shadow needs a black that is not a label colour.
enum SearchInk {

    /// The query chip's fill.
    ///
    /// `systemBlue` and explicitly **not** `Ink.accent` / `NSColor.controlAccentColor`. The accent is
    /// the user's own choice, so it is purple on any Mac whose owner picked purple — and purple is
    /// off-brand everywhere in this product (INV-UI-1). A chip that is purple on some machines and
    /// not others is not a design, it is a coin flip. `systemBlue` is still a system semantic colour,
    /// so it tracks the appearance and increases contrast under the accessibility setting, and it is
    /// the hue the reference reads as.
    ///
    /// 0.14 is a wash rather than a fill: the chip's job is to say "this run of text is the query",
    /// and the text inside it is `Ink.primary`, which has to stay the highest-contrast thing in the
    /// bar. A saturated fill would put a mid-luminance hue under near-black type on light glass and
    /// near-white type on dark glass, and only one of those can be legible.
    static let queryChipFill = Color(nsColor: .systemBlue).opacity(0.14)
    /// The chip's edge — the same hue, a little stronger, so the capsule has a boundary without a
    /// border heavy enough to read as a control.
    static let queryChipStroke = Color(nsColor: .systemBlue).opacity(0.28)
    /// The magnifier inside the chip. Full-strength `systemBlue` is legible as a *glyph* at 11 pt on
    /// both grounds where it would not be as text.
    static let queryChipGlyph = Color(nsColor: .systemBlue)

    /// A filter chip at rest: the near-white/very light grey of the reference, expressed the way
    /// every other fill in this app is — an alpha on `labelColor`, so it darkens light glass and
    /// lightens dark glass instead of being one grey that is wrong in one appearance.
    static let chipFill = Color(nsColor: .labelColor).opacity(0.05)
    static let chipFillHover = Color(nsColor: .labelColor).opacity(0.09)
    /// The selected chip. Stronger, still neutral — selection is weight, never hue.
    static let chipFillSelected = Color(nsColor: .labelColor).opacity(0.14)
    /// "A very subtle border", per the reference. Half of `Ink.hairline`, which is the edge of
    /// something you press; a chip is a lighter promise than that.
    static let chipStroke = Color(nsColor: .labelColor).opacity(0.10)

    /// The neutral standing in for a thumbnail that has not decoded yet, or whose file retention
    /// already removed. Never a broken-image glyph and never an empty hole.
    static let thumbnailPlaceholder = Color(nsColor: .labelColor).opacity(0.06)

    /// The well a spoken line is set on, where a screen card has its picture.
    ///
    /// **Neutral, not tinted, and that is the point.** A hue here would be a second colour meaning
    /// on a surface that already spends its one hue on the query chip, and any hue picked to say
    /// "speech" is a hue somebody has to learn. What separates the two kinds of card is the *shape*
    /// of what is in the well — a photograph or a run of type — which needs no legend. A shade
    /// darker than `thumbnailPlaceholder` so a card with words on it reads as filled rather than as
    /// a picture that failed to load.
    static let spokenWell = Color(nsColor: .labelColor).opacity(0.08)
}

// MARK: - What a result is

/// One thing the search found, with everything a card draws and nothing it does not.
///
/// **Two kinds of thing, one shape.** The surface answers over what was on screen *and* over what was
/// said, and those are genuinely different rows in two different tables — but a person scrolling one
/// page of results should not have to hold two mental models, and a merged ranking
/// (`SearchRanking`) cannot order two unrelated types against each other. So both collapse to this,
/// and `kind` is what the card switches its picture and its glyph on.
///
/// Distinct from `RewindFrame` and from `ScreenSearchQueries.SpokenLine` because a card shows a
/// *source* — a domain when the window carried one, the app when it did not, and where a
/// conversation was held when it is speech — and deriving that in the view would put a
/// string-parsing decision inside a `body` where no test can reach it.
struct SearchMoment: Identifiable, Equatable {

    /// Which half of the capture this came from.
    enum Kind: String, Equatable, Sendable {
        /// A screen frame: `frames.id`, and a picture when one survives on disk.
        case screen
        /// A transcript line: `segments.id`, and the words themselves.
        case conversation
    }

    let kind: Kind
    /// The row this came from — `frames.id` for a screen, `segments.id` for a spoken line.
    ///
    /// **Not the identity.** The two tables number their rows independently, so frame 41 and segment
    /// 41 are both real and both can be on the same page; a list keyed on this alone would have
    /// SwiftUI reuse one card's state for the other's row. `id` below is what the list uses.
    let rowId: Int64
    /// The window title, the app name when the capture had no title, or who spoke. Never empty.
    let title: String
    /// The domain the title carried, the app that owned the window, or where the conversation was.
    let source: String
    /// The app that owned the window. **Empty for a conversation**, deliberately: a spoken line was
    /// not in a window, and the session's `appHint` is only where the conversation *started*. It
    /// reads as a `source`, never as a claim that these words happened in that app — which is also
    /// why speech never appears in the app facet row.
    let appName: String
    let bundleId: String?
    /// Unix epoch seconds.
    let capturedAt: Double
    /// The stored frame, when there is a picture on disk. Nil is an ordinary outcome — retention
    /// unlinks files, 8.7% of captured rows never had an image at all, and a conversation never has
    /// one.
    let frame: RewindFrame?
    /// The words behind the hit: the matched screen text, or the spoken line.
    ///
    /// It is what makes a result *answerable* rather than merely findable — a screenshot that matched
    /// deep inside a page of OCR looks arbitrary without it, and a frame whose picture retention
    /// already removed has nothing else to show at all.
    let snippet: String?
    /// The conversation a spoken line belongs to, for a future "open this conversation". Nil for a
    /// screen.
    let sessionId: Int64?

    /// Unique across both kinds, which `rowId` is not.
    var id: String { "\(kind.rawValue)-\(rowId)" }

    /// The text the ranking scores this hit's relevance against.
    ///
    /// Kind-specific on purpose. A screen is findable by everything the window announced about
    /// itself; a spoken line is only its words — folding its `title` ("You said") in would hand every
    /// conversation on the machine a free match for the word "said".
    var relevanceText: String {
        switch kind {
        case .screen:
            return [title, appName, snippet].compactMap { $0 }.joined(separator: " ")
        case .conversation:
            return snippet ?? ""
        }
    }

    init(
        rowId: Int64,
        title: String,
        source: String,
        appName: String,
        bundleId: String?,
        capturedAt: Double,
        frame: RewindFrame?,
        kind: Kind = .screen,
        snippet: String? = nil,
        sessionId: Int64? = nil
    ) {
        self.kind = kind
        self.rowId = rowId
        self.title = title
        self.source = source
        self.appName = appName
        self.bundleId = bundleId
        self.capturedAt = capturedAt
        self.frame = frame
        self.snippet = snippet
        self.sessionId = sessionId
    }

    /// The card shape for a captured frame, with the title and source already decided.
    ///
    /// - Parameter snippet: the frame's matched text, from `ScreenSearchQueries.frameText`. Nil is
    ///   ordinary — a frame can genuinely have had no text on it.
    init(frame: RewindFrame, snippet: String? = nil) {
        let title = SearchSource.title(appName: frame.appName, windowTitle: frame.windowTitle)
        self.init(
            rowId: frame.id,
            title: title,
            source: SearchSource.source(appName: frame.appName, windowTitle: frame.windowTitle),
            appName: frame.appName,
            bundleId: frame.bundleId,
            capturedAt: frame.capturedAt,
            frame: frame,
            kind: .screen,
            snippet: snippet)
    }

    /// The card shape for a spoken line.
    ///
    /// The title is *who*, not *what*: the words are the card's picture, so putting them in the title
    /// as well would print the same sentence twice on a 230 pt card. What the title has to carry is
    /// the one thing the words cannot say for themselves — whether this was the user or the room.
    init(line: ScreenSearchQueries.SpokenLine) {
        self.init(
            rowId: line.id,
            title: SearchSpeech.title(for: line.source),
            source: line.appHint ?? SearchSpeech.unplacedSource,
            appName: "",
            bundleId: nil,
            capturedAt: line.startedAt,
            frame: nil,
            kind: .conversation,
            snippet: line.text,
            sessionId: line.sessionId)
    }
}

/// What a conversation card calls the thing it is showing.
///
/// Attribution here is only ever *which side of the microphone*, which is a fact this app observed
/// itself and stays true forever. A name is a current property of the user's Omi account — see the
/// attribution note in `Queries` — so nothing in this app's own UI may invent one from a row.
enum SearchSpeech {

    /// The card's headline for a spoken line.
    ///
    /// "Heard" and not "They said": the system tap is everyone else *and* everything else, so a line
    /// it captured may have come from a person in the room, a person on a call, or a video. Claiming
    /// a speaker would be a confident wrong answer in every case but the first; "Heard" is true in
    /// all of them.
    static func title(for source: SegmentSource) -> String {
        source == .mic ? "You said" : "Heard"
    }

    /// The source line when the session recorded no app to place it in.
    static let unplacedSource = "Conversation"
}

/// What a card calls the thing it is showing.
enum SearchSource {

    /// The card's headline. The window title when there is one, otherwise the app — never blank, and
    /// never the literal string "Untitled", which says less than the app's own name does.
    static func title(appName: String, windowTitle: String?) -> String {
        let trimmed = windowTitle?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return trimmed.isEmpty ? appName : trimmed
    }

    /// The line under the title: the site the window was showing, or the app that owned it.
    ///
    /// Browsers put the page's host in the window title often enough that pulling it out is what
    /// makes a grid of screenshots scannable — twelve cards all sourced "Arc" say nothing, and twelve
    /// sourced by their domains say where the user was. When no host is present the app name is the
    /// honest answer; nothing is ever invented.
    static func source(appName: String, windowTitle: String?) -> String {
        domain(in: windowTitle) ?? appName
    }

    /// The first host-looking run in a string, normalised (lowercased, `www.` dropped), or nil.
    ///
    /// **The suffix must be one this file knows.** A "looks like `word.word`" rule is the obvious
    /// implementation and it is wrong in the direction that matters: it reads `Engine.swift`,
    /// `notes.txt` and `main.py` as websites, which puts a filename under the card of every editor
    /// screenshot and then offers it as a website chip. Since every one of those is a *confident*
    /// wrong answer, the rule is inverted — a domain is claimed only when the suffix is a suffix
    /// people actually browse, and everything else falls back to the app name, which is always true.
    ///
    /// The list is not exhaustive and is not meant to be: an unrecognised suffix costs a domain chip
    /// the user did not need, and a wrong one costs the surface its credibility.
    static func domain(in text: String?) -> String? {
        guard let text, !text.isEmpty else { return nil }
        // Hosts are the only runs of `[A-Za-z0-9.-]` that end in a suffix we recognise.
        let allowed = CharacterSet(charactersIn: "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-")
        for run in text.unicodeScalars.split(whereSeparator: { !allowed.contains($0) }) {
            let candidate = String(String.UnicodeScalarView(run)).lowercased()
            let labels = candidate.split(separator: ".", omittingEmptySubsequences: false)
            guard labels.count >= 2, let tld = labels.last, knownSuffixes.contains(String(tld)) else {
                continue
            }
            guard labels.dropLast().allSatisfy({ !$0.isEmpty }) else { continue }
            // A leading `www.` is noise on a chip 12 characters wide.
            let host = candidate.hasPrefix("www.") ? String(candidate.dropFirst(4)) : candidate
            return host.isEmpty ? nil : host
        }
        return nil
    }

    /// Suffixes a person browses. Deliberately excludes the ones that are also file extensions
    /// (`.sh`, `.rs`, `.py`, `.go`, `.md`, `.ts`, `.js`) even though several are real country codes:
    /// on a Mac being screen-captured, `main.rs` is overwhelmingly more likely than a Serbian site,
    /// and the cost of the two mistakes is not symmetric.
    static let knownSuffixes: Set<String> = [
        "com", "net", "org", "edu", "gov", "mil", "int", "info", "biz", "app", "dev", "ai", "io",
        "co", "me", "tv", "fm", "gg", "xyz", "cloud", "page", "site", "news", "blog", "shop",
        "store", "tech", "design", "studio", "digital", "media", "online", "live", "life", "world",
        "email", "chat", "wiki", "space", "link", "team", "works", "systems", "software", "network",
        "uk", "de", "fr", "es", "it", "nl", "se", "no", "dk", "fi", "pl", "cz", "at", "ch", "be",
        "ie", "pt", "gr", "hu", "ro", "ru", "ua", "tr", "il", "in", "jp", "kr", "cn", "tw", "hk",
        "sg", "au", "nz", "za", "br", "mx", "ar", "cl", "ca", "us", "eu",
    ]

    /// A domain cut to fit a chip, with a real ellipsis.
    ///
    /// Truncation is the *expected* state here rather than the failure one — the reference's website
    /// chips read `shop.flix…`, `archit-lal…`, `now.hdfc…` — so it is a value with a test rather than
    /// a `.lineLimit(1)` and a hope. The character budget is what fits a chip at
    /// `InkType.statusLabel`; the ellipsis is one character and is counted.
    static func truncated(_ text: String, limit: Int = 12) -> String {
        guard limit > 1, text.count > limit else { return text }
        return String(text.prefix(limit - 1)) + "…"
    }
}

// MARK: - Time

/// The friendly timestamp under a card, and the one place its rules live.
///
/// `ContextTime.describe` is the MCP wire format ("Tue 28 Jul 2026 at 2:14 PM") and is deliberately
/// unfriendly — a model reasons better about a full date than about "yesterday". A person reads the
/// opposite way, so a card gets this instead. Both exist; neither is a substitute for the other.
enum SearchTime {

    /// e.g. `Today, 2:14 PM` · `Yesterday, 11:53 AM` · `Monday, 9:02 AM` · `Jul 12, 3:40 PM` ·
    /// `Jul 12, 2025, 3:40 PM`.
    ///
    /// Takes `now` and the calendar rather than reading them, so the whole ladder is assertable in a
    /// test that does not depend on the day it runs on.
    static func describe(
        _ epoch: Double,
        now: Date = Date(),
        calendar: Calendar = .current,
        locale: Locale = .current
    ) -> String {
        let date = Date(timeIntervalSince1970: epoch)
        let time = formatted(date, template: "j:mm", calendar: calendar, locale: locale)

        // Measured against `now`, not against `Date()`. `Calendar.isDateInToday` reads the wall
        // clock, so a card rendered from a fixed instant — a test, a golden render — would silently
        // describe itself relative to the day the process happened to run on.
        let days =
            calendar.dateComponents(
                [.day], from: calendar.startOfDay(for: date), to: calendar.startOfDay(for: now)
            ).day ?? 0
        if days == 0 { return "Today, \(time)" }
        if days == 1 { return "Yesterday, \(time)" }

        // Inside the last week a weekday name is the most useful thing a person can be told; past
        // that it stops being a location in time and becomes a riddle ("which Monday?").
        if (0...6).contains(days) {
            return "\(formatted(date, template: "EEEE", calendar: calendar, locale: locale)), \(time)"
        }

        let sameYear = calendar.component(.year, from: date) == calendar.component(.year, from: now)
        let template = sameYear ? "MMM d" : "MMM d, yyyy"
        return "\(formatted(date, template: template, calendar: calendar, locale: locale)), \(time)"
    }

    /// Localised field order from a template, so `j:mm` is 24-hour where the user's region is and the
    /// month/day order follows their format — a hand-written `"MMM d"` pattern would not.
    private static func formatted(
        _ date: Date, template: String, calendar: Calendar, locale: Locale
    ) -> String {
        let formatter = DateFormatter()
        formatter.calendar = calendar
        formatter.locale = locale
        formatter.timeZone = calendar.timeZone
        formatter.setLocalizedDateFormatFromTemplate(template)
        return formatter.string(from: date)
    }
}

// MARK: - What the panel was asked

/// Whether the panel is reporting a **search**, or simply showing what this Mac has captured.
///
/// This distinction is the whole of a defect the surface shipped without it. With nothing typed and
/// no chip lit, nobody has asked the panel anything — and yet it answered, in two places at once:
/// the header said `No results` and the results section said `Nothing captured matches that yet`.
/// Both are verdicts on a search that was never run, and both are the *first* two sentences a brand
/// new install shows, on the one screen whose job is to make the app look like it works.
///
/// A search that really was run and really found nothing still says so. That state is `.searching`,
/// and its copy is unchanged.
enum SearchIntent: Equatable, Sendable {

    /// Nothing typed, nothing narrowed. The panel is showing the newest captures, which is not an
    /// answer to anything.
    case browsing
    /// No query, but a filter chip is lit. The user did ask something — "today", "this site" — so a
    /// nothing-found answer is honest here.
    case filtering
    /// Something is typed.
    case searching

    /// Which of the three a given query and filter state is.
    ///
    /// Trimmed, because a bar holding one space is an untouched bar as far as the user is concerned
    /// (and as far as `SearchResultsModel.search` is: it trims before it queries).
    static func of(query: String, isNarrowed: Bool) -> SearchIntent {
        if !query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { return .searching }
        return isNarrowed ? .filtering : .browsing
    }

    /// Whether a "found nothing" sentence would be an answer rather than a false negative.
    var wasAsked: Bool { self != .browsing }
}

// MARK: - Copy

/// The sentences the surface says about its own results.
enum SearchCopy {

    /// The count on the filter row for a panel that was actually asked something: `109 results` ·
    /// `1 result` · `No results`.
    ///
    /// "No results" and not "0 results", because zero is a number a person has to convert and the
    /// words are the answer. Singular is not a nicety either — "1 results" is the tell that nobody
    /// looked at the empty and near-empty cases, which are the two a new install always shows.
    static func resultCount(_ count: Int) -> String {
        switch count {
        case ..<1: return "No results"
        case 1: return "1 result"
        default: return "\(count) results"
        }
    }

    /// What the filter row says opposite `Filter`, or **nil when it should say nothing at all**.
    ///
    /// Nil is the point of this function rather than an oversight in it. With nothing typed and
    /// nothing narrowed there is no search to report a verdict on, and `No results` in that state is
    /// a failure the user never asked for — the single worst sentence a fresh install could open
    /// with. A browsing panel that *does* have captures says how many, because that is a fact about
    /// what is on the screen rather than a judgement about a query, and it is also the only place
    /// the surface says how much there is to search.
    static func countLabel(_ count: Int, intent: SearchIntent) -> String? {
        guard !intent.wasAsked else { return resultCount(count) }
        switch count {
        case ..<1: return nil
        case 1: return "1 moment captured"
        default: return "\(count) moments captured"
        }
    }

    /// **What is narrowing this answer, in words** — for the header, when the filter block is closed
    /// and the lit chips are therefore not on screen. Nil when nothing is narrowing it.
    ///
    /// The point of the sentence is that closing the block costs the user no information. A count
    /// that dropped from 109 to 4 with no visible cause is the worst state this panel could be in:
    /// it is indistinguishable from a machine that captured almost nothing, and the user has no way
    /// to find the control that did it. Naming the narrowing removes that state entirely, which is
    /// what earns the closed block.
    ///
    /// The filters are named in the order the block draws them, so pressing `Filter` shows the lit
    /// chips in the order they were just read out. `pickADate` says "a date" rather than the date
    /// itself: the day lives in the picker, and a header that reprints it would be the one place in
    /// the surface where a filter's *value* is stated twice and can disagree with itself.
    static func filterSummary(time: SearchTimeFilter, website: String?, app: String?) -> String? {
        var parts: [String] = []
        if time != .anytime { parts.append(time == .pickADate ? "a date" : time.title) }
        if let website { parts.append(SearchSource.truncated(website)) }
        if let app { parts.append(app) }
        return parts.isEmpty ? nil : parts.joined(separator: ", ")
    }

    /// What a section says when it has nothing in it yet.
    ///
    /// Every one of these is reachable on a fresh install — a Mac that has captured for ten minutes
    /// has no websites and two apps — so a bare header with a void under it is the *normal* first
    /// experience, not an edge case. A sentence in its place is what makes the section read as
    /// deliberate rather than broken.
    static let noWebsites = "No sites captured yet"
    static let noApps = "No apps captured yet"

    /// A search ran and matched nothing. Every word of it is about the query.
    static let noResults = "Nothing captured matches that yet"

    /// …and what the same section says when there was no query to fail.
    ///
    /// Reached only when the panel is browsing and the capture is genuinely empty (no query and no
    /// filter means the count is the whole of what exists), so it can state the real reason the
    /// section is bare and what will change it. It is deliberately *not* an invitation to type: on
    /// the machine that sees this sentence there is nothing to type at yet, and "try searching" over
    /// an empty database is the same false promise in a friendlier voice.
    static let nothingCapturedYet = "Nothing captured yet — what you see and say shows up here"

    /// The results section's sentence for a given intent.
    static func results(intent: SearchIntent) -> String {
        intent.wasAsked ? noResults : nothingCapturedYet
    }
}
