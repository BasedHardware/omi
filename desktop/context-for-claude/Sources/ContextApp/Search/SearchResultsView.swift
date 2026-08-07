//
//  SearchResultsView.swift — the second panel: what you can filter by, and what was found.
//
//  Structure, top to bottom: a `Filter` row with the result count opposite it, a full-width hairline
//  under it, then sections with small uppercase headers — time, website, app — and finally the
//  results themselves as a three-across grid of cards.
//
//  Two things in here are load-bearing and easy to lose in a refactor:
//
//  - **Every section has an empty state.** A Mac that has been capturing for ten minutes has no
//    websites and two apps, so a bare header over a void is the *first* thing a new user sees, not an
//    edge case. Each section says something in that state instead.
//  - **Long text truncates, it never wraps.** A card title is one line; a domain chip is a fixed
//    number of characters with an ellipsis (`SearchSource.truncated`). A grid whose cells are
//    different heights because one page had a long title is the thing that made the old surface look
//    unconsidered.
//

import AppKit
import ContextCore
import SwiftUI

// MARK: - The panel

struct SearchResultsView: View {
    @ObservedObject var model: SearchResultsModel
    /// **What activating a result does.** Supplied by whoever owns the surface, because opening the
    /// timeline is a window operation and this is a view — the same reasoning that keeps
    /// `RewindView`'s `onSearch` a closure rather than a call into the shell.
    ///
    /// Defaulted to nothing so a preview or the render harness can draw the panel without a route to
    /// a window; the cards are still buttons there, they just have nowhere to go.
    var onOpen: (SearchMoment) -> Void = { _ in }

    /// The natural height of everything under the divider, measured rather than assumed. See
    /// `SearchPanelHeightKey` for why a constant here is wrong at both ends.
    @State private var contentHeight: CGFloat = 0

    private var bodyHeight: CGFloat { SearchLayout.resultsBodyHeight(contentHeight: contentHeight) }

    /// Whether there is more below the panel's bottom edge than fits inside it.
    private var scrolls: Bool { SearchLayout.bodyScrolls(contentHeight: contentHeight) }

