import AppKit
import SwiftUI

//  The mark, the wordmark, and the one object they become — beats 2, 3 and 4.
//
//  The geometry is `MenuBar/ContextMark.swift`'s, transcribed rather than redrawn: the same 20×20
//  design box, the same head oval, the same two vertical-oval eyes, the same two curved legs, the
//  same stroke widths. The only change is the y axis — `ContextMark` draws into an unflipped AppKit
//  context (y up) and SwiftUI is y down, so every y below is `20 − y_appkit`, and every rect's y is
//  `20 − (y_appkit + height)`. Each value carries the number it came from so the two can be
//  compared line by line.
//
//  Beat 2 draws the mark by *stroke-end*: the head and the legs are `Shape`s trimmed from 0 to 1,
//  so the outline is genuinely under construction rather than a finished image fading up. The eyes
//  are fills in the source drawing and stay fills here — they are placed, with a little overshoot,
//  which is the honest animation for a fill.
//
//  Beats 3 and 4 are one object changing shape, and there is deliberately no
//  `matchedGeometryEffect`: nothing here ever changes view identity. The mark, the wordmark and the
//  shell are the same three views from beat 2 to beat 5, and only their frames and offsets move —
//  so SwiftUI interpolates real continuity rather than being asked to fake it across an identity
//  break. `matchedGeometryEffect` exists for the case where identity *must* break; using it where
//  it need not is strictly weaker.

// MARK: - Palette

/// The cinematic's colours.
///
/// Deliberately **not** `Ink`'s semantic ladder, and this is the one surface in the app where that
/// is correct. `Ink` colours a *sheet*: `labelColor` on `controlBackgroundColor`, which flips with
/// the system appearance so a sheet is a sheet in both. The cinematic is not a sheet — it is a
/// dimmed *desktop*, and "dim" has to mean darker in both appearances. Handing this surface to
/// `Ink.primary` would draw near-black type on a near-black scrim in Light.
///
/// So: the scrim is black and everything on it is white, at the alphas `Ink` uses for the same
/// roles. White is also exactly the neutral INV-UI-1 asks for, and this surface spends no accent at
/// all — the intro has one thing to look at per beat and a hue would be a second.
enum CinematicPalette {
    /// The dim over the desktop. Not fully opaque: the last few per cent keep the user's own desktop
    /// faintly present, so the intro reads as happening *on their Mac*.
    ///
    /// 0.96 and not the 0.93 this started at — measured against a real desktop, 7% transmission left
    /// a bright window behind the grid legible enough to compete with the cards.
    static let scrim = Color.black.opacity(0.96)
    /// The mark, the wordmark, the typed question. `Ink.glow` is `Color.white`, named there as the
    /// neutral this repo's brand rule asks for.
    static let ink = Ink.glow
    /// A line someone reads rather than the headline.
    static let inkSecondary = Ink.glow.opacity(0.58)
    /// The edge of the prompt shell and of a window card.
    static let hairline = Ink.glow.opacity(0.20)
    /// The prompt shell's fill.
    static let shellFill = Ink.glow.opacity(0.07)
    /// A window card's ground, under a frame that has not decoded yet or has none to show.
    static let cardFill = Ink.glow.opacity(0.06)
    /// The neutral bars a placeholder card is built from.
    static let cardLine = Ink.glow.opacity(0.13)
}

// MARK: - Geometry

/// `ContextMark`'s 20×20 design box, in SwiftUI's y-down space.
enum CinematicMarkGeometry {
    /// The box every value below is expressed in, matching `ContextMark.draw`.
    static let box: CGFloat = 20

    /// `ContextMark`: `NSRect(x: 3.4, y: 5.9, width: 13.2, height: 12.6)`.
    /// Centre y flips to `20 − (5.9 + 12.6/2)` = 7.8.
    static let headCentre = CGPoint(x: 10.0, y: 7.8)
    static let headRadii = CGSize(width: 6.6, height: 6.3)
    /// `head.lineWidth = 1.9 * s`.
    static let headLineWidth: CGFloat = 1.9

    /// `ContextMark`: eyes at x 7.9 and 12.1, `NSRect(x: x − 0.78, y: 11.0, width: 1.56, height: 2.1)`.
    /// Centre y flips to `20 − (11.0 + 2.1/2)` = 7.95.
    static let eyeCentres = [CGPoint(x: 7.9, y: 7.95), CGPoint(x: 12.1, y: 7.95)]
    static let eyeRadii = CGSize(width: 0.78, height: 1.05)

    /// `legs.lineWidth = 1.7 * s`.
    static let legLineWidth: CGFloat = 1.7

