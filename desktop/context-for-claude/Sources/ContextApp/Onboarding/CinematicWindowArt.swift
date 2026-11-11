import SwiftUI

//  The synthetic windows beat 5 flies in.
//
//  Beat 5 used to render the user's **own** captured frames and fall back to a grey skeleton when
//  the store was empty. The store is empty for everyone who ever sees this: the cinematic is gated
//  on `context.onboarded`, and screen capture is not granted until Phase 4 — so the fallback *was*
//  the shipping path, and it read as six loading cards that never finished. These windows replace
//  both paths. See `CinematicWindows.swift` for why there is no longer a real-frames path at all.
//
//  The motif is the one from the product page (`archit-lal.github.io/Periphery/context.html`),
//  redrawn natively: a 10 pt-radius card, a chrome strip of three neutral dots and a tab pill, a
//  hairline edge, a soft ground shadow, a resting tilt of a degree or two, and a slow independent
//  float. The page's own dark variant is the one translated here — its light windows are drawn for
//  paper, and six white rectangles on this near-black scrim would be a lightbox.
//
//  **Nothing here can draw text.** `CinematicWindowLayout` and every element it carries are numbers:
//  widths, heights, counts, tones. There is no case with a `String` payload and no `Text` in any
//  view in this file, so a window cannot name an app, a person, or a message. That is a property of
//  the types rather than a rule someone has to remember — which matters, because this is the
//  onboarding of a product whose whole claim is that it does not invent your context. A plausible
//  fake name in the first eight seconds would be the most expensive lie the app could tell.

// MARK: - Ink

/// The interior ladder of a synthetic window.
///
/// The shell keeps `CinematicPalette` (`cardFill`, `hairline`) so a window sits on the same ladder
/// as the prompt shell above it. Only the *contents* need more steps than that palette carries, and
/// they are all `Ink.glow` — white — at fixed opacities over the scrim. No accent, no hue: the
/// system accent colour is purple on a default Mac (`INV-UI-1`), and the cinematic is monochrome by
/// design.
enum CinematicWindowInk {
    /// The chrome strip, lifted off the window's own fill the way the page's `.chrome` is.
    static let chrome = Ink.glow.opacity(0.06)
    /// Under the chrome strip.
    static let chromeEdge = Ink.glow.opacity(0.07)
    /// The three window dots.
    static let dot = Ink.glow.opacity(0.22)
    /// The tab pill beside them.
    static let tab = Ink.glow.opacity(0.14)
    /// A bar standing in for a line of text.
    static let line = Ink.glow.opacity(0.175)
    /// A heading, a prompt marker, the near edge of a chart.
    static let lineStrong = Ink.glow.opacity(0.31)
    /// A second line that has already been read.
    static let lineFaint = Ink.glow.opacity(0.115)
    /// The ground of an image well, a tile, an avatar.
    static let well = Ink.glow.opacity(0.105)
    /// A rule between two panes.
    static let divider = Ink.glow.opacity(0.08)
}

// MARK: - Layout

/// What one synthetic window shows.
///
/// Every case carries numbers only. Adding a `String` payload here — an app name, a title, a
/// message — is the change this type exists to make impossible without a deliberate edit to the
/// type itself, which is a change a reviewer sees.
enum CinematicWindowLayout: Hashable, Sendable {
    /// A heading and a paragraph. Widths are fractions of the body's usable width.
    case document(heading: Double, lines: [Double])
    /// An image well over a caption.
    case media(cover: Double, captions: [Double])
    /// Alternating bubbles. `+1` is trailing (outgoing), `-1` leading (incoming).
    case chat(turns: [Turn])
    /// Indented runs of monospaced-looking segments. The first segment of a row marked `marker`
    /// is brighter, the way a shell prompt is.
    case terminal(rows: [Row])
    /// Rows of an avatar disc and two lines.
    case feed(rows: Int)
    /// A tiled board.
    case gallery(columns: Int, rows: Int)
    /// Bars over a baseline. Heights are fractions of the plot's height.
    case chart(bars: [Double])
    /// A navigation rail beside a pane of lines.
    case sidebar(rail: [Double], lines: [Double])

    /// One bubble in a `chat`.
    struct Turn: Hashable, Sendable {
        /// Fraction of the body's usable width.
        var width: Double
        var height: Double
        /// `true` when the bubble hangs off the trailing edge.
        var isOutgoing: Bool
        /// Bars drawn inside the bubble. Zero for a short one.
        var lines: Int = 0
    }

