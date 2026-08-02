import SwiftUI

// The two things the tutorial has to *show* rather than describe: the chord being typed, and the
// gesture being made.
//
// Both beats used to be a picture of the answer — a chip with the chord printed on it, three
// capsules sliding under a double-headed arrow — and both were reported the same way: the card asks
// for an action and shows a still life of it. A still keycap says *which* keys; it does not say that
// this is a double tap, which is what the app's own default chord is and what a picture of two ⌘
// symbols side by side actively argues against. A sliding bar says something moved; it does not say
// that the user's fingers are what moves it.
//
// So each of these is a loop of the real thing, and each stops for the same reason: the card that
// hosts it is only rendered while the step is still waiting (`TutorialCardView.extras`), so the
// demonstration disappears the moment the user does the thing themselves. Nothing here polls the
// model and nothing here can satisfy a gate — an animation that could would be the one lie this
// whole flow is built to avoid.
//
// The timing lives in a value type, not in the view. `TutorialChordCycle` and `TutorialScrollCycle`
// are pure, so the two claims that actually matter — that the picture shows the same gesture the app
// listens for, and that the content moves *with* the fingers rather than against them — are
// assertions a headless test can make. What cannot be asserted headlessly is the drawing, and
// nothing about the drawing decides what is being demonstrated.

// MARK: - The chord, being typed

/// Which of a chord's keycaps are held down at each beat of a repeating press.
///
/// Two shapes, because this app ships both and they are not the same gesture:
///
/// - **A repeated tap** — `⌘⌘`, the default for `openTimeline`, which is one key pressed twice.
///   Drawing that as "hold the first ⌘ while you press the second" is not a thing a hand can do, and
///   a user copying the picture would never fire the shortcut.
/// - **An ordinary chord** — `⌘⇧K`, what a rebind produces. Here the modifiers really are held while
///   the last key is struck, and drawing it as three separate taps teaches the wrong gesture.
///
/// The split is by keycap, and a keycap is not a character: `Space`, `⌫` and the `Key 40` fallback
/// are single keys with multi-character labels, so the leading run of modifier glyphs is peeled off
/// and everything after it is one cap.
struct TutorialChordCycle: Equatable {
    /// The modifier glyphs `SettingsShortcutChord.displayString` can put in front of a key. Listed
    /// here rather than shared with that type because this is a question about *rendering* a string
    /// somebody may have rebound, not about the chord model.
    static let modifierGlyphs: Set<Character> = ["⌘", "⌥", "⌃", "⇧"]

    /// How long one beat of the demonstration lasts. Slower than a real double tap — a real one is
    /// under 400 ms for both presses — because this is being read rather than performed, and the two
    /// taps have to be legible as two.
    static let beat: Double = 0.28

    /// Beats the completed chord stays down. This is the moment the shortcut fires, so it is the
    /// only part of the loop that holds still long enough to look at.
    static let holdBeats = 2

    /// Beats with everything back up before it starts again. Without this the loop reads as one
    /// continuous stutter rather than as a gesture with a beginning.
    static let restBeats = 2

    /// One cap each, in the order they are typed.
    let keys: [String]

    init(chord: String) {
        var caps: [String] = []
        var rest = Substring(chord)
        while let first = rest.first, Self.modifierGlyphs.contains(first) {
            caps.append(String(first))
            rest = rest.dropFirst()
        }
        if !rest.isEmpty { caps.append(String(rest)) }
        self.keys = caps
    }

    /// Whether this chord is the *same key struck twice*, which is what the two leading caps being
    /// identical means and the only thing they can mean.
    var isRepeatedTap: Bool { keys.count >= 2 && keys[0] == keys[1] }

    /// The length of one loop, in beats. Never zero: a chord this app could not parse still has to
    /// divide by something.
    var beats: Int {
        // A repeated tap is three beats of movement whatever else is in the chord — down, up, down —
        // because the caps after the second one are modifiers held across both taps rather than
        // presses of their own.
        let movement = isRepeatedTap ? 3 : max(1, keys.count)
        return movement + Self.holdBeats + Self.restBeats
    }

