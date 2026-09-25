import AppKit
import SwiftUI

//  The mark, saying the card's own words.
//
//  Onboarding has always been written in the mark's voice — "I keep Claude caught up on what you
//  see and say", "Here's what I do", "I would like to hear you", "Turn me on" — and has never once
//  shown the mark saying any of it. This file finishes that idea. It is not a new character; it is
//  `CinematicMarkView`, the drawing the cinematic already builds, given a body.
//
//  The whole design problem is in one sentence: **the mark has no mouth.** It is a head, two eyes
//  and two legs, and none of those can be lip-synced. So "speaking" has to be carried by rhythm,
//  and it is carried by four things, in descending order of how much work they do:
//
//  1. **Cadence.** The words arrive one at a time, in reading order, on a fixed beat, and the mark's
//     body moves on the *same clock* (`SpokenCadence.start` drives both). Synchronised rhythm is
//     what makes a viewer attribute words to a character; get it right and nobody looks for a mouth.
//  2. **One breath per phrase.** A single raised-cosine lift with a little stretch at the top —
//     `TalkingMarkMotion.breath`. One per phrase and never one per word: a per-word bounce is
//     indistinguishable from a rendering glitch.
//  3. **Eyes.** A blink as the line begins, then a resting rate. On a mouthless face the eyes are
//     the only expressive part there is.
//  4. **Weight.** A slow shift about the feet, on a period that never locks to the blink, so the
//     mark reads as standing there rather than as being pasted there.
//
//  **There is no speech bubble, and there is deliberately nothing in its place.** It had one — an
//  `Ink.rowFill` ground, an `Ink.hairline` edge and a tail — and that was wrong twice over. A filled
//  slab under the copy is a second ground competing with the window's own, which is the thing it was
//  reported as: an ugly hue behind the words. And it was expensive: the tail plus two lots of
//  horizontal padding took ~34 pt out of the reading column on top of the mark's own box, which is
//  what pushed the welcome hero past the card's edge the moment `introHero` grew from 32 pt to 34.
//
//  Nothing is lost by deleting it, because the bubble was never what made the mark read as speaking
//  — none of the four things above is a bubble. The mark and the words sit straight on the window
//  now, and the motion, untouched, carries the whole performance.
//
//  Reduce Motion removes every one of the four: no breath, no stretch, no blink, no sway, and the
//  copy appears at once. What is left is a mark standing beside a line of type, which is a perfectly
//  good static illustration — the precedent is `CinematicCaret`, which stops blinking for the same
//  reason.

// MARK: - Cadence

/// A line delivered at speaking pace: one word every beat, in reading order, from `start`.
///
/// A value with pure functions on it rather than state inside a view, because the rhythm is the
/// thing most worth asserting and a `View` is not a place a rhythm can be tested. The same value is
/// handed to `RandomizedText` (which words are lit) and to `TalkingMarkMotion` (where the body is),
/// so the two cannot drift: there is one clock, not two that start near each other.
struct SpokenCadence: Hashable, Sendable {
    /// The instant the phrase began.
    let start: Date
    /// Words in the phrase. Whitespace runs are not words — see `wordCount(of:)`.
    let wordCount: Int

    init(start: Date, wordCount: Int) {
        self.start = start
        self.wordCount = wordCount
    }

    init(start: Date, segments: [RandomizedText.Segment]) {
        self.init(start: start, wordCount: Self.wordCount(of: segments))
    }

    // MARK: The constants

    /// The beat one word gets when the phrase is short enough to afford it.
    ///
    /// Conversational English runs around 150 words a minute — roughly 400 ms a word — and a reveal
    /// at that pace makes a card feel stalled: the reader finishes the line long before the line has
    /// finished arriving. 155 ms (≈390 wpm) is the other end of the usable range. It is still well
    /// clear of the ~80 ms below which two events stop reading as a sequence and start reading as
    /// one, so the words are seen to arrive *in order*, which is the entire trick — and it puts a
    /// four-word headline fully out in half a second.
    static let secondsPerWord: Double = 0.155

