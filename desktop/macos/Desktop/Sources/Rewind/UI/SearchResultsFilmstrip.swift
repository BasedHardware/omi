//
//  SearchResultsFilmstrip.swift — the second of the search surface's two panels: what you can filter
//  by, and what was found.
//
//  Structure, top to bottom: a `Filter` row with the result count opposite it, a full-width hairline
//  under it, then a section with a small uppercase header — the apps this answer came from — and
//  finally the results themselves as a three-across grid of cards.
//
//  Two things in here are load-bearing and easy to lose in a refactor:
//
//  - **The panel is as tall as what is in it, between two bounds.** A fixed height is a slab of empty
//    glass with two results and a row of cards sliced through the middle with a hundred. It measures
//    its own content and clamps it (`RewindSearchLayout.resultsBodyHeight`).
//  - **Long text truncates, it never wraps.** A card title is one line. A grid whose cells are
//    different heights because one window had a long title is the thing that makes a surface look
//    unconsidered.
//
//  (The file is still called `SearchResultsFilmstrip` because the e2e flow's `covers:` list and the
//  glass tripwire tests name it; the horizontal filmstrip it used to hold is gone.)
//

import OmiTheme
import SwiftUI

// MARK: - The panel

/// Everything found, and the one control that narrows it.
struct RewindSearchResultsPanel: View {
  let groups: [SearchResultGroup]
  let query: String
  /// The total number of screenshots behind those groups, for the count the header reports.
  let totalScreenshots: Int
  @Binding var selectedIndex: Int
  /// The room the page has left for the body. See `RewindSearchLayout.resultsBodyHeight` — inside a
  /// tab this, and not the reference's ceiling, is usually what bounds the panel.
  var availableBodyHeight: CGFloat = .infinity
  var onOpen: (Int) -> Void = { _ in }

  /// Whether the filter block is open. Closed by default: **the results are what the panel is for**,
  /// and with the block open on a short panel the user sees three cards out of a hundred.
  @State private var isShowingFilters = false
  /// The app the grid is narrowed to, or nil for all of them. Held here rather than in the page's
  /// view model because it narrows what this panel *displays* and nothing else — no query is re-run.
  @State private var selectedApp: String?
  /// The natural height of everything under the divider, measured rather than assumed.
  @State private var contentHeight: CGFloat = 0

  private var bodyHeight: CGFloat {
    RewindSearchLayout.resultsBodyHeight(
      contentHeight: contentHeight, available: availableBodyHeight)
  }
  private var scrolls: Bool {
    RewindSearchLayout.bodyScrolls(contentHeight: contentHeight, available: availableBodyHeight)
  }
  private var fade: CGFloat {
    RewindSearchLayout.scrollFade(contentHeight: contentHeight, available: availableBodyHeight)
  }

  /// The apps this answer came from, most frequent first, so the tiles a user reaches for are the
  /// ones they are most likely to want.
  private var apps: [String] {
    var order: [String] = []
    var counts: [String: Int] = [:]
    for group in groups {
      if counts[group.appName] == nil { order.append(group.appName) }
      counts[group.appName, default: 0] += 1
    }
    return order.sorted { (counts[$0] ?? 0, $1) > (counts[$1] ?? 0, $0) }
  }

  /// What the grid actually draws.
  private var visibleGroups: [SearchResultGroup] {
    guard let selectedApp else { return groups }
    return groups.filter { $0.appName == selectedApp }
  }

  var body: some View {
    VStack(alignment: .leading, spacing: 0) {
      header
      Rectangle()
        .fill(Ink.separator)
        .frame(height: 1)
        .padding(.horizontal, RewindSearchLayout.panelPaddingHorizontal)

      // The reader is here for one job: a selection moved by the keyboard has to be *visible*. A page
      // of sixty cards is several panels tall, so ↓ pressed enough times would otherwise move a
      // highlight the user cannot see.
      ScrollViewReader { proxy in
        ScrollView(.vertical) {
          content
            .background(
              GeometryReader { proxy in
                Color.clear.preference(
                  key: RewindSearchPanelHeightKey.self, value: proxy.size.height)
              }
            )
            // Spare room under the last row, only when the body scrolls, so a reader who has scrolled
            // all the way down has the fade falling on empty glass rather than on a card's source
            // line. Applied *outside* the height reader on purpose: the measurement stays the
            // content's own natural height, so this inset cannot feed back into the clamp that
            // decided to add it.
            .padding(.bottom, fade)
        }
        // The platform affordance, restored the moment there is anything to scroll to.
        .scrollIndicators(scrolls ? .automatic : .never)
        .frame(height: bodyHeight)
        // …and the part that works at rest: overlay scrollers are invisible until something moves, so
        // the first impression of an overflowing panel is carried entirely by the bottom edge.
        .mask(RewindSearchScrollFade(fade: fade))
        .onChange(of: selectedIndex) { _, index in
          // Centred, not `.top`: the card the keyboard is on should have the cards either side of it
          // in view, because "the next best answer" is only meaningful next to the ones it beat.
          OmiMotion.withGated(.easeOut(duration: InkMotion.settle)) {
            proxy.scrollTo(index, anchor: .center)
          }
        }
      }
    }
    .frame(width: RewindSearchLayout.panelWidth, alignment: .top)
    .onPreferenceChange(RewindSearchPanelHeightKey.self) { contentHeight = $0 }
  }

