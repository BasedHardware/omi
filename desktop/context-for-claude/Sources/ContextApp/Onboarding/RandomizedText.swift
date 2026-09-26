import Foundation
import SwiftUI

/// The word-by-word reveal every onboarding headline uses.
///
///     RandomizedText(
///         segments: [
///             ("Hi, I’m Omi. I give ", .plain),
///             ("Claude", .bold),
///             (" everything you’ve seen and said.", .plain),
///         ],
///         style: .introHero
///     )
///     .multilineTextAlignment(.center)
///
/// Words resolve out of nothing on staggered delays over `InkMotion.wordReveal`. Whitespace is
/// preserved as its own token with delay 0, so wrapping is untouched.
///
/// The whole thing renders as a **single** `Text` built by concatenating styled runs — never an
/// `HStack` of words, which would break line wrapping and let an emphasised run drift out of step
/// with the words around it.
///
/// Two consequences of that, both deliberate:
///
/// - **Colour is a parameter, not the environment.** Per-word opacity has to ride on each run's
///   colour, because colour is the only per-run knob `Text` concatenation offers. A
///   `.foregroundStyle` applied further out cannot reach the runs — pass `color:` instead.
/// - **Alignment is left alone**, so the caller's `.multilineTextAlignment` governs. Leading comes
///   from the role (`style.lineSpacing`); the role's `shadow` does not, because a shadow is a
///   view-level effect — apply it at the call site as `Text.inkStyle` does.
struct RandomizedText: View {
    enum Emphasis: Hashable {
        case plain
        case bold
        case italic
    }

    struct Segment: Hashable {
        var text: String
        var emphasis: Emphasis

        init(_ text: String, _ emphasis: Emphasis = .plain) {
            self.text = text
            self.emphasis = emphasis
        }
    }

    private let segments: [Segment]
    private let style: InkTextStyle
    private let color: Color
    private let cadence: SpokenCadence?

    /// - Parameters:
    ///   - segments: Text runs and their emphasis, in reading order.
    ///   - style: A complete type role — `.introHero`, `.stepHeadline`, `.prose`, …
    ///   - color: The colour the words resolve *to*. See the note on the type.
    ///   - cadence: Nil is the scattered stagger described above, which every headline in the app
    ///     uses. A `SpokenCadence` replaces it with reading order on a fixed beat, driven from an
    ///     instant the caller owns — see `TalkingMark`, which hands the *same* instant to the mark's
    ///     body so the words and the character move on one clock rather than two that started near
    ///     each other. Scattered is right for a line resolving; ordered is the only thing that reads
    ///     as someone saying it.
    init(
        segments: [(String, Emphasis)],
        style: InkTextStyle,
        color: Color = Ink.primary,
        cadence: SpokenCadence? = nil
    ) {
        self.segments = segments.map { Segment($0.0, $0.1) }
        self.style = style
        self.color = color
        self.cadence = cadence
    }

    /// Convenience for a headline with no emphasis runs.
    init(_ text: String, style: InkTextStyle, color: Color = Ink.primary, cadence: SpokenCadence? = nil) {
        self.init(segments: [(text, .plain)], style: style, color: color, cadence: cadence)
    }

    /// Tokens *and their delays*, generated once per piece of content and then held. This is the
    /// whole trick: see `body` and the `.task` below.
    @State private var plan: RevealPlan?
    @State private var startedAt: Date?
    @State private var isRevealed = false

    var body: some View {
        // `plan` is nil only for the frame between first layout and `.task` firing. The fallback
        // is deterministic — every delay 0, no RNG. A random fallback here is exactly the bug that
        // makes the text shimmer instead of resolve.
        let resolved = plan ?? RevealPlan(segments: segments, randomized: false, cadence: cadence)

        return Group {
            if InkReduceMotion.isEnabled || isRevealed {
                // Reduce Motion jumps straight to revealed; so does every frame after the reveal
                // completes, which retires the timeline rather than leaving it idling.
                styled(resolved, progress: 1)
            } else {
                TimelineView(.animation(minimumInterval: 1.0 / 60.0)) { context in
                    styled(resolved, progress: progress(at: context.date))
                }
            }
        }
        .lineSpacing(style.lineSpacing)
        // Fires on appear, and again only when the *content* actually changes — which is exactly
        // when a fresh reveal is wanted. Re-renders that leave the segments alone (a parent
        // redrawing, a window resize, the timeline ticking sixty times a second) never reach this,
        // so the delays rolled on the first pass are the delays every later frame reads.
        // Keyed on the cadence as well as the content, because a card can say the *same* words a
        // second time — the permissions title goes "First…" → "Say yes." → back — and a new
        // `SpokenCadence.start` is what says "this is a new delivery of it".
        .task(id: RevealKey(segments: segments, cadence: cadence)) {
            plan = RevealPlan(segments: segments, randomized: !InkReduceMotion.isEnabled, cadence: cadence)
            guard !InkReduceMotion.isEnabled else {
                isRevealed = true
                return
            }
            isRevealed = false
            startedAt = Date()
            try? await Task.sleep(for: .seconds(cadence?.duration ?? InkMotion.wordReveal))
            guard !Task.isCancelled else { return }
            isRevealed = true
        }
    }