    /// The size `ContextMark`'s stroke weights were chosen for.
    static let menuBarSize: CGFloat = 18
    /// The size the cinematic draws the mark at in beat 2.
    static let displaySize: CGFloat = 132
    /// What the weights become at `displaySize`.
    ///
    /// `ContextMark` says its geometry "is deliberately heavier than the source drawing", because
    /// "at 18 pt a hairline outline disappears into a busy menu bar". 1.9 units is 9.5% of the box,
    /// which is right for an 18 pt glyph and draws a **torus** at 132 pt — measured on this machine
    /// before this constant existed: a 19 pt stroke on a 198 pt circle, with the eyes swallowed.
    /// So the *paths* stay `ContextMark`'s exactly and only the weight scales back toward the
    /// drawing's own as the mark gets bigger. Interpolated rather than switched, so the 26 pt mark
    /// in the prompt bar sits between the two and stays legible.
    static let displayLineWidthScale: CGFloat = 0.42

    static func lineWidthScale(for size: CGFloat) -> CGFloat {
        let span = displaySize - menuBarSize
        guard span > 0 else { return 1 }
        let t = min(1, max(0, (size - menuBarSize) / span))
        return 1 + (displayLineWidthScale - 1) * t
    }

    /// One leg: out of the head, down, then a short foot curving outward. Points are
    /// `ContextMark`'s with y flipped.
    struct Leg {
        let start: CGPoint
        let knee: CGPoint
        let foot: CGPoint
        let control1: CGPoint
        let control2: CGPoint
    }

    /// Left: `move(7.7, 6.4) line(7.3, 3.3) curve(5.8, 2.6) cp1(7.2, 2.7) cp2(6.5, 2.5)`.
    /// Right: `move(12.3, 6.4) line(12.7, 3.3) curve(14.2, 2.6) cp1(12.8, 2.7) cp2(13.5, 2.5)`.
    static let legs: [Leg] = [
        Leg(
            start: CGPoint(x: 7.7, y: 13.6),
            knee: CGPoint(x: 7.3, y: 16.7),
            foot: CGPoint(x: 5.8, y: 17.4),
            control1: CGPoint(x: 7.2, y: 17.3),
            control2: CGPoint(x: 6.5, y: 17.5)),
        Leg(
            start: CGPoint(x: 12.3, y: 13.6),
            knee: CGPoint(x: 12.7, y: 16.7),
            foot: CGPoint(x: 14.2, y: 17.4),
            control1: CGPoint(x: 12.8, y: 17.3),
            control2: CGPoint(x: 13.5, y: 17.5)),
    ]

    /// Scale from design box to a rendered box, and the origin that centres it.
    static func transform(in rect: CGRect) -> (scale: CGFloat, origin: CGPoint) {
        let scale = min(rect.width, rect.height) / box
        let origin = CGPoint(
            x: rect.midX - box * scale / 2,
            y: rect.midY - box * scale / 2)
        return (scale, origin)
    }
}

// MARK: - Shapes

/// The head's outline, starting at twelve o'clock and going clockwise, so the stroke reads as a
/// circle being drawn rather than as an arc appearing from the side.
///
/// Built from four cubic arcs rather than `Path(ellipseIn:)` for exactly that reason:
/// `ellipseIn` starts at three o'clock, and rotating the shape to fix that would also swap the
/// oval's 13.2 × 12.6 proportions onto the wrong axis.
struct CinematicHead: Shape {
    /// Standard circular-arc bezier constant: 4/3·tan(π/8).
    private static let kappa: CGFloat = 0.5522847498307936

    func path(in rect: CGRect) -> Path {
        let (scale, origin) = CinematicMarkGeometry.transform(in: rect)
        func point(_ x: CGFloat, _ y: CGFloat) -> CGPoint {
            CGPoint(x: origin.x + x * scale, y: origin.y + y * scale)
        }

        let c = CinematicMarkGeometry.headCentre
        let r = CinematicMarkGeometry.headRadii
        let kx = r.width * Self.kappa
        let ky = r.height * Self.kappa

        var path = Path()
        path.move(to: point(c.x, c.y - r.height))
        path.addCurve(
            to: point(c.x + r.width, c.y),
            control1: point(c.x + kx, c.y - r.height),
            control2: point(c.x + r.width, c.y - ky))
        path.addCurve(
            to: point(c.x, c.y + r.height),
            control1: point(c.x + r.width, c.y + ky),
            control2: point(c.x + kx, c.y + r.height))
        path.addCurve(
            to: point(c.x - r.width, c.y),
            control1: point(c.x - kx, c.y + r.height),
            control2: point(c.x - r.width, c.y + ky))
        path.addCurve(
            to: point(c.x, c.y - r.height),
            control1: point(c.x - r.width, c.y - ky),
            control2: point(c.x - kx, c.y - r.height))
        return path
    }
}