    /// How long one word takes to reach full opacity.
    ///
    /// Deliberately **shorter** than the beat, so at most one word is ever mid-fade. Let the fades
    /// overlap and the line dissolves in as a block, which is exactly the reading the sequence
    /// exists to avoid — and is what the scattered stagger `RandomizedText` uses everywhere else
    /// deliberately *does*.
    static let wordRamp: Double = 0.09

    /// The ceiling on a whole phrase, and it is `InkMotion.wordReveal` on purpose.
    ///
    /// 1.2 s is what the welcome hero already took before any of this existed, and the rule for this
    /// feature is that nothing may become slower than it is today — nobody is ever to be held behind
    /// an animation. So a long line speaks *faster* rather than running longer: `pace` compresses
    /// the beat until the phrase fits, and every card's button stays reachable exactly when it was.
    static let maximumPhrase: Double = InkMotion.wordReveal

    // MARK: The rhythm

    /// The beat this particular phrase gets: `secondsPerWord`, compressed if that would overrun
    /// `maximumPhrase`.
    var pace: Double {
        guard wordCount > 1 else { return Self.secondsPerWord }
        return min(Self.secondsPerWord, (Self.maximumPhrase - Self.wordRamp) / Double(wordCount - 1))
    }

    /// The whole phrase: the last word's beat plus the time it takes to land. Never longer than
    /// `maximumPhrase`, and never zero, so it is always safe to divide by.
    var duration: Double {
        Double(max(wordCount - 1, 0)) * pace + Self.wordRamp
    }

    /// When word `index` starts arriving, as a fraction of `duration` — which is the form
    /// `RandomizedText` states every delay in.
    func normalizedDelay(wordIndex index: Int) -> Double {
        guard index > 0 else { return 0 }
        return min(1, Double(index) * pace / duration)
    }

    /// `wordRamp` in the same normalised units.
    var normalizedRamp: Double { Self.wordRamp / duration }

    /// Elapsed phrase time as a fraction of `duration`, clamped. 0 before the phrase starts, 1 once
    /// the last word has landed.
    func progress(at date: Date) -> Double {
        min(max(date.timeIntervalSince(start) / duration, 0), 1)
    }

    /// Words, counted the way `RandomizedText` tokenises: runs of non-whitespace, **per segment**.
    ///
    /// Per segment and not over the joined string, because that is what the reveal plan does, and
    /// the two counts have to agree or the last word's delay lands somewhere other than the end of
    /// the phrase. An emphasis break mid-word ("see and say" + ".") is therefore two words here, and
    /// two tokens there.
    static func wordCount(of segments: [RandomizedText.Segment]) -> Int {
        segments.reduce(0) { $0 + $1.text.split(whereSeparator: \.isWhitespace).count }
    }
}

// MARK: - Motion

/// The mark's body at one instant. Everything the pose is, and nothing about how it is drawn.
///
/// A value rather than four `let`s inside a `ViewBuilder`, because "Reduce Motion really stops the
/// motion" is a claim about *this* and can only be asserted if this exists: the setting resolves to
/// `.rest`, and `.rest` is a value a test can hold.
struct TalkingMarkPose: Equatable {
    /// Lift, as a fraction of the mark's box, upward.
    var lift: CGFloat = 0
    /// Vertical stretch, as a fraction added to 1.
    var stretch: CGFloat = 0
    /// Lean about the feet, in degrees.
    var lean: Double = 0
    /// Vertical scale of both eyes. 1 is wide open.
    var eyeOpen: Double = 1

    /// Standing still with its eyes open.
    ///
    /// What Reduce Motion resolves to — and also the animated pose's own t = 0, which is the point:
    /// one rest position, not a second static drawing that could drift from the moving one.
    static let rest = TalkingMarkPose()

    /// True when nothing about the drawing is being changed.
    var isStill: Bool { self == .rest }
}

/// Where the mark's body is at a given moment. Pure functions of elapsed time, for the same reason
/// `CinematicCaret.isOn(at:)` is one: a pose that is a function of the clock cannot get out of step
/// with itself across a re-render, and it can be asserted without rendering anything.
///
/// Every value is a *fraction of the mark's box* rather than a point measurement, so the same
/// numbers hold if the mark is ever drawn at another size.
enum TalkingMarkMotion {