    /// Whether the cap at `index` is down on `tick`, which repeats every `beats`.
    ///
    /// Total for both shapes rather than an optional "the one that is down": a chord is a *set* of
    /// keys held together, and a function that could only answer with one of them could not express
    /// the thing being taught.
    func isDown(_ index: Int, at tick: Int) -> Bool {
        guard keys.indices.contains(index) else { return false }
        let beat = ((tick % beats) + beats) % beats
        guard isRepeatedTap else {
            // Held together: each cap goes down in turn and none of them lifts until the whole chord
            // has fired and the hold is over.
            if beat < keys.count { return index < beat + 1 }
            return beat < keys.count + Self.holdBeats && index < keys.count
        }
        // A double tap, with any remaining modifiers held across both of them.
        switch beat {
        case 0: return index == 0 || index >= 2
        case 1: return index >= 2
        case 2..<(3 + Self.holdBeats): return index == 1 || index >= 2
        default: return false
        }
    }
}

/// The chord, on a small board, typing itself.
///
/// The board is there because two floating keycaps read as two badges; keys sit on something. It is
/// the app's own wash rather than a drawn keyboard — a photorealistic keyboard would be a picture of
/// *a* keyboard, and the point of the beat is the two keys on the user's own.
struct TutorialChordDemo: View {
    let chord: String

    /// Which beat of the loop is showing. A counter driven by a sleep loop rather than by a
    /// `repeatForever` animation, because the press is a *sequence of discrete states* and an
    /// interpolated `Bool` is not something SwiftUI can give us. The `.animation(_:value:)` below is
    /// what makes each of those states arrive as a press rather than as a jump.
    @State private var tick = 0

    private var cycle: TutorialChordCycle { TutorialChordCycle(chord: chord) }

    var body: some View {
        HStack(spacing: 5) {
            ForEach(cycle.keys.indices, id: \.self) { index in
                TutorialKeycap(label: cycle.keys[index], isDown: isDown(index))
            }
        }
        .padding(.horizontal, 6)
        .padding(.vertical, 5)
        .background(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .fill(Ink.wash)
                .overlay(
                    RoundedRectangle(cornerRadius: 10, style: .continuous)
                        .strokeBorder(Ink.hairline, lineWidth: 1)))
        .animation(InkReduceMotion.animation(.easeOut(duration: InkMotion.press)), value: tick)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(Text("Press \(chord)"))
        // `.task` rather than a `Timer` publisher: it is tied to this view's lifetime, so it is
        // cancelled the instant the card stops rendering the demonstration — which is the instant
        // the user presses the chord for real — and, unlike a publisher built in `init`, it does not
        // restart every time the model republishes and the card is re-evaluated.
        .task {
            guard !InkReduceMotion.isEnabled else { return }
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(TutorialChordCycle.beat))
                guard !Task.isCancelled else { return }
                tick &+= 1
            }
        }
    }

    /// Under Reduce Motion every cap is at rest. A repeating press is precisely the kind of movement
    /// that setting exists to stop, and the card still says which keys to press.
    private func isDown(_ index: Int) -> Bool {
        guard !InkReduceMotion.isEnabled else { return false }
        return cycle.isDown(index, at: tick)
    }
}

/// One key, up or down.
///
/// Pressed is four things at once, because one of them alone reads as a highlight rather than as a
/// press: the cap fills with the accent, its label inverts, it travels a point and a half *down* into
/// the board, and it takes a soft accent glow with it. Never purple — the accent is `Ink.accent`,
/// which is a named system blue this app picks (`INV-UI-1`).
struct TutorialKeycap: View {
    let label: String
    let isDown: Bool

    var body: some View {
        Text(label)
            .font(.system(size: 13, weight: .semibold, design: .rounded))
            .foregroundStyle(isDown ? Ink.glow : Ink.primary)
            .frame(minWidth: 18)
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(
                RoundedRectangle(cornerRadius: 7, style: .continuous)
                    .fill(isDown ? Ink.accent : Ink.rowFill)
                    .overlay(
                        RoundedRectangle(cornerRadius: 7, style: .continuous)
                            .strokeBorder(isDown ? Ink.accent : Ink.hairline, lineWidth: 1))
                    .shadow(color: Ink.accent.opacity(isDown ? 0.45 : 0), radius: isDown ? 7 : 0))
            .offset(y: isDown ? 1.5 : 0)
            .scaleEffect(isDown ? 0.96 : 1)
    }
}

// MARK: - The gesture, being made