/// One leg. Two separate shapes rather than one two-subpath shape, because `trim` measures along a
/// path's *total* length — one shape would draw the left leg fully before the right one started.
struct CinematicLeg: Shape {
    let index: Int

    func path(in rect: CGRect) -> Path {
        let (scale, origin) = CinematicMarkGeometry.transform(in: rect)
        func point(_ p: CGPoint) -> CGPoint {
            CGPoint(x: origin.x + p.x * scale, y: origin.y + p.y * scale)
        }

        guard CinematicMarkGeometry.legs.indices.contains(index) else { return Path() }
        let leg = CinematicMarkGeometry.legs[index]

        var path = Path()
        path.move(to: point(leg.start))
        path.addLine(to: point(leg.knee))
        path.addCurve(
            to: point(leg.foot),
            control1: point(leg.control1),
            control2: point(leg.control2))
        return path
    }
}

// MARK: - The mark

/// The mark, drawing itself on.
///
/// `size` is the rendered box; every stroke width scales from it exactly as `ContextMark` scales
/// from `min(size)/20`, so the mark is the same drawing at 26 pt in a prompt bar and at 132 pt in
/// the middle of the screen.
struct CinematicMarkView: View {
    var draw: CinematicMarkDraw
    var size: CGFloat
    var color: Color = CinematicPalette.ink
    /// How open the eyes are, vertically. 1 is the drawing; `TalkingMark` squashes this towards
    /// `TalkingMarkMotion.blinkFloor` and back to blink. Defaulted, so every call site that predates
    /// blinking draws exactly what it drew before.
    ///
    /// A blink has to be a *vertical* squash and cannot be `draw.eyes`, which scales both axes:
    /// shrinking an eye uniformly reads as the eye receding, not as a lid coming down. This is the
    /// one expressive control the drawing has — the mark has no mouth — so it belongs with the
    /// geometry rather than being faked by an overlay somewhere else.
    var eyeOpen: Double = 1

    /// How much wider a closing eye gets, at fully closed.
    ///
    /// The eye is a fill: what it loses in height it has to keep somewhere or it is gone before it
    /// reads as shut. 22% is a real lid's spread, and it is what makes the closed frame a *line*
    /// rather than an absence.
    private static let eyeWidenAtClosed: CGFloat = 0.22

    private var scale: CGFloat { size / CinematicMarkGeometry.box }
    /// See `CinematicMarkGeometry.lineWidthScale`: the paths are `ContextMark`'s, the weight is not
    /// its menu-bar compensation.
    private var weight: CGFloat { CinematicMarkGeometry.lineWidthScale(for: size) * scale }

    var body: some View {
        ZStack {
            CinematicHead()
                .trim(from: 0, to: draw.head)
                .stroke(
                    color,
                    style: StrokeStyle(
                        lineWidth: CinematicMarkGeometry.headLineWidth * weight,
                        lineCap: .round))

            ForEach(CinematicMarkGeometry.eyeCentres.indices, id: \.self) { index in
                eye(index)
            }

            ForEach(CinematicMarkGeometry.legs.indices, id: \.self) { index in
                CinematicLeg(index: index)
                    .trim(from: 0, to: draw.legs)
                    .stroke(
                        color,
                        style: StrokeStyle(
                            lineWidth: CinematicMarkGeometry.legLineWidth * weight,
                            lineCap: .round,
                            lineJoin: .round))
            }
        }
        .frame(width: size, height: size)
        .accessibilityHidden(true)
    }

    /// A fill, so it is placed rather than stroked. Scales up from the eye's own centre.
    private func eye(_ index: Int) -> some View {
        let centre = CinematicMarkGeometry.eyeCentres[index]
        let radii = CinematicMarkGeometry.eyeRadii
        let open = min(max(eyeOpen, 0), 1)
        let widen = 1 + (1 - open) * Self.eyeWidenAtClosed
        return Ellipse()
            .fill(color)
            .frame(width: radii.width * 2 * scale, height: radii.height * 2 * scale)
            // `draw.eyes` is the place-on scale from the cinematic and `open` is the lid; they
            // multiply, so an eye that has not been placed yet cannot be blinked into existence.
            .scaleEffect(x: draw.eyes * widen, y: draw.eyes * open)
            .opacity(draw.eyes > 0 ? 1 : 0)
            .offset(
                x: (centre.x - CinematicMarkGeometry.box / 2) * scale,
                y: (centre.y - CinematicMarkGeometry.box / 2) * scale)
    }
}