    /// The whole pose, `elapsed` seconds into `phrase`.
    ///
    /// `elapsed` is nil under Reduce Motion and the answer is `.rest`: no breath, no stretch, no
    /// lean, no blink. There is one branch, here, rather than four `if` statements at the four
    /// places the pose is applied.
    static func pose(elapsed: Double?, phrase: SpokenCadence) -> TalkingMarkPose {
        guard let elapsed else { return .rest }
        let rise = breath(progress: min(max(elapsed / phrase.duration, 0), 1))
        return TalkingMarkPose(
            lift: breathRise * rise,
            stretch: breathStretch * rise,
            lean: sway(elapsed: elapsed),
            eyeOpen: eyeOpen(elapsed: elapsed))
    }

    // MARK: The breath

    /// Where the phrase's single breath peaks, as a fraction of the phrase.
    ///
    /// 0.34 and not 0.5: a speaker's stress lands near the *start* of a phrase, so the mark lifts
    /// under the first two or three words and is already settling while the rest arrive. A
    /// symmetric bob peaks under the middle of the sentence, which reads as a shrug rather than as
    /// speech.
    static let breathPeak: Double = 0.34

    /// The lift at the peak, as a fraction of the mark's box. At the 56 pt mark that is 3 pt — a
    /// nod, not a jump.
    static let breathRise: Double = 0.055

    /// How much taller the mark gets at the peak, and the fraction of that it gives back in width.
    ///
    /// Squash-and-stretch at the smallest amount that still reads: 3.5% of a 56 pt mark is 2 pt.
    /// The width gives back only 70% of it, because a shape that conserves area exactly reads as
    /// rubber, and this is a small creature taking a breath.
    static let breathStretch: Double = 0.035
    static let breathNarrow: Double = 0.7

    /// 0 → 1 → 0 across the phrase, with zero velocity at 0, at the peak, and at 1.
    ///
    /// Two half-cosines rather than one `sin(πt)`, whose slope is *steepest* exactly at the ends —
    /// the mark would jerk into motion on the first frame and stop dead on the last. A raised cosine
    /// starts and ends still, which is what a body does. Note there is no overshoot on either side:
    /// a bounce here would turn the mark into a toy.
    static func breath(progress t: Double) -> Double {
        guard t > 0, t < 1 else { return 0 }
        if t < breathPeak {
            return (1 - cos(.pi * t / breathPeak)) / 2
        }
        return (1 + cos(.pi * (t - breathPeak) / (1 - breathPeak))) / 2
    }

    // MARK: The blink

    /// Seconds between blinks. A resting human blinks 15–20 times a minute — one every three to four
    /// seconds — and a mouthless face has nothing else to be alive with, so this sits at the fast
    /// end of resting.
    static let blinkPeriod: Double = 4.0

    /// One blink, lid down and back up. Human blinks measure 100–150 ms; below about 80 ms it stops
    /// reading as a blink and starts reading as a dropped frame.
    static let blinkSeconds: Double = 0.13

    /// The share of a blink spent closing. Lids snap shut and release open, so the down-stroke is
    /// the shorter half.
    static let blinkCloseFraction: Double = 0.38

    /// How open the eye is at the bottom of a blink.
    ///
    /// Not 0. The eye is a *fill* in this drawing, so scaling it to nothing deletes it for two
    /// frames and reads as the eyes vanishing rather than as a lid coming down. A sliver of ink is
    /// what a closed eye looks like here.
    static let blinkFloor: Double = 0.12