    /// One line in a `terminal`.
    struct Row: Hashable, Sendable {
        /// Left indent, as a fraction of the usable width.
        var indent: Double
        /// Segment widths, as fractions, separated by a fixed gap.
        var segments: [Double]
        /// Draws the first segment at `lineStrong`.
        var marker: Bool = false
    }
}

/// One window: its layout, and the two chrome measurements that vary between windows.
struct CinematicWindowSpec: Identifiable, Hashable, Sendable {
    /// Stable across a run, and the `ForEach` identity beat 5 uses.
    let id: Int
    let layout: CinematicWindowLayout
    /// The tab pill's width, as a fraction of the chrome strip's usable width. The page caps its
    /// own at 52%; varying it is what stops six chrome strips from being one repeated strip.
    let tab: Double
    /// A trailing toolbar affordance, as the page's windows carry one. Count only — never a glyph
    /// that could stand for an app.
    let toolbarDots: Int
}

// MARK: - The deck

/// The windows beat 5 shows, in the order they land.
///
/// Fixed and ordered, with no randomness: the file this replaced already made the argument, and it
/// still holds — a cinematic that composes itself differently on each run cannot be reviewed
/// against a screenshot. The order is chosen so no two neighbours in the 3-wide grid have the same
/// visual weight.
enum CinematicWindowDeck {
    /// The archetypes, in grid order. Eight, for a grid that may one day hold more than six.
    static let archetypes: [CinematicWindowLayout] = [
        .document(heading: 0.52, lines: [0.96, 0.89, 0.94, 0.82, 0.55]),
        .media(cover: 40, captions: [0.62, 0.38]),
        .chat(turns: [
            .init(width: 0.56, height: 14, isOutgoing: true),
            .init(width: 0.80, height: 24, isOutgoing: false, lines: 3),
            .init(width: 0.44, height: 13, isOutgoing: true),
        ]),
        .terminal(rows: [
            .init(indent: 0, segments: [0.05, 0.28], marker: true),
            .init(indent: 0.04, segments: [0.44]),
            .init(indent: 0.04, segments: [0.16, 0.30]),
            .init(indent: 0, segments: [0.05, 0.36], marker: true),
            .init(indent: 0.08, segments: [0.22, 0.26]),
            .init(indent: 0.08, segments: [0.34]),
            .init(indent: 0.04, segments: [0.14, 0.20]),
        ]),
        .gallery(columns: 3, rows: 2),
        .feed(rows: 4),
        .chart(bars: [0.34, 0.58, 0.44, 0.79, 0.52, 0.95, 0.68]),
        .sidebar(rail: [0.74, 0.52, 0.86, 0.44], lines: [0.92, 0.78, 0.88, 0.60]),
    ]

    /// Tab widths and toolbar counts, walked alongside the archetypes.
    private static let tabs: [Double] = [0.50, 0.34, 0.44, 0.28, 0.52, 0.38, 0.46, 0.30]
    private static let toolbars: [Int] = [1, 0, 2, 1, 0, 2, 1, 0]

    /// `count` windows. Cycles the archetypes if asked for more than there are, so the deck is
    /// total for any grid size rather than having a size it silently mishandles.
    static func windows(count: Int) -> [CinematicWindowSpec] {
        guard count > 0 else { return [] }
        return (0..<count).map { index in
            CinematicWindowSpec(
                id: index,
                layout: archetypes[index % archetypes.count],
                tab: tabs[index % tabs.count],
                toolbarDots: toolbars[index % toolbars.count])
        }
    }
}

// MARK: - Motion

/// Where a settled window sits relative to its slot, this instant.
struct CinematicWindowDrift: Equatable, Sendable {
    var dx: CGFloat
    var dy: CGFloat
    /// Degrees, on top of the window's resting tilt.
    var rotation: Double

    static let still = CinematicWindowDrift(dx: 0, dy: 0, rotation: 0)
}

/// The slow float the page's windows have, translated to a grid that has to stay legible.
///
/// The page runs each window the whole height of the viewport on a 17–26 s loop. A card that
/// travelled like that could not also be a grid, so what is kept is the *quality*: every window on
/// its own long period, none of them in step, drifting a few points and a fraction of a degree.
/// Amplitude scales with the window's resting scale, which is what makes the near ones move more
/// than the far ones — the page's parallax, from the same source.
enum CinematicWindowMotion {
    /// Seconds per cycle. Deliberately not multiples of each other: any common factor and the
    /// whole field breathes in unison, which reads as one sheet rather than six windows.
    static let periods: [Double] = [8.3, 10.9, 7.1, 12.4, 9.2, 11.6, 13.7, 6.7]
    /// Points, at a resting scale of 1.
    static let verticalAmplitude: CGFloat = 5.5
    static let horizontalAmplitude: CGFloat = 2.2
    /// Degrees, at a resting scale of 1.
    static let rotationAmplitude: Double = 0.5