// MARK: - The vessel

/// The metrics of the one object beats 2–5 share, per form.
///
/// Every field is interpolated by SwiftUI because the views holding them never change identity —
/// see the note at the top of this file.
struct CinematicVesselMetrics: Equatable {
    /// The mark's rendered box.
    var markSize: CGFloat
    /// The mark's offset from the composition's centre.
    var markOffset: CGSize
    /// The shell — nothing in beat 2, a bar in beat 3, a prompt field in beats 4–5.
    var shellSize: CGSize
    var shellOpacity: Double
    /// The wordmark under the mark in beat 2, gone by beat 3.
    var wordmarkOffset: CGSize
    var wordmarkOpacity: Double
    var wordmarkScale: CGFloat
    /// The typed question inside the shell.
    var questionOpacity: Double
    /// How far in from the shell's leading edge the question starts — the mark's slot.
    var questionInset: CGFloat

    static func metrics(for form: CinematicForm) -> CinematicVesselMetrics {
        switch form {
        case .mark:
            // The shell already exists at the wordmark's own footprint, at zero opacity, so beat 3
            // is a bar *growing out of the wordmark* rather than a bar appearing over it.
            return CinematicVesselMetrics(
                markSize: 132,
                markOffset: CGSize(width: 0, height: -56),
                shellSize: CGSize(width: 260, height: 46),
                shellOpacity: 0,
                wordmarkOffset: CGSize(width: 0, height: 62),
                wordmarkOpacity: 1,
                wordmarkScale: 1,
                questionOpacity: 0,
                questionInset: 44)
        case .bar:
            return CinematicVesselMetrics(
                markSize: 28,
                markOffset: CGSize(width: -104, height: 0),
                shellSize: CGSize(width: 268, height: 52),
                shellOpacity: 1,
                wordmarkOffset: .zero,
                wordmarkOpacity: 0,
                wordmarkScale: 0.68,
                questionOpacity: 0,
                questionInset: 44)
        case .prompt:
            return CinematicVesselMetrics(
                markSize: 26,
                markOffset: CGSize(width: -(Self.promptWidth / 2 - 30), height: 0),
                shellSize: CGSize(width: Self.promptWidth, height: Self.promptShellHeight),
                shellOpacity: 1,
                wordmarkOffset: .zero,
                wordmarkOpacity: 0,
                wordmarkScale: 0.6,
                questionOpacity: 1,
                questionInset: 56)
        }
    }

    /// The prompt's width, and therefore the width of the card grid under it — the grid is three
    /// cards across and lines up with the field exactly.
    static let promptWidth: CGFloat = 560
    /// The prompt shell's height. The composition centres a block of this plus the grid.
    static let promptShellHeight: CGFloat = 58
    /// The fixed box the vessel is laid out in, so growing the shell never moves the composition's
    /// centre — the shell stretches, the layout does not.
    static let stageHeight: CGFloat = 220
}

/// The mark, the wordmark, the shell and the typed question, as one object.
struct CinematicVessel: View {
    var draw: CinematicMarkDraw
    var form: CinematicForm
    var question: String
    var showsCaret: Bool
    /// Reduce Motion: the caret stops blinking too.
    var animatesCaret: Bool

    private var metrics: CinematicVesselMetrics { .metrics(for: form) }

    var body: some View {
        let m = metrics
        ZStack {
            shell(m)
            questionField(m)
            wordmark(m)
            CinematicMarkView(draw: draw, size: m.markSize)
                .offset(x: m.markOffset.width, y: m.markOffset.height)
        }
        // A fixed box so the composition's centre does not move as the shell grows — the shell is
        // what stretches, not the layout around it.
        .frame(
            width: CinematicVesselMetrics.promptWidth,
            height: CinematicVesselMetrics.stageHeight,
            alignment: .center)
    }

    private func shell(_ m: CinematicVesselMetrics) -> some View {
        Capsule(style: .continuous)
            .fill(CinematicPalette.shellFill)
            .overlay(
                Capsule(style: .continuous)
                    .strokeBorder(CinematicPalette.hairline, lineWidth: 1))
            .frame(width: m.shellSize.width, height: m.shellSize.height)
            .opacity(m.shellOpacity)
    }

