import AppKit
import ContextCore
import SwiftUI

//  Beat 5 — the window cards — and the composition that holds every beat.
//
//  The cards render the user's **own** recent captured frames, read through
//  `RewindQueries.frames`. On a fresh install there are none, and the cards fall back to neutral
//  placeholders: a ground, a hairline, three window dots and a few grey bars. There is deliberately
//  no third option. This app's entire claim is that it does not invent context, so a mocked-up
//  screenshot of an app the user does not have — or an app name attached to a frame we did not
//  read — would be the single most expensive lie in the product. A placeholder names nothing.
//
//  Nothing on this path can hold a beat up. The store read happens on a detached task started
//  before beat 1 and is never awaited; a real frame's image decodes through `FrameLoader` (off the
//  main thread, and already the tested decode path for the Rewind timeline) and cross-fades in
//  whenever it lands. A card whose image never arrives simply stays the neutral card it started as.

// MARK: - Cards

/// One window card.
struct CinematicCard: Identifiable, Equatable, Sendable {
    /// Real cards carry the frame's row id. Placeholders take a negative id derived from their slot,
    /// so the two can never collide in a `ForEach`.
    let id: Int64
    /// `nil` for a placeholder. The only source of an app name or an image on this surface.
    let frame: RewindFrame?

    var isPlaceholder: Bool { frame == nil }

    /// The app the frame was captured from, when we actually read one. Never synthesised.
    var appName: String? { frame?.appName }

    static func placeholder(slot: Int) -> CinematicCard {
        CinematicCard(id: Int64(-(slot + 1)), frame: nil)
    }

    static func placeholders(count: Int) -> [CinematicCard] {
        (0..<max(0, count)).map(placeholder(slot:))
    }

    static func real(_ frame: RewindFrame) -> CinematicCard {
        CinematicCard(id: frame.id, frame: frame)
    }
}

/// Turns the frames we read into the cards beat 5 shows.
///
/// Pure, and the whole of the "never fabricate" rule in one place: zero frames means every card is
/// a placeholder, and any frame at all means every card is real. The two are never mixed, because a
/// grid of two screenshots and four grey rectangles reads as four failures rather than as two
/// successes.
enum CinematicFrameSelection {
    /// - Parameters:
    ///   - frames: oldest first, as `RewindQueries.frames` returns them.
    ///   - slots: how many cards the grid can hold.
    static func cards(from frames: [RewindFrame], slots: Int) -> [CinematicCard] {
        let slots = max(0, slots)
        guard slots > 0 else { return [] }
        guard !frames.isEmpty else { return CinematicCard.placeholders(count: slots) }

        return select(frames, count: min(slots, frames.count)).map(CinematicCard.real)
    }

    /// Which frames the grid shows.
    ///
    /// Two passes, and the first one is the point. Taking the last six rows would be six pictures of
    /// the same window — capture writes a frame every couple of seconds — and even an evenly spread
    /// sample over an hour of focused work comes back as five frames of one editor, which is exactly
    /// what it looked like the first time this was rendered on a real store. So: **the most recent
    /// frame from each distinct app first**, then an even spread of everything else to fill. Every
    /// card is still a frame we actually read; the choice only decides which real frames get shown.
    ///
    /// Result is ordered oldest first, which is the order the grid fills in.
    static func select(_ frames: [RewindFrame], count: Int) -> [RewindFrame] {
        guard count > 0, !frames.isEmpty else { return [] }
        guard count < frames.count else { return frames }

        var chosen: [Int64: RewindFrame] = [:]

        // Pass 1: one per app, the most recent of each. `frames` is oldest first, so the last write
        // for an app name wins.
        var latestPerApp: [String: RewindFrame] = [:]
        for frame in frames { latestPerApp[frame.appName] = frame }
        let apps = latestPerApp.values.sorted {
            $0.capturedAt == $1.capturedAt ? $0.id > $1.id : $0.capturedAt > $1.capturedAt
        }
        for frame in apps.prefix(count) { chosen[frame.id] = frame }

        // Pass 2: fill from an even spread of the whole window.
        for frame in sample(frames, count: count) where chosen.count < count {
            chosen[frame.id] = frame
        }
        // Pass 3: the spread can collide with what pass 1 already took. Walk back from the newest
        // until the grid is full — `count < frames.count`, so this always can be.
        for frame in frames.reversed() where chosen.count < count {
            chosen[frame.id] = frame
        }

        return chosen.values.sorted {
            $0.capturedAt == $1.capturedAt ? $0.id < $1.id : $0.capturedAt < $1.capturedAt
        }
    }

    /// Evenly spaced across the range, newest last.
    static func sample(_ frames: [RewindFrame], count: Int) -> [RewindFrame] {
        guard count > 0, !frames.isEmpty else { return [] }
        guard count < frames.count else { return frames }
        let step = Double(frames.count - 1) / Double(count - 1 == 0 ? 1 : count - 1)
        var picked: [RewindFrame] = []
        var seen = Set<Int>()
        for index in 0..<count {
            let position = min(frames.count - 1, Int((Double(index) * step).rounded()))
            guard seen.insert(position).inserted else { continue }
            picked.append(frames[position])
        }
        return picked
    }
}