    /// Normalised against the total, so every constant in `Reveal` is a fraction of the whole —
    /// exactly as the design doc writes them.
    ///
    /// A spoken cadence brings its own start with it and is measured from that, not from the frame
    /// `.task` happened to fire on: the mark beside the words is reading the same instant, and a
    /// frame of skew between a body and its voice is the one error this feature cannot afford.
    private func progress(at date: Date) -> Double {
        if let cadence { return cadence.progress(at: date) }
        guard let startedAt else { return 0 }
        return min(max(date.timeIntervalSince(startedAt) / InkMotion.wordReveal, 0), 1)
    }

    private func styled(_ plan: RevealPlan, progress: Double) -> Text {
        var out = Text(verbatim: "")
        for token in plan.tokens {
            let alpha = Reveal.opacity(progress: progress, delay: token.delay, ramp: plan.ramp)
            out = out
                + emphasised(Text(verbatim: token.text).inkFont(style), token.emphasis)
                .foregroundStyle(color.opacity(alpha))
        }
        return out
    }

    /// Emphasis names a weight rather than asking for a trait, and has to.
    ///
    /// Open Runde's faces are resolved by PostScript name (`OpenRunde-Bold`), because the family +
    /// weight route does not reliably reach them. `.bold()` on a Semibold headline therefore has no
    /// bolder member to resolve to and the emphasis quietly vanishes; naming the weight cannot
    /// silently resolve to nothing, and it is also what the design means.
    ///
    /// `.italic()` stays a trait. Open Runde ships no italic, so above the display threshold this is
    /// a synthesised slant — acceptable, and unused by any headline in the product today.
    private func emphasised(_ text: Text, _ emphasis: Emphasis) -> Text {
        switch emphasis {
        case .plain: return text
        case .bold: return text.font(.openRunde(style.size, .bold))
        case .italic: return text.italic()
        }
    }
}

/// Lets call sites write the documented `[(String, Emphasis)]` without qualification.
typealias Emphasis = RandomizedText.Emphasis

/// What a fresh reveal *is*: this content, delivered from this instant. Content alone is not
/// enough — a card can repeat itself — and the instant alone is not enough either.
private struct RevealKey: Hashable {
    let segments: [RandomizedText.Segment]
    let cadence: SpokenCadence?
}

// MARK: - Reveal plan

/// The tokenised headline plus one fixed delay per token.
///
/// Built exactly once per piece of content and parked in `@State`. Nothing in the render path
/// builds one, so `Double.random` is called once per word per headline — not once per word per
/// frame, which would re-roll the stagger sixty times a second and read as a shimmer rather than
/// a reveal.
private struct RevealPlan {
    struct Token {
        let text: String
        let emphasis: RandomizedText.Emphasis
        let delay: Double
    }

    let tokens: [Token]
    /// How much of the total one word spends fading in. A property rather than a constant because
    /// the two cadences want opposite things from it — see `Reveal.ramp` and
    /// `SpokenCadence.wordRamp`.
    let ramp: Double

    init(segments: [RandomizedText.Segment], randomized: Bool, cadence: SpokenCadence? = nil) {
        var tokens: [Token] = []
        // Counts non-whitespace runs only, which is exactly what `SpokenCadence.wordCount(of:)`
        // counts — the two have to agree or the last word's beat lands somewhere other than the end
        // of the phrase.
        var wordIndex = 0
        for segment in segments {
            for run in RevealPlan.tokenize(segment.text) {
                let isWhitespace = run.first?.isWhitespace ?? true
                let delay: Double
                if isWhitespace {
                    // Whitespace has no ink, so revealing it early is invisible and revealing it
                    // late would open gaps in a line that is otherwise laid out.
                    delay = 0
                } else if let cadence {
                    delay = cadence.normalizedDelay(wordIndex: wordIndex)
                    wordIndex += 1
                } else if randomized {
                    delay = Reveal.minimumDelay + Double.random(in: 0..<1) * Reveal.delayJitter
                } else {
                    delay = 0
                }
                tokens.append(Token(text: run, emphasis: segment.emphasis, delay: delay))
            }
        }
        self.tokens = tokens
        self.ramp = cadence?.normalizedRamp ?? Reveal.ramp
    }

    /// The equivalent of `/\s+|\S+/`: alternating runs of whitespace and non-whitespace, with
    /// every character preserved so the string round-trips exactly.
    private static func tokenize(_ text: String) -> [String] {
        var runs: [String] = []
        var current = ""
        var currentIsWhitespace: Bool?
        for character in text {
            let isWhitespace = character.isWhitespace
            if isWhitespace != currentIsWhitespace, !current.isEmpty {
                runs.append(current)
                current = ""
            }
            currentIsWhitespace = isWhitespace
            current.append(character)
        }
        if !current.isEmpty { runs.append(current) }
        return runs
    }
}

// MARK: - Spec

/// Fractions of `InkMotion.wordReveal`, straight from the motion table.
private enum Reveal {
    static let minimumDelay = 0.05
    static let delayJitter = 0.18
    /// How much of the total one word spends fading in. The latest a word can start is
    /// 0.05 + 0.18 = 0.23, so the last word lands at 0.85 — inside the animation, with room.
    static let ramp = 0.62

    static func opacity(progress: Double, delay: Double, ramp: Double = Reveal.ramp) -> Double {
        guard ramp > 0 else { return progress >= delay ? 1 : 0 }
        let t = min(max((progress - delay) / ramp, 0), 1)
        guard t < 1 else { return 1 }
        return 1 - pow(2, -10 * t)  // easeOutExpo
    }
}
