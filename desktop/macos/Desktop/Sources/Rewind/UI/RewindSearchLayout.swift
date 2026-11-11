//
//  RewindSearchLayout.swift — every number, colour and measurement the Rewind search surface is
//  laid out from, as values rather than literals inside a `body`.
//
//  The surface is **two objects, not one slab**. A place you type and a place you look are different
//  in kind; drawing them as one tall block with a rule across it says they are the same object. Here
//  they are two panels of the same width with real air between them (`panelGap`), each wearing the
//  app's one glass and its own ambient shadow, so the eye reads two floating things rather than one
//  container pretending not to be one.
//
//  Everything a test can hold lives here and not in a view: the gap, the column count and the card
//  width it implies, the clamp on the panel's height, whether the body scrolls and therefore how deep
//  its bottom edge dissolves. A view then has no arithmetic of its own to get wrong.
//

import AppKit
import OmiTheme
import SwiftUI

// MARK: - Metrics

/// Every number the search surface is laid out from.
///
/// Sizes that already exist elsewhere are taken from there — the corner is `InkGlass.cornerRadius`,
/// the shadow margin is the shadow's own padding — and only the values this surface genuinely
/// introduces are stated here, each with what set it.
enum RewindSearchLayout {

  /// The width of both panels. Wide enough for a three-across grid of legible cards (see
  /// `cardWidth`) and no wider: past this the query bar stops reading as a bar.
  static let panelWidth: CGFloat = 760

  /// **The gap.** The single most important number in this file.
  ///
  /// Eight points keeps the objects distinct without turning the shared search
  /// shell into a large empty band above every destination.
  static let panelGap: CGFloat = 8

  /// The corner is the shared one. Not restated as a number: a search panel and a settings card cut
  /// to two different radii read as two products, which is exactly why `InkGlass` owns it.
  static var panelCornerRadius: CGFloat { InkGlass.cornerRadius }

  /// Matches the product-wide query bar so search does not change size by page.
  static let barHeight: CGFloat = 48

  /// The results panel is **as tall as what is in it**, between these two bounds.
  ///
  /// A fixed height is wrong at both ends: with two results the panel is a slab of empty glass, and
  /// with a page of them the last row of cards is sliced through the middle at the panel's edge. The
  /// panel measures its own content and clamps it here instead.
  static let minimumResultsBodyHeight: CGFloat = 40

  /// The ceiling is **set by the cards, not by taste**: it is the filter block plus one whole card —
  /// well, title and source line — plus the panel's bottom padding. A ceiling under that is the
  /// clipped-card defect by another route, because the first row the user sees would be sliced
  /// through the middle.
  static let maximumResultsBodyHeight: CGFloat = 545

  /// What the surface opens at, before the view has measured itself. A prediction, not the truth —
  /// the measured height arrives within a frame.
  static let initialFilterPanelHeight: CGFloat = 430

  /// The results body's height for a given natural content height.
  ///
  /// The clamp, as a function, so both ends of it are a test rather than a screenshot: below the
  /// floor the panel is a sliver, above the ceiling it is taller than the Rewind tab, and inside it
  /// the panel is exactly as tall as what is in it and nothing scrolls that did not need to.
  /// `available` is the room the page actually has left for the body after its own chrome.
  ///
  /// The reference's ceiling was measured for a floating window over the desktop, where the only
  /// limit is the display. Rewind is a tab: the room is whatever is left under the app's nav and the
  /// query bar, and on a short window that is *less* than `maximumResultsBodyHeight`. A body taller
  /// than its container is the sliced-card defect arriving by the one route the clamp did not cover,
  /// so the ceiling is the smaller of the two.
  static func resultsBodyHeight(contentHeight: CGFloat, available: CGFloat = .infinity) -> CGFloat {
    let ceiling = min(maximumResultsBodyHeight, max(minimumResultsBodyHeight, available))
    return min(max(contentHeight, minimumResultsBodyHeight), ceiling)
  }