// MARK: - Where the frames come from

/// Beat 5's frames.
///
/// A protocol so the selection rule is tested without a database, and so a caller can hand the
/// director an empty source to see the fresh-install path.
protocol CinematicFrameSource: Sendable {
    func recent(limit: Int) async -> [CinematicCard]
}

/// The real thing: a read-only snapshot of the capture store.
///
/// Read-only and opened here rather than borrowed from `Engine`, exactly as
/// `ScreenActivityUploader` does — WAL means this never blocks the writer, and a fresh install
/// throws `notInitialized`, which is not an error but the answer "nothing captured yet".
struct StoredCinematicFrames: CinematicFrameSource {
    /// Widened until a window holds enough frames. Bounded on purpose: `frames(_:since:until:)`
    /// materialises every row in the window, and asking for a month up front to fill six cards
    /// would decode thousands of rows nobody looks at.
    static let windows: [Double] = [3600, 12 * 3600, 30 * 86_400]

    func recent(limit: Int) async -> [CinematicCard] {
        await Task.detached(priority: .utility) {
            StoredCinematicFrames.read(limit: limit)
        }.value
    }

    /// Every failure here means the same thing to the caller — no frames, so placeholders — which
    /// is why nothing is rethrown.
    private static func read(limit: Int) -> [CinematicCard] {
        guard let store = try? ContextStore(readOnly: true) else {
            return []
        }
        // The end of what has actually been captured, not `Date()`: an install that ran a week ago
        // and has been quiet since still has frames worth showing.
        let end = (try? RewindQueries.coverage(store))?.upperBound ?? Date().timeIntervalSince1970

        var best: [RewindFrame] = []
        for window in windows {
            guard let frames = try? RewindQueries.frames(store, since: end - window, until: end) else {
                continue
            }
            if frames.count > best.count { best = frames }
            if best.count >= limit { break }
        }
        return CinematicFrameSelection.cards(from: best, slots: limit)
    }
}

/// A fixed set of frames, for tests and previews.
struct StaticCinematicFrames: CinematicFrameSource {
    let frames: [RewindFrame]

    func recent(limit: Int) async -> [CinematicCard] {
        CinematicFrameSelection.cards(from: frames, slots: limit)
    }
}

// MARK: - Grid

/// Where the cards settle, and where they fly in from.
///
/// Every value is a function of the card's index, with no randomness anywhere: a cinematic that
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

    /// The card's resting offset from the grid's centre. The last row is centred rather than
    /// left-aligned, so four cards read as a deliberate arrangement instead of a truncated one.
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

    /// Off-screen, on a fan around the composition, so the swarm arrives from every direction
    /// rather than sliding in from one edge.
    static func entry(_ index: Int, count: Int, in size: CGSize) -> CGSize {
        guard count > 0 else { return .zero }
        let angle = Double(index) / Double(count) * 2 * .pi + .pi / 5
        let radius = Double(max(size.width, size.height)) * 0.78
        return CGSize(width: cos(angle) * radius, height: sin(angle) * radius)
    }

    /// The tilt a card carries while it is still in the air. Alternates side, so the swarm does not
    /// read as one sheet of paper folded over.
    static func entryRotation(_ index: Int) -> Double {
        let magnitude = 9 + Double(index % 3) * 4.5
        return index.isMultiple(of: 2) ? -magnitude : magnitude
    }
}

// MARK: - One card

/// A window card: a header strip with three neutral dots, and either a real captured frame or a
/// neutral placeholder body.
///
/// The dots are `CinematicPalette.cardLine` and not red/amber/green on purpose — this is a card
/// that reads as a window, not a forgery of macOS's own chrome.
struct CinematicCardView: View {
    let card: CinematicCard
    /// The decoded frame, once it has arrived. Until then, and for a placeholder, the body is
    /// neutral.
    let image: NSImage?

    private var shape: RoundedRectangle {
        RoundedRectangle(cornerRadius: 10, style: .continuous)
    }

    var body: some View {
        VStack(spacing: 0) {
            header
            Group {
                if let image {
                    Image(nsImage: image)
                        .resizable()
                        .aspectRatio(contentMode: .fill)
                        .frame(
                            width: CinematicGrid.cardSize.width,
                            height: CinematicGrid.cardSize.height - Self.headerHeight)
                        .clipped()
                } else {
                    placeholderBody
                }
            }
        }
        .frame(width: CinematicGrid.cardSize.width, height: CinematicGrid.cardSize.height)
        .background(CinematicPalette.cardFill)
        .clipShape(shape)
        .overlay(shape.strokeBorder(CinematicPalette.hairline, lineWidth: 1))
        // A card in flight needs to read as being in front of the scrim; a dark shadow is the only
        // thing that separates a translucent white-edged card from a black ground.
        .shadow(color: .black.opacity(0.55), radius: 14, x: 0, y: 7)
        .accessibilityHidden(true)
    }