    /// Whether the field floats at all.
    ///
    /// Reduce Motion is the whole of the rule. `crossFade` is the director's own reduced timing
    /// table, and the workspace flag is read directly as well so a caller holding the standard
    /// table still honours the setting.
    static func allowsDrift(crossFade: Bool, reduceMotion: Bool) -> Bool {
        !crossFade && !reduceMotion
    }

    /// Where window `index` is at `time`, in seconds on any monotonic clock.
    ///
    /// Pure, so the composition at a given instant is a value a test can assert, and so rendering
    /// it at several phases is a loop rather than a stopwatch.
    static func drift(index: Int, at time: TimeInterval, depth: CGFloat = 1) -> CinematicWindowDrift
    {
        guard index >= 0 else { return .still }
        let period = periods[index % periods.count]
        // A quarter-turn of phase per window, so neighbours are never at the same point of their
        // own cycle even when two periods happen to be close.
        let phase = Double(index) * .pi / 2
        let vertical = sin(time / period * 2 * .pi + phase)
        // Cosine on a slower harmonic: a circle would read as orbiting, a figure-of-eight as
        // floating.
        let horizontal = cos(time / period * .pi + phase)
        return CinematicWindowDrift(
            dx: horizontalAmplitude * depth * CGFloat(horizontal),
            dy: verticalAmplitude * depth * CGFloat(vertical),
            rotation: rotationAmplitude * Double(depth) * sin(time / period * 2 * .pi + phase / 2))
    }
}

// MARK: - The window

/// One synthetic window: chrome strip, body, hairline edge, ground shadow.
struct CinematicWindowView: View {
    let spec: CinematicWindowSpec
    let size: CGSize

    static let chromeHeight: CGFloat = 20
    static let cornerRadius: CGFloat = 10
    static let bodyPadding: CGFloat = 11

    private var shape: RoundedRectangle {
        RoundedRectangle(cornerRadius: Self.cornerRadius, style: .continuous)
    }

    var body: some View {
        VStack(spacing: 0) {
            chrome
            CinematicWindowBody(
                layout: spec.layout,
                size: CGSize(width: size.width, height: size.height - Self.chromeHeight))
        }
        .frame(width: size.width, height: size.height)
        .background(CinematicPalette.cardFill)
        .clipShape(shape)
        // Brighter along the top edge than the bottom. A flat hairline reads as a sticker; the
        // gradient is what makes a dark surface read as raised, and it is the page's own
        // `box-shadow` inset translated to a ground this dark.
        .overlay(
            shape.strokeBorder(
                LinearGradient(
                    colors: [CinematicPalette.hairline, CinematicPalette.hairline.opacity(0.45)],
                    startPoint: .top,
                    endPoint: .bottom),
                lineWidth: 1)
        )
        // Flatten first. Without this the shadow is applied to every leaf inside the window and
        // the blurred silhouette of the *contents* shows straight back through a fill that is only
        // 6% opaque — measured as a dark blob floating behind the bars in the first render of this.
        .compositingGroup()
        // The page's `0 20px 44px -20px`: a soft ground shadow well below the window. On a scrim
        // this dark it is the only thing separating a card in flight from the black behind it.
        .shadow(color: .black.opacity(0.55), radius: 14, x: 0, y: 7)
        .accessibilityHidden(true)
    }

    /// Three neutral dots and a tab pill.
    ///
    /// Not red/amber/green. This is a card that reads as a window, not a forgery of macOS's own
    /// chrome — and the page's dark windows draw theirs neutral for the same reason.
    private var chrome: some View {
        HStack(spacing: 4) {
            ForEach(0..<3, id: \.self) { _ in
                Circle()
                    .fill(CinematicWindowInk.dot)
                    .frame(width: 4.5, height: 4.5)
            }
            Capsule(style: .continuous)
                .fill(CinematicWindowInk.tab)
                .frame(width: max(0, (size.width - 24) * spec.tab), height: 5)
                .padding(.leading, 3)
            Spacer(minLength: 0)
            ForEach(0..<max(0, spec.toolbarDots), id: \.self) { _ in
                RoundedRectangle(cornerRadius: 1.5, style: .continuous)
                    .fill(CinematicWindowInk.tab)
                    .frame(width: 5, height: 5)
            }
        }
        .padding(.horizontal, 8)
        .frame(height: Self.chromeHeight)
        .background(CinematicWindowInk.chrome)
        .overlay(alignment: .bottom) {
            Rectangle()
                .fill(CinematicWindowInk.chromeEdge)
                .frame(height: 1)
        }
    }
}