/// Where the hand and everything under it sit at a point in the sweep.
///
/// `phase` runs −1 → +1 and back, which is why the loop demonstrates travel in **both** directions:
/// which way is "back" through the day depends on the user's own natural-scrolling setting, this app
/// does not get to read that off them, and the gate accepts either — so a picture committing to one
/// direction would disagree with the behaviour for half of everybody.
///
/// The one relationship worth stating as code is `content`: the panels move **with** the fingers, by
/// exactly as much. That is what direct manipulation is, and a demonstration that showed the content
/// travelling the other way would be teaching an inverted drag to a user who has never made this
/// gesture before.
enum TutorialScrollCycle {
    /// How far the hand travels from the centre, each way.
    static let travel: CGFloat = 30

    /// One sweep, in seconds. Slow enough to follow with your eyes, which is slower than anyone
    /// actually scrolls.
    static let sweep: Double = 1.6

    static func hand(_ phase: CGFloat) -> CGFloat { phase * travel }

    /// The panels under the hand. Identical to the hand's travel on purpose — see the type's note.
    static func content(_ phase: CGFloat) -> CGFloat { hand(phase) }

    /// The hour ticks behind the panels, which travel less so the strip reads as having depth rather
    /// than as one flat sheet sliding.
    static func backdrop(_ phase: CGFloat) -> CGFloat { hand(phase) * 0.42 }
}

/// A hand sweeping across a strip of the timeline, with the strip travelling under it.
///
/// Replaces three capsules sliding one way under an arrow. That picture had the direction argument
/// right and the subject wrong: it showed *content moving*, which is the outcome, and left the user
/// to infer the cause. This shows the cause.
struct TutorialScrollDemo: View {
    /// −1 at one end of the sweep, +1 at the other. One value drives the hand, the panels and the
    /// ticks, so "the panels move because the hand did" is true by construction rather than by three
    /// animations happening to agree.
    @State private var phase: CGFloat = -1

    /// Reduce Motion parks everything at the centre of the sweep and runs nothing.
    private var pose: CGFloat { InkReduceMotion.isEnabled ? 0 : phase }

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "arrow.left.and.right")
                .font(.system(size: 11, weight: .semibold))
                .foregroundStyle(Ink.secondary)
            strip
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(Text("Drag across the timeline"))
        .onAppear {
            guard !InkReduceMotion.isEnabled else { return }
            withAnimation(.easeInOut(duration: TutorialScrollCycle.sweep).repeatForever()) {
                phase = 1
            }
        }
    }

    private var strip: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .fill(Ink.wash)

            ticks.offset(x: TutorialScrollCycle.backdrop(pose))
            panels.offset(x: TutorialScrollCycle.content(pose))

            // Over the panels, because a hand behind the thing it is moving is a hand under glass.
            Image(systemName: "hand.draw.fill")
                .font(.system(size: 18, weight: .regular))
                .foregroundStyle(Ink.primary)
                .shadow(color: Ink.glow.opacity(0.25), radius: 3)
                .offset(x: TutorialScrollCycle.hand(pose), y: 4)
        }
        .frame(height: 46)
        // Clipped, so the panels travel *through* the strip rather than sliding out over the card's
        // own copy — which is what makes it read as a window onto a longer day.
        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .strokeBorder(Ink.hairline, lineWidth: 1))
    }

    /// The hour marks. Deliberately featureless: this is a diagram of a gesture, and anything here
    /// that looked like captured content would be a picture of somebody's screen that never existed.
    private var ticks: some View {
        HStack(spacing: 11) {
            ForEach(0..<11, id: \.self) { index in
                Capsule()
                    .fill(Ink.hairline)
                    .frame(width: 1, height: index.isMultiple(of: 3) ? 12 : 7)
            }
        }
    }

    /// Three panes of what the timeline holds, the middle one accented as the moment you are on.
    ///
    /// The accent's alpha is 0.85 and is not a free choice: it is the value `InkAccentTests` has
    /// measured this hint's composited hue against, and moving it moves the number that test compares
    /// to the token.
    private var panels: some View {
        HStack(spacing: 7) {
            ForEach(0..<3, id: \.self) { index in
                RoundedRectangle(cornerRadius: 4, style: .continuous)
                    .fill(index == 1 ? Ink.accent.opacity(0.85) : Ink.rowFillHover)
                    .frame(width: index == 1 ? 34 : 26, height: index == 1 ? 26 : 20)
            }
        }
    }
}