    /// How deep the bottom edge dissolves, and the room the content gains under itself to match.
    /// Zero when the panel contains everything it has.
    private var fade: CGFloat { SearchLayout.scrollFade(contentHeight: contentHeight) }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            Divider().overlay(Ink.separator)
                .padding(.horizontal, SearchLayout.panelPaddingHorizontal)
            // The reader is here for one job: a selection moved by the keyboard has to be *visible*.
            // A page of 60 cards is several panels tall, so ↓ pressed enough times would otherwise
            // move a highlight the user cannot see, and Return would open a moment they were never
            // shown — which is worse than the keyboard not working at all.
            ScrollViewReader { proxy in
                ScrollView(.vertical) {
                    SearchFilterContent(model: model, onOpen: onOpen)
                        .background(SearchHeightReader(key: SearchPanelHeightKey.self))
                        // Spare room under the last row, only when the body scrolls, so that a reader
                        // who has scrolled all the way down has the fade falling on empty glass rather
                        // than on the final card's source line. Applied *outside* the height reader on
                        // purpose: the measurement stays the content's own natural height, so this inset
                        // cannot feed back into the clamp that decided to add it.
                        .padding(.bottom, fade)
                }
                // The platform affordance, restored the moment there is anything to scroll to. It was
                // suppressed unconditionally before, which is right for a panel that contains
                // everything and wrong for one that does not: on a Mac with "Show scroll bars: always"
                // the surface was the only scrollable thing on screen with no scroller at all.
                .scrollIndicators(scrolls ? .automatic : .never)
                .frame(height: bodyHeight)
                // …and the part that works at rest, before the user has touched anything: overlay
                // scrollers are invisible until something moves, so the first impression of an
                // overflowing panel is carried entirely by the bottom edge dissolving.
                .mask(SearchScrollFade(fade: fade))
                .onChange(of: model.selection) { _, selection in
                    guard let selection else { return }
                    // Centred, not `.top`: the card the keyboard is on should have the cards either
                    // side of it in view, because "the next best answer" is only meaningful next to
                    // the ones it beat.
                    InkReduceMotion.perform(.easeOut(duration: InkMotion.settle)) {
                        proxy.scrollTo(selection, anchor: .center)
                    }
                }
            }
        }
        .frame(width: SearchLayout.panelWidth, alignment: .top)
        .onPreferenceChange(SearchPanelHeightKey.self) { contentHeight = $0 }
    }

    // MARK: Header

    /// The `Filter` row — and, since the block below it closes, **the control that opens it**.
    ///
    /// The row was already a filter glyph and the word `Filter` over the block it describes; making
    /// it the disclosure adds a chevron and a hit target and invents nothing. A separate "Filters"
    /// button beside it would have been a second thing meaning the first thing.
    private var header: some View {
        HStack(spacing: 8) {
            Button(action: { model.toggleFilters() }) {
                HStack(spacing: 8) {
                    Image(systemName: "line.3.horizontal.decrease")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(Ink.secondary)
                    Text("Filter").inkStyle(.rowCopy, color: Ink.primary)
                    // What the closed block is doing to the answer. See `SearchCopy.filterSummary`
                    // — without it a narrowed count has no visible cause.
                    if let summary = model.hiddenFilterSummary {
                        Text(summary)
                            .inkStyle(.statusLabel, color: Ink.secondary)
                            .lineLimit(1)
                            .truncationMode(.tail)
                    }
                    // Down when open, right when closed — the direction the block will move, which
                    // is the one thing a chevron is read for. Rotated rather than swapped for a
                    // second symbol so the turn is the animation.
                    Image(systemName: "chevron.down")
                        .font(.system(size: 9, weight: .semibold))
                        .foregroundStyle(Ink.secondary)
                        .rotationEffect(.degrees(model.isShowingFilters ? 0 : -90))
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel(Text(Self.filterDisclosureLabel(summary: model.hiddenFilterSummary)))
            .accessibilityAddTraits(model.isShowingFilters ? [.isSelected] : [])
            Spacer(minLength: 12)
            // Nil is a state and not a missing value: an untouched bar over an empty capture has no
            // verdict to report, and `No results` there answers a search nobody ran.
            if let count = SearchCopy.countLabel(model.totalCount, intent: model.intent) {
                Text(count)
                    .inkStyle(.statusLabel, color: Ink.secondary)
                    .fixedSize()
            }
        }
        .padding(.horizontal, SearchLayout.panelPaddingHorizontal)
        .frame(height: SearchLayout.panelHeaderHeight)
        .animation(InkReduceMotion.animation(.easeOut(duration: InkMotion.press)), value: model.isShowingFilters)
    }

    /// What the disclosure is called to VoiceOver. The chevron says "open me" to the eye and nothing
    /// at all to a reader, so the label has to carry both the action and, when there is one, the
    /// narrowing the closed block is holding.
    static func filterDisclosureLabel(summary: String?) -> String {
        guard let summary else { return "Filter" }
        return "Filter — \(summary)"
    }

    /// Fixed-width columns, not adaptive: the panel is a known width, so the card width is arithmetic
    /// (`SearchLayout.cardWidth`) that a test can hold. An adaptive grid would quietly become two or
    /// four across after a padding change and nothing would say so.
    static let columns: [GridItem] = Array(
        repeating: GridItem(
            .fixed(SearchLayout.cardWidth()), spacing: SearchLayout.cardGutter, alignment: .topLeading),
        count: SearchLayout.resultColumns)
}

// MARK: - The sections

/// Everything under the divider, at its natural height.
///
/// Split out of `SearchResultsView` rather than inlined so the height it wants is measurable in a
/// single layout pass — the panel clamps that height, and "an empty panel is much shorter than a
/// full one" is the claim worth testing. Measuring it through the clamped panel would only ever
/// report the clamp back.
struct SearchFilterContent: View {
    @ObservedObject var model: SearchResultsModel
    /// Passed straight through to the cards. See `SearchResultsView.onOpen`.
    var onOpen: (SearchMoment) -> Void = { _ in }

    var body: some View {
        VStack(alignment: .leading, spacing: InkLayout.rhythm[3]) {
            // **The results are what the panel is for, and the filters are one press away.** The
            // three sections are drawn above the grid when they are drawn at all, because that is
            // where a control belongs relative to what it narrows; what changed is that they are
            // not drawn by default. See `SearchResultsModel.isShowingFilters` for the panel-height
            // arithmetic that made the old arrangement show three cards out of a hundred and nine.
            if model.isShowingFilters {
                timeSection
                websiteSection
                appSection
            }
            resultsSection
        }
        .padding(.horizontal, SearchLayout.panelPaddingHorizontal)
        .padding(.top, InkLayout.rhythm[3])
        .padding(.bottom, SearchLayout.panelPaddingVertical)
        .frame(width: SearchLayout.panelWidth, alignment: .leading)
    }

    // MARK: Sections

    private var timeSection: some View {
        SearchSection(title: "Filter by time") {
            HStack(spacing: SearchLayout.chipSpacing) {
                ForEach(SearchTimeFilter.chips) { filter in
                    SearchChip(
                        systemImage: filter.systemImage,
                        title: filter.title,
                        isSelected: model.time == filter
                    ) {
                        model.select(time: model.time == filter ? .anytime : filter)
                    }
                }
                if model.time == .pickADate {
                    DatePicker("", selection: $model.pickedDate, displayedComponents: .date)
                        .labelsHidden()
                        .datePickerStyle(.field)
                        .font(InkType.statusLabel.font)
                        .accessibilityLabel("Pick a date")
                }
                Spacer(minLength: 0)
            }
        }
    }

    private var websiteSection: some View {
        SearchSection(title: "Filter by website") {
            if model.websites.isEmpty {
                SearchEmptyNote(SearchCopy.noWebsites)
            } else {
                // Horizontally scrolling rather than wrapping: the row is one line in the reference,
                // and a wrapping row of chips changes the panel's height every time the query does.
                ScrollView(.horizontal) {
                    HStack(spacing: SearchLayout.chipSpacing) {
                        ForEach(model.websites, id: \.self) { host in
                            SearchChip(
                                leading: { SearchFavicon(host: host, size: 14) },
                                title: SearchSource.truncated(host),
                                fullTitle: host,
                                isSelected: model.website == host
                            ) {
                                model.select(website: model.website == host ? nil : host)
                            }
                        }
                    }
                    .padding(.vertical, 1)
                }
                .scrollIndicators(.never)
            }
        }
    }

    private var appSection: some View {
        SearchSection(title: "Filter by app") {
            if model.apps.isEmpty {
                SearchEmptyNote(SearchCopy.noApps)
            } else {
                ScrollView(.horizontal) {
                    HStack(alignment: .top, spacing: InkLayout.rhythm[6]) {
                        ForEach(model.apps) { app in
                            SearchAppTile(app: app, isSelected: model.app == app.name) {
                                model.select(app: model.app == app.name ? nil : app.name)
                            }
                        }
                    }
                    .padding(.vertical, 1)
                }
                .scrollIndicators(.never)
            }
        }
    }

    /// **The `RESULTS` header is only drawn when something is above it to be separated from.**
    ///
    /// With the filter block open it is one of four section headers and it is doing that job. With
    /// the block closed the grid is the only thing in the panel, directly under a header that
    /// already says how many results there are — so a second, smaller, all-caps label repeating the
    /// word is a rung of chrome between the user and the first row of pictures, and this panel's
    /// ceiling is measured in fractions of a card.
    @ViewBuilder
    private var resultsSection: some View {
        if model.isShowingFilters {
            SearchSection(title: "Results") { results }
        } else {
            results.frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    @ViewBuilder
    private var results: some View {
        if model.moments.isEmpty {
            // Which sentence depends on whether anything was asked. "Nothing captured matches
            // that yet" over an untouched search bar is a verdict on a search that never ran.
            SearchEmptyNote(SearchCopy.results(intent: model.intent))
        } else {
            LazyVGrid(columns: SearchResultsView.columns, alignment: .leading, spacing: InkLayout.rhythm[3]) {
                ForEach(model.moments) { moment in
                    SearchResultCard(
                        moment: moment,
                        loader: model.loader,
                        isSelected: model.selection == moment.id
                    ) {
                        onOpen(moment)
                    }
                    // The anchor `scrollTo` travels to. The same id the selection is stored by,
                    // so the two cannot drift: a card the keyboard can select is a card the
                    // panel can scroll to, by construction.
                    .id(moment.id)
                }
            }
        }
    }

}

// MARK: - The bottom edge

/// The mask that turns a clipped body into a body with more below it.
///
/// A mask and not an overlay, because the panel is glass: there is no opaque colour to fade a
/// gradient *to*, and painting one would put a grey band across the frosting. Fading the content's
/// own alpha lets the sliced row dissolve into the same glass the panel is made of, which is what
/// says "this continues" rather than "this was cut".
///
/// `fade` of zero is the identity mask and is drawn deliberately rather than by leaving the modifier
/// off: a conditional modifier would change the scroll view's identity every time a query grew past
/// one screenful, which throws away the scroll position mid-scroll.
struct SearchScrollFade: View {
    /// How many points at the bottom edge dissolve. Zero when the body contains everything — a fade
    /// over a panel that cannot scroll is a promise of content that is not there.
    let fade: CGFloat

    var body: some View {
        GeometryReader { proxy in
            let height = max(proxy.size.height, 1)
            // Where the fade begins, as a fraction of the body. Clamped so a body shorter than the
            // fade cannot invert the gradient.
            let start = min(max((height - fade) / height, 0), 1)
            LinearGradient(
                stops: [
                    .init(color: .black, location: 0),
                    .init(color: .black, location: start),
                    .init(color: fade > 0 ? .clear : .black, location: 1),
                ],
                startPoint: .top,
                endPoint: .bottom)
        }
    }
}

// MARK: - Section

/// A small uppercase, letter-spaced, low-emphasis header over its content.
///
/// Uppercase with tracking is the one place this app adds letter-spacing to reading type, and it is
/// legitimate here for the reason it is legitimate in every native inspector: at 11 pt an all-caps
/// run closes up and stops being scannable without it. The size sits at `InkType.minimumSize`.
///
/// The colour is `Ink.secondary`, not the glance-word rung it reads like: this panel is glass, and
/// glass carries a two-rung ladder (`Ink.tertiary`). The header is still the quietest thing on the
/// card — it is small, tracked and uppercase, which is most of what made it recede — but at 12 pt on
/// a ground that now shows a third of the desktop, a fainter rung is a header that is simply gone
/// over a dark wallpaper.
private struct SearchSection<Content: View>: View {
    let title: String
    @ViewBuilder var content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: InkLayout.rhythm[6]) {
            Text(title.uppercased())
                .font(.system(size: InkType.minimumSize, weight: .semibold))
                .tracking(0.7)
                .foregroundStyle(Ink.secondary)
            content
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

/// What a section says when it is empty. One sentence, in the step that carries sentences.
private struct SearchEmptyNote: View {
    let text: String

    init(_ text: String) { self.text = text }

    var body: some View {
        Text(text)
            .inkStyle(.statusLabel, color: Ink.secondary)
            .frame(height: SearchLayout.chipHeight, alignment: .leading)
    }
}

// MARK: - Chips

/// One filter pill: a glyph, a word, a very light fill and a very subtle edge.
struct SearchChip<Leading: View>: View {
    let leading: Leading
    let title: String
    /// The untruncated text, for the accessibility label and the tooltip — a chip reading
    /// `shop.flix…` has to still be answerable.
    let fullTitle: String
    let isSelected: Bool
    let action: () -> Void

    @State private var isHovering = false

    init(
        @ViewBuilder leading: () -> Leading,
        title: String,
        fullTitle: String? = nil,
        isSelected: Bool,
        action: @escaping () -> Void
    ) {
        self.leading = leading()
        self.title = title
        self.fullTitle = fullTitle ?? title
        self.isSelected = isSelected
        self.action = action
    }

    private var fill: Color {
        if isSelected { return SearchInk.chipFillSelected }
        return isHovering ? SearchInk.chipFillHover : SearchInk.chipFill
    }

    var body: some View {
        Button(action: action) {
            HStack(spacing: 5) {
                leading
                Text(title)
                    .inkStyle(.statusLabel, color: isSelected ? Ink.primary : Ink.secondary)
                    .lineLimit(1)
                    .fixedSize()
            }
            .padding(.horizontal, 10)
            .frame(height: SearchLayout.chipHeight)
            .background(
                Capsule(style: .continuous).fill(fill)
                    .overlay(Capsule(style: .continuous).strokeBorder(SearchInk.chipStroke, lineWidth: 1)))
            .contentShape(Capsule(style: .continuous))
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
        .animation(InkReduceMotion.animation(.easeOut(duration: InkMotion.press)), value: isHovering)
        .help(fullTitle)
        .accessibilityLabel(Text(fullTitle))
        .accessibilityAddTraits(isSelected ? [.isSelected] : [])
    }
}

extension SearchChip where Leading == Image {
    /// The SF Symbol form, for the time chips.
    init(systemImage: String, title: String, isSelected: Bool, action: @escaping () -> Void) {
        self.init(
            leading: { Image(systemName: systemImage) },
            title: title, fullTitle: title, isSelected: isSelected, action: action)
    }
}

/// A site's mark, as a monogram disc.
///
/// There is no favicon store on this machine and inventing a network fetch for one would put the
/// search surface on the internet, which is the one thing this app promises it is not. A letter in a
/// colour derived from the host is the same honest fallback `RewindAppIcon` already makes for an app
/// it cannot find — recognisable at 14 pt, and never a confident picture of the wrong site.
struct SearchFavicon: View {
    let host: String
    var size: CGFloat = 14

    var body: some View {
        Circle()
            .fill(RewindPalette.color(forApp: host))
            .frame(width: size, height: size)
            .overlay(
                Text(monogram)
                    .font(.system(size: size * 0.62, weight: .semibold, design: .rounded))
                    // Fixed white on a mid-brightness chip in both appearances: the disc is not a
                    // semantic surface, so an inverting label would vanish into it in one of them.
                    .foregroundStyle(.white))
            .accessibilityHidden(true)
    }

    private var monogram: String {
        guard let first = host.first(where: { $0.isLetter || $0.isNumber }) else { return "?" }
        return String(first).uppercased()
    }
}

// MARK: - App tile

/// The app filter is icons, not pills — a large rounded app icon with its name under it.
///
/// Different in kind from the other two sections on purpose, and the reference is right about why: a
/// person recognises an app by its icon faster than they read its name, and at 52 pt the icon is the
/// control. The name under it is the caption, truncated to one line.
struct SearchAppTile: View {
    let app: SearchAppFacet
    let isSelected: Bool
    let action: () -> Void

    @State private var isHovering = false

    var body: some View {
        Button(action: action) {
            VStack(spacing: 6) {
                RewindAppIcon(appName: app.name, bundleId: app.bundleId, size: SearchLayout.appTileIcon)
                    .padding(5)
                    .background(
                        RoundedRectangle(cornerRadius: 14, style: .continuous)
                            .fill(isSelected ? SearchInk.chipFillSelected : (isHovering ? SearchInk.chipFillHover : Color.clear)))
                Text(app.name)
                    .inkStyle(.statusLabel, color: isSelected ? Ink.primary : Ink.secondary)
                    .lineLimit(1)
                    .truncationMode(.tail)
                    .frame(width: SearchLayout.appTileWidth)
                    .multilineTextAlignment(.center)
            }
            .frame(width: SearchLayout.appTileWidth)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
        .animation(InkReduceMotion.animation(.easeOut(duration: InkMotion.press)), value: isHovering)
        .help(app.name)
        .accessibilityLabel(Text(app.name))
        .accessibilityAddTraits(isSelected ? [.isSelected] : [])
    }
}

// MARK: - Result card

/// One thing the search found — a moment on screen, or a moment in a conversation.
///
/// **One shape, two contents.** Both kinds are the same size and carry the same three parts (a well,
/// a title, a source line), so a grid row is never ragged and `SearchLayout.cardHeight` keeps
/// describing every card in it. What differs is what is *in* the well and which glyph sits on the
/// source line, and that is enough: a photograph and a run of type are not mistakable for each other
/// at a glance, which is why this needs no badge, no legend and no second section.
///
/// **And it is a control.** A search result you cannot open is half a feature: the whole reason to
/// find the moment somebody was looking at is to go and look at it. Pressing a card opens the
/// timeline at that instant — `RewindWindow.present(store:at:)` — for both kinds, because both carry
/// the one thing that operation needs, an instant. The same vocabulary as the chips and the app
/// tiles beside it: a plain `Button`, a neutral wash on hover, `.help`, an accessibility label.
struct SearchResultCard: View {
    let moment: SearchMoment
    let loader: FrameLoader
    /// Whether the keyboard is on this card. Drawn as weight, never as hue — the rule
    /// `SearchInk.chipFillSelected` is written against.
    var isSelected: Bool = false
    /// Open this moment. Defaulted to nothing so the card can be rendered somewhere with no window
    /// behind it (previews, the render harness, a layout test) without a second code path.
    var onOpen: () -> Void = {}

    @State private var isHovering = false

    var body: some View {
        Button(action: onOpen) {
            content
        }
        .buttonStyle(SearchResultCardStyle(isHovering: isHovering, isSelected: isSelected))
        .onHover { isHovering = $0 }
        .animation(InkReduceMotion.animation(.easeOut(duration: InkMotion.press)), value: isHovering)
        // The matched text, whole, for the two readers a 230 pt card cannot serve: somebody hovering
        // to check *why* this frame came back, and somebody who cannot see the picture at all.
        .help(moment.snippet ?? moment.title)
        .accessibilityLabel(Text(readAloud))
        // What pressing it does, said once. The label is already a sentence about *when* and *where*;
        // the hint is the only place the card can say that it is a door.
        .accessibilityHint(Text(Self.activationHint))
        .accessibilityAddTraits(isSelected ? [.isSelected] : [])
    }

    /// What VoiceOver says the card does. "Timeline" is the word the menu bar already opens it by
    /// ("Open Timeline"), so the hint names a thing the user has a way of having heard of — "Rewind"
    /// is this directory's name, not the product's.
    static let activationHint = "Opens the timeline at this moment"

    private var content: some View {
        VStack(alignment: .leading, spacing: 7) {
            well
            Text(moment.title)
                // One line, always. `.tail` and not the default middle truncation: the front of a
                // window title is the part that says what it is.
                .inkStyle(.rowCopy, color: Ink.primary)
                .lineLimit(1)
                .truncationMode(.tail)
            HStack(spacing: 5) {
                sourceGlyph
                Text(moment.source)
                    .inkStyle(.statusLabel, color: Ink.secondary)
                    .lineLimit(1)
                    .truncationMode(.tail)
                    .layoutPriority(1)
                Text("•").inkStyle(.statusLabel, color: Ink.secondary)
                Text(SearchTime.describe(moment.capturedAt))
                    .inkStyle(.statusLabel, color: Ink.secondary)
                    .lineLimit(1)
                    .fixedSize()
            }
        }
        .frame(width: SearchLayout.cardWidth(), alignment: .leading)
    }

    /// The picture, or the words.
    @ViewBuilder
    private var well: some View {
        switch moment.kind {
        case .screen:
            SearchThumbnail(frame: moment.frame, loader: loader, fallbackText: moment.snippet)
        case .conversation:
            SearchSpokenWell(line: moment.snippet ?? "")
        }
    }

    /// What owned the window, or that this was speech at all.
    @ViewBuilder
    private var sourceGlyph: some View {
        switch moment.kind {
        case .screen:
            RewindAppIcon(appName: moment.appName, bundleId: moment.bundleId, size: 12)
        case .conversation:
            // A waveform rather than an app icon: there is no app to name, and `RewindAppIcon` given
            // an empty name would draw its monogram fallback — a coloured disc with a "?" in it,
            // which is a confident picture of nothing.
            Image(systemName: "waveform")
                .font(.system(size: 11, weight: .semibold))
                .foregroundStyle(Ink.secondary)
                .frame(width: 12, height: 12)
                .accessibilityHidden(true)
        }
    }

    /// The card read aloud. The snippet is included for a conversation because the words *are* the
    /// card, and left out for a screen because the title and source already name it — a whole page of
    /// OCR read out after every card would make the grid unusable with VoiceOver.
    private var readAloud: String {
        let when = SearchTime.describe(moment.capturedAt)
        switch moment.kind {
        case .screen:
            return "\(moment.title), \(moment.source), \(when)"
        case .conversation:
            return "\(moment.title): \(moment.snippet ?? ""), \(moment.source), \(when)"
        }
    }
}

/// How a result card answers the pointer: a wash behind it on hover, a stronger one with an edge
/// when the keyboard is on it, and a dip in opacity while it is held.
///
/// **The affordance is drawn outside the card's own bounds, and that is deliberate.** A card is a
/// picture, a title and a source line with no padding of its own — insetting them to make room for a
/// highlight would change `SearchLayout.cardHeight`, which the panel's ceiling, its scroll fade and
/// three tests are all stated in terms of. A `background` is layout-neutral, and the negative padding
/// lets the wash spread into the gutter the grid already leaves between cards. So the card gains a
/// hit state without the grid moving by a point.
///
/// Weight and never hue, exactly as `SearchInk.chipFillSelected` says: this surface spends its one
/// colour on the query chip, and a second meaning-bearing hue is one more thing to learn (and one
/// more chance to be off-brand — INV-UI-1).
private struct SearchResultCardStyle: ButtonStyle {
    let isHovering: Bool
    let isSelected: Bool

    /// A shade larger than the card's own corner, because the wash sits outside it: two concentric
    /// rounded rectangles with the *same* radius read as a rendering seam rather than as one object.
    private static let cornerRadius = SearchLayout.cardCornerRadius + 4
    /// How far the wash spreads past the card. Half the grid's gutter, so two selected neighbours
    /// could never touch.
    private static let outset: CGFloat = SearchLayout.cardGutter / 2

    func makeBody(configuration: Configuration) -> some View {
        let shape = RoundedRectangle(cornerRadius: Self.cornerRadius, style: .continuous)
        let fill: Color = {
            if isSelected { return SearchInk.chipFillSelected }
            return isHovering || configuration.isPressed ? SearchInk.chipFillHover : .clear
        }()
        return
            configuration.label
            // Pressed drops opacity rather than scaling: a card is a picture of something real, and
            // a photograph that shrinks under the finger reads as a toy. The same reasoning
            // `InkButtonStyle` gives for its pills.
            .opacity(configuration.isPressed ? 0.72 : 1)
            .background(
                shape
                    .fill(fill)
                    .overlay(
                        shape.strokeBorder(isSelected ? Ink.hairline : Color.clear, lineWidth: 1)
                    )
                    .padding(-Self.outset)
            )
            // The whole card is the target, including the air between the picture and the caption —
            // a control with holes in it is a control that ignores half its clicks.
            .contentShape(Rectangle())
            .animation(
                InkReduceMotion.animation(.easeOut(duration: InkMotion.press)),
                value: configuration.isPressed)
    }
}

/// A spoken line, where a screen card has its picture.
///
/// The words are set at reading size and given the whole well, because they are the answer rather
/// than a caption on one: a conversation result whose line was truncated to the same single line the
/// title gets would be a card that proves a match without showing it. Four lines is what fits the
/// 4:3 well at this size, and the tail is cut rather than the middle — a sentence's opening is what
/// says whether it is the one you meant.
///
/// Mirrors `SearchThumbnail`'s construction exactly (fill, aspect ratio, overlay, clip, edge) so both
/// kinds of well are the same object at the same size, and neither can drift into being taller than
/// the other.
struct SearchSpokenWell: View {
    let line: String

    private var shape: RoundedRectangle {
        RoundedRectangle(cornerRadius: SearchLayout.cardCornerRadius, style: .continuous)
    }

    var body: some View {
        shape
            .fill(SearchInk.spokenWell)
            .aspectRatio(SearchLayout.thumbnailAspect, contentMode: .fit)
            .overlay(alignment: .topLeading) {
                VStack(alignment: .leading, spacing: 5) {
                    Image(systemName: "quote.opening")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(Ink.secondary)
                    Text(line)
                        .inkStyle(.statusLabel, color: Ink.primary)
                        .lineLimit(4)
                        .truncationMode(.tail)
                        .multilineTextAlignment(.leading)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(10)
                .frame(maxWidth: .infinity, alignment: .topLeading)
            }
            .clipShape(shape)
            .overlay(shape.strokeBorder(Ink.hairline.opacity(0.5), lineWidth: 1))
            .accessibilityHidden(true)
    }
}

/// The card's picture, through the app's one decoder.
///
/// `FrameLoader` and nothing else: it decodes off the main thread, charges the cache real bytes, and
/// remembers a file it could not read so a pruned frame costs one attempt rather than one per
/// redraw. A second loading path here would be a second cache and a second set of those bugs.
struct SearchThumbnail: View {
    let frame: RewindFrame?
    let loader: FrameLoader
    /// What the frame said, for the state where there is no picture to show it.
    ///
    /// Not a decoration on the normal path: it is only ever drawn when the picture is genuinely gone,
    /// which is a real and common state — retention unlinks files after 30 days, and 8.7% of captured
    /// rows never had an image at all. A card in that state used to be a grey well with a photo glyph
    /// in it, which says "this failed"; the words the frame actually matched on say "this is what was
    /// there", which is both true and the reason the card is in the results.
    var fallbackText: String? = nil

    @State private var image: NSImage?

    private var shape: RoundedRectangle {
        RoundedRectangle(cornerRadius: SearchLayout.cardCornerRadius, style: .continuous)
    }

    var body: some View {
        shape
            .fill(SearchInk.thumbnailPlaceholder)
            .aspectRatio(SearchLayout.thumbnailAspect, contentMode: .fit)
            .overlay {
                if let image {
                    Image(nsImage: image)
                        .resizable()
                        // Fill and clip: a screenshot letterboxed inside a 4:3 well leaves two grey
                        // bars, and a grid of those reads as broken images.
                        .aspectRatio(contentMode: .fill)
                        .clipped()
                } else if let fallbackText, !fallbackText.isEmpty {
                    // The no-picture state, when the frame still knows what was on it. The text is
                    // the honest substitute for the picture — same well, same size, nothing invented.
                    Text(fallbackText)
                        .inkStyle(.statusLabel, color: Ink.secondary)
                        .lineLimit(4)
                        .truncationMode(.tail)
                        .multilineTextAlignment(.leading)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(10)
                        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                } else {
                    // …and the no-picture, no-text state, which is still a real one: a frame the
                    // dedupe gate stored for its app/title transition alone. A neutral well with a
                    // quiet glyph is honest; nothing here is ever a broken-image icon.
                    Image(systemName: "photo")
                        .font(.system(size: 18, weight: .light))
                        .foregroundStyle(Ink.secondary)
                }
            }
            .clipShape(shape)
            .overlay(shape.strokeBorder(Ink.hairline.opacity(0.5), lineWidth: 1))
            .task(id: frame?.id) {
                guard let frame else {
                    image = nil
                    return
                }
                if let cached = loader.cached(frame) {
                    image = cached
                    return
                }
                loader.load(frame) { decoded in
                    // The card may have been recycled onto another moment while the decode ran.
                    guard self.frame?.id == frame.id else { return }
                    image = decoded
                }
            }
            .accessibilityHidden(true)
    }
}