    /// Vertical scale of both eyes, `elapsed` seconds into the phrase. 1 is wide open.
    ///
    /// Phase zero is a blink, deliberately: a line begins with one, which is the cheapest way to
    /// tell a viewer that the thing about to speak is awake. After that it is the resting rate.
    static func eyeOpen(elapsed: Double) -> Double {
        guard elapsed >= 0 else { return 1 }
        let sinceBlink = elapsed.truncatingRemainder(dividingBy: blinkPeriod)
        guard sinceBlink < blinkSeconds else { return 1 }

        let u = sinceBlink / blinkSeconds
        // Closing and opening are both raised cosines for the same reason `breath` is: an eyelid
        // does not travel at a constant speed.
        let closed: Double
        if u < blinkCloseFraction {
            closed = (1 - cos(.pi * u / blinkCloseFraction)) / 2
        } else {
            closed = (1 + cos(.pi * (u - blinkCloseFraction) / (1 - blinkCloseFraction))) / 2
        }
        return 1 - (1 - blinkFloor) * closed
    }

    // MARK: The weight shift

    /// The period of the weight shift, in seconds.
    ///
    /// 5.2 and not 4: locked to the blink's period the two would fire together forever and become a
    /// single repeating tell. An incommensurate period is what makes idling look unplanned.
    static let swaySeconds: Double = 5.2

    /// How far the mark leans, in degrees about its feet. ±1.1° moves the head about a point at
    /// 56 pt — the difference between a drawing and a small creature standing there, and far below
    /// the angle at which a rotating logo reads as broken.
    static let swayDegrees: Double = 1.1

    static func sway(elapsed: Double) -> Double {
        swayDegrees * sin(2 * .pi * elapsed / swaySeconds)
    }

    /// The tick the mark's timeline runs at. 30 fps rather than 60: nothing here moves more than
    /// three points, and the reveal beside it is already driving a timeline of its own.
    static let frameInterval: Double = 1.0 / 30.0
}

// MARK: - The layout

/// The two gaps the mark and its words are built from, derived from the type being spoken.
///
/// Deliberately **not** a table of point sizes. `Ink`'s type scale is expected to grow — it grew
/// once already, 32 → 34 at the hero — and a gap measured against last year's headline reads as a
/// collision at this year's. Both gaps and the mark's own offset are fractions of the lead role's
/// line box, so the arrangement is always the same *shape* around whatever the role currently is.
///
/// There is nothing here for a ground, a border, a corner or a tail, and that is the point: the mark
/// and the words sit on the window, so the only numbers left are the distances between them.
struct TalkingMarkLayout: Equatable {
    /// Gap between the mark's box and the first glyph.
    ///
    /// 0.30 of the line box — about 11 pt at the hero. The mark's drawing does not fill its own box
    /// (the head spans 3.4…16.6 of a 20-unit canvas), so ~9 pt of that box is already air; the two
    /// together come to roughly 0.6 of a line box between ink and ink, which is close enough to read
    /// as one utterance and far enough not to crowd it. It replaces a gap of 40 pt — 6 + an 11 pt
    /// tail + 23 pt of bubble padding — which without a bubble around it would read as two unrelated
    /// things sharing a row.
    let gap: CGFloat
    /// Gap between the line the mark says and the sentence under it.
    let asideSpacing: CGFloat
    let markSize: CGFloat
    /// How far the mark shifts so its head lands on the first line. Negative: the head sits 39% down
    /// the mark's box, which is lower than the first line's centre, so the mark rides slightly high.
    let markOffsetY: CGFloat
    /// The centre of the first line, in points from the top of the copy — where the head goes.
    let firstLineCentreY: CGFloat

    /// The mark is the same size on every card, because it is the same creature — so it is sized
    /// once, off the largest role in the system, and does not grow and shrink between screens as
    /// the headline role changes. 1.6 line boxes of the hero is 60 pt today.
    static var markSize: CGFloat { (InkType.introHero.lineHeight * 1.6).rounded() }

    /// Where the head's centre sits inside the mark's box, from `CinematicMarkGeometry` rather than
    /// from a number typed here — the head is what lands on the line, so if the drawing ever moves,
    /// this follows it.
    static var markHeadCentreFraction: CGFloat {
        CinematicMarkGeometry.headCentre.y / CinematicMarkGeometry.box
    }

