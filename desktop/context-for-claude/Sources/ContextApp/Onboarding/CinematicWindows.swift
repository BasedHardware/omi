import AppKit
import SwiftUI

//  Beat 5 — the window field — and the composition that holds every beat.
//
//  ## Why these windows are synthetic, and only synthetic
//
//  This beat used to render the user's **own** recent captured frames, read live from the capture
//  store, and fall back to a grey skeleton — a hairline, three dots, three bars — when the store
//  had nothing in it. That fallback was not the rare path. It was the *only* path:
//
//  - The cinematic is gated on `context.onboarded` (`CinematicGate`), so the only person who ever
//    sees it is someone running the app for the first time.
//  - Screen capture is not granted until Phase 4, which happens *after* this. A first-run store is
//    empty by construction, not by accident.
//
//  So every real user got six identical unfinished-looking cards, and the branch that was supposed
//  to be the good one could only fire for a developer with a pre-seeded database. Keeping a
//  real-frames path would mean keeping the branch nobody sees, in front of the one everybody does.
//  It is also the wrong thing to *want*: a full-screen intro that flashes the user's own recent
//  screenshots is a shoulder-surfing hazard in a product whose pitch is privacy, and a composition
//  that changes with the store cannot be reviewed against a screenshot.
//
//  These windows are therefore drawn, always, for everyone. There is no store read on this path,
//  no image decode, no `CinematicFrameSource`, and so no fallback branch and nothing to record —
//  the honest way to satisfy `.github/agent-docs/fallback-telemetry.md` is to not have a second path.
//
//  What they must never be is *plausible*. `CinematicWindowArt.swift` holds the drawing, and the
//  invariant that makes this safe: a window is built from numbers only and no view in that file can
//  draw text, so no synthetic window can carry a name, a message, or an app. See its header.

// MARK: - Grid

/// Where the windows settle, where they fly in from, and how they sit once they land.
///
/// Every value is a function of the window's index, with no randomness anywhere: a cinematic that
/// looks different on each run cannot be reviewed against a screenshot, and a stagger built on
/// `Double.random` is the same bug `RandomizedText` documents at length.
enum CinematicGrid {
    static let slots = 6
    static let columns = 3
    static let cardSize = CGSize(width: 176, height: 110)
    static let gap: CGFloat = 16

    /// The grid is exactly as wide as the prompt field above it, so the two read as one object.
    static var width: CGFloat {
        CGFloat(columns) * cardSize.width + CGFloat(columns - 1) * gap
    }

    static func rows(for count: Int) -> Int {
        guard count > 0 else { return 0 }
        return (count + columns - 1) / columns
    }

    static func height(for count: Int) -> CGFloat {
        let rows = rows(for: count)
        guard rows > 0 else { return 0 }
        return CGFloat(rows) * cardSize.height + CGFloat(rows - 1) * gap
    }

    /// The window's resting offset from the grid's centre. The last row is centred rather than
    /// left-aligned, so four windows read as a deliberate arrangement instead of a truncated one.
    static func slot(_ index: Int, count: Int) -> CGSize {
        let rowCount = rows(for: count)
        guard rowCount > 0, index < count else { return .zero }
        let row = index / columns
        let inRow = min(columns, count - row * columns)
        let column = index % columns

        let rowWidth = CGFloat(inRow) * cardSize.width + CGFloat(inRow - 1) * gap
        let x = -rowWidth / 2 + cardSize.width / 2 + CGFloat(column) * (cardSize.width + gap)

        let gridHeight = height(for: count)
        let y = -gridHeight / 2 + cardSize.height / 2 + CGFloat(row) * (cardSize.height + gap)
        return CGSize(width: x, height: y)
    }

    /// Off-screen, on a fan around the composition, so the field arrives from every direction
    /// rather than sliding in from one edge.
    static func entry(_ index: Int, count: Int, in size: CGSize) -> CGSize {
        guard count > 0 else { return .zero }
        let angle = Double(index) / Double(count) * 2 * .pi + .pi / 5
        let radius = Double(max(size.width, size.height)) * 0.78
        return CGSize(width: cos(angle) * radius, height: sin(angle) * radius)
    }

    /// The tilt a window carries while it is still in the air. Alternates side, so the field does
    /// not read as one sheet of paper folded over.
    static func entryRotation(_ index: Int) -> Double {
        let magnitude = 9 + Double(index % 3) * 4.5
        return index.isMultiple(of: 2) ? -magnitude : magnitude
    }