// MARK: - Bodies

/// The interior of a window. One `switch`, one archetype each, all of it geometry.
struct CinematicWindowBody: View {
    let layout: CinematicWindowLayout
    let size: CGSize

    /// The width a layout's fractions are measured against.
    private var usable: CGFloat {
        max(0, size.width - CinematicWindowView.bodyPadding * 2)
    }

    var body: some View {
        content
            .padding(.horizontal, CinematicWindowView.bodyPadding)
            .padding(.top, 11)
            .frame(width: size.width, height: size.height, alignment: .topLeading)
            .clipped()
    }

    @ViewBuilder
    private var content: some View {
        switch layout {
        case .document(let heading, let lines):
            document(heading: heading, lines: lines)
        case .media(let cover, let captions):
            media(cover: cover, captions: captions)
        case .chat(let turns):
            chat(turns)
        case .terminal(let rows):
            terminal(rows)
        case .feed(let rows):
            feed(rows)
        case .gallery(let columns, let rows):
            gallery(columns: columns, rows: rows)
        case .chart(let bars):
            chart(bars)
        case .sidebar(let rail, let lines):
            sidebar(rail: rail, lines: lines)
        }
    }

    // MARK: Primitives

    private func bar(_ fraction: Double, height: CGFloat, tone: Color) -> some View {
        RoundedRectangle(cornerRadius: height / 2, style: .continuous)
            .fill(tone)
            .frame(width: usable * CGFloat(min(1, max(0, fraction))), height: height)
    }

    // MARK: Archetypes

    private func document(heading: Double, lines: [Double]) -> some View {
        VStack(alignment: .leading, spacing: 7) {
            bar(heading, height: 7, tone: CinematicWindowInk.lineStrong)
                .padding(.bottom, 2)
            ForEach(lines.indices, id: \.self) { index in
                bar(
                    lines[index], height: 4,
                    tone: index == lines.count - 1
                        ? CinematicWindowInk.lineFaint : CinematicWindowInk.line)
            }
        }
    }

    private func media(cover: Double, captions: [Double]) -> some View {
        VStack(alignment: .leading, spacing: 7) {
            RoundedRectangle(cornerRadius: 5, style: .continuous)
                .fill(CinematicWindowInk.well)
                // A single soft sweep across the well. An image behind glass is never flat, and a
                // perfectly even rectangle is the one thing that says "nothing loaded".
                .overlay(
                    RoundedRectangle(cornerRadius: 5, style: .continuous)
                        .fill(
                            LinearGradient(
                                colors: [
                                    Ink.glow.opacity(0.06), Ink.glow.opacity(0.0),
                                    Ink.glow.opacity(0.035),
                                ],
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing))
                )
                .frame(width: usable, height: CGFloat(cover))
                .padding(.bottom, 2)
            ForEach(captions.indices, id: \.self) { index in
                bar(
                    captions[index], height: index == 0 ? 5 : 4,
                    tone: index == 0 ? CinematicWindowInk.lineStrong : CinematicWindowInk.lineFaint)
            }
        }
    }

    private func chat(_ turns: [CinematicWindowLayout.Turn]) -> some View {
        VStack(spacing: 8) {
            ForEach(turns.indices, id: \.self) { index in
                let turn = turns[index]
                bubble(turn)
                    .frame(
                        maxWidth: .infinity,
                        alignment: turn.isOutgoing ? .trailing : .leading)
            }
        }
    }