  /// **Whether the body scrolls** — the content did not fit in the height the clamp gave it.
  ///
  /// The one question the bottom edge's appearance turns on. A row of cards sliced by the panel's
  /// edge with no fade and no scroller reads as a clipped view, not as "there is more below".
  static func bodyScrolls(contentHeight: CGFloat, available: CGFloat = .infinity) -> Bool {
    // Half a point of slack: a content height that lands exactly on the ceiling fits, and
    // floating-point measurement noise must not make a settled panel flicker its fade on.
    contentHeight > resultsBodyHeight(contentHeight: contentHeight, available: available) + 0.5
  }

  /// The soft edge at the bottom of a body that has more below it, and the room the content gains
  /// underneath itself so the fade always has something spare to fall on.
  ///
  /// Sized between two failures. Under about ten points a fade is a rendering artefact rather than a
  /// signal; at more than `cardCaptionHeight` it could swallow a card's whole title-and-source block,
  /// which would make the *last* row unreadable to fix the *next* row's slice.
  static let scrollFadeHeight: CGFloat = 26

  /// **How deep the bottom edge fades for a measured content height** — the whole of the view's
  /// decision, as a value. A fade the panel forgets to turn on, and a fade it leaves on over content
  /// that fits, are both invisible in a `body` and both obvious here.
  static func scrollFade(contentHeight: CGFloat, available: CGFloat = .infinity) -> CGFloat {
    bodyScrolls(contentHeight: contentHeight, available: available) ? scrollFadeHeight : 0
  }

  /// The results panel's own header — the `Filter` row and the rule under it.
  static let panelHeaderHeight: CGFloat = 36

  static let panelPaddingHorizontal: CGFloat = 14
  static let panelPaddingVertical: CGFloat = 10

  /// Clear margin kept around the panels so the ambient shadow has room to fall off instead of being
  /// clipped at the surface's edge. Taken from the shadow itself, never guessed — a margin that stops
  /// tracking the shadow is a panel with a straight grey line down one side.
  static var shadowMargin: CGFloat { InkGlassShadow.ambient.padding }

  // The results grid.

  /// Three across, as in the reference. A count and not a `.adaptive` minimum: the panel is a fixed
  /// width, so an adaptive grid would silently become two or four across after any padding change and
  /// nothing would say so.
  static let resultColumns = 3
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
  /// A function rather than a constant so the reflow claim is testable: the grid has to keep three
  /// legible columns at the width it is actually given, and a card that goes under `minimumCardWidth`
  /// is a clipped one.
  static func cardWidth(panelWidth: CGFloat = panelWidth, columns: Int = resultColumns) -> CGFloat {
    let columns = max(1, columns)
    let gutters = cardGutter * CGFloat(columns - 1)
    return max(0, (contentWidth(panelWidth: panelWidth) - gutters) / CGFloat(columns))
  }

  /// Below this a card's title has no room to say anything before it truncates, and the thumbnail
  /// stops being recognisable as a screen.
  static let minimumCardWidth: CGFloat = 150

  /// The gap between the well and the two lines under it, and the height those two lines take.
  /// Stated rather than measured so `cardHeight` is arithmetic.
  static let cardCaptionHeight: CGFloat = 46

  /// One whole card: the picture, plus the title and source under it.
  static func cardHeight(panelWidth: CGFloat = panelWidth) -> CGFloat {
    cardWidth(panelWidth: panelWidth) / thumbnailAspect + cardCaptionHeight
  }

  // The bar's own furniture.

  /// The glyph at the leading edge.
  static let glyphSize: CGFloat = 18

  /// Room the query chip may grow into before it stops. The bar's content width, less the glyph and
  /// the space the keyboard hint needs on the other side.
  static let queryFieldWidth: CGFloat = contentWidth() - glyphSize - 12 - 190

  /// The whole surface including the clear margin the shadows fall into.
  static var surfaceWidth: CGFloat { panelWidth + shadowMargin * 2 }
}

// MARK: - Measurement

/// The one place the query's text is measured, so the chip and the text inside it cannot disagree.
enum RewindSearchMetrics {

  /// What the empty bar says it is for. It names what is actually searched rather than an app, and it
  /// is the only thing on an untouched surface that says what typing will do.
  static let placeholder = "Search what you've seen and heard…"

  /// The size the query is set at.
  ///
  /// The shared search face: prominent enough to find immediately, compact
  /// enough to remain utility chrome rather than a page title.
  static let queryFontSize: CGFloat = 17