  // MARK: Header

  /// The `Filter` row — and, since the block below it closes, **the control that opens it**.
  ///
  /// The row was already a glyph and the word `Filter` over the block it describes; making it the
  /// disclosure adds a chevron and a hit target and invents nothing.
  private var header: some View {
    HStack(spacing: 8) {
      Button {
        isShowingFilters.toggle()
      } label: {
        HStack(spacing: 8) {
          Image(systemName: "line.3.horizontal.decrease")
            .font(.system(size: 12, weight: .semibold))
            .foregroundStyle(Ink.secondary)
          Text("Filter").inkStyle(.rowCopy, color: Ink.primary)
          // What the closed block is doing to the answer — without it a narrowed count has no
          // visible cause.
          if let selectedApp, !isShowingFilters {
            Text(selectedApp)
              .inkStyle(.statusLabel, color: Ink.secondary)
              .lineLimit(1)
              .truncationMode(.tail)
          }
          // Down when open, right when closed — the direction the block will move, which is the one
          // thing a chevron is read for.
          Image(systemName: "chevron.down")
            .font(.system(size: 9, weight: .semibold))
            .foregroundStyle(Ink.secondary)
            .rotationEffect(.degrees(isShowingFilters ? 0 : -90))
        }
        .contentShape(Rectangle())
      }
      .buttonStyle(.plain)
      .accessibilityLabel(Text(Self.filterDisclosureLabel(app: selectedApp)))
      .accessibilityAddTraits(isShowingFilters ? [.isSelected] : [])

      Spacer(minLength: 12)

      if let count = Self.countLabel(groups: visibleGroups.count, screenshots: totalScreenshots) {
        Text(count)
          .inkStyle(.statusLabel, color: Ink.secondary)
          .fixedSize()
      }
    }
    .padding(.horizontal, RewindSearchLayout.panelPaddingHorizontal)
    .frame(height: RewindSearchLayout.panelHeaderHeight)
    .omiAnimation(.easeOut(duration: InkMotion.press), value: isShowingFilters)
  }

  /// What the disclosure is called to VoiceOver. The chevron says "open me" to the eye and nothing at
  /// all to a reader, so the label carries both the action and the narrowing the closed block holds.
  static func filterDisclosureLabel(app: String?) -> String {
    guard let app else { return "Filter" }
    return "Filter — \(app)"
  }

  /// The verdict, phrased. `nil` when nothing has been asked: "No results" over an untouched surface
  /// answers a search nobody ran.
  static func countLabel(groups: Int, screenshots: Int) -> String? {
    guard screenshots > 0 || groups > 0 else { return nil }
    if groups == 0 { return "No results" }
    if groups == 1 { return "1 result" }
    return "\(groups) results"
  }

  // MARK: Sections

  private var content: some View {
    VStack(alignment: .leading, spacing: InkLayout.rhythm[3]) {
      if isShowingFilters {
        RewindSearchSection(title: "Filter by app") {
          if apps.isEmpty {
            RewindSearchEmptyNote("Nothing captured yet.")
          } else {
            ScrollView(.horizontal) {
              HStack(alignment: .top, spacing: InkLayout.rhythm[6]) {
                ForEach(apps, id: \.self) { app in
                  RewindSearchAppTile(app: app, isSelected: selectedApp == app) {
                    selectedApp = selectedApp == app ? nil : app
                  }
                }
              }
              .padding(.vertical, 1)
            }
            .scrollIndicators(.never)
          }
        }
      }
      results
    }
    .padding(.horizontal, RewindSearchLayout.panelPaddingHorizontal)
    .padding(.top, InkLayout.rhythm[3])
    .padding(.bottom, RewindSearchLayout.panelPaddingVertical)
    .frame(width: RewindSearchLayout.panelWidth, alignment: .leading)
  }