    /// The tilt a window keeps *after* it lands.
    ///
    /// The product page's windows rest at ±2.2°, and it is the single detail that makes a set of
    /// rectangles read as a field of windows rather than as a table. Pulled in slightly here,
    /// because a 3-wide grid still has to read as rows.
    static func restRotation(_ index: Int) -> Double {
        let magnitude = [1.5, 0.7, 1.2, 0.9, 1.6, 1.0][abs(index) % 6]
        return index.isMultiple(of: 2) ? -magnitude : magnitude
    }

    /// How large a window sits at rest.
    ///
    /// The page runs 0.64–0.88, which is a 27% spread. At that range a grid stops being a grid, so
    /// this is the same idea across a twentieth of it: enough that the field has a near and a far,
    /// not enough to unalign the rows.
    static func restScale(_ index: Int) -> CGFloat {
        [1.0, 0.965, 0.985, 0.955, 1.0, 0.97][abs(index) % 6]
    }

    static let nearestScale: CGFloat = 1.0
    static let farthestScale: CGFloat = 0.955

    /// How much of the float a window takes: the near ones move more than the far ones, which is
    /// the page's parallax expressed through the same scale that sets it.
    static func depth(_ index: Int) -> CGFloat {
        let span = nearestScale - farthestScale
        guard span > 0 else { return 1 }
        let position = (restScale(index) - farthestScale) / span
        return 0.75 + position * 0.45
    }
}

// MARK: - The field

/// Every window, flying in, settling, and then floating.
struct CinematicWindowGrid: View {
    let windows: [CinematicWindowSpec]
    /// Windows `0..<settled` have arrived; the rest are still off-screen.
    let settled: Int
    /// The window's size, which is what "off-screen" is measured against.
    let stageSize: CGSize
    /// Reduce Motion: no travel, no tilt, no float — just the cross-fade.
    let crossFade: Bool

    /// Overridden by the render harness and by tests so a phase of the float is a value rather
    /// than a moment. `nil` in production, where the clock is `TimelineView`'s.
    var pinnedPhase: TimeInterval?

    private var drifts: Bool {
        pinnedPhase == nil
            && CinematicWindowMotion.allowsDrift(
                crossFade: crossFade, reduceMotion: InkReduceMotion.isEnabled)
    }

    var body: some View {
        Group {
            if drifts {
                // The float is a function of the clock, not a repeating animation: six independent
                // `repeatForever` springs would each own their own transaction and fight the
                // settle, and none of them could be rendered at a chosen phase for review.
                TimelineView(.animation) { context in
                    field(at: context.date.timeIntervalSinceReferenceDate)
                }
            } else {
                field(at: pinnedPhase)
            }
        }
        .frame(width: CinematicGrid.width, height: CinematicGrid.height(for: windows.count))
    }

    /// The whole field at one instant. `nil` is the static composition Reduce Motion gets.
    private func field(at time: TimeInterval?) -> some View {
        ZStack {
            ForEach(Array(windows.enumerated()), id: \.element.id) { index, spec in
                let hasArrived = index < settled
                let slot = CinematicGrid.slot(index, count: windows.count)
                let entry = CinematicGrid.entry(index, count: windows.count, in: stageSize)
                let drift =
                    time.map {
                        CinematicWindowMotion.drift(
                            index: index, at: $0, depth: CinematicGrid.depth(index))
                    } ?? .still

                CinematicWindowView(spec: spec, size: CinematicGrid.cardSize)
                    .rotationEffect(
                        .degrees(CinematicGrid.restRotation(index) + drift.rotation))
                    .scaleEffect(CinematicGrid.restScale(index))
                    .offset(x: drift.dx, y: drift.dy)
                    // The float updates every frame and must never be animated: inside the settle
                    // spring's transaction it would lag a frame behind itself and smear.
                    .transaction { $0.animation = nil }
                    .rotationEffect(
                        .degrees(hasArrived || crossFade ? 0 : CinematicGrid.entryRotation(index)))
                    .scaleEffect(hasArrived ? 1 : (crossFade ? 1 : 0.84))
                    .offset(
                        x: hasArrived || crossFade ? slot.width : slot.width + entry.width,
                        y: hasArrived || crossFade ? slot.height : slot.height + entry.height)
                    .opacity(hasArrived ? 1 : 0)
            }
        }
    }
}

// MARK: - The composition

/// The whole cinematic: the scrim, the one object beats 2–4 build, the window field, and the two
/// controls that can stop it.
struct CinematicView: View {
    @ObservedObject var director: CinematicDirector