  /// The face the query is set in, resolved to the AppKit font the field is actually made of. Both
  /// the chip's width and the field's own text use this exact value; two different faces here is a
  /// capsule a few points too narrow that looks like a rendering bug.
  static var queryFace: NSFont {
    InkFonts.role(size: queryFontSize, weight: .semiBold).metrics
  }

  /// The line box the query needs, with room above the ascenders. A field shorter than its own font
  /// clips the top of the placeholder's ascenders.
  static var queryLineHeight: CGFloat {
    (InkFonts.naturalLineHeight(queryFace) + 10).rounded()
  }

  /// Padding inside the query chip, either end.
  static let chipPaddingHorizontal: CGFloat = 12
  /// The magnifier plus the gap after it.
  static let chipGlyphWidth: CGFloat = 13 + 6

  /// A chip narrower than this is a coloured smudge rather than a chip.
  static let minimumChipWidth: CGFloat = 54

  /// How wide the tinted capsule is for a given query.
  ///
  /// A pure function of the string and the room it has, which is what makes "the chip hugs the text"
  /// and "the chip stops at the bar's edge" two things a test can hold rather than two things that
  /// looked right on the one query somebody tried.
  static func chipWidth(for query: String, available: CGFloat) -> CGFloat {
    guard !query.isEmpty else { return 0 }
    let wanted = chipPaddingHorizontal * 2 + chipGlyphWidth + textWidth(query)
    return min(max(wanted, minimumChipWidth), max(minimumChipWidth, available))
  }

  /// The rendered width of a run of text in the query face.
  static func textWidth(_ text: String, font: NSFont? = nil) -> CGFloat {
    let face = font ?? queryFace
    return NSAttributedString(string: text, attributes: [.font: face]).size().width
  }
}

// MARK: - Colour

/// The washes the search surface spends, and the reason each one is neutral.
///
/// `Ink` is the palette and this is not a second one — every value here is an alpha on `labelColor`,
/// so it darkens light glass and lightens dark glass instead of being one grey that is wrong in one
/// appearance. The rungs are the repository's own (`Ink.rowFill` / `Ink.rowFillHover` /
/// `PageGlass.chipFill(isActive:)`) rather than a private ladder, so a filter chip here and a filter
/// chip on any other page are visibly the same control.
enum RewindSearchInk {

  /// A filter chip at rest.
  static let chipFill = Ink.rowFill
  static let chipFillHover = Ink.rowFillHover
  /// The selected chip. Stronger, still neutral — **selection is weight, never hue.** A second
  /// meaning-bearing colour is one more thing to learn and one more chance to be off-brand.
  static let chipFillSelected = PageGlass.chipFill(isActive: true)
  /// "A very subtle border", per the reference. Lighter than `Ink.hairline`, which is the edge of
  /// something you press; a chip is a lighter promise than that.
  static let chipStroke = Color(nsColor: .labelColor).opacity(0.10)

  /// The neutral standing in for a well whose picture has not decoded yet, or whose file retention
  /// already removed. Never a broken-image glyph and never an empty hole.
  static let wellPlaceholder = Color(nsColor: .labelColor).opacity(0.06)

  /// The well a matched line of text is set on, where a card with a picture has its picture. A shade
  /// darker than `wellPlaceholder` so a card with words on it reads as filled rather than as a
  /// picture that failed to load.
  static let textWell = Color(nsColor: .labelColor).opacity(0.08)

  /// The query chip's fill, edge and glyph.
  ///
  /// `Ink.accent` is `systemBlue` and explicitly **not** the machine's own accent colour, which is
  /// whatever hue its owner picked and is off-brand on plenty of Macs (INV-UI-1). A chip that is one
  /// colour on some machines and another elsewhere is not a design, it is a coin flip.
  ///
  /// 0.14 is a wash rather than a fill: the chip's job is to say "this run of text is the query", and
  /// the text inside it is `Ink.primary`, which has to stay the highest-contrast thing in the bar.
  static let queryChipFill = Ink.accent.opacity(0.14)
  static let queryChipStroke = Ink.accent.opacity(0.28)
  /// Full-strength, legible as a *glyph* at 11 pt on both grounds where it would not be as text.
  static let queryChipGlyph = Ink.accent
}