    private func bubble(_ turn: CinematicWindowLayout.Turn) -> some View {
        // The page's own bubble radius — one corner squared off on the side the bubble hangs from.
        UnevenRoundedRectangle(
            topLeadingRadius: 7,
            bottomLeadingRadius: turn.isOutgoing ? 7 : 2,
            bottomTrailingRadius: turn.isOutgoing ? 2 : 7,
            topTrailingRadius: 7,
            style: .continuous
        )
        .fill(turn.isOutgoing ? CinematicWindowInk.well : Ink.glow.opacity(0.065))
        .frame(width: usable * CGFloat(turn.width), height: CGFloat(turn.height))
        .overlay(alignment: .topLeading) {
            if turn.lines > 0 {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(0..<turn.lines, id: \.self) { line in
                        RoundedRectangle(cornerRadius: 1.5, style: .continuous)
                            .fill(CinematicWindowInk.line)
                            .frame(
                                width: usable * CGFloat(turn.width)
                                    * [0.78, 0.86, 0.52][line % 3],
                                height: 3)
                    }
                }
                .padding(.horizontal, 7)
                .padding(.top, 6)
            }
        }
    }

    private func terminal(_ rows: [CinematicWindowLayout.Row]) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            ForEach(rows.indices, id: \.self) { index in
                let row = rows[index]
                HStack(spacing: 4) {
                    ForEach(row.segments.indices, id: \.self) { segment in
                        RoundedRectangle(cornerRadius: 1.75, style: .continuous)
                            .fill(
                                row.marker && segment == 0
                                    ? CinematicWindowInk.lineStrong : CinematicWindowInk.line
                            )
                            .frame(width: usable * CGFloat(row.segments[segment]), height: 3.5)
                    }
                }
                .padding(.leading, usable * CGFloat(row.indent))
            }
        }
    }

    private func feed(_ rows: Int) -> some View {
        VStack(spacing: 7) {
            ForEach(0..<max(0, rows), id: \.self) { row in
                HStack(spacing: 8) {
                    Circle()
                        .fill(CinematicWindowInk.well)
                        .frame(width: 12, height: 12)
                    VStack(alignment: .leading, spacing: 4) {
                        bar([0.44, 0.36, 0.52, 0.40][row % 4], height: 3.5,
                            tone: CinematicWindowInk.line)
                        bar([0.72, 0.84, 0.64, 0.78][row % 4], height: 3,
                            tone: CinematicWindowInk.lineFaint)
                    }
                    Spacer(minLength: 0)
                }
            }
        }
    }

    private func gallery(columns: Int, rows: Int) -> some View {
        let columns = max(1, columns)
        let rows = max(1, rows)
        let gap: CGFloat = 6
        let tileWidth = max(0, (usable - gap * CGFloat(columns - 1)) / CGFloat(columns))
        let tones: [Double] = [0.125, 0.09, 0.14, 0.10, 0.13, 0.085]
        return VStack(spacing: gap) {
            ForEach(0..<rows, id: \.self) { row in
                HStack(spacing: gap) {
                    ForEach(0..<columns, id: \.self) { column in
                        RoundedRectangle(cornerRadius: 4, style: .continuous)
                            .fill(Ink.glow.opacity(tones[(row * columns + column) % tones.count]))
                            .frame(width: tileWidth, height: 30)
                    }
                }
            }
        }
    }

    private func chart(_ bars: [Double]) -> some View {
        let plot: CGFloat = 50
        let gap: CGFloat = 6
        let width = max(
            0, (usable - gap * CGFloat(max(0, bars.count - 1))) / CGFloat(max(1, bars.count)))
        return VStack(alignment: .leading, spacing: 8) {
            bar(0.34, height: 4, tone: CinematicWindowInk.lineFaint)
            HStack(alignment: .bottom, spacing: gap) {
                ForEach(bars.indices, id: \.self) { index in
                    RoundedRectangle(cornerRadius: 2, style: .continuous)
                        .fill(
                            index == bars.count - 2
                                ? CinematicWindowInk.lineStrong : CinematicWindowInk.line
                        )
                        .frame(width: width, height: max(2, plot * CGFloat(bars[index])))
                }
            }
            .frame(height: plot, alignment: .bottom)
            Rectangle()
                .fill(CinematicWindowInk.divider)
                .frame(width: usable, height: 1)
        }
    }

    private func sidebar(rail: [Double], lines: [Double]) -> some View {
        let railWidth: CGFloat = 44
        return HStack(alignment: .top, spacing: 0) {
            VStack(alignment: .leading, spacing: 9) {
                ForEach(rail.indices, id: \.self) { index in
                    RoundedRectangle(cornerRadius: 2, style: .continuous)
                        .fill(index == 0 ? CinematicWindowInk.lineStrong : CinematicWindowInk.line)
                        .frame(width: railWidth * CGFloat(rail[index]), height: 4)
                }
            }
            .frame(width: railWidth, alignment: .leading)

            Rectangle()
                .fill(CinematicWindowInk.divider)
                .frame(width: 1)
                .frame(maxHeight: .infinity)
                .padding(.trailing, 10)

            VStack(alignment: .leading, spacing: 7) {
                ForEach(lines.indices, id: \.self) { index in
                    RoundedRectangle(cornerRadius: 2, style: .continuous)
                        .fill(
                            index == 0 ? CinematicWindowInk.lineStrong : CinematicWindowInk.line
                        )
                        .frame(
                            width: (usable - railWidth - 11) * CGFloat(lines[index]),
                            height: index == 0 ? 5 : 4)
                }
            }
            Spacer(minLength: 0)
        }
        .frame(height: 70)
    }
}
