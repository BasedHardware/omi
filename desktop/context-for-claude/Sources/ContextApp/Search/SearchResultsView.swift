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
            ScrollView(.vertical) {
                SearchFilterContent(model: model)
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
        }
        .frame(width: SearchLayout.panelWidth, alignment: .top)
        .onPreferenceChange(SearchPanelHeightKey.self) { contentHeight = $0 }
    }

    // MARK: Header

    private var header: some View {
        HStack(spacing: 8) {
            Image(systemName: "line.3.horizontal.decrease")
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(Ink.secondary)
            Text("Filter").inkStyle(.rowCopy, color: Ink.primary)
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

    var body: some View {
        VStack(alignment: .leading, spacing: InkLayout.rhythm[3]) {
            timeSection
            websiteSection
            appSection
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

    @ViewBuilder
    private var resultsSection: some View {
        SearchSection(title: "Results") {
            if model.moments.isEmpty {
                // Which sentence depends on whether anything was asked. "Nothing captured matches
                // that yet" over an untouched search bar is a verdict on a search that never ran.
                SearchEmptyNote(SearchCopy.results(intent: model.intent))
            } else {
                LazyVGrid(columns: SearchResultsView.columns, alignment: .leading, spacing: InkLayout.rhythm[3]) {
                    ForEach(model.moments) { moment in
                        SearchResultCard(moment: moment, loader: model.loader)
                    }
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
/// run closes up and stops being scannable without it. The size sits at `InkType.minimumSize` and the
/// colour is `Ink.tertiary`, which is what a header a reader *skips* should cost them.
private struct SearchSection<Content: View>: View {
    let title: String
    @ViewBuilder var content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: InkLayout.rhythm[6]) {
            Text(title.uppercased())
                .font(.system(size: InkType.minimumSize, weight: .semibold))
                .tracking(0.7)
                .foregroundStyle(Ink.tertiary)
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

/// One captured moment: a picture of the screen, its title, and where it came from.
struct SearchResultCard: View {
    let moment: SearchMoment
    let loader: FrameLoader

    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            SearchThumbnail(frame: moment.frame, loader: loader)
            Text(moment.title)
                // One line, always. `.tail` and not the default middle truncation: the front of a
                // window title is the part that says what it is.
                .inkStyle(.rowCopy, color: Ink.primary)
                .lineLimit(1)
                .truncationMode(.tail)
            HStack(spacing: 5) {
                RewindAppIcon(appName: moment.appName, bundleId: moment.bundleId, size: 12)
                Text(moment.source)
                    .inkStyle(.statusLabel, color: Ink.tertiary)
                    .lineLimit(1)
                    .truncationMode(.tail)
                    .layoutPriority(1)
                Text("•").inkStyle(.statusLabel, color: Ink.tertiary)
                Text(SearchTime.describe(moment.capturedAt))
                    .inkStyle(.statusLabel, color: Ink.tertiary)
                    .lineLimit(1)
                    .fixedSize()
            }
        }
        .frame(width: SearchLayout.cardWidth(), alignment: .leading)
        .accessibilityElement(children: .combine)
        .accessibilityLabel(
            Text("\(moment.title), \(moment.source), \(SearchTime.describe(moment.capturedAt))"))
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
                } else {
                    // The no-picture state, and it is a real state: retention unlinks files, and some
                    // captures never had an image. A neutral well with a quiet glyph is honest;
                    // nothing here is ever a broken-image icon.
                    Image(systemName: "photo")
                        .font(.system(size: 18, weight: .light))
                        .foregroundStyle(Ink.tertiary)
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