    init(lead: InkTextStyle) {
        let line = lead.lineHeight
        gap = (line * 0.30).rounded()
        asideSpacing = (line * 0.22).rounded()
        markSize = Self.markSize

        // The mark's head sits beside the line it is saying, not beside the middle of the paragraph.
        // Stated once, here, so the drawing and the copy cannot disagree about where "beside" is.
        firstLineCentreY = line / 2
        markOffsetY = firstLineCentreY - markSize * Self.markHeadCentreFraction
    }
}

// MARK: - The view

/// The mark delivering one phrase: the character, a gap, and the words. Nothing under either.
///
/// Composition, not a new drawing: `CinematicMarkView` supplies every path, `RandomizedText`
/// supplies the words, `Ink` supplies the colour. What is added here is the timing that binds
/// them, which is the only part that was ever missing.
struct TalkingMark: View {
    /// The line the mark says, word by word. Same shape as `RandomizedText`'s, so a call site reads
    /// the same as the plain headline it replaces.
    private let lead: [RandomizedText.Segment]
    private let leadStyle: InkTextStyle
    /// The sentence under it, if the card has one.
    ///
    /// It arrives as a block once the lead has landed, and gets no second breath: it is the same
    /// character continuing a thought, not a second performance. Two bobs in a row is the thing that
    /// makes an idle animation read as a loop.
    private let aside: String?
    private let asideStyle: InkTextStyle
    private let start: Date

    /// - Parameter start: When this phrase began. Defaults to the moment the view value is made,
    ///   which is the moment the card appears; a caller passing an instant in the past gets the
    ///   delivery already under way, which is the seam the render tests walk the sequence through.
    ///   Read once per *delivery* — see the `.id` in `body`.
    init(
        lead: [(String, Emphasis)],
        leadStyle: InkTextStyle,
        aside: String? = nil,
        asideStyle: InkTextStyle = .prose,
        start: Date = Date()
    ) {
        self.lead = lead.map { RandomizedText.Segment($0.0, $0.1) }
        self.leadStyle = leadStyle
        self.aside = aside
        self.asideStyle = asideStyle
        self.start = start
    }

    /// The lead as one string — what was written, before it was cut into runs for emphasis.
    ///
    /// The copy's accessibility label, and the reason the runs can never be read as fragments.
    static func plainCopy(of lead: [(String, Emphasis)]) -> String {
        lead.map(\.0).joined()
    }

    var body: some View {
        Delivery(lead: lead, leadStyle: leadStyle, aside: aside, asideStyle: asideStyle, start: start)
            // A new phrase is a new *delivery*, not the same one restarted — so it gets the copy's
            // own identity and SwiftUI rebuilds its clock from scratch.
            //
            // Deliberately not an `onChange` that resets the clock alongside a `task` that reads it:
            // those two fire in an order nobody controls, and the losing combination leaves the
            // sentence under the headline permanently hidden. Identity has no such ordering. The
            // case this is for is real — the permissions title goes "First…" → "Say yes." while the
            // user is standing on the card.
            .id(lead)
    }
}

/// One phrase, being delivered. Split out of `TalkingMark` only so that a change of copy can
/// destroy it: everything time-dependent lives here, and none of it has to be reset by hand.
private struct Delivery: View {
    let lead: [RandomizedText.Segment]
    let leadStyle: InkTextStyle
    let aside: String?
    let asideStyle: InkTextStyle

    init(
        lead: [RandomizedText.Segment],
        leadStyle: InkTextStyle,
        aside: String?,
        asideStyle: InkTextStyle,
        start: Date
    ) {
        self.lead = lead
        self.leadStyle = leadStyle
        self.aside = aside
        self.asideStyle = asideStyle
        _phraseStart = State(initialValue: start)
        // A phrase that began long enough ago has already been said, so the sentence under it is
        // already up. Seeding rather than always starting hidden is what makes `start` a real seam:
        // hand the view an instant in the past and you get the state that instant implies, not a
        // delivery that begins again.
        let elapsed = -start.timeIntervalSinceNow
        _asideSaid = State(initialValue: elapsed >= SpokenCadence(start: start, segments: lead).duration)
    }

    /// When this phrase started. Held rather than recomputed, because the reveal beside it keys its
    /// `.task` on this instant — a fresh `Date()` per body pass would restart the reveal sixty times
    /// a second.
    @State private var phraseStart: Date
    /// The aside is held back until the lead has been said.
    @State private var asideSaid: Bool