    /// "Context for Claude", resolving under the mark. `draw.wordmark` is its own sub-beat, so the
    /// mark is finished before a letter of it is legible.
    private func wordmark(_ m: CinematicVesselMetrics) -> some View {
        Text(verbatim: "Context for Claude")
            .inkStyle(InkType.stepHeadline, color: CinematicPalette.ink)
            .opacity(draw.wordmark * m.wordmarkOpacity)
            // Resolves *out* of a blur rather than out of nothing: at this size a plain opacity
            // ramp reads as a label switching on.
            .blur(radius: (1 - draw.wordmark) * 9)
            .scaleEffect(m.wordmarkScale)
            .offset(x: m.wordmarkOffset.width, y: m.wordmarkOffset.height)
            .fixedSize()
    }

    /// The typed question, and the caret that follows it.
    ///
    /// `.center` and deliberately **not** `.firstTextBaseline`, which is the alignment this wants to
    /// be and cannot: `CinematicCaret` is a `Rectangle`, and SwiftUI resolves both text baselines of
    /// a view that contains no text to its own *bottom edge*. So under baseline alignment the caret
    /// hung its entire 19 pt above the baseline instead of straddling it, and the stack's
    /// above-baseline extent became the caret's 19 rather than the text's ~15 pt ascent. Measured on
    /// this machine at the `.prompt` shell's 58 pt: the caret sat 4 pt higher than the line it
    /// belongs to, and the whole stack — text included — was pushed 2 pt below the shell's centre.
    /// The mark was never the thing that moved; `markOffset.height` is 0 in `.bar` and in `.prompt`,
    /// so the mark has always been exactly on the shell's centre and the text was simply low.
    ///
    /// Centring costs nothing, because `CinematicCaret.barHeight` is exactly the line box the text
    /// is laid out in: concentric with that line box is where a text caret goes, so `.center`
    /// *reaches* baseline alignment's intended result along the one axis SwiftUI can measure here
    /// without being told the face's ascent. Text and caret then both land on the shell's centre, in
    /// every form, next to a mark that is already there.
    private func questionField(_ m: CinematicVesselMetrics) -> some View {
        HStack(alignment: .center, spacing: 3) {
            Text(verbatim: question)
                .inkStyle(InkType.prose, color: CinematicPalette.ink)
                .fixedSize()
            CinematicCaret(visible: showsCaret, animated: animatesCaret)
            Spacer(minLength: 0)
        }
        .padding(.leading, m.questionInset)
        .padding(.trailing, 22)
        .frame(width: m.shellSize.width, height: m.shellSize.height, alignment: .leading)
        .opacity(m.questionOpacity)
        .clipShape(Capsule(style: .continuous))
    }
}

/// The prompt's caret. Blinks on macOS's own cadence; static under Reduce Motion, where a blinking
/// bar is exactly the kind of motion the setting is asking us to stop.
struct CinematicCaret: View {
    var visible: Bool
    var animated: Bool

    /// The period macOS blinks a text caret at.
    static let blinkSeconds: Double = 1.06

    /// The bar's height, and the reason `questionField` can centre rather than baseline-align it.
    ///
    /// 21 pt is the line box SwiftUI lays `InkType.prose` out in: at 17 pt the system face measures
    /// ascender 16.44 and descender 3.59, and TextKit rounds each away from the baseline, so
    /// `ceil(16.44) + ceil(3.59)` = 21 — the height a single-line `Text` in this role actually
    /// reports, verified by measuring the face. A caret exactly one line box tall, centred on that
    /// line box, is the same bar a text view would draw from the baseline; it is only the *route*
    /// to it that changes, because a `Rectangle` has no baseline to align to.
    ///
    /// This tracks `InkType.prose`'s size and must be recomputed when it moves: it was 19 when
    /// prose was 15 pt (ascender 14.50, descender 3.16). A stale value does not fail the centring
    /// test — text and caret share a centre either way — it just quietly makes the caret the wrong
    /// height for the line it belongs to, which is the defect centring was chosen to avoid.
    static let barHeight: CGFloat = 21

    /// Phase as a pure function of the clock, so the caret does not need state and cannot get out
    /// of step with itself across a re-render.
    static func isOn(at date: Date) -> Bool {
        let half = blinkSeconds / 2
        return Int((date.timeIntervalSinceReferenceDate / half).rounded(.down)).isMultiple(of: 2)
    }

    var body: some View {
        Group {
            if animated {
                TimelineView(.periodic(from: .now, by: Self.blinkSeconds / 2)) { context in
                    bar.opacity(Self.isOn(at: context.date) ? 1 : 0.12)
                }
            } else {
                bar
            }
        }
        .opacity(visible ? 1 : 0)
        .accessibilityHidden(true)
    }

    private var bar: some View {
        Rectangle()
            .fill(CinematicPalette.ink)
            .frame(width: 2, height: Self.barHeight)
    }
}