  /// **The `RESULTS` header is only drawn when something is above it to be separated from.**
  ///
  /// With the filter block open it is one of two section headers and it is doing that job. With the
  /// block closed the grid is the only thing in the panel, directly under a header that already says
  /// how many results there are — so a second, smaller, all-caps label repeating the word is a rung
  /// of chrome between the user and the first row of pictures.
  @ViewBuilder
  private var results: some View {
    if isShowingFilters {
      RewindSearchSection(title: "Results") { grid }
    } else {
      grid.frame(maxWidth: .infinity, alignment: .leading)
    }
  }

  @ViewBuilder
  private var grid: some View {
    if visibleGroups.isEmpty {
      RewindSearchEmptyNote(
        query.isEmpty ? "Nothing captured matches that yet." : "No screens match “\(query)”.")
    } else {
      LazyVGrid(columns: Self.columns, alignment: .leading, spacing: InkLayout.rhythm[3]) {
        ForEach(Array(visibleGroups.enumerated()), id: \.element.id) { index, group in
          RewindSearchResultCard(
            group: group,
            query: query,
            isSelected: selectedIndex == index
          ) {
            selectedIndex = index
            onOpen(index)
          }
          // The anchor `scrollTo` travels to, and the identity the grid reuses cells by. Stable
          // across a filter change because it is the row's own id, not its position.
          .id(index)
        }
      }
    }
  }

  /// Fixed-width columns, not adaptive: the panel is a known width, so the card width is arithmetic
  /// (`RewindSearchLayout.cardWidth`) that a test can hold. An adaptive grid would quietly become two
  /// or four across after a padding change and nothing would say so.
  static let columns: [GridItem] = Array(
    repeating: GridItem(
      .fixed(RewindSearchLayout.cardWidth()),
      spacing: RewindSearchLayout.cardGutter,
      alignment: .topLeading),
    count: RewindSearchLayout.resultColumns)
}

extension RewindSearchResultsPanel {
  /// The results as a free-standing sheet of glass — the second of the surface's two objects.
  var panel: some View {
    self
      .inkGlassPanel(cornerRadius: RewindSearchLayout.panelCornerRadius, shadow: .ambient)
      .contentShape(
        RoundedRectangle(cornerRadius: RewindSearchLayout.panelCornerRadius, style: .continuous))
  }
}

/// The results panel, sized to the room the page actually gives it.
///
/// The `GeometryReader` is here and not in the page for the reason every other number on this
/// surface is here: "how tall may the body be" is the panel's own question, and a page that had to
/// compute it would be a second opinion about `RewindSearchLayout`'s clamp. It reports the room
/// offered, and the panel subtracts its own header and margins from it.
struct RewindSearchResultsSurface: View {
  let groups: [SearchResultGroup]
  let query: String
  let totalScreenshots: Int
  @Binding var selectedIndex: Int
  var onOpen: (Int) -> Void = { _ in }

  var body: some View {
    GeometryReader { proxy in
      RewindSearchResultsPanel(
        groups: groups,
        query: query,
        totalScreenshots: totalScreenshots,
        selectedIndex: $selectedIndex,
        availableBodyHeight: max(
          0,
          proxy.size.height - RewindSearchLayout.panelHeaderHeight - RewindSearchLayout.panelGap
            - RewindSearchLayout.shadowMargin),
        onOpen: onOpen
      )
      .panel
      // The gap that makes the bar above and this panel read as two objects rather than one slab.
      .padding(.top, RewindSearchLayout.panelGap)
      .frame(maxWidth: .infinity, alignment: .top)
    }
  }
}

/// The results panel's measured height, on its way up to whatever sizes it.
///
/// A preference and not a constant because the panel is content-sized: an empty answer and a page of
/// cards are 400 pt apart, and a panel sized for one of them is wrong for the other in a way the user
/// sees immediately.
struct RewindSearchPanelHeightKey: PreferenceKey {
  static let defaultValue: CGFloat = 0
  static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) {
    value = max(value, nextValue())
  }
}

// MARK: - The bottom edge