    private var metrics: TalkingMarkLayout { TalkingMarkLayout(lead: leadStyle) }
    private var cadence: SpokenCadence { SpokenCadence(start: phraseStart, segments: lead) }

    var body: some View {
        HStack(alignment: .top, spacing: metrics.gap) {
            mark
            words
        }
        .task {
            guard !InkReduceMotion.isEnabled else {
                asideSaid = true
                return
            }
            guard !asideSaid else { return }
            try? await Task.sleep(for: .seconds(cadence.duration))
            guard !Task.isCancelled else { return }
            withAnimation(.easeOut(duration: InkMotion.settle)) { asideSaid = true }
        }
    }

    // MARK: The character

    /// Decorative throughout — VoiceOver reads the copy beside it, which is where the words are.
    private var mark: some View {
        Group {
            if InkReduceMotion.isEnabled {
                posed(at: nil)
            } else {
                TimelineView(.animation(minimumInterval: TalkingMarkMotion.frameInterval)) { context in
                    posed(at: context.date)
                }
            }
        }
        .frame(width: metrics.markSize, height: metrics.markSize)
        .offset(y: metrics.markOffsetY)
        .accessibilityHidden(true)
    }

    /// The mark at one instant. `date` is nil under Reduce Motion, which resolves to
    /// `TalkingMarkPose.rest` — the drawing, untouched.
    private func posed(at date: Date?) -> some View {
        let pose = TalkingMarkMotion.pose(
            elapsed: date.map { $0.timeIntervalSince(phraseStart) },
            phrase: cadence)

        return CinematicMarkView(
            draw: .complete,
            size: metrics.markSize,
            color: Ink.primary,
            eyeOpen: pose.eyeOpen
        )
        // Anchored at the feet for both: a creature's weight is on the floor, so the head is what
        // moves and the legs are what it moves from.
        .scaleEffect(
            x: 1 - pose.stretch * TalkingMarkMotion.breathNarrow,
            y: 1 + pose.stretch,
            anchor: .bottom)
        .rotationEffect(.degrees(pose.lean), anchor: .bottom)
        .offset(y: -pose.lift * metrics.markSize)
    }

    // MARK: The words

    /// The copy, and only the copy — no ground, no border, no padding of its own. Every point of the
    /// column that is not the mark is available to the words, which is what stopped the welcome hero
    /// running off the card.
    private var words: some View {
        VStack(alignment: .leading, spacing: metrics.asideSpacing) {
            RandomizedText(
                segments: lead.map { ($0.text, $0.emphasis) },
                style: leadStyle,
                color: Ink.primary,
                cadence: cadence
            )
            .fixedSize(horizontal: false, vertical: true)
            // The reveal is a per-word *opacity*, so VoiceOver already sees the whole line — but
            // naming it makes that a guarantee rather than a property of how `RandomizedText`
            // happens to be built, and the words must never be read as fragments.
            .accessibilityLabel(Text(TalkingMark.plainCopy(of: lead.map { ($0.text, $0.emphasis) })))

            if let aside {
                Text(aside)
                    .inkStyle(asideStyle, color: Ink.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .opacity(asideSaid ? 1 : 0)
            }
        }
    }
}

// MARK: - Previews

#if DEBUG
#Preview("Talking") {
    VStack(alignment: .leading, spacing: 28) {
        TalkingMark(
            lead: [
                ("I keep ", .plain), ("Claude", .bold), (" caught up on what you ", .plain),
                ("see and say", .bold), (".", .plain),
            ],
            leadStyle: .introHero)

        TalkingMark(
            lead: [("Here's what I do.", .plain)],
            leadStyle: .firstTitle,
            aside: "Three things I take in, and one place they go.")
    }
    .frame(width: InkLayout.contentMaxWidth, alignment: .leading)
    .padding(45)
    // The window's own glass is the ground in the product; a preview canvas has none, so it stands
    // in with the flat surface the glass is scrimmed with.
    .background(Ink.surface)
}
#endif