    static let headerHeight: CGFloat = 20

    private var header: some View {
        HStack(spacing: 4) {
            ForEach(0..<3, id: \.self) { _ in
                Circle()
                    .fill(CinematicPalette.cardLine)
                    .frame(width: 5, height: 5)
            }
            // Only ever the app name of a frame we genuinely read. A placeholder has no name, and
            // no stand-in for one.
            if let appName = card.appName {
                Text(appName)
                    .inkStyle(InkType.statusLabel, color: CinematicPalette.inkSecondary)
                    .lineLimit(1)
                    .truncationMode(.tail)
                    .padding(.leading, 2)
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 8)
        .frame(height: Self.headerHeight)
        .background(Ink.glow.opacity(0.05))
    }

    /// Neutral geometry — the shape of a document, with nothing written on it. Widths are a
    /// function of the card's slot so the six placeholders are not six identical rectangles.
    private var placeholderBody: some View {
        VStack(alignment: .leading, spacing: 7) {
            ForEach(0..<3, id: \.self) { line in
                RoundedRectangle(cornerRadius: 2, style: .continuous)
                    .fill(CinematicPalette.cardLine)
                    .frame(width: lineWidth(line), height: 6)
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 12)
        .padding(.top, 12)
        .frame(
            width: CinematicGrid.cardSize.width,
            height: CinematicGrid.cardSize.height - Self.headerHeight,
            alignment: .topLeading)
    }

    private func lineWidth(_ line: Int) -> CGFloat {
        let base: [CGFloat] = [0.82, 0.62, 0.44]
        let jitter = CGFloat((abs(Int(card.id)) + line * 3) % 4) * 0.03
        let usable = CinematicGrid.cardSize.width - 24
        return usable * min(0.94, base[line % base.count] + jitter)
    }
}

// MARK: - The swarm

/// Every card, flying in and settling.
struct CinematicCardGrid: View {
    let cards: [CinematicCard]
    /// Cards `0..<settled` have arrived; the rest are still off-screen.
    let settled: Int
    /// The window's size, which is what "off-screen" is measured against.
    let stageSize: CGSize
    /// Reduce Motion: no travel and no tilt, just the cross-fade.
    let crossFade: Bool

    /// Decoded frames, keyed by card id. Populated off the main thread by `FrameLoader`.
    @State private var images: [Int64: NSImage] = [:]
    @State private var loader = FrameLoader()

    var body: some View {
        ZStack {
            ForEach(Array(cards.enumerated()), id: \.element.id) { index, card in
                let hasArrived = index < settled
                let slot = CinematicGrid.slot(index, count: cards.count)
                let entry = CinematicGrid.entry(index, count: cards.count, in: stageSize)

                CinematicCardView(card: card, image: images[card.id])
                    .rotationEffect(
                        .degrees(hasArrived || crossFade ? 0 : CinematicGrid.entryRotation(index)))
                    .scaleEffect(hasArrived ? 1 : (crossFade ? 1 : 0.84))
                    .offset(
                        x: hasArrived || crossFade ? slot.width : slot.width + entry.width,
                        y: hasArrived || crossFade ? slot.height : slot.height + entry.height)
                    .opacity(hasArrived ? 1 : 0)
            }
        }
        .frame(width: CinematicGrid.width, height: CinematicGrid.height(for: cards.count))
        // Kicks whenever the card set changes — the placeholders are replaced in place the moment
        // the store read lands, and each real frame then decodes on its own.
        .task(id: cards.map(\.id)) { decodeFrames() }
    }

    private func decodeFrames() {
        for card in cards {
            guard let frame = card.frame else { continue }
            loader.load(frame) { image in
                images[card.id] = image
            }
        }
    }
}

// MARK: - The composition

/// The whole cinematic: the scrim, the one object beats 2–4 build, the card grid, and the two
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

    /// The vessel and the grid, positioned as one block so opening the grid lifts the prompt rather
    /// than pushing it off centre.
    private func composition(in stageSize: CGSize) -> some View {
        let count = director.cards.count
        let gridHeight = director.gridOpen ? CinematicGrid.height(for: count) : 0
        let blockHeight = CinematicVesselMetrics.promptShellHeight + Self.gridGap + gridHeight
        let vesselY = director.gridOpen ? -(blockHeight - CinematicVesselMetrics.promptShellHeight) / 2 : 0
        let gridY = (blockHeight - gridHeight) / 2

        return ZStack {
            CinematicCardGrid(
                cards: director.cards,
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

    /// Between the prompt field and the top of the grid.
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
            // button hanging over the welcome card would be pointing at nothing.
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