/// The mask that turns a clipped body into a body with more below it.
///
/// **A mask and not an overlay, because the panel is glass**: there is no opaque colour to fade a
/// gradient *to*, and painting one would put a grey band across the frosting. Fading the content's
/// own alpha lets the sliced row dissolve into the same glass the panel is made of, which is what
/// says "this continues" rather than "this was cut".
///
/// A `fade` of zero is the identity mask and is drawn deliberately rather than by leaving the
/// modifier off: a conditional modifier would change the scroll view's identity every time a query
/// grew past one screenful, which throws away the scroll position mid-scroll.
struct RewindSearchScrollFade: View {
  let fade: CGFloat

  var body: some View {
    GeometryReader { proxy in
      let height = max(proxy.size.height, 1)
      // Where the fade begins, as a fraction of the body. Clamped so a body shorter than the fade
      // cannot invert the gradient.
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
/// Uppercase with tracking is the one place this surface adds letter-spacing to reading type, and it
/// is legitimate here for the reason it is legitimate in every native inspector: at this size an
/// all-caps run closes up and stops being scannable without it. The size sits at
/// `InkType.minimumSize`, and the colour is `Ink.secondary` — the bottom rung glass carries.
struct RewindSearchSection<Content: View>: View {
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
struct RewindSearchEmptyNote: View {
  let text: String

  init(_ text: String) { self.text = text }

  var body: some View {
    Text(text)
      .inkStyle(.statusLabel, color: Ink.secondary)
      .frame(height: RewindSearchLayout.chipHeight, alignment: .leading)
  }
}

// MARK: - Chips and tiles

/// One filter pill: a glyph, a word, a very light fill and a very subtle edge.
struct RewindSearchChip<Leading: View>: View {
  let leading: Leading
  let title: String
  let isSelected: Bool
  let action: () -> Void

  @State private var isHovering = false

  init(
    @ViewBuilder leading: () -> Leading,
    title: String,
    isSelected: Bool,
    action: @escaping () -> Void
  ) {
    self.leading = leading()
    self.title = title
    self.isSelected = isSelected
    self.action = action
  }

  private var fill: Color {
    if isSelected { return RewindSearchInk.chipFillSelected }
    return isHovering ? RewindSearchInk.chipFillHover : RewindSearchInk.chipFill
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
      .frame(height: RewindSearchLayout.chipHeight)
      .background(
        Capsule(style: .continuous)
          .fill(fill)
          .overlay(
            Capsule(style: .continuous)
              .strokeBorder(RewindSearchInk.chipStroke, lineWidth: 1))
      )
      .contentShape(Capsule(style: .continuous))
    }
    .buttonStyle(.plain)
    .onHover { isHovering = $0 }
    .omiAnimation(.easeOut(duration: InkMotion.press), value: isHovering)
    .help(title)
    .accessibilityLabel(Text(title))
    .accessibilityAddTraits(isSelected ? [.isSelected] : [])
  }
}

/// The app filter is icons, not pills — a large rounded app icon with its name under it.
///
/// Different in kind from a chip on purpose, and the reference is right about why: a person
/// recognises an app by its icon faster than they read its name, so at 46 pt the icon *is* the
/// control. The name under it is the caption, truncated to one line.
struct RewindSearchAppTile: View {
  let app: String
  let isSelected: Bool
  let action: () -> Void

  @State private var isHovering = false

  var body: some View {
    Button(action: action) {
      VStack(spacing: 6) {
        AppIconView(appName: app, size: RewindSearchLayout.appTileIcon)
          .padding(5)
          .background(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
              .fill(
                isSelected
                  ? RewindSearchInk.chipFillSelected
                  : (isHovering ? RewindSearchInk.chipFillHover : Color.clear))
          )
        Text(app)
          .inkStyle(.statusLabel, color: isSelected ? Ink.primary : Ink.secondary)
          .lineLimit(1)
          .truncationMode(.tail)
          .frame(width: RewindSearchLayout.appTileWidth)
          .multilineTextAlignment(.center)
      }
      .frame(width: RewindSearchLayout.appTileWidth)
      .contentShape(Rectangle())
    }
    .buttonStyle(.plain)
    .onHover { isHovering = $0 }
    .omiAnimation(.easeOut(duration: InkMotion.press), value: isHovering)
    .help(app)
    .accessibilityLabel(Text(app))
    .accessibilityAddTraits(isSelected ? [.isSelected] : [])
  }
}

#if canImport(PreviewsMacros)
  #Preview {
    RewindSearchResultsPanel(
      groups: [],
      query: "claude",
      totalScreenshots: 0,
      selectedIndex: .constant(0)
    )
    .panel
    .padding(RewindSearchLayout.shadowMargin)
    .frame(width: RewindSearchLayout.surfaceWidth)
    .background(Ink.surface)
  }
#endif