    /// The layout every metric in `CinematicVesselMetrics` and `CinematicGrid` was authored
    /// against. The composition is scaled to the display rather than laid out for it, so a 13"
    /// panel and a 5K display get the same picture at different sizes.
    static let designSize = CGSize(width: 700, height: 470)

    /// Where the welcome card will land: `OnboardingWindow.centredFrame` sits the card 5% of the
    /// screen above true centre, so that is where beat 6 recedes to.
    static let cardAnchor = UnitPoint(x: 0.5, y: 0.45)

    var body: some View {
        GeometryReader { geometry in
            ZStack {
                CinematicPalette.scrim
                    .opacity(director.dim)

                composition(in: geometry.size)
                    .scaleEffect(
                        scale(for: geometry.size) * (director.receding ? 0.66 : 1),
                        anchor: Self.cardAnchor)
                    .opacity(director.receding ? 0 : 1)

                controls
            }
            .frame(width: geometry.size.width, height: geometry.size.height)
        }
        .ignoresSafeArea()
        // The scrim is the click target for nothing at all, but it must not let a click through to
        // whatever is behind it either — the desktop is dimmed because it is not part of this.
        .contentShape(Rectangle())
    }

    /// The vessel and the field, positioned as one block so opening the field lifts the prompt
    /// rather than pushing it off centre.
    private func composition(in stageSize: CGSize) -> some View {
        let count = director.windows.count
        let gridHeight = director.gridOpen ? CinematicGrid.height(for: count) : 0
        let blockHeight = CinematicVesselMetrics.promptShellHeight + Self.gridGap + gridHeight
        let vesselY = director.gridOpen ? -(blockHeight - CinematicVesselMetrics.promptShellHeight) / 2 : 0
        let gridY = (blockHeight - gridHeight) / 2

        return ZStack {
            CinematicWindowGrid(
                windows: director.windows,
                settled: director.settledCards,
                stageSize: stageSize,
                crossFade: director.timing.isCrossFade
            )
            .opacity(director.gridOpen ? 1 : 0)
            .offset(y: gridY)

            CinematicVessel(
                draw: director.draw,
                form: director.form,
                question: director.typedQuestion,
                showsCaret: director.showsCaret,
                animatesCaret: !director.timing.isCrossFade
            )
            .offset(y: vesselY)
        }
        .frame(width: Self.designSize.width, height: Self.designSize.height)
    }

    /// Between the prompt field and the top of the field.
    private static let gridGap: CGFloat = 30

    /// "Skip intro", and the bed's own mute control.
    ///
    /// The bed is content rather than chrome, so the system's UI-sound switch does not govern it
    /// (`Sound.swift`) — this is the explicit control that does, and it persists.
    private var controls: some View {
        VStack {
            Spacer()
            HStack(spacing: 14) {
                Button(action: director.toggleMusic) {
                    Image(systemName: director.musicEnabled ? "speaker.wave.2" : "speaker.slash")
                        .font(.system(size: 12, weight: .medium))
                        .frame(width: 30, height: 30)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .foregroundStyle(CinematicPalette.inkSecondary)
                .accessibilityLabel(Text(director.musicEnabled ? "Mute music" : "Unmute music"))

                Button(action: director.skip) {
                    Text(verbatim: "Skip intro")
                        .inkStyle(InkType.statusLabel, color: CinematicPalette.inkSecondary)
                        .padding(.horizontal, 14)
                        .frame(height: 30)
                        .overlay(
                            Capsule(style: .continuous)
                                .strokeBorder(CinematicPalette.hairline, lineWidth: 1))
                        .contentShape(Capsule(style: .continuous))
                }
                .buttonStyle(.plain)
                // Esc. The window also carries a key monitor, because a borderless accessory
                // window is not guaranteed to be the one AppKit routes cancelAction to.
                .keyboardShortcut(.cancelAction)
            }
            .padding(.bottom, 44)
            // Arrives with the dim rather than before it, and leaves with beat 6 — a "Skip intro"
            // button hanging over the field would be pointing at nothing.
            .opacity(director.dim > 0.35 && !director.receding ? 1 : 0)
            .animation(
                InkReduceMotion.animation(.easeOut(duration: CinematicTiming.crossFade)),
                value: director.dim > 0.35 && !director.receding)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func scale(for size: CGSize) -> CGFloat {
        guard size.width > 0, size.height > 0 else { return 1 }
        let fit = min(
            size.width / Self.designSize.width,
            size.height / Self.designSize.height)
        // Floored so a small window still reads, capped so a 5K display does not turn the prompt
        // field into a billboard.
        return min(max(fit * 0.92, 0.78), 1.5)
    }
}
